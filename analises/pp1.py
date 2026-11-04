"""Gera tabelas e figuras da PP1 a partir dos acumulados de consultas e perf."""

import argparse
from pathlib import Path

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

if __package__:
    from .perf import analisar_perf
else:
    from perf import analisar_perf


RESULTADOS_PADRAO = Path(__file__).resolve().parents[1] / "resultados" / "pp1"


def analisar(resultados=RESULTADOS_PADRAO):
    RAIZ = Path(resultados).resolve()
    ARQUIVO = RAIZ / "acumulado" / "consultas_acumulado.csv"
    SAIDA = RAIZ / "figuras"
    RESUMOS = RAIZ / "analise"

    SAIDA.mkdir(parents=True, exist_ok=True)
    RESUMOS.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(ARQUIVO)
    # A ausência do campo identifica as coletas anteriores à migração SAMJ.
    if "modelo_pp1" not in df:
        df["modelo_pp1"] = "legado_masj"
    df["modelo_pp1"] = df["modelo_pp1"].fillna("legado_masj").replace("", "legado_masj")

    # Garantir tipo numérico.
    df["tempo_cliente_ms"] = pd.to_numeric(
        df["tempo_cliente_ms"],
        errors="coerce"
    )

    df = df.dropna(subset=["tempo_cliente_ms"])


    # Ordem fixa para todos os gráficos.
    ORDEM = [
        "SEM_PARTICIONAMENTO",
        "TWO_LAYER",
        "STR",
        "HILBERT",
        "BSP",
        "STR_SAMJ",
        "HILBERT_SAMJ",
    ]


    # =========================================================
    # RESUMO ESTATÍSTICO
    # =========================================================

    resumo = (
        df.groupby(["modelo_pp1", "dataset", "cenario", "algoritmo"])["tempo_cliente_ms"]
        .agg(
            n="count",
            media_ms="mean",
            mediana_ms="median",
            desvio_ms="std",
            minimo_ms="min",
            maximo_ms="max",
        )
        .reset_index()
    )

    resumo["cv_percentual"] = (
        100.0 * resumo["desvio_ms"] / resumo["media_ms"]
    )

    resumo.to_csv(
        RESUMOS / "resumo_tempos.csv",
        index=False
    )


    # =========================================================
    # SPEEDUP
    # =========================================================

    speedups = []

    for (modelo, dataset, cenario), grupo in resumo.groupby(
        ["modelo_pp1", "dataset", "cenario"]
    ):
        baseline = grupo[
            grupo["algoritmo"] == "SEM_PARTICIONAMENTO"
        ]

        if baseline.empty:
            continue

        baseline_ms = baseline.iloc[0]["media_ms"]

        for _, linha in grupo.iterrows():
            speedups.append({
                "modelo_pp1": modelo,
                "dataset": dataset,
                "cenario": cenario,
                "algoritmo": linha["algoritmo"],
                "media_ms": linha["media_ms"],
                "speedup": baseline_ms / linha["media_ms"],
            })

    speedup_df = pd.DataFrame(speedups, columns=[
        "modelo_pp1", "dataset", "cenario", "algoritmo", "media_ms", "speedup"
    ])

    speedup_df.to_csv(
        RESUMOS / "speedup.csv",
        index=False
    )


    # =========================================================
    # GRÁFICOS POR CENÁRIO
    # =========================================================

    for (modelo, dataset, cenario), grupo in df.groupby(
        ["modelo_pp1", "dataset", "cenario"]
    ):

        sufixo = "" if modelo == "legado_masj" else "_" + str(modelo)

        presentes = [
            algoritmo
            for algoritmo in ORDEM
            if algoritmo in grupo["algoritmo"].unique()
        ]

        # -----------------------------------------------------
        # 1. BOXPLOT
        # -----------------------------------------------------

        dados = [
            grupo.loc[
                grupo["algoritmo"] == algoritmo,
                "tempo_cliente_ms"
            ].values
            for algoritmo in presentes
        ]

        plt.figure(figsize=(9, 5))

        plt.boxplot(
            dados,
            tick_labels=presentes,
            showmeans=True
        )

        plt.ylabel("Tempo de execução (ms)")
        plt.xlabel("Estratégia de particionamento")
        plt.title(
            f"Tempo de execução — {dataset} / {cenario} / {modelo}"
        )

        plt.xticks(rotation=25)
        plt.tight_layout()

        plt.savefig(
            SAIDA / f"tempo_boxplot_{dataset}_{cenario}{sufixo}.pdf"
        )
        plt.savefig(
            SAIDA / f"tempo_boxplot_{dataset}_{cenario}{sufixo}.png",
            dpi=300
        )

        plt.close()


        # -----------------------------------------------------
        # 2. MÉDIA + DESVIO PADRÃO
        # -----------------------------------------------------

        estatisticas = (
            grupo.groupby("algoritmo")["tempo_cliente_ms"]
            .agg(["mean", "std"])
            .reindex(presentes)
        )

        plt.figure(figsize=(9, 5))

        plt.bar(
            estatisticas.index,
            estatisticas["mean"],
            yerr=estatisticas["std"],
            capsize=5
        )

        plt.ylabel("Tempo médio (ms)")
        plt.xlabel("Estratégia de particionamento")
        plt.title(
            f"Tempo médio — {dataset} / {cenario} / {modelo}"
        )

        plt.xticks(rotation=25)
        plt.tight_layout()

        plt.savefig(
            SAIDA / f"tempo_medio_{dataset}_{cenario}{sufixo}.pdf"
        )
        plt.savefig(
            SAIDA / f"tempo_medio_{dataset}_{cenario}{sufixo}.png",
            dpi=300
        )

        plt.close()


        # -----------------------------------------------------
        # 3. SPEEDUP
        # -----------------------------------------------------

        s = speedup_df[
            (speedup_df["modelo_pp1"] == modelo)
            & (speedup_df["dataset"] == dataset)
            & (speedup_df["cenario"] == cenario)
        ].copy()

        if not s.empty:

            s["algoritmo"] = pd.Categorical(
                s["algoritmo"],
                categories=ORDEM,
                ordered=True
            )

            s = s.sort_values("algoritmo")

            plt.figure(figsize=(9, 5))

            plt.bar(
                s["algoritmo"].astype(str),
                s["speedup"]
            )

            plt.axhline(1.0, linestyle="--")

            plt.ylabel("Speedup em relação ao baseline")
            plt.xlabel("Estratégia de particionamento")
            plt.title(
                f"Speedup — {dataset} / {cenario} / {modelo}"
            )

            plt.xticks(rotation=25)
            plt.tight_layout()

            plt.savefig(
                SAIDA / f"speedup_{dataset}_{cenario}{sufixo}.pdf"
            )
            plt.savefig(
                SAIDA / f"speedup_{dataset}_{cenario}{sufixo}.png",
                dpi=300
            )

            plt.close()


    analisar_perf(RAIZ)

    print("Análise concluída.")
    print(f"Resumo: {RESUMOS / 'resumo_tempos.csv'}")
    print(f"Speedup: {RESUMOS / 'speedup.csv'}")
    print(f"Figuras: {SAIDA}")



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resultados", type=Path, default=RESULTADOS_PADRAO,
        help="Raiz dos resultados da PP1; padrão: resultados/pp1 do projeto.",
    )
    args = parser.parse_args()
    analisar(args.resultados)


if __name__ == "__main__":
    main()
