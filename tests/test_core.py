"""Testes unitários do network-doctor (parsers, formatação e avaliação)."""

from __future__ import annotations

import unittest

from src import relatorio, util
from src.relatorio import _banda
from src.roteador import fabricante

PING_PT = """\
Pingando 192.168.0.1 com 32 bytes de dados:
Resposta de 192.168.0.1: bytes=32 tempo=3ms TTL=64
Resposta de 192.168.0.1: bytes=32 tempo=4ms TTL=64
Resposta de 192.168.0.1: bytes=32 tempo=5ms TTL=64
Resposta de 192.168.0.1: bytes=32 tempo=3ms TTL=64

Estatísticas do Ping para 192.168.0.1:
    Pacotes: Enviados = 4, Recebidos = 4, Perdidos = 0 (0% perda),
"""

PING_EN = """\
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=12ms TTL=117
Reply from 8.8.8.8: bytes=32 time=14ms TTL=117
Request timed out.
Reply from 8.8.8.8: bytes=32 time=13ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),
"""

PING_PERDA_TOTAL_PT = """\
Pingando 10.0.0.1 com 32 bytes de dados:
Esgotado o tempo limite do pedido.
Esgotado o tempo limite do pedido.
Estatísticas do Ping para 10.0.0.1:
    Pacotes: Enviados = 2, Recebidos = 0, Perdidos = 2 (100% perda),
"""

TRACERT_PT = """\
Rastreando a rota para 8.8.8.8 até um máximo de 30 saltos

  1    <1 ms    <1 ms    <1 ms  192.168.0.1
  2     9 ms     *       10 ms  10.255.1.1
  3     *        *        *     Tempo esgotado para este requisito.

Rastreamento concluído.
"""

PATHPT = """\
Rastreando a rota para 8.8.8.8...
  0  192.168.0.10    0/ 100 =   0%   |     0/ 100 =   0%   |    0/ 100 =   0%
  1  192.168.0.1     0/ 100 =   0%   |     0/ 100 =   0%   |    0/ 100 =   0%
  2  10.255.1.1     25/ 100 =  25%   |    25/ 100 =  25%   |    25/ 100 =  25%
  3  8.8.8.8        40/ 100 =  40%   |    40/ 100 =  40%   |    40/ 100 =  40%
"""

NETSH_PT = """\
Nome da interface : Wi-Fi
    SSID                             : MinhaRede
    Modo                             : Infraestrutura
    Sinal                            : 80%
    Tipo de r\u00e1dio                    : 802.11ac
    Canal                            : 36
    Velocidade de recep\u00e7\u00e3o (Mbps)    : 866.7
    Velocidade de transmiss\u00e3o (Mbps) : 866.7
    Banda                            : 5 GHz
    Autentica\u00e7\u00e3o                     : WPA2-Personal
"""

NETSH_EN = """\
    SSID                             : MyNetwork
    Signal                           : 60%
    Radio type                       : 802.11n
    Channel                          : 6
    Receive rate (Mbps)              : 144.4
    Transmit rate (Mbps)             : 144.4
    Band                             : 2.4 GHz
    Authentication                   : WPA2-Personal
"""

NETSH_SEM_WIFI = "N\u00e3o h\u00e1 interfaces sem fio no sistema."
NETSH_EN_SEM_WIFI = "There is no wireless interface on the system."


class TestParsePing(unittest.TestCase):
    def test_ping_pt(self):
        r = util.parse_ping(PING_PT)
        self.assertEqual(r["rtts"], [3.0, 4.0, 5.0, 3.0])
        self.assertEqual(r["perda"], 0.0)

    def test_ping_en(self):
        r = util.parse_ping(PING_EN)
        self.assertEqual(r["rtts"], [12.0, 14.0, 13.0])
        self.assertEqual(r["perda"], 25.0)

    def test_ping_perda_total(self):
        r = util.parse_ping(PING_PERDA_TOTAL_PT)
        self.assertEqual(r["rtts"], [])
        self.assertEqual(r["perda"], 100.0)


class TestJitter(unittest.TestCase):
    def test_jitter(self):
        self.assertAlmostEqual(util.jitter([10.0, 20.0, 20.0]), (10 + 0) / 2)
        self.assertIsNone(util.jitter([10.0]))
        self.assertIsNone(util.jitter([]))


class TestParseRota(unittest.TestCase):
    def test_tracert(self):
        saltos = util.parse_tracert(TRACERT_PT)
        self.assertEqual(len(saltos), 2)  # salto 3 estourou timeout, não tem IP
        self.assertEqual(saltos[0]["num"], 1)
        self.assertEqual(saltos[0]["ip"], "192.168.0.1")
        # '<1 ms' vira 1 ms
        self.assertEqual(saltos[0]["rtts"], [1.0, 1.0, 1.0])
        self.assertEqual(saltos[1]["rtts"], [9.0, 10.0])

    def test_pathping(self):
        saltos = util.parse_pathping(PATHPT)
        self.assertEqual(len(saltos), 4)
        self.assertEqual(saltos[2]["perda"], 25.0)
        self.assertEqual(saltos[2]["ip"], "10.255.1.1")


class TestNetsh(unittest.TestCase):
    def test_pt(self):
        info = util.parse_netsh_wlan(NETSH_PT)
        self.assertEqual(info["ssid"], "MinhaRede")
        self.assertEqual(info["sinal"], "80%")
        self.assertEqual(info["canal"], "36")

    def test_en(self):
        info = util.parse_netsh_wlan(NETSH_EN)
        self.assertEqual(info["ssid"], "MyNetwork")
        self.assertEqual(info["sinal"], "60%")

    def test_sem_wifi(self):
        self.assertIsNone(util.parse_netsh_wlan(NETSH_SEM_WIFI))
        self.assertIsNone(util.parse_netsh_wlan(NETSH_EN_SEM_WIFI))


class TestMac(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(util.normalizar_mac("50-c7-bf-12-34-56"), "50C7BF")
        self.assertEqual(util.normalizar_mac("50:c7:bf:12:34:56"), "50C7BF")

    def test_fabricante(self):
        self.assertEqual(fabricante("50-C7-BF-12-34-56"), "TP-LINK")
        self.assertEqual(fabricante("00-E0-FC-11-22-33"), "Huawei")
        self.assertEqual(fabricante("00-1A-3F-11-22-33"), "Intelbras")
        self.assertEqual(fabricante("48-8F-5A-11-22-33"), "MikroTik")
        self.assertEqual(fabricante("04-18-D6-11-22-33"), "Ubiquiti")
        self.assertEqual(fabricante("74-05-A5-11-22-33"), "Fiberhome")
        self.assertIn("desconhecido", fabricante("AA-BB-CC-11-22-33"))


class TestMTU(unittest.TestCase):
    def test_ping_mtu_ok(self):
        saida = "Resposta de 1.1.1.1: bytes=1472 tempo=12ms TTL=57"
        self.assertTrue(util.parse_ping_mtu(saida))

    def test_ping_mtu_fragmentado(self):
        saida_pt = "Resposta de 192.168.0.1: O pacote precisa ser fragmentado, mas a desfragmentacao esta ativa."
        saida_en = "Packet needs to be fragmented but DF set."
        self.assertFalse(util.parse_ping_mtu(saida_pt))
        self.assertFalse(util.parse_ping_mtu(saida_en))


class TestFormatacao(unittest.TestCase):
    def test_banda(self):
        self.assertEqual(_banda(5, 10, 30), (100, "ok"))
        self.assertEqual(_banda(20, 10, 30), (60, "atencao"))
        self.assertEqual(_banda(50, 10, 30), (25, "critico"))
        self.assertEqual(_banda(None, 10, 30), (None, None))

    def test_duration(self):
        self.assertEqual(util.fmt_duration(86400 * 2 + 3600 * 3), "2 dias, 3 horas")
        self.assertEqual(util.fmt_duration(30), "30 segundos")
        self.assertEqual(util.fmt_duration(0), "0 minutos")

    def test_tempo_download(self):
        # 4096 MB a 100 Mbps = ~5,5 min
        self.assertIn("minuto", util.tempo_download(100, 4096))
        self.assertEqual(util.tempo_download(0, 4096), "—")


def _resultados_saudaveis() -> dict:
    return {
        "sistema": {"uptime_seg": 3600},
        "adaptadores": [{"nome": "Ethernet", "link_mbps": 1000.0, "tipo": "802.3"}],
        "config": {
            "adaptador": "Ethernet",
            "ipv4": "192.168.0.10",
            "ipv6": "2804:14d:5483:8160::1",
            "mascara": "255.255.255.0",
            "gateway": "192.168.0.1",
            "dhcp": "Sim",
            "mac": "AA-BB-CC-DD-EE-FF",
            "lease_inicio": "—",
            "lease_fim": "—",
            "dns": ["192.168.0.1"],
        },
        "mtu": {"mtu_maximo": 1500, "padrao_1500": True, "fragmenta_em_1500": False},
        "wifi": None,
        "latencia_gateway": {"media_ms": 2.0, "min_ms": 1.0, "max_ms": 4.0, "jitter_ms": 1.0, "perda": 0.0},
        "latencia_internet": [
            {"nome": "Google (8.8.8.8)", "media_ms": 22.0, "jitter_ms": 3.0, "perda": 0.0},
            {"nome": "Cloudflare (1.1.1.1)", "media_ms": 18.0, "jitter_ms": 2.0, "perda": 0.0},
        ],
        "velocidade": {
            "download_mbps": 150.0,
            "upload_mbps": 40.0,
            "origem": "Cloudflare",
            "provedor": {"isp": "Fibra Telecom", "as": "AS12345", "ip_publico": "190.1.2.3", "cidade": "São Paulo"},
            "bufferbloat": {"ping_repouso_ms": 15.0, "ping_carregado_ms": 20.0, "delta_ms": 5.0, "grau": "A", "classificacao": "excelente"},
        },
        "dns": {"media_ms": 35.0, "servidores_configurados": ["192.168.0.1"]},
        "dns_publico": [{"nome": "Cloudflare", "ip": "1.1.1.1", "media_ms": 10.0}],
        "roteador": {"gateway": "192.168.0.1", "uptime_seg": 86400 * 2, "painel_http": True, "fabricante": "TP-LINK"},
        "conexoes": {"total": 40, "estabelecidas": 10},
        "top_processos": [{"nome": "chrome", "pid": 1, "conexoes": 5}],
        "banda": [{"nome": "Ethernet", "download_mbps": 1.0, "upload_mbps": 0.5}],
        "rota": [],
    }


class TestAvaliacao(unittest.TestCase):
    def test_saudavel(self):
        av = relatorio.avaliar(_resultados_saudaveis())
        self.assertGreaterEqual(av["nota"], 80)
        criticos = [a for a in av["achados"] if a["sev"] == "critico"]
        self.assertEqual(criticos, [])

    def test_problemas(self):
        r = _resultados_saudaveis()
        r["latencia_gateway"] = {"media_ms": 120.0, "jitter_ms": 60.0, "perda": 10.0}
        r["wifi"] = {"ssid": "X", "sinal_pct": 20.0}
        r["velocidade"] = {"download_mbps": 4.0, "upload_mbps": 0.5, "origem": "Cloudflare"}
        r["roteador"] = {"gateway": "192.168.0.1", "uptime_seg": 86400 * 45, "painel_http": True}
        av = relatorio.avaliar(r)
        self.assertLess(av["nota"], 60)
        texto = " ".join(f"{a['titulo']} {a['explicacao']}" for a in av["achados"])
        self.assertIn("roteador", texto.lower())
        self.assertIn("Wi-Fi", texto)
        self.assertIn("download", texto)

    def test_bufferbloat_e_mtu(self):
        r = _resultados_saudaveis()
        r["velocidade"]["bufferbloat"] = {
            "ping_repouso_ms": 15.0,
            "ping_carregado_ms": 120.0,
            "delta_ms": 105.0,
            "grau": "D",
            "classificacao": "crítica",
        }
        r["mtu"] = {"mtu_maximo": 1400, "padrao_1500": False, "fragmenta_em_1500": True}
        av = relatorio.avaliar(r)
        texto = " ".join(f"{a['titulo']} {a['explicacao']}" for a in av["achados"])
        self.assertIn("Bufferbloat", texto)
        self.assertIn("MTU", texto)

    def test_modo_parcial_nao_inventa_achados(self):
        """Modos que não rodaram (ex.: --rapido) não devem gerar avisos sobre eles."""
        r = _resultados_saudaveis()
        del r["velocidade"]
        del r["roteador"]
        av = relatorio.avaliar(r)
        texto = " ".join(a["titulo"] for a in av["achados"])
        self.assertNotIn("velocidade", texto.lower())
        self.assertNotIn("SNMP", texto)

    def test_contratada(self):
        r = _resultados_saudaveis()
        r["contratada_mbps"] = 400.0
        av = relatorio.avaliar(r)
        texto = " ".join(f"{a['titulo']} {a['explicacao']} {a['recomendacao']}" for a in av["achados"])
        self.assertIn("contratados", texto)


class TestRelatorioTexto(unittest.TestCase):
    def test_formatar_sem_cores(self):
        av = relatorio.avaliar(_resultados_saudaveis())
        texto = relatorio.formatar(_resultados_saudaveis(), av, colorido=False)
        self.assertIn("NOTA DE SAÚDE", texto)
        self.assertIn("Fibra Telecom", texto)
        self.assertIn("IPv6", texto)
        self.assertIn("Bufferbloat", texto)
        self.assertNotIn("\x1b[", texto)

    def test_formatar_rapido(self):
        av = relatorio.avaliar(_resultados_saudaveis())
        texto = relatorio.formatar_rapido(_resultados_saudaveis(), av, colorido=False)
        self.assertIn("TESTE RÁPIDO", texto.upper())


if __name__ == "__main__":
    unittest.main()
