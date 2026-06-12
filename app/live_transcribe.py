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


async def transcrever_ao_vivo(client, ler_pcm, on_texto, on_status, on_erro, parar):
    """
    client: genai.Client.
    ler_pcm: async callable -> bytes (proximo bloco), b"" (nada ainda) ou None (fim).
    on_texto: async callable(str) chamado a cada trecho transcrito.
    on_status: async callable(str) — 'capturando' | 'reconectando'.
    on_erro: async callable(str) — chamado quando a sessao falha em definitivo.
    parar: asyncio.Event que encerra tudo.
    """
    handle = None
    falhas = 0
    while not parar.is_set():
        await on_status("capturando")
        try:
            handle = await _uma_sessao(client, ler_pcm, on_texto, parar, handle)
            falhas = 0
        except Exception as e:
            falhas += 1
            if falhas > 5:
                await on_erro(f"Conexao ao vivo falhou repetidamente: {e}")
                parar.set()
                break
            await on_status("reconectando")
            for _ in range(min(2 ** falhas, 30)):  # backoff respeitando parar
                if parar.is_set():
                    break
                await asyncio.sleep(1)
            continue
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
                if not pcm:        # b"" = timeout, nada ainda; nao encerra a sessao
                    continue
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
