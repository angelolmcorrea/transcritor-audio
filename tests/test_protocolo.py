import pytest
from app.protocolo import parse_comando


def test_iniciar_valido():
    assert parse_comando({"acao": "iniciar", "fonte": "ambos"}) == {
        "acao": "iniciar", "fonte": "ambos"}


def test_parar_valido():
    assert parse_comando({"acao": "parar"}) == {"acao": "parar"}


def test_fonte_invalida():
    with pytest.raises(ValueError):
        parse_comando({"acao": "iniciar", "fonte": "tudo"})


def test_acao_invalida():
    with pytest.raises(ValueError):
        parse_comando({"acao": "voar"})


def test_iniciar_sem_fonte():
    with pytest.raises(ValueError):
        parse_comando({"acao": "iniciar"})
