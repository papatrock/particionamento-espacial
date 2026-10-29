"""Consolida execuções concluídas PP2, sem misturar os resultados da PP1."""
import argparse
from pathlib import Path
from consolidar_pp1 import consolidar, imprimir_resumo, ErroConsolidacao

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("resultados/pp2"))
    args = parser.parse_args()
    try:
        imprimir_resumo(consolidar(args.entrada, "pp2"), "pp2")
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação PP2 falhou: {erro}\n")
