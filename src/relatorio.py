"""Relatório: transforma os resultados crus em nota de saúde, explicações em
linguagem simples e recomendações priorizadas — o 'tradutor' do network-doctor.
"""

from __future__ import annotations

import sys

from . import util

# pesos por categoria (normalizados depois, descartando categorias sem medição)
_PESOS = {
    "latencia": 0.22,
    "perda": 0.18,
    "jitter": 0.10,
    "velocidade": 0.20,
    "wifi": 0.12,
    "dns": 0.08,
    "roteador": 0.10,
}

_CORES = util._COLORS

_NIVEL = {"ok": "green", "atencao": "yellow", "critico": "red"}
_ICONE = {"ok": "✅", "atencao": "⚠️ ", "critico": "❌", "info": "ℹ️ "}
_SEV_ORDEM = {"critico": 0, "atencao": 1, "info": 2}


def _p(texto: str, cor: str | None = None, colorido: bool = True) -> str:
    if not colorido or cor is None:
        return texto
    return f"{_CORES[cor]}{texto}{_CORES['reset']}"


def _banda(valor: float | None, ok: float, atencao: float, s_ok=100, s_ate=60, s_crit=25, invertido=False):
    """Classifica um valor em ok/atenção/crítico e devolve (nota 0-100, nível).

    Por padrão assume "quanto menor, melhor" (ping, perda, jitter, DNS).
    Com invertido=True, "quanto maior, melhor" (velocidade, sinal Wi-Fi).
    """
    if valor is None:
        return None, None
    if not invertido:
        if valor <= ok:
            return s_ok, "ok"
        if valor <= atencao:
            return s_ate, "atencao"
        return s_crit, "critico"
    if valor >= ok:
        return s_ok, "ok"
    if valor >= atencao:
        return s_ate, "atencao"
    return s_crit, "critico"


def avaliar(r: dict) -> dict:
    """Calcula notas, semáforos, achados e recomendações a partir dos resultados."""
    notas: dict[str, tuple[float | None, str | None]] = {}
    achados: list[dict] = []

    # --- latência ------------------------------------------------------------
    lat_gw = (r.get("latencia_gateway") or {}).get("media_ms")
    lat_internet = [t["media_ms"] for t in r.get("latencia_internet", []) if t.get("media_ms")]
    notas_gw = _banda(lat_gw, 10, 30)
    notas_int = _banda(util.media(lat_internet), 60, 130)
    if notas_gw[0] is None and notas_int[0] is None:
        notas["latencia"] = (None, None)
    elif notas_gw[0] is None:
        notas["latencia"] = notas_int
    elif notas_int[0] is None:
        notas["latencia"] = notas_gw
    else:
        notas["latencia"] = ((notas_gw[0] + notas_int[0]) / 2, max(notas_gw[1], notas_int[1], key=lambda n: {"ok": 0, "atencao": 1, "critico": 2}[n]))

    if notas_gw[0] is not None and notas_gw[1] != "ok":
        achados.append(_achado_gateway(lat_gw, notas_gw[1]))
    if notas_int[0] is not None and notas_int[1] != "ok":
        achados.append(_achado_internet(util.media(lat_internet), notas_int[1]))

    # --- perda de pacotes -----------------------------------------------------
    perdas = []
    if r.get("latencia_gateway"):
        perdas.append(r["latencia_gateway"]["perda"])
    perdas += [t["perda"] for t in r.get("latencia_internet", [])]
    perda_max = max(perdas) if perdas else None
    notas["perda"] = _banda(perda_max, 1, 5)
    if notas["perda"][1] and notas["perda"][1] != "ok":
        achados.append(_achado_perda(perda_max, notas["perda"][1]))

    # --- jitter ---------------------------------------------------------------
    jitters = []
    if r.get("latencia_gateway") and r["latencia_gateway"].get("jitter_ms") is not None:
        jitters.append(r["latencia_gateway"]["jitter_ms"])
    jitters += [t["jitter_ms"] for t in r.get("latencia_internet", []) if t.get("jitter_ms") is not None]
    jitter_max = max(jitters) if jitters else None
    notas["jitter"] = _banda(jitter_max, 10, 25)
    if notas["jitter"][1] and notas["jitter"][1] != "ok":
        achados.append(_achado_jitter(jitter_max, notas["jitter"][1]))

    # --- velocidade ------------------------------------------------------------
    # Só avalia se o teste foi executado (a chave existe) — senão não inventa achado.
    if "velocidade" in r:
        vel = r["velocidade"] or {}
        down, up = vel.get("download_mbps"), vel.get("upload_mbps")
        contratada = r.get("contratada_mbps")
        if down is not None:
            if contratada:
                frac = down / contratada if contratada else None
                if frac is not None:
                    nota_v, nivel_v = _banda(frac, 0.80, 0.40, 100, 60, 25, invertido=True)
                    achados.append(_achado_velocidade(down, up, contratada, nivel_v))
                else:
                    nota_v, nivel_v = 60, "atencao"
            else:
                nota_v, nivel_v = _banda(down, 50, 10, 100, 60, 25, invertido=True)
                achados.append(_achado_velocidade(down, up, None, nivel_v))
            if up is not None:
                nota_u, nivel_u = _banda(up, 10, 2, 100, 60, 25, invertido=True)
                nota_v = 0.7 * nota_v + 0.3 * nota_u
                if nivel_u != "ok":
                    achados.append(_achado_upload(up, nivel_u))
            notas["velocidade"] = (nota_v, nivel_v)
        else:
            notas["velocidade"] = (None, None)
            achados.append(
                {
                    "sev": "info",
                    "titulo": "Teste de velocidade não pôde ser concluído",
                    "explicacao": "Não foi possível baixar o arquivo de teste (sem internet, proxy ou bloqueio).",
                    "recomendacao": "Confira se há internet navegando em um site; se houver, o bloqueio pode ser do provedor.",
                }
            )

    # --- Wi-Fi ---------------------------------------------------------------
    wifi = r.get("wifi")
    if wifi:
        sinal = wifi.get("sinal_pct")
        notas["wifi"] = _banda(sinal, 60, 30, invertido=True)
        if notas["wifi"][1] and notas["wifi"][1] != "ok":
            achados.append(_achado_wifi(sinal, notas["wifi"][1]))
        if notas["wifi"][1] == "ok" and wifi.get("banda", "").startswith("2.4"):
            visiveis = r.get("redes_visiveis")
            if visiveis is not None and visiveis >= 5:
                achados.append(
                    {
                        "sev": "info",
                        "titulo": "Muitas redes Wi-Fi por perto (canal 2,4 GHz congestionado)",
                        "explicacao": f"Seu Wi-Fi está na banda 2,4 GHz e há {visiveis} redes vizinhas — o canal fica disputado e a velocidade cai.",
                        "recomendacao": "No painel do roteador, ative/priorize a banda 5 GHz, que tem menos interferência.",
                    }
                )
    else:
        notas["wifi"] = (None, None)  # conexão por cabo: categoria não se aplica

    # --- DNS -------------------------------------------------------------------
    dns = r.get("dns") or {}
    media_dns = dns.get("media_ms")
    notas["dns"] = _banda(media_dns, 100, 250)
    if notas["dns"][1] and notas["dns"][1] != "ok":
        achados.append(_achado_dns(media_dns, r.get("dns_publico", []), notas["dns"][1]))

    # --- roteador ---------------------------------------------------------------
    roteador = r.get("roteador")
    if roteador:
        uptime = roteador.get("uptime_seg")
        if uptime is not None:
            dias = uptime / 86400
            notas["roteador"] = _banda(dias, 7, 30)
            if notas["roteador"][1] and notas["roteador"][1] != "ok":
                achados.append(_achado_roteador(dias, notas["roteador"][1]))
        else:
            notas["roteador"] = (70, "ok")
            if r.get("config"):
                achados.append(
                    {
                        "sev": "info",
                        "titulo": "Uptime do roteador não pôde ser lido (SNMP desativado)",
                        "explicacao": "Seu roteador não respondeu à consulta de tempo ligado — é comum em modelos de operadora, sem problema.",
                        "recomendacao": "Se a internet estiver lenta, reinicie o roteador mesmo assim: desligue por 30 segundos e ligue de novo.",
                    }
                )

    # --- uso da rede / sobrecarga ------------------------------------------------
    banda_atual = r.get("banda") or []
    uso_total = 0.0
    link_total = 0.0
    for b in banda_atual:
        uso_total += (b.get("download_mbps") or 0) + (b.get("upload_mbps") or 0)
    for a in r.get("adaptadores", []):
        if a.get("link_mbps"):
            link_total += a["link_mbps"]
    if link_total > 0:
        frac_uso = uso_total / link_total
        if frac_uso > 0.8:
            achados.append(
                {
                    "sev": "atencao",
                    "titulo": "Rede em uso intenso agora (sobrecarga)",
                    "explicacao": f"Seu adaptador está usando {frac_uso * 100:.0f}% da capacidade do link neste momento — downloads, jogos ou sincronizações em segundo plano consomem quase tudo.",
                    "recomendacao": "Feche programas que baixam em segundo plano (launchers, nuvem, atualizações) para liberar banda.",
                }
            )
        elif frac_uso > 0.5:
            achados.append(
                {
                    "sev": "info",
                    "titulo": "Uso de rede moderado",
                    "explicacao": f"O adaptador está usando cerca de {frac_uso * 100:.0f}% da capacidade do link.",
                    "recomendacao": "Nada a fazer por enquanto; se travar, veja os processos com mais conexões abaixo.",
                }
            )

    top = r.get("top_processos") or []
    if top and top[0]["conexoes"] >= 50:
        p = top[0]
        achados.append(
            {
                "sev": "atencao",
                "titulo": f"'{p['nome']}' está segurando muitas conexões ({p['conexoes']})",
                "explicacao": "Um único programa com dezenas de conexões abertas pode estar baixando/atualizando em segundo plano e pesando na rede.",
                "recomendacao": f"Abra o Gerenciador de Tarefas, encontre '{p['nome']}' (PID {p['pid']}) e feche-o se não estiver em uso.",
            }
        )

    conns = r.get("conexoes") or {}
    if conns.get("total", 0) > 400:
        achados.append(
            {
                "sev": "info",
                "titulo": "Muitas conexões abertas no PC",
                "explicacao": f"Há {conns['total']} conexões de rede abertas neste momento — normal em PCs usados há dias sem reiniciar.",
                "recomendacao": "Reiniciar o PC limpa as conexões antigas e libera recursos de rede.",
            }
        )

    # --- instabilidade regional (pathping) ----------------------------------------
    perda_rota = r.get("perda_rota")
    if perda_rota:
        salto = next((s for s in perda_rota if s["perda"] >= 20), None)
        if salto:
            achados.append(
                {
                    "sev": "atencao",
                    "titulo": f"Instabilidade começa no salto {salto['num']} da rota (IP {salto['ip']})",
                    "explicacao": "A perda de pacotes aparece a partir de um ponto da rota que provavelmente é da sua operadora — o problema é regional/provedor, não do seu Wi-Fi ou roteador.",
                    "recomendacao": "Guarde este relatório e entre em contato com a operadora citando a perda no salto. Se o primeiro salto (seu roteador) já tiver perda, reinicie o roteador antes.",
                }
            )

    # --- bufferbloat (latência sob carga) -----------------------------------------
    if "velocidade" in r and r.get("velocidade") and r["velocidade"].get("bufferbloat"):
        bb = r["velocidade"]["bufferbloat"]
        if bb.get("delta_ms", 0) > 40:
            achados.append(_achado_bufferbloat(bb))

    # --- MTU e fragmentação -------------------------------------------------------
    mtu = r.get("mtu")
    if mtu and mtu.get("fragmenta_em_1500") and mtu.get("mtu_maximo", 1500) < 1492:
        achados.append(_achado_mtu(mtu["mtu_maximo"]))

    # --- pistas extras ------------------------------------------------------------
    sistema = r.get("sistema") or {}
    if sistema.get("uptime_seg") and sistema["uptime_seg"] > 7 * 86400:
        achados.append(
            {
                "sev": "info",
                "titulo": "PC ligado há muito tempo",
                "explicacao": f"Seu PC está ligado há {util.fmt_duration(sistema['uptime_seg'])} sem reiniciar.",
                "recomendacao": "Uma reinicialização resolve lentidão e conexões 'vazadas' que se acumulam com o tempo.",
            }
        )

    if roteador and roteador.get("painel_http") is False and roteador.get("gateway"):
        achados.append(
            {
                "sev": "info",
                "titulo": "Painel do roteador não respondeu",
                "explicacao": "O roteador não abriu a página de configuração em http://" + roteador["gateway"] + "/ durante o teste.",
                "recomendacao": "Tente abrir http://" + roteador["gateway"] + "/ no navegador; se não abrir, o roteador pode estar com problemas.",
            }
        )

    # --- nota geral ----------------------------------------------------------------
    nota_geral = _nota_geral(notas)
    return {
        "nota": nota_geral,
        "notas": notas,
        "achados": sorted(achados, key=lambda a: _SEV_ORDEM.get(a["sev"], 3)),
        "nivel_geral": _nivel_geral(nota_geral),
    }


def _nota_geral(notas: dict) -> float | None:
    """Média ponderada das categorias medidas (as não medidas ficam de fora)."""
    soma_peso = 0.0
    soma_nota = 0.0
    for categoria, (nota, _) in notas.items():
        if nota is None:
            continue
        soma_peso += _PESOS[categoria]
        soma_nota += nota * _PESOS[categoria]
    if soma_peso <= 0:
        return None
    return round(soma_nota / soma_peso)


def _nivel_geral(nota: float | None) -> str:
    if nota is None:
        return "sem dados"
    if nota >= 80:
        return "excelente"
    if nota >= 60:
        return "boa"
    if nota >= 40:
        return "regular"
    return "crítica"


# --- construtores de achados (linguagem simples) ----------------------------------

def _achado_gateway(media, nivel):
    return {
        "sev": nivel,
        "titulo": f"Ping alto até o roteador ({media:.0f} ms)",
        "explicacao": "O 'ping' é o tempo que um dado leva para ir do seu PC até o roteador e voltar. Acima de 10 ms indica problema local: Wi-Fi fraco, interferência ou roteador sobrecarregado.",
        "recomendacao": "Aproxime-se do roteador ou conecte por cabo. Se continuar alto, reinicie o roteador (desligue 30 segundos).",
    }


def _achado_internet(media, nivel):
    return {
        "sev": nivel,
        "titulo": f"Ping alto para a internet ({media:.0f} ms)",
        "explicacao": "O atraso até servidores na internet acima de 60 ms torna jogos e chamadas de vídeo lentos. Pode ser a distância até o servidor, Wi-Fi ruim ou problema do provedor.",
        "recomendacao": "Teste com cabo de rede para separar Wi-Fi de internet. Se continuar alto, é com a operadora.",
    }


def _achado_perda(perda, nivel):
    return {
        "sev": nivel,
        "titulo": f"Perda de pacotes de {perda:.0f}%",
        "explicacao": "Parte dos dados enviados não chega ao destino — causa cortes em chamadas, travamentos e lentidão geral. Acima de 1% já é perceptível.",
        "recomendacao": "Reinicie roteador e modem. Se o Wi-Fi estiver fraco, use cabo. Se a perda continuar, o problema pode ser da operadora.",
    }


def _achado_jitter(jitter, nivel):
    return {
        "sev": nivel,
        "titulo": f"Conexão instável (jitter de {jitter:.0f} ms)",
        "explicacao": "O 'jitter' mede o quanto o atraso varia entre uma resposta e outra. Quanto maior, mais instável — causa travamentos em videoconferência e jogos mesmo com ping médio bom.",
        "recomendacao": "Mesma receita do ping alto: cabo de rede, reiniciar roteador e, se persistir, acionar a operadora.",
    }


def _achado_velocidade(down, up, contratada, nivel):
    if contratada:
        frac = down / contratada * 100
        texto = f"Sua velocidade de download ({down:.0f} Mbps) está em {frac:.0f}% dos {contratada:.0f} Mbps contratados."
        rec = "Teste com cabo de rede direto no modem. Se continuar baixa, ligue para a operadora com este relatório em mãos."
    else:
        texto = f"Sua velocidade de download é de {down:.0f} Mbps."
        rec = "Para referência: baixar um filme em HD (4 GB) levaria cerca de " + util.tempo_download(down, 4096) + ". Se estiver abaixo do esperado, teste com cabo e reinicie o modem."
    return {
        "sev": nivel,
        "titulo": f"Velocidade de download: {down:.0f} Mbps",
        "explicacao": texto,
        "recomendacao": rec,
    }


def _achado_upload(up, nivel):
    return {
        "sev": nivel,
        "titulo": f"Upload lento ({up:.0f} Mbps)",
        "explicacao": "O upload é a velocidade de envio — usada em chamadas de vídeo, envio de arquivos e jogos online. Abaixo de 2 Mbps fica difícil usar essas funções.",
        "recomendacao": "Verifique se algo não está enviando dados em segundo plano (nuvem, backup). Se o upload for sempre baixo, é limitação do plano/operadora.",
    }


def _achado_wifi(sinal, nivel):
    return {
        "sev": nivel,
        "titulo": f"Sinal Wi-Fi fraco ({sinal:.0f}%)",
        "explicacao": "O sinal Wi-Fi abaixo de 60% significa que o PC está longe do roteador ou com obstáculos (paredes, móveis) no caminho. Sinal fraco = ping alto, perda e velocidade baixa.",
        "recomendacao": "Aproxime-se do roteador, evite aparelhos entre você e ele, ou use cabo de rede para atividades que exigem estabilidade.",
    }


def _achado_dns(media, dns_publico, nivel):
    melhor_publico = None
    for d in dns_publico:
        if d.get("media_ms") and (melhor_publico is None or d["media_ms"] < melhor_publico[1]):
            melhor_publico = (d["nome"], d["media_ms"])
    if melhor_publico and melhor_publico[1] < media * 0.6:
        rec = f"Seu DNS atual resolve em ~{media:.0f} ms, enquanto o DNS {melhor_publico[0]} respondeu em ~{melhor_publico[1]:.0f} ms. Troque o DNS do Windows para {melhor_publico[0]} (1.1.1.1 ou 8.8.8.8) — pesquisa rápida na web mostra o passo a passo para o seu roteador."
    else:
        rec = "Tente trocar o DNS do Windows para um público (1.1.1.1 ou 8.8.8.8) e veja se melhora."
    return {
        "sev": nivel,
        "titulo": f"Resolução de nomes (DNS) lenta: {media:.0f} ms",
        "explicacao": "O DNS traduz endereços como 'google.com' para números. Quando ele demora, a navegação 'engasga' mesmo com internet rápida — o navegador fica esperando o nome ser resolvido.",
        "recomendacao": rec,
    }


def _achado_roteador(dias, nivel):
    return {
        "sev": nivel,
        "titulo": f"Roteador ligado há {dias:.0f} dia{'s' if dias >= 2 else ''} sem reiniciar",
        "explicacao": "Roteadores acumulam falhas com o tempo: a memória interna enche, a tabela de conexões (NAT) estoura e a velocidade cai aos poucos. É a causa clássica de 'internet lenta de um dia para o outro'.",
        "recomendacao": "Desligue o roteador, espere 30 segundos e ligue de novo. Faça isso a cada 1-2 semanas para evitar o problema.",
    }


def _achado_bufferbloat(bb: dict):
    delta = bb.get("delta_ms", 0)
    sev = "critico" if delta > 100 else "atencao"
    return {
        "sev": sev,
        "titulo": f"Bufferbloat detectado (latência sobe +{delta:.0f} ms sob carga)",
        "explicacao": f"Quando a rede está em uso (downloads/uploads), o ping sobe de {bb['ping_repouso_ms']:.0f} ms para {bb['ping_carregado_ms']:.0f} ms. A fila do roteador incha e causa atrasos em jogos e travamentos em chamadas de vídeo quando alguém usa a internet.",
        "recomendacao": "Se o seu roteador tiver QoS (Quality of Service) ou SQM, ative-o. Caso contrário, evite downloads grandes durante videoconferências ou jogos.",
    }


def _achado_mtu(mtu_max: int):
    return {
        "sev": "info",
        "titulo": f"MTU de rede reduzido ({mtu_max} bytes)",
        "explicacao": f"Sua conexão fragmenta pacotes no tamanho padrão (1500 bytes), suportando até {mtu_max} bytes. Isso é comum em conexões PPPoE/fibra com cabeçalhos adicionais.",
        "recomendacao": "Geralmente ajustado automaticamente pelo roteador (MSS Clamping). Se encontrar sites que demoram para abrir, verifique a configuração de MTU no modem/roteador.",
    }


# --- formatação do relatório ---------------------------------------------------

def formatar(resultados: dict, avaliacao: dict, colorido: bool | None = None) -> str:
    """Monta o texto final do relatório (com ou sem cores ANSI).

    Só renderiza seções que foram realmente medidas — modos individuais
    (ex.: --rota, --uso) não mostram blocos vazios.
    """
    if colorido is None:
        colorido = sys.stdout.isatty()
    L: list[str] = []
    a = L.append

    a(_p("═" * 58, "cyan", colorido))
    a(_p("  🩺 NETWORK DOCTOR — Diagnóstico da sua rede", "bold", colorido))
    a(_p("═" * 58, "cyan", colorido))
    a(f"  Data: {util.agora()}")

    # --- SISTEMA ---------------------------------------------------------------
    sistema = resultados.get("sistema") or {}
    if sistema or resultados.get("adaptadores"):
        a("")
        a(_p("▶ SISTEMA", "bold", colorido))
        if sistema:
            a(f"  • Windows: {sistema.get('so', '—')} {sistema.get('versao', '')}".rstrip())
            a(f"  • PC ligado há: {util.fmt_duration(sistema.get('uptime_seg'))}")
            if sistema.get("memoria_total_gb"):
                a(f"  • Memória: {sistema['memoria_livre_gb']:.1f} GB livres de {sistema['memoria_total_gb']:.1f} GB")

    # --- CONEXÃO ATUAL ----------------------------------------------------------
    cfg = resultados.get("config")
    if cfg:
        a("")
        a(_p("▶ CONEXÃO ATUAL", "bold", colorido))
        a(f"  • Adaptador: {cfg['adaptador']}")
        a(f"  • IP local: {cfg['ipv4']}  ·  Máscara: {cfg['mascara']}")
        if cfg.get("ipv6") and cfg["ipv6"] != "—":
            a(f"  • IPv6: {cfg['ipv6']}")
        a(f"  • Gateway (roteador): {cfg['gateway']}  ·  MAC: {cfg.get('mac', '—')}")
        a(f"  • DHCP: {cfg['dhcp']}  ·  DNS: {', '.join(cfg['dns']) or '—'}")
        if cfg.get("lease_fim") and cfg["lease_fim"] != "—":
            a(f"  • Concessão DHCP obtida: {cfg.get('lease_inicio', '—')}  ·  expira: {cfg['lease_fim']}")
        for ad in resultados.get("adaptadores", []):
            a(f"  • Link {ad['nome']}: {util.fmt_bits(ad.get('link_mbps'))}  ({ad['tipo']})")

        # Provedor e IP público (quando disponíveis via metadados)
        prov = (resultados.get("velocidade") or {}).get("provedor")
        if prov:
            if prov.get("isp") and prov["isp"] != "—":
                a(f"  • Provedor (ISP): {prov['isp']}  ·  ASN: {prov.get('as', '—')}")
                local_partes = [p for p in (prov.get("cidade"), prov.get("regiao"), prov.get("pais")) if p and p != "—"]
                local_str = f"  ·  Região: {', '.join(local_partes)}" if local_partes else ""
                a(f"  • IP público: {prov['ip_publico']}{local_str}")
            elif prov.get("ip_publico") and prov["ip_publico"] != "—":
                a(f"  • IP público: {prov['ip_publico']}")

        # MTU detectado
        mtu_info = resultados.get("mtu")
        if mtu_info:
            padrao_txt = "1500 bytes (padrão Ethernet, sem fragmentação)" if mtu_info.get("padrao_1500") else f"{mtu_info.get('mtu_maximo')} bytes (fragmenta em 1500, típico de PPPoE)"
            a(f"  • MTU de rede: {padrao_txt}")

    # --- WI-FI ------------------------------------------------------------------
    if "wifi" in resultados:
        a("")
        a(_p("▶ WI-FI", "bold", colorido))
        wifi = resultados["wifi"]
        if wifi:
            sinal = wifi.get("sinal_pct")
            cor_sinal = _NIVEL.get(_banda(sinal, 60, 30, invertido=True)[1] or "ok", "green")
            sinal_txt = f"{sinal:.0f}%" if sinal is not None else "—"
            a(f"  • Rede: {wifi['ssid']}  ·  Sinal: {_p(sinal_txt, cor_sinal, colorido)}")
            a(f"  • Banda: {wifi['banda']}  ·  Canal: {wifi['canal']}  ·  Autenticação: {wifi['autenticacao']}")
            a(f"  • Taxa do link: {util.fmt_bits(wifi.get('rx_mbps'))} recebendo / {util.fmt_bits(wifi.get('tx_mbps'))} enviando")
            visiveis = resultados.get("redes_visiveis")
            if visiveis is not None:
                a(f"  • Redes Wi-Fi visíveis por perto: {visiveis}")
        else:
            a("  • Conexão por cabo (sem interface Wi-Fi ativa) — Wi-Fi não se aplica.")

    # --- LATÊNCIA ----------------------------------------------------------------
    if resultados.get("latencia_gateway") or resultados.get("latencia_internet"):
        a("")
        a(_p("▶ LATÊNCIA (PING)", "bold", colorido))
        _linha_latencia(a, "Roteador (gateway)", resultados.get("latencia_gateway"), colorido)
        for t in resultados.get("latencia_internet", []):
            _linha_latencia(a, t.get("nome", t.get("alvo", "?")), t, colorido)

    # --- ROTA --------------------------------------------------------------------
    if "rota" in resultados:
        a("")
        a(_p("▶ ROTA", "bold", colorido))
        rota = resultados.get("rota") or []
        if rota:
            a(f"  • {len(rota)} saltos até {resultados.get('alvo_rota', '8.8.8.8')}:")
            for s in rota:
                rtt = util.media(s["rtts"])
                a(f"    {s['num']:>2}  {s['ip']:<16}  {f'{rtt:.0f} ms' if rtt is not None else 'sem resposta'}")
            salto_ruim = next((s for s in rota if s.get("salto_ruim")), None)
            if salto_ruim:
                a(_p(f"  ⚠️  Salto {salto_ruim['num']} ({salto_ruim['ip']}) com salto brusco de latência — possível gargalo na rota", "yellow", colorido))
        else:
            a("  • Não foi possível rastrear a rota.")
        perda_rota = resultados.get("perda_rota")
        if perda_rota:
            saltos_com_perda = [s for s in perda_rota if s["perda"] > 0]
            if saltos_com_perda:
                a("  • Perda por salto (pathping): " + ", ".join(f"salto {s['num']}={s['perda']:.0f}%" for s in saltos_com_perda[:5]))
            else:
                a("  • Pathping: nenhuma perda significativa nos saltos.")

    # --- VELOCIDADE ---------------------------------------------------------------
    if "velocidade" in resultados:
        a("")
        a(_p("▶ VELOCIDADE & BUFFERBLOAT", "bold", colorido))
        vel = resultados.get("velocidade") or {}
        down_v, up_v = vel.get("download_mbps"), vel.get("upload_mbps")
        if down_v is not None:
            cor_d = _NIVEL.get(avaliacao["notas"].get("velocidade", (None, "ok"))[1] or "ok", "green")
            down_txt = _p(f"{down_v:.0f} Mbps", cor_d, colorido)
            up_txt = f"{up_v:.0f} Mbps" if up_v is not None else "—"
            a(f"  • Download: {down_txt}  ·  Upload: {up_txt}  (fonte: {vel.get('origem', '?')})")
            a(f"  • Um filme em HD (4 GB) baixaria em ~{util.tempo_download(down_v, 4096)} a essa velocidade")

            bb = vel.get("bufferbloat")
            if bb:
                cor_bb = "green" if bb.get("grau") in ("A+", "A") else ("yellow" if bb.get("grau") == "B" else "red")
                bb_txt = _p(f"+{bb.get('delta_ms', 0):.0f} ms (Grau {bb.get('grau', '—')})", cor_bb, colorido)
                a(f"  • Bufferbloat: {bb_txt} — {bb.get('ping_repouso_ms', 0):.0f} ms repouso → {bb.get('ping_carregado_ms', 0):.0f} ms sob carga ({bb.get('classificacao', '')})")
        else:
            a("  • Teste de velocidade falhou (sem internet ou bloqueio).")

    # --- DNS ----------------------------------------------------------------------
    if "dns" in resultados:
        a("")
        a(_p("▶ DNS", "bold", colorido))
        dns = resultados.get("dns") or {}
        a(f"  • Resolução média (DNS atual): {dns.get('media_ms', 0):.0f} ms"
          + (f"  ·  servidores: {', '.join(dns.get('servidores_configurados', [])) or '—'}" if dns.get("servidores_configurados") else ""))
        for d in resultados.get("dns_publico", []):
            a(f"  • DNS público {d['nome']} ({d['ip']}): {d.get('media_ms', 0):.0f} ms")

    # --- ROTEADOR ------------------------------------------------------------------
    if "roteador" in resultados:
        a("")
        a(_p("▶ ROTEADOR", "bold", colorido))
        rot = resultados.get("roteador") or {}
        a(f"  • Fabricante identificado: {rot.get('fabricante', '—')}  ·  Painel web: {'acessível' if rot.get('painel_http') else ('não respondeu' if rot.get('painel_http') is False else 'não testado')}")
        if rot.get("uptime_seg"):
            a(f"  • Tempo ligado (via SNMP): {util.fmt_duration(rot['uptime_seg'])}")
        else:
            a("  • Tempo ligado: não disponível (SNMP desativado no roteador)")

    # --- USO DA REDE -----------------------------------------------------------------
    if "banda" in resultados or "conexoes" in resultados:
        a("")
        a(_p("▶ USO DA REDE AGORA", "bold", colorido))
        for b in resultados.get("banda", []):
            a(f"  • {b['nome']}: {b.get('download_mbps', 0):.1f} Mbps ↓ / {b.get('upload_mbps', 0):.1f} Mbps ↑")
        conns = resultados.get("conexoes") or {}
        a(f"  • Conexões abertas: {conns.get('total', 0)} ({conns.get('estabelecidas', 0)} ativas, {conns.get('time_wait', 0)} em espera)")
        for p in resultados.get("top_processos", [])[:4]:
            a(f"  • {p['nome']} (PID {p['pid']}): {p['conexoes']} conexões")

    # --- nota + achados --------------------------------------------------------------
    nota = avaliacao.get("nota")
    achados = avaliacao.get("achados") or []
    if nota is not None or achados:
        a("")
        a(_p("─" * 58, "cyan", colorido))
        if nota is not None:
            nivel = avaliacao.get("nivel_geral", "sem dados")
            cor_nota = _NIVEL.get(_nivel_nota(nota), "green")
            a(_p("  NOTA DE SAÚDE DA CONEXÃO: ", "bold", colorido) + _p(f"{nota}/100", cor_nota, colorido) + _p(f" — {nivel.upper()}", "bold", colorido))
        a(_p("─" * 58, "cyan", colorido))
        if nota is not None and not achados:
            a(_p("  ✅ Nenhum problema significativo encontrado. Sua rede está saudável!", "green", colorido))

    for i, ach in enumerate(achados, 1):
        cor = _NIVEL.get(ach["sev"], "info")
        a("")
        a(_p(f"  {_ICONE.get(ach['sev'], '•')} {i}. {ach['titulo']}", cor, colorido))
        a(f"     {ach['explicacao']}")
        a(_p(f"     → O que fazer: {ach['recomendacao']}", "dim", colorido))

    if nota is None and not achados:
        a("")
        a(_p("Rode o diagnóstico completo (sem argumentos) para ter a nota de saúde geral.", "dim", colorido))

    a("")
    a(_p("LEGENDA — o que significam os termos:", "dim", colorido))
    a(_p("  • Ping: tempo de ida e volta de um dado (menor = melhor).", "dim", colorido))
    a(_p("  • Jitter: o quanto o ping varia (estabilidade).", "dim", colorido))
    a(_p("  • Perda de pacotes: dados que não chegam (cortes/travamentos).", "dim", colorido))
    a(_p("  • DNS: 'agenda telefônica' que converte nomes em endereços.", "dim", colorido))
    a(_p("  • Mbps: megabits por segundo — unidade de velocidade.", "dim", colorido))
    return "\n".join(L)


def _linha_latencia(a, nome, dados, colorido):
    if not dados:
        a(f"  • {nome}: sem resposta")
        return
    media = dados.get("media_ms")
    perda = dados.get("perda")
    if media is None and (perda or 0) >= 100:
        a(_p(f"  • {nome}: sem resposta (100% de perda)", "red", colorido))
        return
    jit = dados.get("jitter_ms")
    cor = _NIVEL.get(_banda(media, 60, 130)[1] or "ok", "green")
    a(f"  • {nome}: {_p(f'{media:.0f} ms', cor, colorido)} (mín {dados.get('min_ms', 0):.0f} · máx {dados.get('max_ms', 0):.0f} · jitter {jit:.0f} ms · perda {perda:.0f}%)")


def _nivel_nota(nota: float) -> str:
    if nota >= 60:
        return "ok"
    if nota >= 40:
        return "atencao"
    return "critico"


def formatar_rapido(resultados: dict, avaliacao: dict, colorido: bool | None = None) -> str:
    """Versão enxuta para o modo --rapido: nota + latência + principais achados."""
    if colorido is None:
        colorido = sys.stdout.isatty()
    L: list[str] = []
    a = L.append

    a(_p("═" * 58, "cyan", colorido))
    a(_p("  ⚡ NETWORK DOCTOR — Teste rápido de estabilidade", "bold", colorido))
    a(_p("═" * 58, "cyan", colorido))
    a(f"  Data: {util.agora()}")

    a("")
    a(_p("▶ LATÊNCIA", "bold", colorido))
    _linha_latencia(a, "Roteador (gateway)", resultados.get("latencia_gateway"), colorido)
    for t in resultados.get("latencia_internet", []):
        _linha_latencia(a, t.get("nome", t.get("alvo", "?")), t, colorido)

    nota = avaliacao.get("nota")
    nivel = avaliacao.get("nivel_geral", "sem dados")
    a("")
    a(_p("─" * 58, "cyan", colorido))
    if nota is not None:
        cor_nota = _NIVEL.get(_nivel_nota(nota), "green")
        a(_p("  NOTA DE SAÚDE DA CONEXÃO: ", "bold", colorido) + _p(f"{nota}/100", cor_nota, colorido) + _p(f" — {nivel.upper()}", "bold", colorido))
    else:
        a("  NOTA DE SAÚDE DA CONEXÃO: sem dados suficientes")
    a(_p("─" * 58, "cyan", colorido))

    achados = avaliacao.get("achados") or []
    if not achados:
        a(_p("  ✅ Nenhum problema significativo encontrado.", "green", colorido))
    for i, ach in enumerate(achados, 1):
        cor = _NIVEL.get(ach["sev"], "info")
        a("")
        a(_p(f"  {_ICONE.get(ach['sev'], '•')} {i}. {ach['titulo']}", cor, colorido))
        a(f"     {ach['explicacao']}")
        a(_p(f"     → O que fazer: {ach['recomendacao']}", "dim", colorido))
    a("")
    a(_p("Dica: rode o diagnóstico completo (sem argumentos) para ver Wi-Fi, velocidade, DNS e roteador.", "dim", colorido))
    return "\n".join(L)
