"""Consolida execuções concluídas da PP4, separadas das demais perguntas."""
import argparse
from pathlib import Path
from consolidar_pp1 import consolidar, imprimir_resumo, ErroConsolidacao

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("resultados/pp4"))
    args = parser.parse_args()
    try:
        imprimir_resumo(consolidar(args.entrada, "pp4"), "pp4")
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação PP4 falhou: {erro}\n")
