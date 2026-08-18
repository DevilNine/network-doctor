# 🩺 Network Doctor

Diagnóstico de rede em linha de comando para Windows, que **traduz termos técnicos em
linguagem simples** e entrega uma **nota de saúde (0–100)** com recomendações práticas
— feito para qualquer pessoa, não só para quem entende de rede.

Ele olha sua conexão de ponta a ponta: sinal Wi-Fi, ping, perda de pacotes, instabilidade
(jitter), velocidade de download/upload, DNS, uso de banda por programa, rota até a internet
e até o **tempo que o roteador está ligado sem reiniciar** (quando o modelo permite).

## Requisitos

- Windows 10 ou 11
- Python 3.10+ (sem nenhuma dependência extra — só a biblioteca padrão)
- Não precisa de administrador

## Como usar

### ⚡ Execução instantânea via PowerShell (sem precisar clonar ou instalar nada)

Abra o **PowerShell** e cole o comando único:

```powershell
irm https://raw.githubusercontent.com/DevilNine/network-doctor/main/run.ps1 | iex
```

> **Nota:** Caso a máquina não tenha Python instalado, o script baixa automaticamente um ambiente Python portátil e isolado no diretório temporário, sem exigir permissões de administrador.

### 🖱️ No Windows Explorer

Dê dois cliques em **`Iniciar-Diagnostico.cmd`** e aguarde o relatório.

### 💻 No terminal local

```bat
python main.py                 :: diagnóstico completo (~1-2 min)
python main.py --rapido        :: teste rápido de estabilidade (~20 s)
python main.py --contratada 300:: compara a velocidade com os 300 Mbps contratados
python main.py --salvar        :: salva o relatório em relatorio-rede.txt
```

### Modos individuais

| Comando | O que faz |
|---|---|
| `python main.py --rapido` | Só ping, perda, estabilidade e MTU — mais rápido |
| `python main.py --latencia` | Ping no roteador e na internet, com jitter e perda |
| `python main.py --wifi` | Sinal, banda, canal e redes vizinhas |
| `python main.py --dns` | Tempo de resolução de nomes (sistema × DNS públicos) |
| `python main.py --velocidade` | Teste de download, upload e Bufferbloat (latência sob carga) |
| `python main.py --uso` | Banda em uso agora e processos com mais conexões |
| `python main.py --roteador` | Fabricante, painel web e uptime do roteador |
| `python main.py --rota [alvo]` | Rota até um destino, salto a salto |
| `python main.py --rota --profundo` | Rota + perda de pacotes por salto (pathping, ~2 min) |
| `python main.py --json` | Resultados crus em JSON (para scripts) |
| `python main.py --salvar [arquivo]` | Grava o relatório em um arquivo de texto |

## O que ele diagnostica (e por quê)

- **Ping (latência)** — tempo de ida e volta de um dado. Alto = demora para "responder".
- **Jitter** — o quanto o ping varia. Alto = chamadas de vídeo e jogos travando.
- **Perda de pacotes** — dados que se perdem no caminho. Causa cortes e lentidão.
- **Bufferbloat (Latência sob Carga)** — o quanto o ping aumenta enquanto a rede faz downloads/uploads. Inchaço de fila no roteador que causa lag severo quando outros usam a internet.
- **MTU e Fragmentação** — detecta o tamanho máximo de pacote sem fragmentação (1500 padrão, 1492/1480 PPPoE/túneis) para evitar gargalos silenciosos.
- **Provedor (ISP), ASN e IP público** — identifica automaticamente a operadora, ASN e geolocalização da conexão.
- **Sinal Wi-Fi** — sinal fraco = ping alto, perda e velocidade baixa.
- **Velocidade** — download e upload medidos na prática, com estimativa de quanto tempo leva para baixar um filme (para "sentir" o número).
- **DNS** — o "catálogo de nomes" da internet. Lento = navegação engasgada.
- **Rota (traceroute/pathping)** — mostra onde na rota começa um problema. Se a perda aparece só depois de um salto da operadora, o problema é **regional/provedor**, não seu Wi-Fi ou roteador.
- **Roteador** — fabricante (base expandida: TP-Link, Intelbras, MikroTik, Ubiquiti, Huawei, ZTE, Fiberhome, Sagemcom, MitraStar, Nokia, Cisco, etc.), painel web acessível e **uptime via SNMP** (melhor esforço).
- **Uso de banda** — o que está consumindo a rede agora e quantas conexões cada programa tem.
- **Sobrecarga** — se o adaptador está perto de 100% da capacidade do link.

## Como ler o relatório

Cada seção tem um semáforo: ✅ verde (bom), ⚠️ amarelo (atenção), ❌ vermelho (crítico).
No final você recebe a **Nota de Saúde da Conexão** e uma lista de **recomendações
priorizadas**, cada uma explicando em linguagem simples *o que está acontecendo* e
*o que fazer* — ex.: "Seu roteador está ligado há 45 dias sem reiniciar. Desligue,
espere 30 segundos e ligue de novo."

## Limitações (honestidade em primeiro lugar)

- **Uptime do roteador:** a leitura via SNMP funciona em roteadores que expõem SNMP
  (comunidade `public`). Muitos roteadores de operadora não expõem — nesse caso o
  relatório avisa que não foi possível ler, sem inventar número.
- **Velocidade:** é uma medição pontual (2 tentativas de ~6 s, melhor resultado) contra
  servidores Cloudflare/OVH. Valores variam com o horário e o tráfego da região.
- **Fabricante do roteador:** identificação aproximada pelo prefixo do MAC; quando não
  reconhece, o relatório diz para consultar o adesivo do aparelho.
- O diagnóstico é **somente leitura**: não altera configurações, não reinicia nada e
  não exige administrador.

## Estrutura

```
network-doctor/
├── main.py                 # CLI (argumentos, saída, JSON, salvar)
├── run.ps1                 # Launcher PowerShell (execução local ou irm ... | iex)
├── Iniciar-Diagnostico.cmd # Duplo clique para rodar no Windows
├── src/
│   ├── diagnostico.py      # Orquestra as verificações
│   ├── sistema.py          # SO, uptime, adaptadores, Wi-Fi
│   ├── rede.py             # IP/gateway/DHCP/DNS, conexões, MTU, uso de banda
│   ├── latencia.py         # Ping, jitter, perda
│   ├── rota.py             # Traceroute e pathping
│   ├── dns.py              # Tempo de resolução de nomes
│   ├── velocidade.py       # Teste de download/upload, ISP e Bufferbloat
│   ├── roteador.py         # MAC/fabricante, painel web, SNMP
│   ├── relatorio.py        # Nota de saúde, linguagem simples e recomendações
│   └── util.py             # Subprocess, parsing pt-BR/en-US, formatação
└── tests/                  # Testes unitários (unittest, stdlib)
```

## Testes

```bat
python -m unittest discover tests
```

## Licença

Código aberto, sem restrições — use e adapte como quiser.
