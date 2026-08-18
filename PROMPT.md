# PROMPT.md — Spec do projeto `network-doctor`

> Documento de contrato lido a cada iteração (spec-first). Estado do trabalho em `IMPLEMENTATION_PLAN.md`.

## Objetivo (Goal)

Criar um programa CLI em Python (apenas stdlib, sem dependências externas) para Windows que diagnostica
a rede do usuário em detalhe — sobrecarga, ping alto, jitter, perda de pacotes, uso de banda, instabilidade
regional, roteador sem reiniciar há muito tempo, Wi-Fi fraco, DNS lento — e **traduz tudo em linguagem
simples** com explicações e recomendações de correção centralizadas, adaptadas ao caso da pessoa.

## Pronto quando (Done when)

- [ ] Pasta `network-doctor/` criada dentro de `C:\Users\ferna\Documents\coding-projects\`.
- [ ] CLI executável via `python main.py` com modos: completo, `--rapido`, `--latencia`, `--dns`,
      `--velocidade`, `--uso`, `--roteador`, `--rota [alvo]`, `--wifi`, `--json`, `--salvar [caminho]`.
- [ ] Diagnóstico completo cobre: sistema/uptime, adaptadores, Wi-Fi (sinal/canal/banda), configuração
      local (IP/gateway/DHCP/DNS), latência+perda+**jitter** para gateway e internet, rota (traceroute),
      DNS, **velocidade de download/upload**, **uso de banda por processo**, **status do roteador**
      (MAC/fornecedor, HTTP acessível, uptime via SNMP quando disponível, contrato DHCP) e
      **instabilidade regional** (salto problemático na rota).
- [ ] Relatório final em **português simples**: cada métrica com explicação leiga + semáforo
      (bom/atenção/crítico) + **nota de saúde 0-100** + lista de recomendações priorizadas
      (ex.: "seu roteador está ligado há X dias — reinicie-o"; "sinal Wi-Fi fraco — aproxime-se").
- [ ] Sem dependências externas (apenas stdlib); comandos do Windows chamados via subprocess com
      parsing tolerante a pt-BR/en-US (ping, tracert, pathping, ipconfig, netsh, arp, netstat, PowerShell).
- [ ] `Iniciar-Diagnostico.cmd` para duplo clique sem precisar digitar comando.
- [ ] Testes unitários (unittest, stdlib) cobrindo parsers e lógica de score/recomendações: `python -m unittest discover tests` verde.
- [ ] Verificação real: rodar o diagnóstico completo nesta máquina e conferir a saída sem erros.

## Nunca tocar (Never touch)

- Nenhum arquivo fora de `C:\Users\ferna\Documents\coding-projects\network-doctor\`.
- Não instalar pacotes globais, não modificar registro do Windows, não exigir administrador.
- Não executar ações destrutivas na rede do usuário (sem reiniciar roteador, sem mudar configuração).

## Parar se (Stop if)

- Mais de ~15 arquivos fora do escopo forem alterados.
- Um teste que passava começar a falhar sem motivo explicado.
- Precisar de privilégio de administrador para funcionar (não deve precisar).
