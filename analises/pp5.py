"""PP5: desempenho, balanceamento e overhead por algoritmo e número de partições."""
import argparse
from collections import defaultdict
import csv
import math
from pathlib import Path
import statistics

from analises.pp2 import CHAVES as CHAVES_PP2

RAIZ = Path(__file__).resolve().parents[1] / "resultados/pp5"
CHAVES = ("pp5_run_id", *CHAVES_PP2[1:], "gist", "max_parallel_workers", "max_worker_processes",
          "parallel_leader_participation")
TEMPOS = ("n", "mediana_ms", "media_ms", "desvio_ms", "minimo_ms", "maximo_ms",
          "speedup_vs_baseline", "melhor_do_algoritmo")
# Valores por caso: repetidos em cada linha do CSV, mas não são n observações independentes.
CONTEXTO = ("particoes_efetivas", "capacidade", "intersecoes", "seletividade",
            "particoes_vazias", "particoes_com_a_e_b", "carga_media", "carga_maxima", "carga_max_sobre_media",
            "carga_cv", "fator_replicacao", "pares_candidatos", "pares_max_sobre_media",
            "particionamento_s", "materializacao_s", "tamanho_saidas_bytes",
            "planejamento_primeiro_ms", "planejamento_mediana_ms", "plano_execucao_ms",
            "plano_gathers", "plano_workers_planejados_max", "plano_workers_lancados_max", "plano_gathers_com_deficit")


def analisar(resultados=RAIZ):
    raiz = Path(resultados)
    grupos = defaultdict(list)
    with (raiz / "acumulado/consultas_acumulado.csv").open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            alvo = int(linha["particoes_alvo"]) if linha["particoes_alvo"] else 0
            grupos[(tuple(linha[c] for c in CHAVES), linha["algoritmo"], alvo)].append(linha)
    resumos = []
    for (chave, algoritmo, alvo), linhas in sorted(grupos.items()):
        tempos = [float(l["tempo_cliente_ms"]) for l in linhas]
        if any(not math.isfinite(t) or t < 0 for t in tempos):
            raise ValueError("Tempo inválido no CSV")
        if any(any(l[c] != linhas[0][c] for c in CONTEXTO) for l in linhas):
            raise ValueError("Contexto divergente dentro de um caso")
        resumos.append({**dict(zip(CHAVES, chave)), "algoritmo": algoritmo, "particoes_alvo": alvo or "",
                        "n": len(tempos), "mediana_ms": statistics.median(tempos), "media_ms": statistics.mean(tempos),
                        "desvio_ms": statistics.stdev(tempos) if len(tempos) > 1 else "",
                        "minimo_ms": min(tempos), "maximo_ms": max(tempos),
                        **{c: linhas[0][c] for c in CONTEXTO}})
    baselines, melhores = {}, {}
    for r in resumos:
        chave = tuple(r[c] for c in CHAVES)
        if r["algoritmo"] == "SEM_PARTICIONAMENTO":
            baselines[chave] = r["mediana_ms"]
        grupo = (chave, r["algoritmo"])
        melhores[grupo] = min(melhores.get(grupo, r["mediana_ms"]), r["mediana_ms"])
    for r in resumos:
        chave = tuple(r[c] for c in CHAVES)
        baseline = baselines.get(chave)
        r["speedup_vs_baseline"] = baseline / r["mediana_ms"] if baseline is not None and r["mediana_ms"] > 0 else ""
        particionado = r["algoritmo"] != "SEM_PARTICIONAMENTO"
        r["melhor_do_algoritmo"] = particionado and r["mediana_ms"] == melhores[(chave, r["algoritmo"])]
    destino = raiz / "analise"
    destino.mkdir(exist_ok=True)
    with (destino / "resumo_granularidade.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[*CHAVES, "algoritmo", "particoes_alvo", *TEMPOS, *CONTEXTO])
        writer.writeheader()
        writer.writerows(resumos)
    return resumos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", type=Path, default=RAIZ)
    args = parser.parse_args()
    analisar(args.resultados)
    print(f"Resumo: {args.resultados / 'analise/resumo_granularidade.csv'}")
