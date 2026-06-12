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
