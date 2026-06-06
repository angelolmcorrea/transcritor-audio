"""Transcritor — backend FastAPI.

Recebe um arquivo de audio, envia para o Gemini via File API e devolve a
transcricao em PT-BR. Ferramenta pessoal: sem login, sem banco, sem historico.
"""

import os
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

STATIC_DIR = Path(__file__).parent / "static"

# Extensoes que o Gemini aceita nativamente. Outras (ex: .m4a, .opus, .wma)
# sao convertidas para .flac via ffmpeg antes do upload.
EXT_NATIVAS = {".wav", ".mp3", ".aiff", ".aif", ".aac", ".ogg", ".flac"}

PROMPT = (
    "Transcreva integralmente o audio a seguir em portugues do Brasil. "
    "Use pontuacao e paragrafos naturais. Nao resuma, nao comente, nao adicione "
    "rotulos de falante — devolva apenas o texto transcrito."
)

app = FastAPI(title="Transcritor")

_client = genai.Client(api_key=API_KEY) if API_KEY else None
_ffmpeg = shutil.which("ffmpeg")


def _converter_para_flac(origem: str) -> str:
    """Converte um audio nao-nativo para .flac usando ffmpeg. Devolve o novo path."""
    if not _ffmpeg:
        raise HTTPException(
            415,
            "Formato nao suportado nativamente pelo Gemini e ffmpeg nao encontrado "
            "para conversao. Converta o audio para mp3/wav/flac e tente de novo.",
        )
    destino = origem + ".flac"
    proc = subprocess.run(
        [_ffmpeg, "-y", "-i", origem, "-vn", "-c:a", "flac", destino],
        capture_output=True,
    )
    if proc.returncode != 0 or not os.path.exists(destino):
        raise HTTPException(422, "Falha ao converter o audio (ffmpeg).")
    return destino


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

    tamanho_mb = len(conteudo) / (1024 * 1024)
    if tamanho_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            413,
            f"Arquivo de {tamanho_mb:.1f} MB excede o limite de {MAX_UPLOAD_MB} MB.",
        )

    ext = Path(arquivo.filename or "audio").suffix.lower() or ".bin"
    tmp_path = None
    convertido = None
    enviado = None
    try:
        # Grava num temp porque a File API sobe a partir de um caminho.
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(conteudo)
            tmp_path = tmp.name

        # Formato fora da lista nativa do Gemini -> converte pra flac.
        caminho_envio = tmp_path
        if ext not in EXT_NATIVAS:
            convertido = _converter_para_flac(tmp_path)
            caminho_envio = convertido

        enviado = _client.files.upload(file=caminho_envio)

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
        # Limpa o arquivo remoto e os temps locais.
        if enviado is not None:
            try:
                _client.files.delete(name=enviado.name)
            except Exception:
                pass
        for p in (tmp_path, convertido):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


# Serve os assets estaticos (CSS/JS) caso sejam adicionados depois.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
