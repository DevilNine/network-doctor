"""Teste de velocidade (download/upload) usando speed.cloudflare.com, sem chave de API.

Fallback de download: arquivo público da OVH. Se tudo falhar, o relatório apenas
informa que o teste não pôde ser feito (rede sem internet, proxy, etc.).
"""

from __future__ import annotations

import http.client
import json
import ssl
import threading
import time
import urllib.request

from . import util

_HOST = "speed.cloudflare.com"
_DOWNLOAD_BYTES = 50_000_000  # limite do endpoint do Cloudflare (acima disso responde 403)
_UPLOAD_BYTES = 12_000_000
_DURACAO = 6.0


def _conexao(host: str) -> http.client.HTTPSConnection:
    ctx = ssl.create_default_context()
    return http.client.HTTPSConnection(host, timeout=12, context=ctx)


def info_provedor() -> dict | None:
    """Identifica provedor (ISP), ASN, cidade e IP público via metadados públicos."""
    # 1ª tentativa: ip-api (traz ISP e ASN formatados)
    try:
        url = "http://ip-api.com/json/?fields=status,country,regionName,city,isp,org,as,query"
        req = urllib.request.Request(url, headers={"User-Agent": "network-doctor/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            dados = json.loads(resp.read().decode("utf-8", errors="replace"))
            if dados.get("status") == "success":
                return {
                    "ip_publico": dados.get("query") or "—",
                    "isp": dados.get("isp") or dados.get("org") or "—",
                    "as": dados.get("as") or "—",
                    "cidade": dados.get("city") or "—",
                    "regiao": dados.get("regionName") or "—",
                    "pais": dados.get("country") or "—",
                }
    except Exception:
        pass

    # 2ª tentativa (fallback): Cloudflare trace
    try:
        req = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": "network-doctor/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            texto = resp.read().decode("utf-8", errors="replace")
            linhas = dict(l.split("=", 1) for l in texto.splitlines() if "=" in l)
            if "ip" in linhas:
                return {
                    "ip_publico": linhas.get("ip", "—"),
                    "isp": "—",
                    "as": "—",
                    "cidade": linhas.get("colo", "—"),
                    "regiao": "—",
                    "pais": linhas.get("loc", "—"),
                }
    except Exception:
        pass

    return None


def _download_mbps(host: str, caminho: str) -> float | None:
    conn = _conexao(host)
    try:
        conn.request("GET", caminho, headers={"User-Agent": "network-doctor/1.0"})
        resp = conn.getresponse()
        if resp.status != 200:
            return None
        inicio = time.perf_counter()
        total = 0
        while time.perf_counter() - inicio < _DURACAO:
            bloco = resp.read(262_144)
            if not bloco:
                break
            total += len(bloco)
        decorrido = time.perf_counter() - inicio
        return util.bytes_para_mbps(total / decorrido) if decorrido > 0 else None
    except OSError:
        return None
    finally:
        conn.close()


def _upload_mbps(host: str, caminho: str) -> float | None:
    conn = _conexao(host)
    payload = b"0" * _UPLOAD_BYTES

    def _corpo():
        yield payload

    try:
        inicio = time.perf_counter()
        conn.request(
            "POST",
            caminho,
            body=_corpo(),
            headers={"Content-Type": "application/octet-stream"},
            encode_chunked=True,
        )
        resp = conn.getresponse()
        if resp.status not in (200, 204):
            return None
        resp.read()
        decorrido = time.perf_counter() - inicio
        return util.bytes_para_mbps(_UPLOAD_BYTES / decorrido) if decorrido > 0 else None
    except OSError:
        return None
    finally:
        conn.close()


def _melhor(fn, vezes: int = 2):
    """Executa a medição N vezes e devolve a melhor (picos de rede descartados)."""
    valores = [fn() for _ in range(vezes)]
    valores = [v for v in valores if v is not None]
    return max(valores) if valores else None


def medir_bufferbloat(alvo: str = "1.1.1.1") -> dict | None:
    """Mede a latência em repouso e compara com a latência sob tráfego de download."""
    # 1. Ping em repouso
    saida_repouso = util.cmd_dos(f"ping -n 4 -w 1000 {alvo}", timeout=8.0)
    p_rep = util.parse_ping(saida_repouso)
    media_repouso = util.media(p_rep.get("rtts", []))
    if media_repouso is None:
        return None

    # 2. Ping sob tráfego ativo de download
    stop_event = threading.Event()

    def _fluxo_download():
        conn = _conexao(_HOST)
        try:
            conn.request("GET", f"/__down?bytes={_DOWNLOAD_BYTES}", headers={"User-Agent": "network-doctor/1.0"})
            resp = conn.getresponse()
            while not stop_event.is_set():
                bloco = resp.read(262_144)
                if not bloco:
                    break
        except Exception:
            pass
        finally:
            conn.close()

    t = threading.Thread(target=_fluxo_download)
    t.daemon = True
    t.start()
    time.sleep(0.4)

    saida_carga = util.cmd_dos(f"ping -n 4 -w 1000 {alvo}", timeout=8.0)
    stop_event.set()
    t.join(timeout=3.0)

    p_car = util.parse_ping(saida_carga)
    media_carga = util.media(p_car.get("rtts", []))
    if media_carga is None:
        return None

    delta = max(0.0, media_carga - media_repouso)
    if delta <= 15:
        grau = "A"
        classificacao = "excelente (quase sem inchaço de buffer)"
    elif delta <= 40:
        grau = "B"
        classificacao = "boa (leve aumento sob carga)"
    elif delta <= 100:
        grau = "C"
        classificacao = "moderada (chamadas/jogos podem oscilar com downloads pesados)"
    else:
        grau = "D"
        classificacao = "crítica (bufferbloat alto: filas do roteador incham e causam lag)"

    return {
        "ping_repouso_ms": media_repouso,
        "ping_carregado_ms": media_carga,
        "delta_ms": delta,
        "grau": grau,
        "classificacao": classificacao,
    }


def teste_completo() -> dict:
    """Download + upload + provedor + bufferbloat. Devolve dicionário para o relatório."""
    provedor = info_provedor()
    download = _melhor(lambda: _download_mbps(_HOST, f"/__down?bytes={_DOWNLOAD_BYTES}"))
    origem = "Cloudflare"
    if download is None:
        download = _melhor(lambda: _download_mbps("proof.ovh.net", "/files/100Mb.dat"))
        origem = "OVH"
    upload = _melhor(lambda: _upload_mbps(_HOST, "/__up"))
    bufferbloat = medir_bufferbloat() if download is not None else None

    return {
        "download_mbps": download,
        "upload_mbps": upload,
        "origem": origem,
        "provedor": provedor,
        "bufferbloat": bufferbloat,
    }
