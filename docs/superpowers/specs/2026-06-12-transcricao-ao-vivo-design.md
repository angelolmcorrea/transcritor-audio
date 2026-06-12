# Transcrição ao vivo (mic + saída do PC) — design

**Data:** 2026-06-12
**Produto:** Transcritor (ferramenta pessoal, roda local em Windows)
**Status:** aprovado para implementação

## Objetivo

Adicionar ao Transcritor um modo **ao vivo**: capturar áudio do **microfone**,
da **saída do PC** (o que toca nas caixas/headset) ou de **ambos**, e exibir a
transcrição em tempo real via Gemini Live API. O modo de **upload de arquivo**
atual permanece intacto.

Viável **somente porque o app roda local** (o servidor é a própria máquina e
tem acesso aos dispositivos de áudio). Se fosse hospedado, seria impossível.

## Decisões fechadas (e por quê)

- **Streaming de verdade**, não blocos. Acesso à Live API no free tier do Angelo
  **confirmado por sonda** em 2026-06-12 (modelo `gemini-3.1-flash-live-preview`,
  `input_audio_transcription` retornou texto correto sem billing).
- **Abas na mesma página:** "Arquivo" (fluxo atual) e "Ao vivo". Mesma
  identidade Corrêa Info, copiar/baixar compartilhados.
- **Fonte selecionável:** `PC` · `Microfone` · `Ambos`. "Ambos" = **mistura numa
  faixa só** (1 sessão Live). Separar com rótulo "Você/Sistema" exigiria 2
  sessões simultâneas — o free tier não garante isso. Fora de escopo.
- **Modelo silenciado:** `gemini-3.1-flash-live-preview` é native-audio e
  conversacional. Usamos só o `input_audio_transcription` e instruímos o modelo
  a não responder, pra não gastar quota gerando áudio de resposta.
- **Windows-only:** captura via WASAPI loopback. Já é o ambiente do produto.

## Arquitetura

Três unidades novas + ajustes no `main.py` e no frontend.

### `app/audio_capture.py` — captura de áudio
**Faz:** captura PCM **16 kHz, mono, 16-bit little-endian** (formato exigido pela
Live API) da fonte escolhida, entregando blocos (~100 ms) por uma fila.

**Interface:**
- `class AudioCapture(fonte: Literal["pc","mic","ambos"])`
- `.iniciar()` / `.parar()` — controla threads de captura.
- `.blocos()` — gerador/fila assíncrona que entrega `bytes` PCM.

**Como:** biblioteca **`soundcard`** (pip puro; mic + loopback; resampla pra 16k
internamente; entrega numpy). Mic = `default_microphone()`. PC = loopback do
`default_speaker()` via `all_microphones(include_loopback=True)`. "Ambos" =
dois recorders em threads, frames somados com proteção de clipping
(`np.clip`), convertidos pra int16.

**Depende de:** `soundcard`, `numpy`. Dependência **nativa nova** — ponto de
risco principal.

### `app/live_transcribe.py` — sessão Gemini Live
**Faz:** abre e mantém a sessão Live, faz streaming do PCM recebido da captura,
lê a transcrição do input e a entrega como texto incremental.

**Interface:**
- `async def transcrever_ao_vivo(blocos, on_texto) -> None` — consome os blocos
  PCM, chama `on_texto(trecho)` a cada `input_transcription` recebido.

**Como:**
- `client.aio.live.connect(model="gemini-3.1-flash-live-preview",
  config={"response_modalities":["AUDIO"], "input_audio_transcription":{},
  "system_instruction": "<transcritor silencioso>"})`.
- Envia `send_realtime_input(audio=Blob(pcm, "audio/pcm;rate=16000"))`.
- Lê `server_content.input_transcription.text`; ignora o áudio de resposta.
- **Reconexão automática:** sessão de áudio dura no máx. ~15 min. Ao receber o
  aviso de fim (GoAway) ou ao se aproximar do limite, reconecta usando
  *session resumption* (handle guardado) pra continuar sem perder contexto.
  Risco aceito: micro-corte de uma palavra na emenda.

**Depende de:** `google-genai` (já instalado, 2.8.0), `audio_capture`.

### `main.py` — endpoint WebSocket
**Faz:** ponte entre o browser e a captura+Live.

- `GET /ao-vivo` não é rota nova — o modo vive na mesma `index.html`.
- `WS /ws/ao-vivo` (autenticado pela mesma sessão de cookie):
  1. browser → `{"acao":"iniciar","fonte":"pc|mic|ambos"}`
  2. backend dispara `AudioCapture` + `transcrever_ao_vivo`, e a cada trecho
     envia `{"tipo":"texto","texto":"..."}` ao browser.
  3. browser → `{"acao":"parar"}` encerra captura e sessão.
  4. erros → `{"tipo":"erro","msg":"..."}` (sem vazar stack).
- Reutiliza `_autenticado`; recusa se não logado.

### Frontend (`app/static/index.html`)
- **Seletor de modo** (abas) no topo do cartão: Arquivo / Ao vivo.
- Painel "Ao vivo": seletor de fonte (PC/Mic/Ambos), Iniciar/Parar, área de
  transcrição (reusa o `<textarea>` e os botões Copiar/Baixar).
- Abre `WebSocket` pra `/ws/ao-vivo`, vai **anexando** o texto recebido.
- Estados claros: "capturando…", "reconectando…", erros legíveis.

## Fluxo de dados

```
mic / loopback WASAPI ─▶ audio_capture (16k mono PCM, blocos ~100ms)
   ─▶ live_transcribe (stream p/ Gemini Live) ─▶ input_transcription (texto)
   ─▶ WS /ws/ao-vivo ─▶ browser (anexa no textarea) ─▶ Copiar / Baixar
```

## Tratamento de erro

- Sem mic/saída disponível, ou device em modo exclusivo → mensagem clara no
  painel, não derruba o app.
- Falha/timeout da Live API → tenta reconectar N vezes; se persistir, avisa e
  para, mantendo o texto já transcrito.
- `soundcard` ausente/quebrado → modo Ao vivo desabilitado com aviso; modo
  Arquivo segue funcionando.
- Erro nunca vaza como 500/stack pro browser (consistente com o que já fizemos
  no `/transcrever`).

## Dependências novas

- `soundcard`, `numpy` no `requirements.txt`. (numpy pode já vir transitivo.)

## Riscos

1. **Captura nativa Windows** — device padrão, modo exclusivo, máquina sem
   dispositivo. Maior fonte de bug. Mitigar com mensagens claras e detecção.
2. **Modelo conversacional** — silenciar via system instruction; validar que
   não emite resposta nem consome quota à toa.
3. **Quota contínua / sessões simultâneas** — 1 sessão por vez; ok pra 1 usuário.
4. **Emenda dos 15 min** — possível palavra perdida na reconexão.

## Fora de escopo (YAGNI)

- Separar falantes / rótulo "Você vs Sistema" (exigiria 2 sessões).
- Diarização, pontuação avançada, tradução.
- Escolha manual de device específico (v1 usa os padrões do sistema).
- Hospedagem (decidido: roda local — ver memória `transcritor-local-only`).

## Como validar

- **Sonda já feita:** Live API acessível, transcrição correta. ✅
- Captura: script de fumaça que grava 5 s de mic e de loopback e confere que
  vêm amostras não-silenciosas.
- Ponta-a-ponta manual: tocar um vídeo no PC + falar no mic, ver o texto
  aparecendo no painel; testar as 3 fontes; testar Parar/Iniciar; deixar rodar
  >15 min pra exercitar a reconexão.
