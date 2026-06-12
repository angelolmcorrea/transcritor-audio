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
