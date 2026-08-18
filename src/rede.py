"""Rede local: configuração (IP, gateway, DHCP, DNS), conexões ativas e uso de banda."""

from __future__ import annotations

import time

from . import util

_PREFIXOS_ADAPTADOR = (
    "Adaptador Ethernet ",
    "Adaptador de LAN sem fio ",
    "Adaptador de t\u00fanel ",
    "Adaptador desconhecido ",
    "Ethernet adapter ",
    "Wireless LAN adapter ",
    "Tunnel adapter ",
    "Unknown adapter ",
)


def _nome_adaptador(header: str | None) -> str:
    """'Adaptador Ethernet Ethernet:' → 'Ethernet' (remove tipo e ':' do cabeçalho)."""
    nome = (header or "—").strip()
    for pref in _PREFIXOS_ADAPTADOR:
        if nome.lower().startswith(pref.lower()):
            nome = nome[len(pref):]
            break
    return nome.strip(":").strip() or "—"


# Chaves do `ipconfig /all` nos dois idiomas (pt-BR / en-US)
_IPCONFIG_CHAVES = {
    "Endere\u00e7o IPv4": "ipv4",
    "IPv4 Address": "ipv4",
    "Endere\u00e7o IPv6": "ipv6",
    "IPv6 Address": "ipv6",
    "Endere\u00e7o IPv6 Tempor\u00e1rio": "ipv6_temp",
    "Temporary IPv6 Address": "ipv6_temp",
    "M\u00e1scara de Sub-rede": "mascara",
    "Subnet Mask": "mascara",
    "Gateway Padr\u00e3o": "gateway",
    "Default Gateway": "gateway",
    "DHCP Ativado": "dhcp",
    "DHCP Habilitado": "dhcp",
    "DHCP Enabled": "dhcp",
    "Concess\u00e3o Obtida": "lease_inicio",
    "Lease Obtained": "lease_inicio",
    "Concess\u00e3o Expira": "lease_fim",
    "Lease Expires": "lease_fim",
    "Servidores DNS": "dns",
    "DNS Servers": "dns",
    "Endere\u00e7o F\u00edsico": "mac",
    "Physical Address": "mac",
    "Servidor DHCP": "dhcp_server",
    "DHCP Server": "dhcp_server",
}


def _parse_ipconfig(saida: str) -> list[dict]:
    """Divide a saída do ipconfig /all em seções de adaptador e extrai os campos conhecidos."""
    secoes: list[dict] = []
    atual: dict | None = None
    ultima_chave = None
    for linha in saida.splitlines():
        if not linha.strip():
            continue
        if linha.startswith(" ") is False and ":" in linha and not linha[0].isdigit():
            # início de nova seção ("Adaptador Ethernet X:" / "Ethernet adapter X:")
            if atual is not None:
                secoes.append(atual)
            atual = {"nome": linha.strip()}
            ultima_chave = None
            continue
        if atual is None:
            atual = {"nome": "?"}
        if ":" not in linha:
            # continuação de valor (ex.: segunda linha de servidores DNS)
            if ultima_chave == "dns":
                ip = linha.strip()
                if ip:
                    atual.setdefault("dns", []).append(ip)
            continue
        chave, _, valor = linha.partition(":")
        chave = chave.strip()
        valor = valor.strip()
        campo = None
        for nome, c in _IPCONFIG_CHAVES.items():
            if chave.lower().startswith(nome.lower()):
                campo = c
                break
        if campo is None:
            continue
        ultima_chave = campo
        if campo == "dns":
            atual.setdefault("dns", [])
            if valor:
                atual["dns"].append(valor)
        else:
            atual[campo] = valor
    if atual is not None:
        secoes.append(atual)
    return secoes


def _gateway_real(gateway: str | None) -> bool:
    """Gateway útil = um IPv4 que não é vazio/0.0.0.0."""
    return bool(gateway and gateway not in ("", "0.0.0.0", ":")) and util.re.match(
        r"^\d+\.\d+\.\d+\.\d+", gateway
    )


def config_local() -> dict | None:
    """Configuração do adaptador ativo (o que tem gateway padrão real)."""
    saida = util.cmd_dos("ipconfig /all", timeout=30.0)
    for secao in _parse_ipconfig(saida):
        gateway = secao.get("gateway")
        if _gateway_real(gateway):
            ip = secao.get("ipv4") or ""
            ip = ip.split("(")[0].split("/")[0] or "—"
            ipv6 = secao.get("ipv6") or secao.get("ipv6_temp") or ""
            ipv6 = ipv6.split("(")[0].split("%")[0].strip() or "—"
            mac = secao.get("mac")
            dns = [d.split("%")[0] for d in (secao.get("dns") or [])]
            nome = _nome_adaptador(secao.get("nome"))
            return {
                "adaptador": nome,
                "ipv4": ip or "—",
                "ipv6": ipv6 or "—",
                "mascara": secao.get("mascara") or "—",
                "gateway": gateway.strip().split()[0] if gateway else "—",
                "dhcp": secao.get("dhcp") or "—",
                "dhcp_server": secao.get("dhcp_server") or "—",
                "lease_inicio": secao.get("lease_inicio") or "—",
                "lease_fim": secao.get("lease_fim") or "—",
                "dns": dns,
                "mac": mac or "—",
            }
    return None


def teste_mtu(alvo: str = "1.1.1.1") -> dict:
    """Testa pacotes ICMP com flag DF (Don't Fragment) para descobrir o MTU suportado."""
    # (payload ICMP, MTU correspondente com 28 bytes de cabeçalho IP+ICMP)
    candidatos = [(1472, 1500), (1464, 1492), (1452, 1480), (1400, 1428), (1372, 1400)]
    maior_mtu = None
    for payload, mtu in candidatos:
        cmd = f"ping -n 1 -w 1000 -f -l {payload} {alvo}"
        out = util.cmd_dos(cmd, timeout=4.0)
        if util.parse_ping_mtu(out):
            maior_mtu = mtu
            break
    mtu_final = maior_mtu or 1500
    padrao = (mtu_final == 1500)
    return {
        "mtu_maximo": mtu_final,
        "padrao_1500": padrao,
        "fragmenta_em_1500": not padrao,
        "alvo": alvo,
    }


def mac_do_gateway(gateway: str | None) -> str | None:
    """MAC do gateway via tabela ARP (arp -a)."""
    if not gateway:
        return None
    saida = util.cmd_dos("arp -a", timeout=15.0)
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0] == gateway:
            mac = partes[1]
            if util.re.match(r"^[0-9a-f-]{17}$", mac, util.re.IGNORECASE):
                return mac
    return None


def _linhas_netstat() -> list[dict]:
    """netstat -ano → lista de conexões {proto, local, remoto, estado, pid}."""
    saida = util.cmd_dos("netstat -ano", timeout=30.0)
    conexoes = []
    for linha in saida.splitlines():
        partes = linha.split()
        if not partes:
            continue
        if partes[0] not in ("TCP", "UDP"):
            continue
        if len(partes) < 5:
            continue
        if partes[0] == "TCP":
            _, local, remoto, estado, pid = partes[:5]
        else:
            _, local, remoto, pid = partes[:4]
            estado = "*"
        conexoes.append(
            {"local": local, "remoto": remoto, "estado": estado, "pid": pid}
        )
    return conexoes


def conexoes() -> dict:
    """Resumo das conexões ativas por estado."""
    conns = _linhas_netstat()
    estados: dict[str, int] = {}
    for c in conns:
        estados[c["estado"]] = estados.get(c["estado"], 0) + 1
    return {
        "total": len(conns),
        "estabelecidas": sum(1 for c in conns if c["estado"] == "ESTABLISHED"),
        "time_wait": sum(1 for c in conns if c["estado"] == "TIME_WAIT"),
        "sintetizadas": sum(1 for c in conns if c["estado"] == "SYN_SENT"),
        "por_estado": estados,
        "brutas": conns,
    }


def processos() -> dict[str, str]:
    """Mapeia PID → nome do processo (para traduzir os PIDs do netstat)."""
    dados = util.ps_json_list("Get-Process | Select-Object Id, ProcessName")
    return {str(d.get("Id")): d.get("ProcessName") or "?" for d in dados}


def top_conexoes(limite: int = 8) -> list[dict]:
    """Processos com mais conexões abertas (top N), com nome do processo."""
    conns = _linhas_netstat()
    por_pid: dict[str, int] = {}
    for c in conns:
        if c["estado"] in ("ESTABLISHED", "SYN_SENT", "TIME_WAIT") and c["pid"] != "0":
            por_pid[c["pid"]] = por_pid.get(c["pid"], 0) + 1
    nomes = processos()
    ranking = sorted(por_pid.items(), key=lambda kv: kv[1], reverse=True)[:limite]
    return [
        {"pid": pid, "nome": nomes.get(pid, "desconhecido"), "conexoes": qtd}
        for pid, qtd in ranking
    ]


def banda_interface(intervalo: float = 3.0) -> list[dict]:
    """Taxa atual de download/upload (Mbps) por adaptador, medindo o delta em N segundos."""
    # sem ConvertTo-Json aqui: o helper ps_json_list já adiciona
    script = "Get-NetAdapterStatistics | Select-Object Name, ReceivedBytes, SentBytes"

    def _amostra():
        dados = util.ps_json_list(script, timeout=30.0)
        return {d.get("Name"): d for d in dados}

    antes = _amostra()
    if not antes:
        return []
    time.sleep(intervalo)
    depois = _amostra()
    if not depois:
        return []

    resultado = []
    for nome, d2 in depois.items():
        d1 = antes.get(nome)
        if not d1:
            continue
        try:
            recebido = (float(d2["ReceivedBytes"]) - float(d1["ReceivedBytes"])) * 8 / 1_000_000 / intervalo
            enviado = (float(d2["SentBytes"]) - float(d1["SentBytes"])) * 8 / 1_000_000 / intervalo
        except (KeyError, TypeError, ValueError):
            continue
        if recebido < 0 or enviado < 0:
            continue  # contador reiniciado (roteador/adaptador reiniciou no meio)
        resultado.append({"nome": nome, "download_mbps": recebido, "upload_mbps": enviado})
    return resultado
