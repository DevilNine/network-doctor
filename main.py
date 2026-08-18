#!/usr/bin/env python3
"""network-doctor — CLI de diagnóstico de rede com relatório em linguagem simples.

Uso:
  python main.py                        diagnóstico completo
  python main.py --rapido               teste rápido (latência e estabilidade)
  python main.py --latencia | --dns | --velocidade | --uso | --roteador | --wifi
  python main.py --rota [alvo]          rota até um destino (--profundo inclui perda por salto)
  python main.py --contratada 300       compara a velocidade com o contratado
  python main.py --json                 imprime os resultados em JSON
  python main.py --salvar relatorio.txt salva o relatório em arquivo
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

from src import diagnostico, relatorio, util

__version__ = "1.1.0"


def _salvar(caminho: str, texto: str) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto + "\n")


def _montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="network-doctor",
        description="Diagnostica a sua rede (ping, perda, Wi-Fi, DNS, velocidade, bufferbloat, "
        "roteador, uso de banda, MTU) e traduz tudo em linguagem simples, com nota de saúde e recomendações.",
    )
    p.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--rapido", action="store_true", help="teste rápido: latência, perda e estabilidade")
    p.add_argument("--latencia", action="store_true", help="só latência (ping/jitter/perda)")
    p.add_argument("--dns", action="store_true", help="só resolução de nomes (DNS)")
    p.add_argument("--velocidade", action="store_true", help="só teste de velocidade e bufferbloat")
    p.add_argument("--uso", action="store_true", help="só uso de banda e conexões")
    p.add_argument("--roteador", action="store_true", help="só status do roteador")
    p.add_argument("--wifi", action="store_true", help="só sinal Wi-Fi")
    p.add_argument(
        "--rota",
        nargs="?",
        const="8.8.8.8",
        metavar="ALVO",
        help="rota até um destino (padrão: 8.8.8.8)",
    )
    p.add_argument(
        "--profundo",
        action="store_true",
        help="com --rota, inclui pathping (perda por salto, ~2 min)",
    )
    p.add_argument(
        "--contratada",
        type=float,
        metavar="MBPS",
        help="velocidade contratada (ex.: 300) para comparar com o download medido",
    )
    p.add_argument("--json", action="store_true", help="imprime os resultados crus em JSON")
    p.add_argument(
        "--salvar",
        nargs="?",
        const="relatorio-rede.txt",
        metavar="ARQUIVO",
        help="salva o relatório em um arquivo de texto",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    util.configure_stdout()
    util.enable_ansi()
    args = _montar_parser().parse_args(argv)
    util.MODO_JSON = args.json

    individuais = [m for m in ("latencia", "dns", "velocidade", "uso", "roteador", "wifi") if getattr(args, m)]
    if args.rota is not None:
        individuais.append("rota")

    if args.rapido:
        modos = None
    elif individuais:
        modos = individuais
    else:
        modos = list(diagnostico.MODOS)

    alvo_rota = args.rota or "8.8.8.8"
    if not re.match(r"^[A-Za-z0-9._-]+$", alvo_rota):
        print(util.cor(f"  ❌ Alvo de rota inválido: {alvo_rota!r}", "red"))
        return 2

    util.msg(util.cor("\n  🩺 NETWORK DOCTOR — vamos olhar a sua rede\n", "cyan"))
    resultados = diagnostico.diagnosticar(
        rapido=args.rapido,
        modos=modos,
        contratada=args.contratada,
        alvo_rota=alvo_rota,
        profundo=args.profundo,
    )
    avaliacao = relatorio.avaliar(resultados)

    if args.json:
        saida = copy.deepcopy(resultados)
        saida["_avaliacao"] = avaliacao
        print(json.dumps(saida, ensure_ascii=False, indent=2, default=str))
    elif args.rapido:
        print(relatorio.formatar_rapido(resultados, avaliacao))
    else:
        print(relatorio.formatar(resultados, avaliacao))

    if args.salvar:
        caminho = os.path.abspath(args.salvar)
        _salvar(caminho, relatorio.formatar(resultados, avaliacao, colorido=False))
        util.msg(util.cor(f"\n  📄 Relatório salvo em: {caminho}", "green"))

    util.msg("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
