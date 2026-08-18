"""Utilitários do network-doctor: subprocess, cores ANSI, formatação e parsing.

Tudo aqui é stdlib. Os parsers aceitam saída em português (pt-BR) e inglês (en-US),
porque o Windows devolve a saída dos comandos no idioma do sistema.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000  # evita janelas de console piscando ao rodar via GUI

# Em modo --json, mensagens de progresso/banner vão para o stderr para o
# stdout conter apenas o JSON válido.
MODO_JSON = False


def msg(texto: str) -> None:
    """Escreve uma mensagem de progresso (stdout normalmente, stderr no modo JSON)."""
    destino = sys.stderr if MODO_JSON else sys.stdout
    destino.write(texto + "\n")
    destino.flush()

# --- console / ANSI -----------------------------------------------------------

_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
    "gray": "\033[90m",
}


def enable_ansi() -> None:
    """Ativa sequências ANSI no console do Windows (Windows 10+)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def configure_stdout() -> None:
    """Garante UTF-8 na saída para não quebrar acentos/emojis."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def cor(texto: str, nome: str = "reset") -> str:
    """Pinta o texto (a cor é aplicada só quando a saída é um terminal)."""
    if nome not in _COLORS:
        return texto
    if not sys.stdout.isatty():
        return texto
    return f"{_COLORS[nome]}{texto}{_COLORS['reset']}"


# --- subprocess ---------------------------------------------------------------

def _codepage_oem() -> str:
    """Página de código OEM do sistema (ex.: cp850 em pt-BR) — é o que os
    executáveis nativos (ipconfig, ping, netsh) usam quando a saída é um pipe."""
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:
        return "cp850"


def _run(
    args: list[str],
    timeout: float = 30.0,
    codificacao: str | None = None,
    incluir_stderr: bool = False,
) -> str:
    """Executa um comando e devolve a saída como texto; nunca levanta exceção."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        saida = proc.stdout or b""
        if incluir_stderr:
            saida += proc.stderr or b""
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return _decodificar(saida, codificacao)


def _decodificar(saida: bytes, codificacao: str | None = None) -> str:
    """Decodifica a saída. UTF-16LE quando há BOM (PowerShell 5.1); senão usa a
    codificação pedida (OEM para comandos do cmd.exe) ou UTF-8 por padrão."""
    if saida.startswith(b"\xff\xfe") or saida.startswith(b"\xfe\xff"):
        return saida.decode("utf-16", errors="replace")
    if codificacao:
        return saida.decode(codificacao, errors="replace")
    try:
        return saida.decode("utf-8")
    except UnicodeDecodeError:
        return saida.decode("cp1252", errors="replace")


def powershell(script: str, timeout: float = 60.0) -> str:
    """Executa um trecho PowerShell e devolve apenas o stdout (sem ruído de avisos)."""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    return _run(cmd, timeout=timeout)


def ps_json(script: str, timeout: float = 60.0):
    """Executa PowerShell esperando saída JSON (ConvertTo-Json). Devolve objetos Python ou None."""
    wrapped = (
        "try { " + script + " | ConvertTo-Json -Compress -Depth 5 } "
        "catch { Write-Output '{\"__erro\": true}' }"
    )
    saida = powershell(wrapped, timeout=timeout).strip()
    if not saida:
        return None
    try:
        return json.loads(saida)
    except json.JSONDecodeError:
        return None


def ps_json_list(script: str, timeout: float = 60.0) -> list:
    """PowerShell + ConvertTo-Json garantindo uma lista de dicionários (ou [])."""
    dados = ps_json(script, timeout=timeout)
    if isinstance(dados, dict):
        return [dados]
    if isinstance(dados, list):
        return [d for d in dados if isinstance(d, dict)]
    return []


def cmd_dos(comando: str, timeout: float = 30.0) -> str:
    """Executa um comando via cmd.exe decodificando na página de código OEM do
    sistema — assim os acentos do português não quebram o parsing (ping, tracert,
    netsh, ipconfig...)."""
    return _run(["cmd.exe", "/C", comando], timeout=timeout, codificacao=_codepage_oem())


# --- formatação ---------------------------------------------------------------

def fmt_bits(mbps: float | None) -> str:
    if mbps is None or mbps < 0:
        return "—"
    if mbps >= 1000:
        return f"{mbps / 1000:.2f} Gbps"
    return f"{mbps:.1f} Mbps"


def fmt_duration(segundos: float | None) -> str:
    """'X dias, Y horas e Z minutos' a partir de segundos."""
    if segundos is None:
        return "—"
    segundos = int(segundos)
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, secs = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias} dia{'s' if dias != 1 else ''}")
    if horas:
        partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
    if minutos:
        partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
    elif secs:
        partes.append(f"{secs} segundo{'s' if secs != 1 else ''}")
    elif not partes:
        partes.append("0 minutos")
    return ", ".join(partes)


def bytes_para_mbps(bytes_por_segundo: float) -> float:
    """Taxa (bytes/s) → Mbps (bits/s / 1e6)."""
    return (bytes_por_segundo * 8) / 1_000_000


def tempo_download(mbps: float, tamanho_mb: float) -> str:
    """Tempo estimado (min) para baixar um arquivo de tamanho_mb a uma taxa em Mbps."""
    if not mbps or mbps <= 0:
        return "—"
    segundos = (tamanho_mb * 8) / mbps
    return fmt_duration(segundos)


def media(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


# --- parsing tolerante a pt-BR / en-US ----------------------------------------

_PING_RTT_RE = re.compile(r"(?:time|tempo)\s*[=<]\s*(\d+)ms", re.IGNORECASE)
_PING_LOSS_RE = re.compile(r"\((\d+)%\s*(?:de\s+)?(?:loss|perda)\)", re.IGNORECASE)
_PING_LOST_RE = re.compile(r"(?:lost|perdidos)\s*=\s*(\d+)", re.IGNORECASE)


def parse_ping(saida: str) -> dict:
    """Extrai RTTs e perda da saída do `ping` (pt-BR ou en-US)."""
    rtts = [float(m) for m in _PING_RTT_RE.findall(saida)]
    perda = 100.0
    m = _PING_LOSS_RE.search(saida)
    if m:
        perda = float(m.group(1))
    else:
        m = _PING_LOST_RE.search(saida)
        if m is not None:
            total = len(rtts) or 4
            perda = min(100.0, float(m.group(1)) * 100.0 / total)
    return {"rtts": rtts, "perda": perda}


def parse_ping_mtu(saida: str) -> bool:
    """Verifica se um pacote ICMP com flag DF (Don't Fragment) passou sem fragmentação."""
    s_lower = saida.lower()
    if "precisa ser fragmentado" in s_lower or "needs to be fragmented" in s_lower:
        return False
    if "esgotado o tempo" in s_lower or "timed out" in s_lower or "inacess" in s_lower or "unreachable" in s_lower:
        return False
    # sucesso quando há indicação de resposta com tempo
    return bool(_PING_RTT_RE.search(saida))


def jitter(rtts: list[float]) -> float | None:
    """Jitter = média das diferenças absolutas entre RTTs consecutivos (ms)."""
    if len(rtts) < 2:
        return None
    diffs = [abs(b - a) for a, b in zip(rtts, rtts[1:])]
    return sum(diffs) / len(diffs)


_TRACERT_RE = re.compile(r"^\s*(\d+)\s+((?:\*\s+|\d+\s+ms\s+|<\s*1\s+ms\s+){0,3})([\d.]+)\s*$")
_TRACERT_RTT_RE = re.compile(r"(\d+|<\s*1)\s+ms")


def parse_tracert(saida: str) -> list[dict]:
    """Extrai saltos do `tracert -d`. Cada salto: {num, ip, rtts:[...]}.
    Aceita '<1 ms' (roteador local) como 1 ms."""
    saltos = []
    for linha in saida.splitlines():
        m = _TRACERT_RE.match(linha)
        if not m:
            continue
        num, tokens, ip = m.groups()
        if num is None or ip is None:
            continue
        rtts = []
        for x in _TRACERT_RTT_RE.findall(tokens):
            rtts.append(1.0 if x.startswith("<") else float(x))
        saltos.append({"num": int(num), "ip": ip, "rtts": rtts})
    return saltos


_PATHPT_RE = re.compile(r"^\s*(\d+)\s+([\d.]+|\*)\s+(\d+)/\s*(\d+)\s*=\s*(\d+)%")


def parse_pathping(saida: str) -> list[dict]:
    """Extrai perda por salto do `pathping -n`. Cada salto: {num, ip, perda}."""
    saltos = []
    for linha in saida.splitlines():
        m = _PATHPT_RE.search(linha)
        if not m:
            continue
        num, ip, perdidos, enviados, perda = m.groups()
        try:
            saltos.append(
                {"num": int(num), "ip": ip, "perda": float(perda) if ip != "*" else 100.0}
            )
        except ValueError:
            continue
    return saltos


_NETSH_CHAVES = {
    "SSID": "ssid",
    "Sinal": "sinal",
    "Signal": "sinal",
    "Velocidade de recep\u00e7\u00e3o": "rx_mbps",
    "Receive rate": "rx_mbps",
    "Velocidade de transmiss\u00e3o": "tx_mbps",
    "Transmit rate": "tx_mbps",
    "Canal": "canal",
    "Channel": "canal",
    "Banda": "banda",
    "Band": "banda",
    "Autentica\u00e7\u00e3o": "autenticacao",
    "Authentication": "autenticacao",
    "Tipo de r\u00e1dio": "radio",
    "Radio type": "radio",
}


def parse_netsh_wlan(saida: str) -> dict | None:
    """Extrai status da interface Wi-Fi do `netsh wlan show interfaces`."""
    if "sem fio" in saida and re.search(r"(?:n[a\u00e3]o|nenhuma)", saida, re.IGNORECASE):
        return None
    if "there is no wireless" in saida.lower():
        return None
    if "SSID" not in saida:
        return None
    info: dict = {}
    for linha in saida.splitlines():
        if ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        chave = chave.strip()
        valor = valor.strip()
        if not chave or not valor:
            continue
        for nome, campo in _NETSH_CHAVES.items():
            if chave.lower().startswith(nome.lower()):
                info[campo] = valor
                break
    if not info:
        return None
    return info


def normalizar_mac(mac: str) -> str:
    """'50-c7-bf-12-34-56' ou '50:c7:bf:12:34:56' → '50C7BF' (prefixo OUI)."""
    hexa = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    return hexa[:6].upper()


def agora() -> str:
    from datetime import datetime

    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")
