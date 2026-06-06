"""Transcritor — backend FastAPI.

Recebe um arquivo de audio, envia para o Gemini via File API e devolve a
transcricao em PT-BR. Ferramenta pessoal: sem login, sem banco, sem historico.
"""

import os
import time
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

STATIC_DIR = Path(__file__).parent / "static"

# Formatos que o Gemini aceita nativamente.
FORMATOS_OK = {
    "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/aiff", "audio/x-aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac", "audio/x-flac",
}

PROMPT = (
    "Transcreva integralmente o audio a seguir em portugues do Brasil. "
    "Use pontuacao e paragrafos naturais. Nao resuma, nao comente, nao adicione "
    "rotulos de falante — devolva apenas o texto transcrito."
)

app = FastAPI(title="Transcritor")

_client = genai.Client(api_key=API_KEY) if API_KEY else None


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/transcrever")
async def transcrever(arquivo: UploadFile = File(...)):
    if _client is None:
        raise HTTPException(500, "GEMINI_API_KEY nao configurada. Veja o .env.")

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio.")

    sufixo = Path(arquivo.filename or "audio").suffix or ".bin"
    tmp_path = None
    enviado = None
    try:
        # Grava num temp porque a File API sobe a partir de um caminho.
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
            tmp.write(conteudo)
            tmp_path = tmp.name

        enviado = _client.files.upload(file=tmp_path)

        # File API processa de forma assincrona; espera ficar ACTIVE.
        esperas = 0
        while enviado.state.name == "PROCESSING":
            if esperas > 120:  # ~2 min de teto
                raise HTTPException(504, "Processamento do audio demorou demais.")
            time.sleep(1)
            esperas += 1
            enviado = _client.files.get(name=enviado.name)

        if enviado.state.name == "FAILED":
            raise HTTPException(502, "O Gemini falhou ao processar o audio.")

        resposta = _client.models.generate_content(
            model=MODEL,
            contents=[enviado, PROMPT],
        )
        texto = (resposta.text or "").strip()
        if not texto:
            raise HTTPException(502, "Transcricao vazia retornada pelo modelo.")

        return JSONResponse({"texto": texto})

    finally:
        # Limpa o arquivo remoto e o temp local.
        if enviado is not None:
            try:
                _client.files.delete(name=enviado.name)
            except Exception:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# Serve os assets estaticos (CSS/JS) caso sejam adicionados depois.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
