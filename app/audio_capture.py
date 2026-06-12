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
        """Proximo bloco PCM (bytes). b"" = nada ainda (timeout); None = fim da
        captura. Levanta o erro de captura, se houver, ao chegar no fim."""
        try:
            item = self._fila.get(timeout=timeout)
        except queue.Empty:
            return b""
        if item is None and self._erro is not None:
            raise self._erro
        return item

    def parar(self):
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=2.0)
