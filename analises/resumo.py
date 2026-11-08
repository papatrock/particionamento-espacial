"""Resumo dos resultados: uma tabela geral e uma figura por pergunta de pesquisa.

    .venv/bin/python -m analises.resumo --resultados resultados/lab/final

Lê o acumulado de cada PP (ppN/acumulado/consultas_acumulado.csv) e grava em <resultados>/resumo/.
Quando há mais de uma execução para o mesmo caso, usa a mais recente.
"""
import argparse
from collections import defaultdict
import csv
from pathlib import Path
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

BASELINE = "SEM_PARTICIONAMENTO"
ORDEM = [BASELINE, "TWO_LAYER", "BSP", "STR", "HILBERT", "STR_SAMJ", "HILBERT_SAMJ"]
NOMES = {BASELINE: "Sem particionamento", "TWO_LAYER": "Two-Layer", "BSP": "BSP", "STR": "STR (MASJ)",
         "HILBERT": "Hilbert (MASJ)", "STR_SAMJ": "STR (SAMJ)", "HILBERT_SAMJ": "Hilbert (SAMJ)"}
WORKLOADS = {"ponto_poligono": "ponto × polígono", "linha_poligono": "linha × polígono",
             "poligono_poligono": "polígono × polígono"}
# Paleta de referência validada (validate_palette.js): slots categóricos em ordem fixa.
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
TINTA, TINTA_2, MUDO, GRADE, EIXO = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
AVISO_BASELINE = ("Preliminar: neste PP, o baseline usa amostras gravadas na ordem do sorteio, "
                  "o que pode deixá-lo mais lento e inflar o speedup.")


def nome_regiao(dataset):
    return dataset.removesuffix("_mapa")


def ler(raiz, pp):
    arquivo = Path(raiz) / pp / "acumulado/consultas_acumulado.csv"
    if not arquivo.exists():
        return []
    with arquivo.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def medianas(linhas, pp, chaves):
    """Mediana por caso; para casos repetidos em várias execuções, fica a execução mais recente."""
    grupos = defaultdict(lambda: defaultdict(list))
    for l in linhas:
        caso = tuple(l.get(c, "") for c in chaves) + (l["algoritmo"],)
        grupos[caso][l[f"{pp}_run_id"]].append(float(l["tempo_cliente_ms"]))
    resultado = {}
    for caso, execucoes in grupos.items():
        tempos = execucoes[max(execucoes)]
        resultado[caso] = (statistics.median(tempos), len(tempos))
    return resultado


def estilo(ax):
    ax.set_facecolor("white")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EIXO)
        ax.spines[lado].set_linewidth(0.8)
    ax.tick_params(colors=TINTA_2, labelsize=8, length=0)
    ax.grid(color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)


def escala_speedup(ax, eixo="y", valores=()):
    """Escala log com ticks legíveis; a linha em 1 separa ganho de perda."""
    marcas = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50]
    menor, maior = min(valores, default=0.5), max(valores, default=2)
    usadas = [m for m in marcas if menor / 1.5 <= m <= maior * 1.5] or [1]
    formato = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
    if eixo == "y":
        ax.set_yscale("log"); ax.yaxis.set_major_locator(FixedLocator(usadas)); ax.yaxis.set_major_formatter(formato)
        ax.yaxis.set_minor_locator(NullLocator()); ax.axhline(1, color=TINTA_2, linewidth=0.9, zorder=1)
        ax.set_ylim(min(usadas + [menor]) / 1.3, max(usadas + [maior]) * 1.3)
    else:
        ax.set_xscale("log"); ax.xaxis.set_major_locator(FixedLocator(usadas)); ax.xaxis.set_major_formatter(formato)
        ax.xaxis.set_minor_locator(NullLocator()); ax.axvline(1, color=TINTA_2, linewidth=0.9, zorder=1)
        ax.set_xlim(min(usadas + [menor]) / 1.3, max(usadas + [maior]) * 1.3)


def salvar(fig, destino, nome, titulo, nota=None):
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=11, color=TINTA, fontweight="bold")
    if nota:
        # Abaixo da figura: o bbox_inches="tight" a inclui sem cobrir os eixos.
        fig.text(0.01, -0.01, nota, fontsize=7.5, color=TINTA_2, ha="left", va="top", wrap=True)
    for formato in ("png", "pdf"):
        fig.savefig(destino / f"{nome}.{formato}", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def pp1(raiz, destino, tabela):
    med = medianas(ler(raiz, "pp1"), "pp1", ("dataset",))
    datasets = sorted({c[0] for c in med}, key=lambda d: (d != "curitiba", d))
    if not datasets:
        return
    algoritmos = [a for a in ORDEM[1:] if any((d, a) in med for d in datasets)]
    fig, eixos = plt.subplots(1, len(datasets), figsize=(2.3 * len(datasets), 3.2), sharey=True, layout="constrained")
    eixos = eixos if len(datasets) > 1 else [eixos]
    todos = []
    for ax, d in zip(eixos, datasets):
        base = med[(d, BASELINE)][0]
        valores = [base / med[(d, a)][0] if (d, a) in med else float("nan") for a in algoritmos]
        todos += [v for v in valores if v == v]
        for a, v in zip(algoritmos, valores):
            tabela.append({"pp": "PP1", "regiao": nome_regiao(d), "algoritmo": a, "speedup": v})
        estilo(ax)
        ax.barh(range(len(algoritmos)), valores, height=0.62, color=SLOTS[0], zorder=2)
        ax.set_title(nome_regiao(d), fontsize=9, color=TINTA)
        ax.grid(axis="y", visible=False)
    for ax in eixos:
        escala_speedup(ax, "x", todos)
    eixos[0].set_yticks(range(len(algoritmos)), [NOMES[a] for a in algoritmos])
    eixos[0].invert_yaxis()
    fig.supxlabel("Speedup sobre o baseline (escala log; à direita de 1, o algoritmo ganhou)", fontsize=8, color=TINTA_2)
    salvar(fig, destino, "pp1_speedup", "PP1: speedup por algoritmo e conjunto de dados (64 partições, 8 workers)")


def pp2(raiz, destino, tabela):
    med = medianas(ler(raiz, "pp2"), "pp2", ("dataset", "workload"))
    regioes = sorted({c[0] for c in med})
    if not regioes:
        return
    algoritmos = [a for a in ORDEM[1:] if any(c[2] == a for c in med)]
    fig, eixos = plt.subplots(1, len(regioes), figsize=(5.2 * len(regioes), 3.4), sharey=True, layout="constrained")
    eixos = eixos if len(regioes) > 1 else [eixos]
    largura = 0.8 / len(algoritmos)
    todos = []
    for ax, d in zip(eixos, regioes):
        estilo(ax)
        for i, a in enumerate(algoritmos):
            ys = []
            for w in WORKLOADS:
                base, alg = med.get((d, w, BASELINE)), med.get((d, w, a))
                ys.append(base[0] / alg[0] if base and alg else float("nan"))
                tabela.append({"pp": "PP2", "regiao": nome_regiao(d), "workload": w, "algoritmo": a, "speedup": ys[-1]})
            todos += [y for y in ys if y == y]
            xs = [j + (i - (len(algoritmos) - 1) / 2) * largura for j in range(len(WORKLOADS))]
            ax.bar(xs, ys, width=largura * 0.88, color=SLOTS[i % len(SLOTS)], label=NOMES[a], zorder=2)
        ax.set_xticks(range(len(WORKLOADS)), list(WORKLOADS.values()))
        ax.set_title(nome_regiao(d), fontsize=9, color=TINTA)
        ax.grid(axis="x", visible=False)
    for ax in eixos:
        escala_speedup(ax, "y", todos)
    eixos[0].set_ylabel("Speedup sobre o baseline (log)", fontsize=8, color=TINTA_2)
    eixos[-1].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    salvar(fig, destino, "pp2_workloads", "PP2: speedup por workload (60 mil objetos em cada relação)", AVISO_BASELINE)


def pp3(raiz, destino, tabela):
    med = medianas(ler(raiz, "pp3"), "pp3", ("dataset", "gist"))
    regioes = sorted({c[0] for c in med})
    if not regioes:
        return
    algoritmos = [a for a in ORDEM if any(c[2] == a for c in med)]
    fig, eixos = plt.subplots(1, len(regioes), figsize=(5.0 * len(regioes), 3.4), layout="constrained")
    eixos = eixos if len(regioes) > 1 else [eixos]
    for ax, d in zip(eixos, regioes):
        estilo(ax)
        for i, (gist, rotulo) in enumerate((("on", "com GiST"), ("off", "sem GiST"))):
            ys = [med.get((d, gist, a), (float("nan"),))[0] / 1000 for a in algoritmos]
            for a, y in zip(algoritmos, ys):
                tabela.append({"pp": "PP3", "regiao": nome_regiao(d), "gist": gist, "algoritmo": a, "mediana_s": y})
            ax.bar([j + (i - 0.5) * 0.38 for j in range(len(algoritmos))], ys, width=0.34,
                   color=SLOTS[i], label=rotulo, zorder=2)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
        curtos = {BASELINE: "Sem part.", "TWO_LAYER": "Two-Layer", "BSP": "BSP", "STR": "STR", "HILBERT": "Hilbert"}
        ax.set_xticks(range(len(algoritmos)), [curtos[a] for a in algoritmos])
        ax.set_title(nome_regiao(d), fontsize=9, color=TINTA)
        ax.set_ylabel("Mediana por consulta (s, log)", fontsize=8, color=TINTA_2)
        ax.grid(axis="x", visible=False)
    eixos[-1].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    salvar(fig, destino, "pp3_indexacao", "PP3: tempo com e sem GiST (64 partições, 8 workers)", AVISO_BASELINE)


def grade_por_algoritmo(algoritmos, alto=2.2):
    colunas = 4
    linhas = -(-len(algoritmos) // colunas)
    fig, eixos = plt.subplots(linhas, colunas, figsize=(2.4 * colunas, alto * linhas), sharey=True, squeeze=False,
                             layout="constrained")
    planos = [ax for linha in eixos for ax in linha]
    for ax in planos[len(algoritmos):]:
        ax.set_visible(False)
    return fig, planos[:len(algoritmos)], planos[len(algoritmos):]


def linhas_por_regiao(ax, regioes, xs_por_regiao, ys_por_regiao):
    for i, d in enumerate(regioes):
        xs, ys = xs_por_regiao[d], ys_por_regiao[d]
        ax.plot(xs, ys, color=SLOTS[i], linewidth=2, marker="o", markersize=5,
                markeredgecolor="white", markeredgewidth=1.2, label=nome_regiao(d), zorder=3)


def pp4(raiz, destino, tabela):
    med = medianas(ler(raiz, "pp4"), "pp4", ("dataset", "workers_por_gather"))
    regioes = sorted({c[0] for c in med})
    if not regioes:
        return
    workers = sorted({int(c[1]) for c in med})
    algoritmos = [a for a in ORDEM if any(c[2] == a for c in med)]
    fig, eixos, livres = grade_por_algoritmo(algoritmos)
    for ax, a in zip(eixos, algoritmos):
        estilo(ax)
        xs, ys = {}, {}
        for d in regioes:
            serial = med[(d, "0", a)][0]
            xs[d] = list(range(len(workers)))
            ys[d] = [serial / med[(d, str(w), a)][0] for w in workers]
            for w, y in zip(workers, ys[d]):
                base = med[(d, str(w), BASELINE)][0]
                tabela.append({"pp": "PP4", "regiao": nome_regiao(d), "workers": w, "algoritmo": a,
                               "speedup_vs_serial": y, "speedup": base / med[(d, str(w), a)][0]})
        linhas_por_regiao(ax, regioes, xs, ys)
        ax.set_title(NOMES[a], fontsize=9, color=TINTA)
        ax.set_xticks(range(len(workers)), [str(w) for w in workers])
    for i, ax in enumerate(eixos):
        if i + 4 >= len(eixos):
            ax.set_xlabel("Workers", fontsize=8, color=TINTA_2)
    for ax in eixos[::4]:
        ax.set_ylabel("Speedup sobre o\npróprio caso serial", fontsize=8, color=TINTA_2)
    alvo = livres[0] if livres else eixos[-1]
    alvo.set_visible(True); alvo.axis("off")
    alvo.legend(*eixos[0].get_legend_handles_labels(), frameon=False, fontsize=8, loc="center", title="Região",
                title_fontsize=8)
    salvar(fig, destino, "pp4_escalabilidade", "PP4: escalabilidade de cada algoritmo com o número de workers",
           AVISO_BASELINE + " No SAMJ, foram lançados só 10 ou 11 workers nos limites 16 e 24, e o plano com "
           "1 worker cria um Gather por par de partições.")


def pp5(raiz, destino, tabela):
    linhas = ler(raiz, "pp5")
    med = medianas(linhas, "pp5", ("dataset", "particoes_alvo"))
    regioes = sorted({c[0] for c in med})
    if not regioes:
        return
    planejamento = {}
    for l in linhas:
        planejamento[(l["dataset"], l["particoes_alvo"], l["algoritmo"])] = float(l["planejamento_mediana_ms"])
    algoritmos = [a for a in ORDEM[1:] if any(c[2] == a for c in med)]
    alvos = sorted({int(c[1]) for c in med if c[1]})
    for nome, titulo, rotulo_y, valor in (
            ("pp5_granularidade", "PP5: speedup sobre o baseline por número de partições (8 workers)",
             "Speedup sobre o\nbaseline (log)", "speedup"),
            ("pp5_planejamento", "PP5: tempo de planejamento da consulta por número de partições",
             "Planejamento (ms, log)", "planejamento")):
        fig, eixos, livres = grade_por_algoritmo(algoritmos)
        todos = []
        for ax, a in zip(eixos, algoritmos):
            estilo(ax)
            xs, ys = {}, {}
            for d in regioes:
                base = med[(d, "", BASELINE)][0]
                pontos = [(i, alvo) for i, alvo in enumerate(alvos) if (d, str(alvo), a) in med]
                xs[d] = [i for i, _ in pontos]
                if valor == "speedup":
                    ys[d] = [base / med[(d, str(alvo), a)][0] for _, alvo in pontos]
                    for (_, alvo), y in zip(pontos, ys[d]):
                        tabela.append({"pp": "PP5", "regiao": nome_regiao(d), "particoes_alvo": alvo, "algoritmo": a,
                                       "speedup": y, "planejamento_ms": planejamento[(d, str(alvo), a)]})
                else:
                    ys[d] = [planejamento[(d, str(alvo), a)] for _, alvo in pontos]
                todos += ys[d]
            linhas_por_regiao(ax, regioes, xs, ys)
            ax.set_title(NOMES[a], fontsize=9, color=TINTA)
            ax.set_xticks(range(len(alvos)), [str(x) for x in alvos])
            ax.set_xlim(-0.4, len(alvos) - 0.6)
        for ax in eixos:
            if valor == "speedup":
                escala_speedup(ax, "y", todos)
            else:
                ax.set_yscale("log")
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
        for i, ax in enumerate(eixos):
            if i + 4 >= len(eixos):
                ax.set_xlabel("Partições (alvo)", fontsize=8, color=TINTA_2)
        for ax in eixos[::4]:
            ax.set_ylabel(rotulo_y, fontsize=8, color=TINTA_2)
        alvo_legenda = livres[0] if livres else eixos[-1]
        alvo_legenda.set_visible(True); alvo_legenda.axis("off")
        alvo_legenda.legend(*eixos[0].get_legend_handles_labels(), frameon=False, fontsize=8, loc="center",
                            title="Região", title_fontsize=8)
        nota = AVISO_BASELINE if valor == "speedup" else None
        if valor == "speedup":
            nota += " STR e Hilbert em MASJ foram medidos só com 4 e 64 partições."
        salvar(fig, destino, nome, titulo, nota)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultados", type=Path, default=Path("resultados/lab/final"))
    args = p.parse_args()
    destino = args.resultados / "resumo"
    destino.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "font.family": "DejaVu Sans"})
    tabela = []
    for etapa in (pp1, pp2, pp3, pp4, pp5):
        etapa(args.resultados, destino, tabela)
    campos = list(dict.fromkeys(k for linha in tabela for k in linha))
    with (destino / "resumo_geral.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in linha.items()} for linha in tabela)
    print(f"Resumo em {destino}: {len(tabela)} linhas na tabela e {len(list(destino.glob('*.png')))} figuras.")


if __name__ == "__main__":
    main()
