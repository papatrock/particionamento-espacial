"""Consolida execuções concluídas da PP3, separadas das demais perguntas."""
import argparse
from pathlib import Path
from consolidar_pp1 import consolidar, imprimir_resumo, ErroConsolidacao

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("resultados/pp3"))
    args = parser.parse_args()
    try:
        imprimir_resumo(consolidar(args.entrada, "pp3"), "pp3")
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação PP3 falhou: {erro}\n")
