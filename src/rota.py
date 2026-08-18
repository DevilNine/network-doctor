"""Rota até a internet: traceroute rápido e pathping (perda por salto).

Ajuda a localizar onde começa uma instabilidade: se a perda/ping alto aparece
só depois de um salto específico (geralmente um ponto da operadora), o problema
é regional/do provedor, e não do Wi-Fi ou do roteador do usuário.
"""

from __future__ import annotations

from . import util

ALVO_PADRAO = "8.8.8.8"
LIMITE_SALTOS = 20


def traceroute(alvo: str = ALVO_PADRAO) -> list[dict]:
    """Rota em até N saltos com o tempo de cada salto (tracert -d)."""
    saida = util.cmd_dos(f"tracert -d -h {LIMITE_SALTOS} {alvo}", timeout=120.0)
    saltos = util.parse_tracert(saida)
    # marca o salto onde a latência dá um salto brusco (sinal de rota ruim)
    anterior = None
    for s in saltos:
        media = util.media(s["rtts"])
        s["salto_ruim"] = bool(
            media is not None and anterior is not None and media > max(50.0, anterior * 3)
        )
        anterior = media if media is not None else anterior
    return saltos


def pathping(alvo: str = ALVO_PADRAO, q: int = 5) -> list[dict]:
    """Perda por salto (pathping -n). Demora ~1-2 min; use apenas com --profundo."""
    saida = util.cmd_dos(
        f"pathping -n -h {LIMITE_SALTOS} -q {q} {alvo}", timeout=240.0
    )
    return util.parse_pathping(saida)
