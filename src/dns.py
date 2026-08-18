"""DNS: tempo de resolução de nomes usando o DNS do sistema e comparando com DNS públicos."""

from __future__ import annotations

import socket
import time

from . import util

DOMINIOS = ["google.com", "cloudflare.com", "wikipedia.org", "globo.com"]
DNS_PUBLICOS = [
    ("Cloudflare", "1.1.1.1"),
    ("Google", "8.8.8.8"),
    ("Quad9", "9.9.9.9"),
    ("OpenDNS", "208.67.222.222"),
]


def _resolucao_sistema(dominio: str) -> float | None:
    """Tempo (ms) que o resolver configurado no Windows leva para resolver o domínio."""
    inicio = time.perf_counter()
    try:
        socket.getaddrinfo(dominio, None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return None
    return (time.perf_counter() - inicio) * 1000


def resolucao_sistema(servidores: list[str] | None = None) -> dict:
    """Média do tempo de resolução dos domínios de teste usando o DNS configurado."""
    tempos = []
    falhas = 0
    for dominio in DOMINIOS:
        t = _resolucao_sistema(dominio)
        if t is None:
            falhas += 1
        else:
            tempos.append(t)
    servidores_finais = servidores if servidores is not None else _servidores_configurados()
    return {
        "media_ms": util.media(tempos),
        "tempos": tempos,
        "falhas": falhas,
        "servidores_configurados": servidores_finais,
    }


def _servidores_configurados() -> list[str]:
    """IPs dos servidores DNS configurados (do ipconfig /all)."""
    from . import rede

    cfg = rede.config_local()
    return cfg["dns"] if cfg else []


def _tempo_dns_publico(servidor: str) -> float | None:
    """Tempo (ms) de uma consulta DNS direta ao servidor público via PowerShell."""
    script = (
        "$t = Measure-Command { Resolve-DnsName -Name google.com -Server "
        f"{servidor} -Type A -ErrorAction SilentlyContinue | Out-Null }}; "
        f"[math]::Round($t.TotalMilliseconds, 1)"
    )
    saida = util.powershell(script, timeout=30.0)
    for trecho in reversed(saida.splitlines()):
        trecho = trecho.strip()
        try:
            return float(trecho.replace(",", "."))
        except ValueError:
            continue
    return None


def comparacao_dns_publico() -> list[dict]:
    """Tempo de consulta a cada DNS público (3 medições; usa a mediana, imune a picos)."""
    resultados = []
    for nome, ip in DNS_PUBLICOS:
        tempos = [t for t in (_tempo_dns_publico(ip) for _ in range(3)) if t is not None]
        ordenados = sorted(tempos)
        mediana = ordenados[len(ordenados) // 2] if ordenados else None
        resultados.append({"nome": nome, "ip": ip, "media_ms": mediana, "tempos": tempos})
    return resultados
