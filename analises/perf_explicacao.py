"""Contadores do perf cruzados com tempos, replicação, ordem física e workers (plano perf do rodar_tudo).

    .venv/bin/python -m analises.perf_explicacao --resultados resultados/lab/perf

Complementa analises/perf.py, que faz a análise descritiva do perf a partir dos acumulados do PP1.

Lê cada medicoes/<execução>/ (consultas.csv, perf.csv) abaixo de --resultados, sobe até o
configuracao.json da execução e até o particionamento.json do caso. Os contadores do perf são
totais do bloco de repetições na máquina inteira (perf stat -a); aqui são divididos pelo número
de repetições. Compare só razões entre casos da mesma rodada, nunca valores absolutos entre dias.

Grava <resultados>/resumo_perf/perf_resumo.csv e imprime três tabelas:
replicação (PP1), ordem física do baseline (pr_centro) e SAMJ por workers (PP4).
"""
import argparse
import csv
import json
from pathlib import Path
import re
import statistics

EVENTOS = ("cycles", "instructions", "cache-references", "cache-misses", "branches", "branch-misses",
           "context-switches", "cpu-migrations", "page-faults")


def evento_normalizado(nome):
    """Em CPUs híbridas o perf separa cpu_core/ e cpu_atom/; o jatoba2 (Xeon) usa nomes simples."""
    if nome.startswith("cpu_atom/"):
        return None
    nome = re.sub(r"^cpu_core/(.*)/$", r"\1", nome)
    return nome.split(":")[0]


def subir_ate(pasta, arquivo, limite):
    while True:
        if (pasta / arquivo).exists():
            return pasta / arquivo
        if pasta == limite or pasta.parent == pasta:
            return None
        pasta = pasta.parent


def ler_caso(medicao, raiz):
    with (medicao / "consultas.csv").open(newline="", encoding="utf-8") as f:
        consultas = list(csv.DictReader(f))
    with (medicao / "perf.csv").open(newline="", encoding="utf-8") as f:
        perf = list(csv.DictReader(f))
    if not consultas or not perf:
        return None
    configuracao_json = subir_ate(medicao, "configuracao.json", raiz)
    config = json.loads(configuracao_json.read_text(encoding="utf-8")) if configuracao_json else {}
    execucao_dir = configuracao_json.parent if configuracao_json else medicao
    pp = execucao_dir.name.split("_")[0]
    partes = medicao.relative_to(execucao_dir).parts
    dataset = (config.get("fontes") or {}).get("dataset") or partes[0]
    algoritmo = consultas[0]["algoritmo"]
    # PP1 lê as tabelas originais da região; PP2 a PP5, amostras gravadas na ordem pedida.
    ordem = config.get("ordem_amostra", "id") if pp != "pp1" else "original"
    particionamento = subir_ate(medicao, "particionamento.json", execucao_dir)
    replicacao = None
    if particionamento and algoritmo != "SEM_PARTICIONAMENTO":
        p = json.loads(particionamento.read_text(encoding="utf-8"))
        copias = sum(o["objetos_a"] + o["objetos_b"] for o in p["ocupacoes"])
        replicacao = copias / (p["objetos_a"] + p["objetos_b"])
    repeticoes = int(perf[0]["repeticoes"])
    contadores = {}
    for linha in perf:
        nome = evento_normalizado(linha["evento"])
        if nome and linha["status"] == "ok" and linha["valor"]:
            contadores[nome] = contadores.get(nome, 0) + float(linha["valor"]) / repeticoes
    c = contadores.get
    return {
        "pp": pp, "execucao_pp": execucao_dir.name, "dataset": dataset.removesuffix("_mapa"),
        "algoritmo": algoritmo, "workers": consultas[0].get("workers_por_gather", ""),
        "ordem_amostra": ordem, "repeticoes": repeticoes, "replicacao": replicacao,
        "tempo_mediana_ms": statistics.median(float(l["tempo_cliente_ms"]) for l in consultas),
        **{f"{e}_por_consulta": c(e) for e in EVENTOS},
        "ipc": c("instructions") / c("cycles") if c("instructions") and c("cycles") else None,
        "taxa_cache_miss": c("cache-misses") / c("cache-references") if c("cache-misses") and c("cache-references") else None,
        "taxa_branch_miss": c("branch-misses") / c("branches") if c("branch-misses") and c("branches") else None,
        "eventos_incompletos": any(l["status"] != "ok" for l in perf),
    }


def relativos(casos):
    """Razões sobre o baseline da mesma execução, dataset e número de workers."""
    base = {(c["execucao_pp"], c["dataset"], c["workers"]): c for c in casos if c["algoritmo"] == "SEM_PARTICIONAMENTO"}
    for c in casos:
        b = base.get((c["execucao_pp"], c["dataset"], c["workers"]))
        for chave, evento in (("instrucoes_sobre_baseline", "instructions_por_consulta"),
                              ("cache_misses_sobre_baseline", "cache-misses_por_consulta"),
                              ("tempo_sobre_baseline", "tempo_mediana_ms")):
            c[chave] = c[evento] / b[evento] if b and c[evento] and b[evento] else None


def fmt(valor, casas=2, escala=1):
    if valor is None:
        return "–"
    return f"{valor / escala:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela(titulo, colunas, linhas):
    if not linhas:
        return
    print(f"\n## {titulo}\n")
    print("| " + " | ".join(nome for nome, _ in colunas) + " |")
    print("|" + "---|" * len(colunas))
    for linha in linhas:
        print("| " + " | ".join(funcao(linha) for _, funcao in colunas) + " |")


ORDEM_ALG = ["SEM_PARTICIONAMENTO", "TWO_LAYER", "BSP", "STR", "HILBERT", "STR_SAMJ", "HILBERT_SAMJ"]


def chave_alg(c):
    return ORDEM_ALG.index(c["algoritmo"]) if c["algoritmo"] in ORDEM_ALG else 99


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultados", type=Path, default=Path("resultados/lab/perf"))
    args = p.parse_args()
    raiz = args.resultados.resolve()
    casos = [c for m in sorted(raiz.rglob("medicoes/*/perf.csv"))
             if (m.parent / "consultas.csv").exists() and (c := ler_caso(m.parent, raiz))]
    if not casos:
        p.exit(1, f"Nenhum medicoes/*/perf.csv com consultas.csv encontrado em {raiz}\n")
    relativos(casos)
    destino = raiz / "resumo_perf"
    destino.mkdir(exist_ok=True)
    with (destino / "perf_resumo.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(casos[0]))
        writer.writeheader()
        writer.writerows(casos)

    tempo = ("Tempo (ms)", lambda c: fmt(c["tempo_mediana_ms"], 0))
    tabela("Replicação: instruções por consulta (PP1)", [
        ("Região", lambda c: c["dataset"]), ("Algoritmo", lambda c: c["algoritmo"]), tempo,
        ("Replicação", lambda c: fmt(c["replicacao"])),
        ("Instruções (bi)", lambda c: fmt(c["instructions_por_consulta"], 1, 1e9)),
        ("Instr. ÷ baseline", lambda c: fmt(c["instrucoes_sobre_baseline"])),
        ("Tempo ÷ baseline", lambda c: fmt(c["tempo_sobre_baseline"])),
        ("IPC", lambda c: fmt(c["ipc"])), ("Taxa de cache miss", lambda c: fmt(c["taxa_cache_miss"], 3)),
    ], sorted((c for c in casos if c["pp"] == "pp1"), key=lambda c: (c["dataset"], chave_alg(c))))

    ordem_fisica = {"original": 0, "sorteio": 1, "id": 2, "espacial": 3}
    tabela("Ordem física: baseline de pr_centro (mesmos objetos, ordens diferentes)", [
        ("Ordem", lambda c: c["ordem_amostra"] + (" (PP1)" if c["pp"] == "pp1" else "")), tempo,
        ("Instruções (bi)", lambda c: fmt(c["instructions_por_consulta"], 1, 1e9)),
        ("IPC", lambda c: fmt(c["ipc"])),
        ("Cache misses (mi)", lambda c: fmt(c["cache-misses_por_consulta"], 1, 1e6)),
        ("Taxa de cache miss", lambda c: fmt(c["taxa_cache_miss"], 3)),
        ("Page faults (mil)", lambda c: fmt(c["page-faults_por_consulta"], 1, 1e3)),
    ], sorted((c for c in casos if c["dataset"] == "pr_centro" and c["algoritmo"] == "SEM_PARTICIONAMENTO"
               and c["pp"] in ("pp1", "pp5")), key=lambda c: ordem_fisica.get(c["ordem_amostra"], 9)))

    tabela("SAMJ por workers (PP4)", [
        ("Algoritmo", lambda c: c["algoritmo"]), ("Workers", lambda c: c["workers"]), tempo,
        ("Trocas de contexto", lambda c: fmt(c["context-switches_por_consulta"], 0)),
        ("Migrações de CPU", lambda c: fmt(c["cpu-migrations_por_consulta"], 0)),
        ("Instruções (bi)", lambda c: fmt(c["instructions_por_consulta"], 1, 1e9)),
        ("IPC", lambda c: fmt(c["ipc"])),
    ], sorted((c for c in casos if c["pp"] == "pp4"), key=lambda c: (chave_alg(c), int(c["workers"] or 0))))

    if any(c["eventos_incompletos"] for c in casos):
        print("\nAviso: há contadores não suportados ou não contados; confira a coluna eventos_incompletos.")
    print(f"\n{len(casos)} casos em {destino / 'perf_resumo.csv'}")


if __name__ == "__main__":
    main()
