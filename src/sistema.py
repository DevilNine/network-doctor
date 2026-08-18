"""Diagnóstico do sistema: versão do Windows, uptime, memória, adaptadores e Wi-Fi."""

from __future__ import annotations

import re
from datetime import datetime

from . import util


def info_sistema() -> dict:
    """SO, versão, build, uptime e memória (via CIM — saída estruturada, sem problema de locale)."""
    dados = util.ps_json(
        "Get-CimInstance Win32_OperatingSystem | "
        "Select-Object Caption, Version, BuildNumber, LastBootUpTime, "
        "TotalVisibleMemorySize, FreePhysicalMemory"
    )
    info = {
        "so": "Windows",
        "versao": "—",
        "uptime_seg": None,
        "memoria_total_gb": None,
        "memoria_livre_gb": None,
    }
    if isinstance(dados, list):
        dados = dados[0] if dados else None
    if not dados:
        return info
    info["so"] = dados.get("Caption") or "Windows"
    info["versao"] = (dados.get("Version") or "—") + (
        " (build " + str(dados.get("BuildNumber")) + ")" if dados.get("BuildNumber") else ""
    )
    try:
        # Dois formatos possíveis: WMI (AAAAMMDDHHMMSS...) ou JSON.NET (/Date(ms)/)
        bruto = str(dados["LastBootUpTime"])
        m = re.match(r"/Date\((\d+)\)/", bruto)
        if m:
            boot = datetime.fromtimestamp(int(m.group(1)) / 1000)
        else:
            m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", bruto)
            boot = datetime(*(int(g) for g in m.groups())) if m else None
        if boot:
            info["uptime_seg"] = (datetime.now() - boot).total_seconds()
    except (KeyError, ValueError, OSError):
        info["uptime_seg"] = None
    try:
        info["memoria_total_gb"] = float(dados["TotalVisibleMemorySize"]) / 1_048_576
        info["memoria_livre_gb"] = float(dados["FreePhysicalMemory"]) / 1_048_576
    except (KeyError, TypeError, ValueError):
        pass
    return info


def adaptadores() -> list[dict]:
    """Adaptadores de rede ativos com velocidade do link, MAC e tipo de mídia."""
    dados = util.ps_json_list(
        "Get-NetAdapter | Where-Object Status -eq 'Up' | "
        "Select-Object Name, InterfaceDescription, LinkSpeed, MacAddress, MediaType, ifIndex"
    )
    lista = []
    for d in dados:
        link_mbps = _link_speed_mbps(d.get("LinkSpeed"))
        lista.append(
            {
                "nome": d.get("Name") or "—",
                "descricao": d.get("InterfaceDescription") or "—",
                "link_mbps": link_mbps,
                "mac": d.get("MacAddress") or "—",
                "tipo": d.get("MediaType") or "—",
                "ifindex": d.get("ifIndex"),
            }
        )
    return lista


def _link_speed_mbps(valor) -> float | None:
    """Converte o LinkSpeed do Windows ('1 Gbps', '866.7 Mbps', 1000000000) em Mbps."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor) / 1_000_000
    m = re.match(r"(\d+(?:\.\d+)?)\s*([GMK])?bps", str(valor), re.IGNORECASE)
    if not m:
        return None
    num, unidade = m.groups()
    mult = {"G": 1000, "M": 1, "K": 0.001}.get((unidade or "M").upper(), 1)
    return float(num) * mult


def wifi() -> dict | None:
    """Sinal, taxas, canal e banda da rede Wi-Fi atual (netsh wlan). None se não houver Wi-Fi."""
    saida = util.cmd_dos("netsh wlan show interfaces", timeout=15.0)
    info = util.parse_netsh_wlan(saida)
    if info is None:
        return None

    def _num(valor: str | None) -> float | None:
        if not valor:
            return None
        m = re.search(r"\d+(?:[.,]\d+)?", valor.replace(",", "."))
        return float(m.group(0)) if m else None

    sinal = _num(info.get("sinal"))
    return {
        "ssid": info.get("ssid") or "—",
        "sinal_pct": sinal,
        "rx_mbps": _num(info.get("rx_mbps")),
        "tx_mbps": _num(info.get("tx_mbps")),
        "canal": info.get("canal") or "—",
        "banda": info.get("banda") or "—",
        "autenticacao": info.get("autenticacao") or "—",
        "radio": info.get("radio") or "—",
    }


def redes_visiveis() -> int | None:
    """Número de redes Wi-Fi visíveis (ajuda a avaliar congestionamento de canal)."""
    saida = util.cmd_dos("netsh wlan show networks mode=bssid", timeout=20.0)
    return len([l for l in saida.splitlines() if l.strip().startswith("SSID")])
