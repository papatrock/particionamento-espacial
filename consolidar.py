"""Reconstrói os acumulados de uma PP a partir das execuções concluídas: python3 consolidar.py pp5"""
import argparse
from pathlib import Path

from nucleo.consolidacao import EXPERIMENTOS, ErroConsolidacao, consolidar, imprimir_resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experimento", choices=EXPERIMENTOS)
    parser.add_argument("--entrada", type=Path,
                        help="Pasta que contém as execuções da PP (padrão: resultados/<pp>); saída em acumulado/.")
    args = parser.parse_args()
    entrada = args.entrada or Path("resultados") / args.experimento
    try:
        imprimir_resumo(consolidar(entrada, args.experimento), args.experimento)
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação {args.experimento.upper()} não concluída: {erro}\n")


if __name__ == "__main__":
    main()
