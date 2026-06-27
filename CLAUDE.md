# CLAUDE.md — transcritor-audio

Transcritor de áudio local (microfone + arquivo), interno. FastAPI + Gemini.

## Stack

- **Python**, **FastAPI** + **uvicorn**, **google-genai** (Gemini), `soundcard`, `numpy`, `python-multipart`, `itsdangerous`.
- `iniciar.bat` / `parar.bat` pra subir e parar local.

## Comandos

- Setup: venv + `pip install -r requirements.txt` (dev: `requirements-dev.txt`)
- Rodar: `iniciar.bat` · Parar: `parar.bat`

## Decisão firme deste projeto

- **Roda SÓ LOCAL.** Hospedagem foi **descartada 2x** (Fly recusou o cartão; Render ficou lento demais). Existem `Dockerfile`, `fly.toml` e `render.yaml` no repo como resíduo dessas tentativas — **NÃO re-sugerir deploy / hospedagem.** Se surgir necessidade real de hospedar, é decisão nova do Angelo, não default.

## Como agir

Comunicação em **português**. **Propor antes de criar**; esperar "sim". **Bugfix não vira refactor.** Sem otimismo. **Sem emojis** em código.

Contexto no vault: `Cerberus/02_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/03_TRANSCRITOR_AUDIO/`.
