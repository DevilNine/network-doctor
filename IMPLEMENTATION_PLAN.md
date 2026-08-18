# IMPLEMENTATION_PLAN.md — Estado do trabalho

## Status geral

**Concluído e verificado na máquina real** (Windows 11 Pro pt-BR, Python 3.14).

## Etapas

- [x] Spec (PROMPT.md) e plano
- [x] `util.py` — subprocess (CREATE_NO_WINDOW), decodificação OEM/UTF-16, ANSI, parsers pt-BR/en-US, remoção de código morto (`resolve_host`, `semaforo`) e ajuste de `tempo_download`
- [x] `sistema.py` — SO, uptime, memória, adaptadores (LinkSpeed string), Wi-Fi (netsh)
- [x] `rede.py` — ipconfig/gateway/DHCP/DNS, conexões (netstat), teste de MTU e fragmentação, IPv6
- [x] `latencia.py` — ping gateway + internet, jitter, perda
- [x] `rota.py` — traceroute (com "<1 ms") e pathping com detecção de salto problemático
- [x] `dns.py` — tempo de resolução (sistema vs DNS públicos 1.1.1.1/8.8.8.8/Quad9/OpenDNS)
- [x] `velocidade.py` — download/upload (com status check), descoberta de ISP/ASN/IP público, teste de Bufferbloat (latência sob carga)
- [x] `roteador.py` — gateway MAC, OUI expandido (Intelbras, MikroTik, Ubiquiti, Fiberhome, ZTE, Huawei, Sagemcom, MitraStar, Nokia, Cisco, etc.), HTTP acessível, SNMP sysUpTime, contrato DHCP
- [x] `relatorio.py` — nota 0-100, deduplicação de cores, achados para MTU, Bufferbloat, IPv6 e ISP
- [x] `diagnostico.py` + `main.py` — orquestração e CLI (com import explícito de regex e versão)
- [x] `run.ps1` — launcher PowerShell universal para execução instantânea remota via `irm ... | iex` com auto-bootstrap de Python portátil
- [x] `Iniciar-Diagnostico.cmd` + `README.md` + `.gitignore`
- [x] `tests/` — 23 testes unittest passando
- [x] Verificação real: testes unitários e teste rápido em PowerShell executados com sucesso

## Decisões registradas

- Python 3 stdlib apenas; comandos Windows via subprocess com parsing tolerante a pt-BR/en-US.
- Codificação: saída de cmd.exe decodificada na página OEM (`GetOEMCP()`); PowerShell com BOM UTF-16 / UTF-8 com BOM para compatibilidade com PowerShell 5.1 e 7+.
- Teste de velocidade usa `speed.cloudflare.com` e `ip-api.com` / `1.1.1.1/cdn-cgi/trace` para ISP/ASN sem chaves de API.
- Teste de Bufferbloat mede a latência em repouso vs latência sob fluxo ativo de tráfego, classificando em graus A-F.
- Teste de MTU utiliza ping ICMP com flag DF (Don't Fragment) descobrindo o tamanho real suportado (1500, 1492, 1480, etc.).
- Launcher PowerShell `run.ps1` baixa automaticamente Python oficial embeddable se a máquina de destino não possuir Python no PATH.
