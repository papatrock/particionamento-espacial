"""Resume PP2 por execução/workload e compara speedup dentro de cada workload."""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
import statistics

RAIZ = Path(__file__).resolve().parents[1] / "resultados/pp2"
# Não misturar sessões, máquinas, escalas, sementes ou instrumentações em uma média.
CHAVES = ("pp2_run_id", "dataset", "workload", "objetos_a", "objetos_b", "semente",
          "ids_a_md5", "ids_b_md5", "workers_por_gather", "indexacao", "perf", "rodada")


def analisar(resultados=RAIZ):
    raiz = Path(resultados)
    grupos = defaultdict(list)
    with (raiz / "acumulado/consultas_acumulado.csv").open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            chave = tuple(linha[c] for c in CHAVES)
            grupos[chave + (linha["algoritmo"],)].append(linha)
    resumos = []
    for chave, linhas in sorted(grupos.items()):
        tempos = [float(l["tempo_cliente_ms"]) for l in linhas]
        if any(not math.isfinite(t) or t < 0 for t in tempos):
            raise ValueError("Tempo inválido no CSV")
        resumos.append({**dict(zip(CHAVES + ("algoritmo",), chave)), "n": len(tempos),
                        "mediana_ms": statistics.median(tempos), "media_ms": statistics.mean(tempos),
                        "desvio_ms": statistics.stdev(tempos) if len(tempos)>1 else "",
                        "minimo_ms": min(tempos), "maximo_ms": max(tempos),
                        "particoes_alvo": linhas[0]["particoes_alvo"],
                        "particoes_efetivas": linhas[0]["particoes_efetivas"],
                        "intersecoes": linhas[0]["intersecoes"], "seletividade": linhas[0]["seletividade"]})
    baselines = {tuple(r[c] for c in CHAVES): r["mediana_ms"] for r in resumos if r["algoritmo"] == "SEM_PARTICIONAMENTO"}
    for r in resumos:
        baseline = baselines.get(tuple(r[c] for c in CHAVES))
        r["speedup_mediana"] = baseline/r["mediana_ms"] if baseline is not None and r["mediana_ms"]>0 else ""
    destino = raiz / "analise"
    destino.mkdir(exist_ok=True)
    campos = [*CHAVES, "algoritmo", "n", "mediana_ms", "media_ms", "desvio_ms", "minimo_ms", "maximo_ms",
              "particoes_alvo", "particoes_efetivas", "intersecoes", "seletividade", "speedup_mediana"]
    with (destino / "resumo_workloads.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resumos)
    return resumos


def figuras(resumos, raiz):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    grupos = defaultdict(list)
    for r in resumos:
        grupos[r["pp2_run_id"]].append(r)
    destino = Path(raiz)/"figuras"
    destino.mkdir(exist_ok=True)
    workloads = ["ponto_poligono", "linha_poligono", "poligono_poligono"]
    for run, linhas in grupos.items():
        fig, ax = plt.subplots(figsize=(9,5))
        for algoritmo in sorted({r["algoritmo"] for r in linhas}):
            pontos = {r["workload"]: r["speedup_mediana"] for r in linhas if r["algoritmo"]==algoritmo}
            ys = [pontos.get(w, "") for w in workloads]
            if any(y != "" for y in ys):
                ax.plot(workloads, [float(y) if y != "" else float("nan") for y in ys], marker="o", label=algoritmo)
        ax.axhline(1,color="gray",linestyle="--")
        ax.set_ylabel("Speedup: mediana do baseline / mediana do algoritmo")
        ax.set_title(f"PP2 — {run}")
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend()
        fig.tight_layout()
        for formato in ("png", "pdf"):
            fig.savefig(destino / f"speedup_{run}.{formato}", dpi=180)
        plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--resultados", type=Path, default=RAIZ)
    p.add_argument("--graficos", action="store_true", help="Requer matplotlib; tabelas usam apenas biblioteca padrão")
    args = p.parse_args()
    resumos = analisar(args.resultados)
    if args.graficos:
        figuras(resumos, args.resultados)
    print(f"Resumo: {args.resultados / 'analise/resumo_workloads.csv'}")
