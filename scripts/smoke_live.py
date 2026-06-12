"""Fumaca manual: captura real (fonte do argv) -> Live API -> imprime
transcricao por ~20s. Uso: ./.venv/Scripts/python.exe scripts/smoke_live.py [pc|mic|ambos]"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    async def on_erro(m):
        print(f"\n[ERRO] {m}", flush=True)

    tarefa = asyncio.create_task(
        live_transcribe.transcrever_ao_vivo(client, ler_pcm, on_texto, on_status, on_erro, parar))
    await asyncio.sleep(20)
    parar.set()
    cap.parar()
    await tarefa
    print("\n--- fim ---")


asyncio.run(main())
