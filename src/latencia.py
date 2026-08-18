"""Latência: ping no gateway e em alvos da internet, com jitter e perda de pacotes."""

from __future__ import annotations

from . import util

ALVOS_INTERNET = [
    ("Google (8.8.8.8)", "8.8.8.8"),
    ("Cloudflare (1.1.1.1)", "1.1.1.1"),
    ("Google Brasil (google.com.br)", "www.google.com.br"),
]


def _ping(alvo: str, qtd: int = 6, timeout_por_pacote_ms: int = 2000) -> dict:
    saida = util.cmd_dos(
        f"ping -n {qtd} -w {timeout_por_pacote_ms} {alvo}", timeout=qtd * 4 + 10
    )
    dados = util.parse_ping(saida)
    rtts = dados["rtts"]
    jit = util.jitter(rtts)
    return {
        "alvo": alvo,
        "rtts": rtts,
        "perda": dados["perda"],
        "min_ms": min(rtts) if rtts else None,
        "media_ms": util.media(rtts),
        "max_ms": max(rtts) if rtts else None,
        "jitter_ms": jit,
    }


def ping_gateway(gateway: str | None, qtd: int = 10) -> dict | None:
    """Latência até o roteador (primeiro salto). Sem gateway, não há o que testar."""
    if not gateway:
        return None
    return _ping(gateway, qtd=qtd)


def ping_internet(qtd: int = 6) -> list[dict]:
    """Latência até alvos da internet (2 internacionais + 1 regional brasileiro)."""
    resultados = []
    for nome, alvo in ALVOS_INTERNET:
        r = _ping(alvo, qtd=qtd)
        r["nome"] = nome
        resultados.append(r)
    return resultados
