"""Roteador: fabricante (via OUI do MAC), painel HTTP acessível e uptime via SNMP.

O uptime via SNMP é melhor esforço: muitos roteadores de operadora não habilitam SNMP.
Quando indisponível, o relatório usa as demais pistas (contrato DHCP, há quanto tempo
a rede está estável) em vez de inventar um número.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request

from . import util

# Prefixos OUI (6 primeiros hexa do MAC) de fabricantes comuns de roteador.
# Identificação aproximada — quando não bate, o relatório diz "desconhecido".
_OUIS = {
    "TP-LINK": ["50C7BF", "D807B6", "14CC20", "30B5C2", "98DAC4", "C04A00", "A42BB0", "7CD1C3", "003192", "3460F9", "F4F26D"],
    "D-Link": ["001B11", "1C7EE5", "28107B", "C83A35", "78321B", "B0C554", "00055D"],
    "Huawei": ["00E0FC", "189EFC", "98E7F5", "487B6B", "405FBE", "F4C479", "7054F5", "20F3A3"],
    "ZTE": ["0019C6", "94BF2D", "5CEA1D", "D46E5C", "74888B", "002293", "B0E5ED"],
    "Asus": ["049226", "000C6E", "44D9E7", "F03D29", "001BFC", "AC9E17", "6045CB"],
    "Intelbras": ["001A3F", "E46F13", "1C3BF3", "30B5C1", "F81A67", "60A44C", "485B39", "ACD180"],
    "MikroTik": ["488F5A", "6C3B6B", "CC2DE0", "B869F4", "085531", "2C4D54", "DC2C6E", "000C42"],
    "Ubiquiti": ["0418D6", "24A43C", "68D79A", "788A20", "B4FBE4", "F492BF", "DC9FDB", "802AA8"],
    "Fiberhome": ["7405A5", "84D81B", "10B1F8", "5866BA", "E01954", "00259E", "882856"],
    "Sagemcom": ["0024D4", "E8F1B0", "7CD967", "40F201", "842B2B", "348A7B"],
    "MitraStar": ["00A026", "24767D", "F4C236", "E0B9E5", "7C1C4E"],
    "Nokia / Alcatel": ["001A8C", "34E894", "506184", "882856", "380146"],
    "Tenda": ["C83A35", "502B73", "0495E6", "CC2D21", "D83214"],
    "Mercusys": ["D84732", "54AF97", "84D81B", "38A78E"],
    "Cisco / Linksys": ["0014BF", "001839", "00259C", "687F74", "C0830A", "203706", "000625"],
    "Netgear": ["00146C", "001E2A", "204E7F", "841B5E", "A00460", "9C3DCF"],
    "DrayTek": ["00507F", "001D0F"],
    "Datacom": ["000456", "0024B1"],
    "Multilaser": ["0016E8", "A09353"],
}


def fabricante(mac: str | None) -> str:
    """Tenta identificar o fabricante do roteador pelo OUI do MAC."""
    if not mac:
        return "—"
    oui = util.normalizar_mac(mac)
    for nome, prefixos in _OUIS.items():
        if oui in prefixos:
            return nome
    return "desconhecido (veja o adesivo do roteador)"


def http_acessivel(gateway: str | None, timeout: float = 4.0) -> bool | None:
    """O painel web do roteador responde em http://gateway/? None = falhou."""
    if not gateway:
        return None
    try:
        with urllib.request.urlopen(f"http://{gateway}/", timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return None


# --- SNMP (melhor esforço, sem dependências) ----------------------------------

def _len_ber(n: int) -> bytes:
    if n < 128:
        return bytes([n])
    out = bytearray()
    while n:
        out.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(out)]) + bytes(out)


def _seq(*partes: bytes) -> bytes:
    corpo = b"".join(partes)
    return b"\x30" + _len_ber(len(corpo)) + corpo


def _int_ber(valor: int) -> bytes:
    corpo = valor.to_bytes(4, "big")
    return b"\x02" + _len_ber(len(corpo)) + corpo


def _octet(s: bytes) -> bytes:
    return b"\x04" + _len_ber(len(s)) + s


def _montar_get(oid: bytes, comunidade: bytes, rid: int) -> bytes:
    varbind = _seq(oid + b"\x05\x00")  # OID + NULL
    varbinds = _seq(varbind)
    pdu = b"\xa0" + _len_ber(len(_int_ber(rid) + _int_ber(0) + _int_ber(0) + varbinds))
    pdu += _int_ber(rid) + _int_ber(0) + _int_ber(0) + varbinds
    return _seq(_int_ber(0) + _octet(comunidade) + pdu)


def _uptime_da_resposta(resposta: bytes) -> float | None:
    """Procura TimeTicks (0x43, centésimos de segundo) na resposta SNMP."""
    i = 0
    while i < len(resposta) - 5:
        if resposta[i] == 0x43 and resposta[i + 1] == 0x04:
            try:
                return int.from_bytes(resposta[i + 2 : i + 6], "big") / 100.0
            except ValueError:
                return None
        i += 1
    return None


def uptime_snmp(gateway: str | None, timeout: float = 3.0) -> float | None:
    """Uptime do roteador (segundos) via SNMPv1 sysUpTime. None se o roteador não responder."""
    if not gateway:
        return None
    # OID sysUpTime.0 = 1.3.6.1.2.1.1.3.0
    oid = bytes([0x2B, 0x06, 0x01, 0x02, 0x01, 0x01, 0x03, 0x00])
    pacote = _montar_get(oid, b"public", 0x7A69)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(pacote, (gateway, 161))
        resposta, _ = sock.recvfrom(65535)
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()
    return _uptime_da_resposta(resposta)


def status_roteador(gateway: str | None, mac: str | None, lease_fim: str | None = None) -> dict:
    """Reúne tudo sobre o roteador em um dicionário para o relatório."""
    uptime = uptime_snmp(gateway)
    return {
        "gateway": gateway or "—",
        "mac": mac or "—",
        "fabricante": fabricante(mac),
        "painel_http": http_acessivel(gateway),
        "uptime_seg": uptime,
        "lease_fim": lease_fim or "—",
    }
