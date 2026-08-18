"""Orquestrador: executa as verificações escolhidas e reúne os resultados brutos."""

from __future__ import annotations

from . import dns, latencia, rede, rota, roteador, sistema, util, velocidade

MODOS = ("sistema", "config", "wifi", "latencia", "rota", "dns", "uso", "roteador", "velocidade")


def _passo(nome: str, fn):
    """Executa uma verificação com feedback de progresso; nunca derruba o programa."""
    util.msg(f"  ⏳ {nome} ...")
    try:
        valor = fn()
    except Exception as e:  # diagnóstico nunca deve quebrar por uma checagem
        util.msg(f"     ⚠️  não foi possível concluir: {e}")
        return None
    util.msg("     ✓")
    return valor


def diagnosticar(
    rapido: bool = False,
    modos: list[str] | None = None,
    contratada: float | None = None,
    alvo_rota: str = "8.8.8.8",
    profundo: bool = False,
) -> dict:
    """Roda as verificações e devolve o dicionário de resultados para o relatório."""
    resultados: dict = {"contratada_mbps": contratada}

    if rapido:
        modos = ["sistema", "config", "latencia"]
        qtd_gw, qtd_int = 8, 4
    else:
        modos = modos or list(MODOS)
        qtd_gw, qtd_int = 10, 6

    if "sistema" in modos:
        resultados["sistema"] = _passo("Sistema (Windows, memória)", sistema.info_sistema)
        resultados["adaptadores"] = _passo("Adaptadores de rede", sistema.adaptadores) or []

    if "config" in modos:
        resultados["config"] = _passo("Configuração da rede (IP, gateway, DNS)", rede.config_local)
        gw = (resultados.get("config") or {}).get("gateway")
        resultados["gateway_mac"] = _passo(
            "MAC do roteador (tabela ARP)", lambda: rede.mac_do_gateway(gw)
        )
        resultados["mtu"] = _passo("Teste de MTU e fragmentação de pacotes", rede.teste_mtu)

    if "wifi" in modos:
        resultados["wifi"] = _passo("Sinal Wi-Fi", sistema.wifi)
        resultados["redes_visiveis"] = _passo("Redes Wi-Fi vizinhas", sistema.redes_visiveis)

    if "latencia" in modos:
        gw = (resultados.get("config") or {}).get("gateway")
        resultados["latencia_gateway"] = _passo(
            f"Ping no roteador ({qtd_gw} pacotes)", lambda: latencia.ping_gateway(gw, qtd_gw)
        )
        resultados["latencia_internet"] = _passo(
            "Ping na internet (Google, Cloudflare, Brasil)", lambda: latencia.ping_internet(qtd_int)
        ) or []

    if "rota" in modos:
        resultados["alvo_rota"] = alvo_rota
        resultados["rota"] = _passo(
            f"Rota até {alvo_rota} (traceroute)", lambda: rota.traceroute(alvo_rota)
        ) or []
        if profundo:
            resultados["perda_rota"] = _passo(
                "Perda por salto (pathping, pode levar ~2 min)", lambda: rota.pathping(alvo_rota)
            ) or []

    if "dns" in modos:
        dns_configurados = (resultados.get("config") or {}).get("dns")
        resultados["dns"] = _passo(
            "Tempo de resolução DNS", lambda: dns.resolucao_sistema(dns_configurados)
        )
        resultados["dns_publico"] = _passo(
            "Comparação com DNS públicos (1.1.1.1, 8.8.8.8, Quad9)", dns.comparacao_dns_publico
        ) or []

    if "uso" in modos:
        resultados["banda"] = _passo(
            "Uso de banda agora (3 s de medição)", rede.banda_interface
        ) or []
        resultados["conexoes"] = _passo("Conexões abertas (netstat)", rede.conexoes)
        resultados["top_processos"] = _passo(
            "Processos com mais conexões", rede.top_conexoes
        ) or []

    if "roteador" in modos:
        gw = (resultados.get("config") or {}).get("gateway")
        lease = (resultados.get("config") or {}).get("lease_fim")
        resultados["roteador"] = _passo(
            "Status do roteador (fabricante, SNMP, painel web)",
            lambda: roteador.status_roteador(gw, resultados.get("gateway_mac"), lease),
        )

    if "velocidade" in modos:
        resultados["velocidade"] = _passo(
            "Teste de velocidade (download/upload, ~15 s)", velocidade.teste_completo
        )

    return resultados
