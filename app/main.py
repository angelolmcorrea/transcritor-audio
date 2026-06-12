"""Transcritor — backend FastAPI.

Recebe um arquivo de audio, envia para o Gemini via File API e devolve a
transcricao em PT-BR. Ferramenta pessoal: sem banco, sem historico.
Acesso protegido por login simples (sessao por cookie assinado).
"""

import os
import time
import shutil
import secrets
import tempfile
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from google import genai
from google.genai import errors as genai_errors

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

APP_USER = os.getenv("APP_USER", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
# Em producao (HTTPS) o cookie de sessao deve ser secure. Local (http) = false.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

STATIC_DIR = Path(__file__).parent / "static"

# Extensoes que o Gemini aceita nativamente. Outras (ex: .m4a, .opus, .wma)
# sao convertidas para .flac via ffmpeg antes do upload.
EXT_NATIVAS = {".wav", ".mp3", ".aiff", ".aif", ".aac", ".ogg", ".flac"}

PROMPT = (
    "Transcreva integralmente o audio a seguir em portugues do Brasil. "
    "Use pontuacao e paragrafos naturais. Nao resuma, nao comente, nao adicione "
    "rotulos de falante — devolva apenas o texto transcrito."
)

# Codigos do Gemini que valem retry: sobrecarga/indisponibilidade transitoria
# (comum no free tier) e rate limit. Espera crescente entre tentativas.
CODIGOS_TRANSITORIOS = {429, 500, 503}


def _com_retry(fn, tentativas=4, espera_inicial=2):
    """Executa fn(); em erro transitorio do Gemini, retenta com backoff."""
    espera = espera_inicial
    for i in range(tentativas):
        try:
            return fn()
        except genai_errors.APIError as e:
            if e.code in CODIGOS_TRANSITORIOS and i < tentativas - 1:
                time.sleep(espera)
                espera *= 2
                continue
            raise


def _mensagem_erro_gemini(e: genai_errors.APIError) -> str:
    if e.code == 503:
        return "O Gemini esta sobrecarregado no momento. Tente novamente em alguns instantes."
    if e.code == 429:
        return "Limite de uso do Gemini atingido (free tier). Aguarde um pouco e tente de novo."
    return f"Erro do Gemini ({e.code}). Tente novamente em instantes."


app = FastAPI(title="Transcritor")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY or secrets.token_hex(16),
    https_only=COOKIE_SECURE,
)

_client = genai.Client(api_key=API_KEY) if API_KEY else None
# FFMPEG_PATH permite apontar o binario direto (util quando rodando como
# servico, que pode nao herdar o PATH). Fallback: procura no PATH.
_ffmpeg = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _autenticado(request: Request) -> bool:
    return bool(request.session.get("auth"))


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


# ---------------------------------------------------------------- autenticacao

@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/login")
def login(request: Request, usuario: str = Form(...), senha: str = Form(...)):
    ok = (
        APP_USER
        and APP_PASSWORD
        and secrets.compare_digest(usuario, APP_USER)
        and secrets.compare_digest(senha, APP_PASSWORD)
    )
    if not ok:
        return RedirectResponse("/login?erro=1", status_code=303)
    request.session["auth"] = True
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ------------------------------------------------------------------ aplicacao

@app.get("/")
def index(request: Request):
    if not _autenticado(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/transcrever")
async def transcrever(request: Request, arquivo: UploadFile = File(...)):
    if not _autenticado(request):
        raise HTTPException(401, "Nao autenticado.")
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

        enviado = _com_retry(lambda: _client.files.upload(file=caminho_envio))

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

        resposta = _com_retry(
            lambda: _client.models.generate_content(
                model=MODEL,
                contents=[enviado, PROMPT],
            )
        )
        texto = (resposta.text or "").strip()
        if not texto:
            raise HTTPException(502, "Transcricao vazia retornada pelo modelo.")

        return JSONResponse({"texto": texto})

    except genai_errors.APIError as e:
        # Erro do Gemini que sobreviveu ao retry: devolve JSON legivel
        # em vez de vazar um 500 em texto puro pro frontend.
        raise HTTPException(502, _mensagem_erro_gemini(e))

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
