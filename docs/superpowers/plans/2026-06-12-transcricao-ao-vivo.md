# Transcrição ao vivo (mic + saída do PC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar ao Transcritor um modo "ao vivo" que captura microfone e/ou saída do PC (WASAPI loopback) e exibe a transcrição em tempo real via Gemini Live API, mantendo o modo de upload de arquivo intacto.

**Architecture:** Backend FastAPI captura áudio local (`soundcard`) em PCM 16k mono, faz streaming pra Gemini Live (`gemini-3.1-flash-live-preview`, `input_audio_transcription`, modelo silenciado, reconexão nos 15 min) e empurra o texto pro browser por um WebSocket. Frontend ganha abas "Arquivo"/"Ao vivo" na mesma página.

**Tech Stack:** Python 3.12, FastAPI, `google-genai` 2.8, `soundcard`, `numpy`, WebSocket; frontend HTML/JS estático; testes com `pytest`.

**Spec:** `docs/superpowers/specs/2026-06-12-transcricao-ao-vivo-design.md`

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/audio_capture.py` (novo) | Captura mic/loopback → blocos PCM 16k mono int16. DSP puro (`to_int16_pcm`, `mix`) + classe `AudioCapture`. |
| `app/protocolo.py` (novo) | Validação das mensagens de controle do WebSocket (`parse_comando`). |
| `app/live_transcribe.py` (novo) | Sessão Gemini Live: streaming, leitura da transcrição, reconexão. |
| `app/main.py` (modificar) | Endpoint `WS /ws/ao-vivo` ligando captura + Live + browser. |
| `app/static/index.html` (modificar) | Abas Arquivo/Ao vivo, painel ao vivo, cliente WebSocket. |
| `requirements.txt` (modificar) | `soundcard`, `numpy`. |
| `tests/test_audio_dsp.py` (novo) | TDD do DSP de áudio. |
| `tests/test_protocolo.py` (novo) | TDD do parsing do protocolo. |
| `scripts/smoke_captura.py` (novo) | Fumaça manual: grava 5s de cada fonte e mede nível. |
| `scripts/smoke_live.py` (novo) | Fumaça manual: captura real → Live → imprime transcrição. |

Princípio: DSP e protocolo são funções puras testáveis; captura de hardware e streaming Live são validados por scripts de fumaça + teste manual (não há como unit-testar device/rede honestamente).

---

## Task 0: Setup de dependências e testes

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py` (vazio)

- [ ] **Step 1: Adicionar deps de runtime**

Append a `requirements.txt`:

```
soundcard
numpy
```

- [ ] **Step 2: Criar `requirements-dev.txt`**

```
-r requirements.txt
pytest
```

- [ ] **Step 3: Instalar**

Run: `./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`
Expected: instala `soundcard`, `numpy`, `pytest` sem erro.

- [ ] **Step 4: Criar pacote de testes**

Create `tests/__init__.py` vazio.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt tests/__init__.py
git commit -m "chore: deps de captura (soundcard/numpy) e pytest"
```

---

## Task 1: DSP de áudio (TDD)

**Files:**
- Create: `app/audio_capture.py`
- Test: `tests/test_audio_dsp.py`

- [ ] **Step 1: Escrever os testes que falham**

Create `tests/test_audio_dsp.py`:

```python
import struct
import numpy as np
from app.audio_capture import to_int16_pcm, mix


def test_to_int16_pcm_silencio():
    out = to_int16_pcm(np.zeros(4, dtype="float32"))
    assert out == b"\x00\x00" * 4


def test_to_int16_pcm_escala_e_clipa():
    out = to_int16_pcm(np.array([1.0, -1.0, 2.0, -2.0], dtype="float32"))
    vals = struct.unpack("<4h", out)
    assert vals[0] == 32767      # +1.0 -> maximo
    assert vals[1] == -32767     # -1.0
    assert vals[2] == 32767      # +2.0 clipado
    assert vals[3] == -32767     # -2.0 clipado


def test_mix_soma_e_clipa():
    a = np.array([0.6, 0.6], dtype="float32")
    b = np.array([0.6, -0.6], dtype="float32")
    out = mix(a, b)
    assert out[0] == 1.0                 # 1.2 -> clipado em 1.0
    assert abs(float(out[1])) < 1e-6     # 0.6 - 0.6 = 0


def test_mix_alinha_pelo_menor():
    a = np.array([0.1, 0.2, 0.3], dtype="float32")
    b = np.array([0.1, 0.1], dtype="float32")
    out = mix(a, b)
    assert len(out) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_audio_dsp.py -v`
Expected: FAIL — `ImportError: cannot import name 'to_int16_pcm'`.

- [ ] **Step 3: Implementar o DSP**

Create `app/audio_capture.py` (só o DSP por enquanto):

```python
"""Captura de audio local -> blocos PCM 16k mono 16-bit, para a Live API."""
import numpy as np

TARGET_RATE = 16000          # Live API exige 16 kHz
BLOCK_MS = 100               # tamanho do bloco enviado
BLOCK_FRAMES = TARGET_RATE * BLOCK_MS // 1000  # 1600 amostras


def to_int16_pcm(frames: np.ndarray) -> bytes:
    """frames float mono em [-1,1] -> bytes PCM 16-bit little-endian."""
    clipado = np.clip(frames, -1.0, 1.0)
    return (clipado * 32767.0).astype("<i2").tobytes()


def mix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Soma duas faixas float mono (alinhadas pelo menor), com clipping."""
    n = min(len(a), len(b))
    return np.clip(a[:n] + b[:n], -1.0, 1.0)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_audio_dsp.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/audio_capture.py tests/test_audio_dsp.py
git commit -m "feat: DSP de audio (to_int16_pcm, mix) com testes"
```

---

## Task 2: Classe `AudioCapture` (captura de device + fumaça)

**Files:**
- Modify: `app/audio_capture.py`
- Create: `scripts/smoke_captura.py`

- [ ] **Step 1: Implementar `AudioCapture`**

Append a `app/audio_capture.py`:

```python
import queue
import threading
from contextlib import ExitStack

import soundcard as sc

FONTES = ("pc", "mic", "ambos")


class AudioCapture:
    """Captura PCM 16k mono da fonte escolhida numa thread; entrega blocos
    de bytes por uma fila. fonte: 'pc' | 'mic' | 'ambos'."""

    def __init__(self, fonte: str):
        if fonte not in FONTES:
            raise ValueError(f"fonte invalida: {fonte!r}")
        self.fonte = fonte
        self._fila: queue.Queue = queue.Queue(maxsize=200)
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._erro: Exception | None = None

    def _abrir_recorders(self, pilha: ExitStack):
        recs = []
        if self.fonte in ("mic", "ambos"):
            mic = sc.default_microphone()
            recs.append(pilha.enter_context(
                mic.recorder(samplerate=TARGET_RATE, channels=1)))
        if self.fonte in ("pc", "ambos"):
            alto_falante = sc.default_speaker()
            loop = sc.get_microphone(alto_falante.name, include_loopback=True)
            recs.append(pilha.enter_context(
                loop.recorder(samplerate=TARGET_RATE, channels=1)))
        if not recs:
            raise RuntimeError("nenhum recorder aberto")
        return recs

    def _loop(self):
        try:
            with ExitStack() as pilha:
                recs = self._abrir_recorders(pilha)
                while not self._parar.is_set():
                    faixas = [r.record(numframes=BLOCK_FRAMES) for r in recs]
                    # soundcard devolve [frames, channels]; channels=1 -> achata
                    mono = [f.reshape(-1).astype("float32") for f in faixas]
                    bloco = mono[0] if len(mono) == 1 else mix(mono[0], mono[1])
                    try:
                        self._fila.put(to_int16_pcm(bloco), timeout=1.0)
                    except queue.Full:
                        pass  # consumidor lento: descarta o bloco mais novo
        except Exception as e:  # device ausente, modo exclusivo, etc.
            self._erro = e
        finally:
            self._fila.put(None)  # sinaliza fim

    def iniciar(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def proximo_bloco(self, timeout: float = 1.0):
        """Bloqueia ate o proximo bloco PCM (bytes) ou None (fim). Levanta o
        erro de captura, se houver, ao chegar no fim."""
        item = self._fila.get(timeout=timeout)
        if item is None and self._erro is not None:
            raise self._erro
        return item

    def parar(self):
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=2.0)
```

- [ ] **Step 2: Criar script de fumaça da captura**

Create `scripts/smoke_captura.py`:

```python
"""Fumaca manual: grava ~3s de cada fonte e reporta nivel medio.
Rode com algo tocando no PC e falando no mic.
Uso: ./.venv/Scripts/python.exe scripts/smoke_captura.py [pc|mic|ambos]"""
import sys
import time
import numpy as np
from app.audio_capture import AudioCapture

fonte = sys.argv[1] if len(sys.argv) > 1 else "ambos"
cap = AudioCapture(fonte)
cap.iniciar()
print(f"Capturando fonte={fonte} por ~3s...")
amostras = bytearray()
fim = time.monotonic() + 3
while time.monotonic() < fim:
    b = cap.proximo_bloco(timeout=2.0)
    if b is None:
        break
    amostras += b
cap.parar()
arr = np.frombuffer(bytes(amostras), dtype="<i2").astype("float32") / 32767.0
rms = float(np.sqrt(np.mean(arr ** 2))) if len(arr) else 0.0
print(f"blocos: {len(amostras)} bytes | RMS: {rms:.4f} "
      f"({'OK, tem som' if rms > 0.001 else 'SILENCIO — verifique device/fonte'})")
```

- [ ] **Step 3: Rodar a fumaça (manual, requer máquina com áudio)**

Run (com um vídeo tocando + falando no mic): `./.venv/Scripts/python.exe scripts/smoke_captura.py ambos`
Expected: imprime `RMS` > 0.001 ("OK, tem som"). Repetir para `mic` e `pc`.
Se der erro de device, anotar a mensagem — é o risco nº 1 da spec.

- [ ] **Step 4: Commit**

```bash
git add app/audio_capture.py scripts/smoke_captura.py
git commit -m "feat: AudioCapture (mic/loopback/ambos) + smoke de captura"
```

---

## Task 3: Protocolo do WebSocket (TDD)

**Files:**
- Create: `app/protocolo.py`
- Test: `tests/test_protocolo.py`

- [ ] **Step 1: Escrever os testes que falham**

Create `tests/test_protocolo.py`:

```python
import pytest
from app.protocolo import parse_comando


def test_iniciar_valido():
    assert parse_comando({"acao": "iniciar", "fonte": "ambos"}) == {
        "acao": "iniciar", "fonte": "ambos"}


def test_parar_valido():
    assert parse_comando({"acao": "parar"}) == {"acao": "parar"}


def test_fonte_invalida():
    with pytest.raises(ValueError):
        parse_comando({"acao": "iniciar", "fonte": "tudo"})


def test_acao_invalida():
    with pytest.raises(ValueError):
        parse_comando({"acao": "voar"})


def test_iniciar_sem_fonte():
    with pytest.raises(ValueError):
        parse_comando({"acao": "iniciar"})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_protocolo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.protocolo'`.

- [ ] **Step 3: Implementar**

Create `app/protocolo.py`:

```python
"""Validacao das mensagens de controle do WebSocket /ws/ao-vivo."""

FONTES = {"pc", "mic", "ambos"}


def parse_comando(raw: dict) -> dict:
    """Valida e normaliza um comando do browser. Levanta ValueError se invalido."""
    acao = raw.get("acao")
    if acao == "parar":
        return {"acao": "parar"}
    if acao == "iniciar":
        fonte = raw.get("fonte")
        if fonte not in FONTES:
            raise ValueError(f"fonte invalida: {fonte!r}")
        return {"acao": "iniciar", "fonte": fonte}
    raise ValueError(f"acao invalida: {acao!r}")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_protocolo.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/protocolo.py tests/test_protocolo.py
git commit -m "feat: parse_comando do WS ao-vivo com testes"
```

---

## Task 4: Sessão Gemini Live (`live_transcribe.py` + fumaça)

**Files:**
- Create: `app/live_transcribe.py`
- Create: `scripts/smoke_live.py`

- [ ] **Step 1: Implementar o módulo**

Create `app/live_transcribe.py`:

```python
"""Sessao Gemini Live: streaming de PCM 16k -> transcricao do input.
Modelo silenciado (so transcreve, nao responde). Reconecta antes do limite
de ~15 min usando session resumption."""
import asyncio
import time

from google.genai import types

MODEL = "gemini-3.1-flash-live-preview"
LIMITE_SESSAO_S = 14 * 60  # reconecta antes do teto de 15 min
SYSTEM = (
    "Voce e um transcritor silencioso. Nunca responda, nunca comente, nunca "
    "gere fala. Apenas ouca o audio. Seu unico papel e permitir a transcricao."
)


def montar_config(handle: str | None):
    cfg = {
        "response_modalities": ["AUDIO"],     # native-audio exige AUDIO
        "input_audio_transcription": {},
        "system_instruction": SYSTEM,
        "session_resumption": types.SessionResumptionConfig(handle=handle),
    }
    return cfg


async def transcrever_ao_vivo(client, ler_pcm, on_texto, on_status, parar):
    """
    client: genai.Client.
    ler_pcm: async callable -> bytes (proximo bloco) ou None (fim da captura).
    on_texto: async callable(str) chamado a cada trecho transcrito.
    on_status: async callable(str) — 'capturando' | 'reconectando'.
    parar: asyncio.Event que encerra tudo.
    """
    handle = None
    while not parar.is_set():
        await on_status("capturando")
        handle = await _uma_sessao(client, ler_pcm, on_texto, parar, handle)
        if parar.is_set():
            break
        await on_status("reconectando")


async def _uma_sessao(client, ler_pcm, on_texto, parar, handle):
    inicio = time.monotonic()
    novo_handle = handle
    async with client.aio.live.connect(model=MODEL,
                                       config=montar_config(handle)) as session:
        async def enviar():
            while not parar.is_set():
                if time.monotonic() - inicio > LIMITE_SESSAO_S:
                    return  # forca reconexao limpa antes do teto
                pcm = await ler_pcm()
                if pcm is None:
                    parar.set()
                    return
                await session.send_realtime_input(
                    audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))

        async def receber():
            nonlocal novo_handle
            async for msg in session.receive():
                sc = msg.server_content
                if sc and sc.input_transcription and sc.input_transcription.text:
                    await on_texto(sc.input_transcription.text)
                upd = getattr(msg, "session_resumption_update", None)
                if upd and upd.resumable and upd.new_handle:
                    novo_handle = upd.new_handle
                if getattr(msg, "go_away", None):
                    return

        env = asyncio.create_task(enviar())
        rec = asyncio.create_task(receber())
        try:
            await env
        finally:
            rec.cancel()
            try:
                await rec
            except asyncio.CancelledError:
                pass
    return novo_handle
```

- [ ] **Step 2: Criar fumaça ponta-a-ponta (captura real → Live)**

Create `scripts/smoke_live.py`:

```python
"""Fumaca manual: captura real (fonte do argv) -> Live API -> imprime
transcricao por ~20s. Uso: ./.venv/Scripts/python.exe scripts/smoke_live.py [pc|mic|ambos]"""
import asyncio
import os
import sys
from dotenv import load_dotenv
load_dotenv()
from google import genai
from app.audio_capture import AudioCapture
from app import live_transcribe

fonte = sys.argv[1] if len(sys.argv) > 1 else "ambos"


async def main():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    cap = AudioCapture(fonte)
    cap.iniciar()
    parar = asyncio.Event()

    async def ler_pcm():
        return await asyncio.to_thread(cap.proximo_bloco, 2.0)

    async def on_texto(t):
        print(t, end="", flush=True)

    async def on_status(s):
        print(f"\n[{s}]", flush=True)

    tarefa = asyncio.create_task(
        live_transcribe.transcrever_ao_vivo(client, ler_pcm, on_texto, on_status, parar))
    await asyncio.sleep(20)
    parar.set()
    cap.parar()
    await tarefa
    print("\n--- fim ---")


asyncio.run(main())
```

- [ ] **Step 3: Rodar a fumaça (manual)**

Run (falando no mic / vídeo tocando): `./.venv/Scripts/python.exe scripts/smoke_live.py mic`
Expected: o texto da fala aparece no terminal em segundos. Testar `pc` e `ambos`.

- [ ] **Step 4: Commit**

```bash
git add app/live_transcribe.py scripts/smoke_live.py
git commit -m "feat: sessao Gemini Live (streaming + reconexao) + smoke e2e"
```

---

## Task 5: Endpoint WebSocket no `main.py`

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Adicionar imports**

Em `app/main.py`, na linha de import do FastAPI, incluir `WebSocket` e `WebSocketDisconnect`:

```python
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, WebSocket, WebSocketDisconnect
```

E logo após os imports locais existentes, adicionar:

```python
import asyncio
from .audio_capture import AudioCapture
from .protocolo import parse_comando
from . import live_transcribe
```

(`asyncio` pode já estar importado indiretamente; garantir o `import asyncio` no topo junto aos demais.)

- [ ] **Step 2: Adicionar o endpoint**

Em `app/main.py`, logo após a rota `@app.get("/healthz")`, inserir:

```python
@app.websocket("/ws/ao-vivo")
async def ws_ao_vivo(websocket: WebSocket):
    await websocket.accept()
    if not websocket.session.get("auth"):
        await websocket.send_json({"tipo": "erro", "msg": "Nao autenticado."})
        await websocket.close(code=1008)
        return
    if _client is None:
        await websocket.send_json({"tipo": "erro", "msg": "GEMINI_API_KEY nao configurada."})
        await websocket.close()
        return

    captura: AudioCapture | None = None
    parar = asyncio.Event()
    tarefa: asyncio.Task | None = None

    async def ler_pcm():
        return await asyncio.to_thread(captura.proximo_bloco, 2.0)

    async def on_texto(t):
        await websocket.send_json({"tipo": "texto", "texto": t})

    async def on_status(s):
        await websocket.send_json({"tipo": "status", "status": s})

    try:
        while True:
            raw = await websocket.receive_json()
            try:
                cmd = parse_comando(raw)
            except ValueError as e:
                await websocket.send_json({"tipo": "erro", "msg": str(e)})
                continue

            if cmd["acao"] == "iniciar":
                if tarefa is not None:
                    continue  # ja rodando
                try:
                    captura = AudioCapture(cmd["fonte"])
                    captura.iniciar()
                except Exception as e:
                    await websocket.send_json(
                        {"tipo": "erro", "msg": f"Falha ao iniciar captura: {e}"})
                    captura = None
                    continue
                parar.clear()
                tarefa = asyncio.create_task(
                    live_transcribe.transcrever_ao_vivo(
                        _client, ler_pcm, on_texto, on_status, parar))

            elif cmd["acao"] == "parar":
                parar.set()
                if captura:
                    captura.parar()
                    captura = None
                if tarefa:
                    try:
                        await tarefa
                    except Exception as e:
                        await websocket.send_json({"tipo": "erro", "msg": str(e)})
                    tarefa = None
                await websocket.send_json({"tipo": "status", "status": "parado"})
    except WebSocketDisconnect:
        pass
    finally:
        parar.set()
        if captura:
            captura.parar()
        if tarefa:
            try:
                await tarefa
            except Exception:
                pass
```

- [ ] **Step 3: Verificar import e boot**

Run: `./.venv/Scripts/python.exe -c "import app.main; print('import ok')"`
Expected: `import ok` (sem erro de sintaxe/import).

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: endpoint WS /ws/ao-vivo ligando captura + Live + browser"
```

---

## Task 6: Frontend — abas Arquivo/Ao vivo + cliente WebSocket

**Files:**
- Modify: `app/static/index.html`

- [ ] **Step 1: Adicionar CSS das abas e do painel**

Em `app/static/index.html`, dentro do `<style>`, antes do fechamento `</style>`, adicionar:

```css
    .tabs { display:flex; gap:6px; margin-bottom:18px; }
    .tab { flex:1; text-align:center; font-size:.85rem; font-weight:600;
           padding:9px 12px; border-radius:10px; border:1px solid #d6dedd;
           background:#fff; color:var(--mut); cursor:pointer; }
    .tab.ativa { background:var(--teal); color:#fff; border-color:var(--teal); }
    .modo { display:none; }
    .modo.ativo { display:block; }
    .fontes { display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }
    .fonte-op { flex:1; min-width:90px; text-align:center; font-size:.8rem;
                padding:9px; border-radius:10px; border:1px solid #d6dedd;
                background:#fff; color:var(--fg); cursor:pointer; }
    .fonte-op.sel { border-color:var(--teal); background:#eef6f6; color:var(--teal); font-weight:600; }
    .ao-vivo-rec { display:inline-block; width:9px; height:9px; border-radius:50%;
                   background:var(--coral); margin-right:6px; vertical-align:1px; }
```

- [ ] **Step 2: Inserir a marcação das abas e do painel ao vivo**

Em `app/static/index.html`, dentro de `<div class="body">`, logo após `<p class="sub">...</p>`, inserir as abas e envolver o conteúdo de arquivo num modo. Substituir o bloco que vai do `<label class="drop" id="drop">` até o `<textarea id="out">` por:

```html
      <div class="tabs">
        <button class="tab ativa" id="tab-arquivo" type="button">Arquivo</button>
        <button class="tab" id="tab-aovivo" type="button">Ao vivo</button>
      </div>

      <!-- MODO ARQUIVO (fluxo existente) -->
      <div class="modo ativo" id="modo-arquivo">
        <label class="drop" id="drop">
          <input type="file" id="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac,.aac,.aiff" multiple>
          <div class="ic">
            <svg viewBox="0 0 24 24" fill="none" stroke="#0F6E78" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>
            </svg>
          </div>
          <div class="big">Arraste um ou vários áudios</div>
          <div class="small">ou clique para escolher</div>
          <div class="chips" id="fname"></div>
        </label>
        <div class="row">
          <button class="primary" id="go" disabled>Transcrever</button>
        </div>
      </div>

      <!-- MODO AO VIVO -->
      <div class="modo" id="modo-aovivo">
        <div class="fontes">
          <button class="fonte-op sel" data-fonte="ambos" type="button">Mic + PC</button>
          <button class="fonte-op" data-fonte="mic" type="button">Microfone</button>
          <button class="fonte-op" data-fonte="pc" type="button">Áudio do PC</button>
        </div>
        <div class="row">
          <button class="primary" id="iniciar" type="button">Iniciar</button>
          <button class="ghost" id="parar" type="button" disabled>Parar</button>
        </div>
      </div>

      <!-- Compartilhado pelos dois modos -->
      <div class="row" style="margin-top:12px;">
        <button class="ghost" id="copy" disabled>Copiar</button>
        <button class="ghost" id="dl" disabled>Baixar .txt</button>
      </div>

      <div class="status" id="status"></div>
      <textarea id="out" placeholder="A transcrição aparece aqui (editável)."></textarea>
```

(Os botões Copiar/Baixar saíram da `.row` do modo arquivo e viraram compartilhados; o botão Transcrever ficou sozinho no modo arquivo.)

- [ ] **Step 3: Adicionar a lógica das abas e do WebSocket**

Em `app/static/index.html`, dentro do `<script>`, logo após a linha `out.addEventListener("input", refreshActions);`, adicionar:

```javascript
    // ----- Abas -----
    const tabArquivo = $("tab-arquivo"), tabAovivo = $("tab-aovivo");
    const modoArquivo = $("modo-arquivo"), modoAovivo = $("modo-aovivo");
    function trocarAba(aovivo) {
      tabAovivo.classList.toggle("ativa", aovivo);
      tabArquivo.classList.toggle("ativa", !aovivo);
      modoAovivo.classList.toggle("ativo", aovivo);
      modoArquivo.classList.toggle("ativo", !aovivo);
    }
    tabArquivo.addEventListener("click", () => trocarAba(false));
    tabAovivo.addEventListener("click", () => trocarAba(true));

    // ----- Seletor de fonte -----
    let fonteSel = "ambos";
    document.querySelectorAll(".fonte-op").forEach(op => {
      op.addEventListener("click", () => {
        document.querySelectorAll(".fonte-op").forEach(o => o.classList.remove("sel"));
        op.classList.add("sel");
        fonteSel = op.dataset.fonte;
      });
    });

    // ----- WebSocket ao vivo -----
    const iniciar = $("iniciar"), parar = $("parar");
    let ws = null;
    iniciar.addEventListener("click", () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/ao-vivo`);
      iniciar.disabled = true;
      out.value = "";
      refreshActions();
      ws.onopen = () => ws.send(JSON.stringify({ acao: "iniciar", fonte: fonteSel }));
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.tipo === "texto") { out.value += m.texto; refreshActions(); }
        else if (m.tipo === "status") {
          if (m.status === "capturando") {
            setStatus('<span class="ao-vivo-rec"></span> Capturando ao vivo…');
            parar.disabled = false;
          } else if (m.status === "reconectando") {
            setStatus('<span class="spin"></span> Reconectando…');
          } else if (m.status === "parado") {
            setStatus("Captura encerrada.", "ok");
          }
        } else if (m.tipo === "erro") {
          setStatus(m.msg, "err");
          iniciar.disabled = false; parar.disabled = true;
        }
      };
      ws.onclose = () => { iniciar.disabled = false; parar.disabled = true; };
      ws.onerror = () => setStatus("Falha na conexão ao vivo.", "err");
    });
    parar.addEventListener("click", () => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ acao: "parar" }));
      parar.disabled = true;
      iniciar.disabled = false;
    });
```

- [ ] **Step 4: Verificar visualmente (headless)**

Run: `"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --window-size=667,760 --screenshot="/c/Cerberus/repos/transcritor-audio/Amostras/_check_tabs.png" "file:///C:/Cerberus/repos/transcritor-audio/app/static/index.html"`
Then: Read `Amostras/_check_tabs.png` — confirmar as abas no topo e, ao não ter backend, o modo Arquivo intacto. Apagar o PNG depois.

- [ ] **Step 5: Commit**

```bash
git add app/static/index.html
git commit -m "feat: abas Arquivo/Ao vivo + cliente WebSocket no frontend"
```

---

## Task 7: Verificação ponta-a-ponta + docs

**Files:**
- Modify: `README.md`
- Modify: `HANDOFF.md` (no vault Cerberus, não neste repo) — ver passo final

- [ ] **Step 1: Subir o app e testar o fluxo de arquivo (não-regressão)**

Run: `cmd //c "C:\Cerberus\repos\transcritor-audio\iniciar.bat"`
Manual: logar, modo **Arquivo**, transcrever 1 áudio — confirmar que continua funcionando como antes.

- [ ] **Step 2: Testar o modo ao vivo no browser**

Manual em `http://127.0.0.1:8000`:
- Aba **Ao vivo**, fonte **Microfone** → Iniciar → falar → texto aparece → Parar.
- Fonte **Áudio do PC** com um vídeo tocando → texto aparece.
- Fonte **Mic + PC** simultâneos.
- Copiar e Baixar .txt funcionam com o texto ao vivo.
- (Opcional, longo) deixar >15 min pra exercitar a reconexão — ver o status "Reconectando…" sem perder o texto anterior.

- [ ] **Step 3: Rodar a suíte de testes**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: todos os testes de `test_audio_dsp.py` e `test_protocolo.py` passam.

- [ ] **Step 4: Atualizar o README**

Em `README.md`, na seção "O que é" / "Stack", acrescentar que há um modo **Ao vivo** (captura de mic/saída do PC via `soundcard`/WASAPI loopback, streaming pela Gemini Live API `gemini-3.1-flash-live-preview`, Windows-only). Mencionar `requirements-dev.txt` e `pytest`.

- [ ] **Step 5: Commit do código/README**

```bash
git add README.md
git commit -m "docs: README com o modo de transcricao ao vivo"
```

- [ ] **Step 6: Parar o servidor e atualizar o vault**

Run: `cmd //c "C:\Cerberus\repos\transcritor-audio\parar.bat"`
Depois, no vault Cerberus, atualizar o estado do produto Transcritor em
`03_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/03_TRANSCRITOR_AUDIO/README.md` e
o `HANDOFF.md` registrando a entrega do modo ao vivo (decisão de design já
está na spec). Sem wikilinks quebrados.

---

## Self-review (preenchido pelo autor do plano)

- **Cobertura da spec:** UX abas (T6) ✓ · captura mic/pc/ambos+mix (T1,T2) ✓ ·
  sessão Live silenciada + reconexão (T4) ✓ · WebSocket (T5) ✓ · seleção de
  fonte (T6) ✓ · erros sem stack (T2,T4,T5) ✓ · deps soundcard/numpy (T0) ✓ ·
  fora-de-escopo respeitado (sem separar falante, sem device manual). ✓
- **Placeholders:** nenhum — todo passo de código tem código real e comandos
  com saída esperada. Partes de hardware/rede usam fumaça + verificação manual
  por serem não-determinísticas (decisão explícita, não placeholder).
- **Consistência de tipos:** `to_int16_pcm`/`mix` (T1) usados igual em T2;
  `AudioCapture.iniciar/proximo_bloco/parar` (T2) batem com o uso em T4/T5;
  `transcrever_ao_vivo(client, ler_pcm, on_texto, on_status, parar)` (T4) idem
  na chamada em T5 e no smoke (T4); `parse_comando` (T3) idem em T5; mensagens
  WS `{tipo: texto|status|erro}` consistentes entre T5 (server) e T6 (client).
