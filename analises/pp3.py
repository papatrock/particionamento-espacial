"""PP3: efeito do GiST e ganho do particionamento sobre o baseline indexado."""
import argparse
from collections import defaultdict
import csv
import math
from pathlib import Path
import statistics

from analises.pp2 import CHAVES as CHAVES_PP2

RAIZ = Path(__file__).resolve().parents[1] / "resultados/pp3"
CHAVES = ("pp3_run_id", *CHAVES_PP2[1:])
MEDIDAS = ("n", "mediana_ms", "media_ms", "desvio_ms", "minimo_ms", "maximo_ms",
           "particoes_alvo", "particoes_efetivas", "intersecoes", "seletividade", "bytes_indices",
           "speedup_particionamento_mesmo_gist", "speedup_gist", "speedup_vs_apenas_gist",
           "ganho_vs_apenas_gist_pct")


def analisar(resultados=RAIZ):
    raiz = Path(resultados)
    grupos = defaultdict(list)
    with (raiz / "acumulado/consultas_acumulado.csv").open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            if linha["gist"] not in ("on", "off"):
                raise ValueError("Estado de GiST inválido no CSV")
            chave = tuple(linha[c] for c in CHAVES)
            grupos[chave + (linha["algoritmo"], linha["gist"])].append(linha)
    resumos = []
    for chave, linhas in sorted(grupos.items()):
        tempos = [float(l["tempo_cliente_ms"]) for l in linhas]
        if any(not math.isfinite(t) or t < 0 for t in tempos):
            raise ValueError("Tempo inválido no CSV")
        resumos.append({**dict(zip((*CHAVES, "algoritmo", "gist"), chave)), "n": len(tempos),
                        "mediana_ms": statistics.median(tempos), "media_ms": statistics.mean(tempos),
                        "desvio_ms": statistics.stdev(tempos) if len(tempos) > 1 else "",
                        "minimo_ms": min(tempos), "maximo_ms": max(tempos),
                        **{c: linhas[0][c] for c in ("particoes_alvo", "particoes_efetivas", "intersecoes",
                                                   "seletividade", "bytes_indices")}})
    medianas = {tuple(r[c] for c in (*CHAVES, "algoritmo", "gist")): r["mediana_ms"] for r in resumos}
    for r in resumos:
        chave = tuple(r[c] for c in CHAVES)
        tempo = r["mediana_ms"]
        baseline = medianas.get((*chave, "SEM_PARTICIONAMENTO", r["gist"]))
        apenas_gist = medianas.get((*chave, "SEM_PARTICIONAMENTO", "on"))
        sem_gist = medianas.get((*chave, r["algoritmo"], "off"))
        r["speedup_particionamento_mesmo_gist"] = baseline / tempo if baseline is not None and tempo > 0 else ""
        r["speedup_gist"] = sem_gist / tempo if r["gist"] == "on" and sem_gist is not None and tempo > 0 else ""
        r["speedup_vs_apenas_gist"] = apenas_gist / tempo if apenas_gist is not None and tempo > 0 else ""
        r["ganho_vs_apenas_gist_pct"] = 100 * (apenas_gist - tempo) / apenas_gist if apenas_gist is not None and apenas_gist > 0 else ""
    destino = raiz / "analise"
    destino.mkdir(exist_ok=True)
    with (destino / "resumo_indexacao.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[*CHAVES, "algoritmo", "gist", *MEDIDAS])
        writer.writeheader()
        writer.writerows(resumos)
    return resumos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", type=Path, default=RAIZ)
    args = parser.parse_args()
    analisar(args.resultados)
    print(f"Resumo: {args.resultados / 'analise/resumo_indexacao.csv'}")
