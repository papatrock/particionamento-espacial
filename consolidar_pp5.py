"""Consolida execuções concluídas da PP5, separadas das demais perguntas."""
import argparse
from pathlib import Path
from consolidar_pp1 import consolidar, imprimir_resumo, ErroConsolidacao

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("resultados/pp5"))
    args = parser.parse_args()
    try:
        imprimir_resumo(consolidar(args.entrada, "pp5"), "pp5")
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação PP5 falhou: {erro}\n")
