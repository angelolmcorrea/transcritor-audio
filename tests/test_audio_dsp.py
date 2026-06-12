import struct
import numpy as np
from app.audio_capture import to_int16_pcm, mix


def test_to_int16_pcm_silencio():
    out = to_int16_pcm(np.zeros(4, dtype="float32"))
    assert out == b"\x00\x00" * 4


def test_to_int16_pcm_escala_e_clipa():
    out = to_int16_pcm(np.array([1.0, -1.0, 2.0, -2.0], dtype="float32"))
    vals = struct.unpack("<4h", out)
    assert vals[0] == 32767      # +1.0 -> maximo
    assert vals[1] == -32767     # -1.0
    assert vals[2] == 32767      # +2.0 clipado
    assert vals[3] == -32767     # -2.0 clipado


def test_mix_soma_e_clipa():
    a = np.array([0.6, 0.6], dtype="float32")
    b = np.array([0.6, -0.6], dtype="float32")
    out = mix(a, b)
    assert out[0] == 1.0                 # 1.2 -> clipado em 1.0
    assert abs(float(out[1])) < 1e-6     # 0.6 - 0.6 = 0


def test_mix_alinha_pelo_menor():
    a = np.array([0.1, 0.2, 0.3], dtype="float32")
    b = np.array([0.1, 0.1], dtype="float32")
    out = mix(a, b)
    assert len(out) == 2
