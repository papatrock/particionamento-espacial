"""PP4: escalabilidade por algoritmo e comparação ao baseline no mesmo limite de workers."""
import argparse
from collections import defaultdict
import csv
import math
from pathlib import Path
import statistics

from analises.pp2 import CHAVES as CHAVES_PP2

RAIZ = Path(__file__).resolve().parents[1] / "resultados/pp4"
CHAVES = ("pp4_run_id", *(c for c in CHAVES_PP2[1:] if c != "workers_por_gather"),
          "gist", "max_parallel_workers", "max_worker_processes", "parallel_leader_participation")
CONTEXTO = ("particoes_alvo", "particoes_efetivas", "intersecoes", "seletividade",
            "plano_gathers", "plano_workers_planejados_max", "plano_workers_lancados_max", "plano_gathers_com_deficit")
MEDIDAS = ("n", "mediana_ms", "media_ms", "desvio_ms", "minimo_ms", "maximo_ms",
           "speedup_vs_serial", "reducao_vs_serial_pct", "speedup_vs_baseline_mesmos_workers")


def analisar(resultados=RAIZ):
    raiz = Path(resultados)
    grupos = defaultdict(list)
    with (raiz / "acumulado/consultas_acumulado.csv").open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            workers = int(linha["workers_por_gather"])
            if workers < 0:
                raise ValueError("Limite de workers inválido")
            chave = tuple(linha[c] for c in CHAVES)
            grupos[chave + (linha["algoritmo"], workers)].append(linha)
    resumos = []
    for chave, linhas in sorted(grupos.items()):
        tempos = [float(l["tempo_cliente_ms"]) for l in linhas]
        if any(not math.isfinite(t) or t < 0 for t in tempos):
            raise ValueError("Tempo inválido no CSV")
        # Os contadores do plano são um diagnóstico por caso, não n observações independentes.
        if any(any(l[c] != linhas[0][c] for c in CONTEXTO) for l in linhas):
            raise ValueError("Contexto divergente dentro de um caso")
        resumos.append({**dict(zip((*CHAVES, "algoritmo", "workers_por_gather"), chave)), "n": len(tempos),
                        "mediana_ms": statistics.median(tempos), "media_ms": statistics.mean(tempos),
                        "desvio_ms": statistics.stdev(tempos) if len(tempos) > 1 else "",
                        "minimo_ms": min(tempos), "maximo_ms": max(tempos),
                        **{c: linhas[0][c] for c in CONTEXTO}})
    medianas = {tuple(r[c] for c in (*CHAVES, "algoritmo", "workers_por_gather")): r["mediana_ms"] for r in resumos}
    for r in resumos:
        chave = tuple(r[c] for c in CHAVES)
        tempo = r["mediana_ms"]
        serial = medianas.get((*chave, r["algoritmo"], 0))
        baseline = medianas.get((*chave, "SEM_PARTICIONAMENTO", r["workers_por_gather"]))
        r["speedup_vs_serial"] = serial / tempo if serial is not None and tempo > 0 else ""
        r["reducao_vs_serial_pct"] = 100 * (serial - tempo) / serial if serial is not None and serial > 0 else ""
        r["speedup_vs_baseline_mesmos_workers"] = baseline / tempo if baseline is not None and tempo > 0 else ""
    destino = raiz / "analise"
    destino.mkdir(exist_ok=True)
    with (destino / "resumo_paralelismo.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[*CHAVES, "algoritmo", "workers_por_gather", *MEDIDAS, *CONTEXTO])
        writer.writeheader()
        writer.writerows(resumos)
    return resumos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", type=Path, default=RAIZ)
    args = parser.parse_args()
    analisar(args.resultados)
    print(f"Resumo: {args.resultados / 'analise/resumo_paralelismo.csv'}")
