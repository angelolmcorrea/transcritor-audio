# Transcritor

Ferramenta pessoal de transcrição de áudio em texto (PT-BR). Dois modos:
- **Arquivo:** upload de um ou mais áudios → transcrição via Gemini File API.
- **Ao vivo:** captura microfone e/ou saída do PC (WASAPI loopback) e transcreve
  em tempo real via Gemini Live API. **Windows-only** (depende do loopback WASAPI).

Texto editável, copiável e baixável nos dois modos.

Sem login, sem banco, sem histórico. Documentação no vault:
`03_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/03_TRANSCRITOR_AUDIO/`.

## Stack

- Python 3 + FastAPI
- google-genai (File API do Gemini no modo Arquivo; Live API no modo Ao vivo,
  modelo `gemini-3.1-flash-live-preview`)
- `soundcard` + `numpy` para a captura ao vivo (mic + loopback WASAPI)
- Frontend estático servido pelo próprio FastAPI (sem build step); o modo ao vivo
  usa um WebSocket (`/ws/ao-vivo`)

## Como rodar

```powershell
# 1. Criar e ativar a venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar a chave
copy .env.example .env
# edite .env e preencha GEMINI_API_KEY=... (gerada no Google AI Studio)

# 4. Subir o servidor
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000

## Notas

- A `GEMINI_API_KEY` fica só no `.env` (ignorado pelo Git). Nunca vai pro browser.
- Modelo padrão: `gemini-2.5-flash`. Sobrescreva com `GEMINI_MODEL` no `.env`.
- Formatos aceitos nativamente pelo Gemini: wav, mp3, aiff, aac, ogg, flac.
  Outros (ex: `.m4a`, `.opus`, `.wma`) são convertidos para flac via **ffmpeg**
  automaticamente (precisa do ffmpeg no PATH).
- Teto de upload: `MAX_UPLOAD_MB` no `.env` (default 100 MB).
- **Privacidade:** no free tier do AI Studio o Google pode usar os dados para
  melhorar os produtos dele. Evite áudio sensível.
- **Modo ao vivo:** seleciona a fonte (Mic / Áudio do PC / ambos, que mistura as
  duas). A sessão Live dura ~15 min e reconecta sozinha. Requer mic/saída de
  áudio disponíveis no Windows.

## Desenvolvimento

```powershell
pip install -r requirements-dev.txt   # inclui pytest
python -m pytest -q                   # DSP de audio + protocolo do WS

# Scripts de fumaca da captura ao vivo (precisam de audio real):
python scripts/smoke_captura.py ambos   # grava 3s e mede nivel
python scripts/smoke_live.py mic        # captura -> Live API -> transcricao
```
