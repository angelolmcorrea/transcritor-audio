"""Validacao das mensagens de controle do WebSocket /ws/ao-vivo."""

FONTES = {"pc", "mic", "ambos"}


def parse_comando(raw: dict) -> dict:
    """Valida e normaliza um comando do browser. Levanta ValueError se invalido."""
    acao = raw.get("acao")
    if acao == "parar":
        return {"acao": "parar"}
    if acao == "iniciar":
        fonte = raw.get("fonte")
        if fonte not in FONTES:
            raise ValueError(f"fonte invalida: {fonte!r}")
        return {"acao": "iniciar", "fonte": fonte}
    raise ValueError(f"acao invalida: {acao!r}")
