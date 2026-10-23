"""Análise descritiva de blocos de perf, sem modificar medições ou acumulados."""

import hashlib
import math
import re
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ORDEM = ["SEM_PARTICIONAMENTO", "TWO_LAYER", "STR", "HILBERT", "BSP"]
CHAVE = ["pp1_run_id", "execucao", "dataset", "cenario", "algoritmo", "rodada"]
METADADOS = ["hostname", "git_commit", "git_dirty"]
CONFIGURACAO = ["workers_por_gather", "indexacao", "particoes_alvo", "perf"]
CONTEXTO = CHAVE + METADADOS + CONFIGURACAO + ["escopo", "repeticoes"]
SOFTWARE = {"context-switches", "cpu-migrations", "page-faults"}
INDICADORES = {
    "ipc": ("instructions", "cycles", 1, "Instruções por ciclo (IPC)"),
    "cache_miss_percentual": (
        "cache-misses", "cache-references", 100, "Falhas de cache / referências (%)"
    ),
    "branch_miss_percentual": (
        "branch-misses", "branches", 100, "Falhas de desvio / desvios (%)"
    ),
}


def _numero(valor):
    try:
        numero = float(valor)
    except (ValueError, TypeError):
        return None
    return numero if math.isfinite(numero) else None


def _evento(nome):
    """Preserva PMU e modificadores: ciclos de :u não casam com instruções :k."""
    if "/" in nome:
        pmu, base, modificadores = nome.split("/", 2)
        return pmu, base, modificadores.lstrip(":")
    base, _, modificadores = nome.partition(":")
    return "software" if base in SOFTWARE else "cpu", base, modificadores


def preparar_contadores(perf, consultas):
    """Uma linha de saída por contador original; nenhuma expansão por repetição."""
    contadores = perf.copy().fillna("")
    for campo in CONTEXTO:
        if campo not in contadores:
            contadores[campo] = ""

    # A ligação usa a identidade do bloco, nunca cada uma das suas consultas.
    if not consultas.empty:
        contexto = consultas.copy().fillna("")
        for campo in CHAVE + CONFIGURACAO:
            if campo not in contexto:
                contexto[campo] = ""
        configuracoes = {}
        for chave, grupo in contexto.groupby(CHAVE, dropna=False, sort=False):
            configuracoes[chave] = {}
            for campo in CONFIGURACAO:
                valores = grupo[campo].astype(str).unique()
                if len(valores) != 1:
                    raise ValueError(f"Configuração inconsistente no bloco {chave}: {campo}")
                configuracoes[chave][campo] = valores[0]
        for indice, linha in contadores.iterrows():
            config = configuracoes.get(tuple(linha[campo] for campo in CHAVE), {})
            for campo, valor in config.items():
                contadores.at[indice, campo] = valor

    componentes = [_evento(str(nome)) for nome in contadores["evento"]]
    for indice, campo in enumerate(["pmu", "evento_base", "modificadores"]):
        contadores[campo] = [partes[indice] for partes in componentes]
    duplicados = contadores.duplicated(
        CHAVE + ["escopo", "pmu", "evento_base", "modificadores"], keep=False
    )
    valores, status, coberturas = [], [], []
    for indice, linha in contadores.iterrows():
        valor = _numero(linha["valor"])
        repeticoes = _numero(linha["repeticoes"])
        percentual = _numero(linha["percentual_ativo"])
        if percentual is None:
            cobertura = "desconhecida"
        elif not 0 < percentual <= 100:
            cobertura = "invalida"
        else:
            cobertura = "completa" if percentual == 100 else "multiplexado"
        motivo = "ok"
        if duplicados.loc[indice]:
            motivo = "evento_duplicado"
        elif linha["status"] != "ok":
            motivo = "perf_" + (str(linha["status"]) or "status_ausente")
        elif valor is None or valor < 0:
            motivo = "valor_invalido"
        elif repeticoes is None or repeticoes <= 0 or not repeticoes.is_integer():
            motivo = "repeticoes_invalidas"
        elif cobertura == "invalida":
            motivo = "cobertura_invalida"
        valores.append(valor / repeticoes if motivo == "ok" else None)
        status.append(motivo)
        coberturas.append(cobertura)
    contadores["valor_por_consulta"] = valores
    contadores["status_analise"] = status
    contadores["cobertura"] = coberturas
    return contadores


def calcular_metricas(contadores):
    colunas = CONTEXTO + [
        "pmu", "modificadores", "metrica", "numerador", "denominador",
        "valor", "status_analise", "percentual_ativo_minimo", "cobertura",
    ]
    metricas = []
    grupos = CHAVE + METADADOS + CONFIGURACAO + ["escopo", "pmu", "modificadores"]
    for _, grupo in contadores.groupby(grupos, dropna=False, sort=False):
        linha = grupo.iloc[0]
        for metrica, (numerador, denominador, fator, _) in INDICADORES.items():
            presentes = grupo[grupo["evento_base"].isin([numerador, denominador])]
            if presentes.empty:
                continue
            valores = {}
            motivo = "ok"
            for evento in [numerador, denominador]:
                evento_df = presentes[presentes["evento_base"] == evento]
                if evento_df.empty:
                    motivo = "evento_ausente:" + evento
                    break
                if len(evento_df) != 1 or evento_df.iloc[0]["status_analise"] != "ok":
                    motivo = "contador_invalido:" + evento
                    break
                valores[evento] = float(evento_df.iloc[0]["valor"])
            valor = None
            if motivo == "ok":
                if valores[denominador] == 0:
                    motivo = "denominador_zero"
                elif presentes["repeticoes"].astype(str).nunique() != 1:
                    motivo = "repeticoes_inconsistentes"
                else:
                    valor = fator * valores[numerador] / valores[denominador]
            percentual = [_numero(p) for p in presentes["percentual_ativo"]]
            cobertura = "desconhecida"
            if all(p is not None for p in percentual):
                cobertura = (
                    "completa" if all(p == 100 for p in percentual) else "multiplexado"
                )
                if any(not 0 < p <= 100 for p in percentual):
                    cobertura = "invalida"
            metricas.append({
                **{campo: linha[campo] for campo in CONTEXTO},
                "pmu": linha["pmu"], "modificadores": linha["modificadores"],
                "metrica": metrica, "numerador": numerador, "denominador": denominador,
                "valor": valor, "status_analise": motivo,
                "percentual_ativo_minimo": (
                    min(percentual) if all(p is not None for p in percentual) else None
                ),
                "cobertura": cobertura,
            })
    return pd.DataFrame(metricas, columns=colunas)


def _nome(texto):
    return re.sub(r"[^\w.-]+", "_", str(texto)) or "desconhecido"


def _grupos_figuras(tabela):
    facetas = (["pp1_run_id", "dataset", "cenario", "rodada", "escopo"] + METADADOS
               + [campo for campo in CONFIGURACAO if campo != "particoes_alvo"])
    for chaves, comparaveis in tabela.groupby(facetas, dropna=False, sort=False):
        baseline = comparaveis["algoritmo"] == "SEM_PARTICIONAMENTO"
        # A referência não particionada naturalmente tem o alvo vazio. Ela serve
        # de referência para cada alvo, sem alterar ou duplicar as tabelas de dados.
        alvos = set(comparaveis.loc[~baseline, "particoes_alvo"])
        alvos.update(comparaveis.loc[baseline & (comparaveis["particoes_alvo"] != ""),
                                    "particoes_alvo"])
        for alvo in sorted(alvos or {""}):
            grupo = comparaveis[(comparaveis["particoes_alvo"] == alvo)
                                | (baseline & (comparaveis["particoes_alvo"] == ""))]
            contexto = dict(zip(facetas, chaves))
            contexto["particoes_alvo"] = alvo
            yield (chaves, alvo), contexto, grupo


def _figuras(tabela, coluna_grupo, coluna_valor, raiz, indicador=False):
    # Não combina execuções globais, rodadas, máquinas ou configurações diferentes.
    for chaves, contexto, grupo in _grupos_figuras(tabela):
        pasta = raiz / "perf" / _nome(contexto["pp1_run_id"])
        pasta.mkdir(parents=True, exist_ok=True)
        for evento, dados in grupo.groupby(coluna_grupo, sort=False):
            if not (dados["status_analise"] == "ok").any():
                continue
            # Modificadores e PMUs distintos ficam em séries distintas.
            dados = dados.copy()
            dados["serie"] = dados["pmu"] + dados["modificadores"].map(
                lambda s: ":" + s if s else ""
            )
            # Blocos repetidos de uma mesma estratégia são mantidos separados.
            if dados.duplicated(["algoritmo", "serie"]).any():
                dados["serie"] += " / " + dados["execucao"]
            dados.loc[dados["status_analise"] != "ok", coluna_valor] = float("nan")
            valores = dados.pivot(index="algoritmo", columns="serie", values=coluna_valor)
            ordem = [a for a in ORDEM if a in valores.index]
            ordem += sorted(set(valores.index) - set(ordem))
            valores = valores.reindex(ordem)
            # Matplotlib converte NaN em barras de altura zero; marcar explicitamente ausências.
            ax = valores.plot.bar(figsize=(10, 5), rot=20)
            for barras, serie in zip(ax.containers, valores.columns):
                for barra, valor in zip(barras, valores[serie]):
                    if pd.isna(valor):
                        barra.set_visible(False)
                        ax.annotate("N/D", (barra.get_x() + barra.get_width() / 2, 0),
                                    ha="center", va="bottom", fontsize=7, rotation=90)
            ylabel = INDICADORES[evento][3] if indicador else "Contagem média por consulta"
            if not indicador:
                unidades = set(dados["unidade"]) - {""}
                if unidades:
                    ylabel = f"Valor médio por consulta ({', '.join(sorted(unidades))})"
            ax.set_ylabel(ylabel)
            ax.set_xlabel("Estratégia de particionamento")
            ax.set_title(f"{evento} — {contexto['dataset']} / {contexto['cenario']}")
            ax.text(0, 1.02, f"Rodada {contexto['rodada']} · {contexto['escopo']} · "
                    "uma medição por bloco", transform=ax.transAxes, fontsize=8)
            ax.legend(title="PMU / modificadores", fontsize=8)
            ax.figure.tight_layout()
            # O hash identifica toda a faceta sem nomes de arquivo excessivamente longos.
            identificador = hashlib.sha256(repr(chaves).encode()).hexdigest()[:12]
            nome = "_".join(_nome(contexto[c]) for c in ["dataset", "cenario", "rodada"])
            nome = (("metrica_" if indicador else "contador_") + _nome(evento)
                    + "_" + nome + "_" + identificador)
            for extensao in ["pdf", "png"]:
                ax.figure.savefig(pasta / f"{nome}.{extensao}", dpi=180)
            plt.close(ax.figure)


def analisar_perf(resultados):
    raiz = Path(resultados)
    entrada = raiz / "acumulado" / "perf_acumulado.csv"
    if not entrada.exists():
        print("Perf: acumulado ausente; análise de contadores ignorada.")
        return
    perf = pd.read_csv(entrada, dtype=str, keep_default_na=False)
    consultas = pd.read_csv(
        raiz / "acumulado" / "consultas_acumulado.csv", dtype=str, keep_default_na=False
    )
    contadores = preparar_contadores(perf, consultas)
    metricas = calcular_metricas(contadores)
    saida = raiz / "analise"
    saida.mkdir(parents=True, exist_ok=True)
    contadores.to_csv(saida / "contadores_perf.csv", index=False)
    metricas.to_csv(saida / "metricas_perf.csv", index=False)
    qualidade = (
        contadores.groupby(
            CONTEXTO + ["pmu", "status_analise", "cobertura"], dropna=False, sort=False
        ).size().rename("n_contadores").reset_index()
    )
    qualidade.to_csv(saida / "qualidade_perf.csv", index=False)
    _figuras(contadores, "evento_base", "valor_por_consulta", raiz / "figuras")
    _figuras(metricas, "metrica", "valor", raiz / "figuras", indicador=True)
    print(f"Perf: {len(contadores)} contadores e {len(metricas)} indicadores; "
          f"tabelas em {saida}, figuras em {raiz / 'figuras' / 'perf'}.")
    if len(contadores):
        problemas = (contadores["status_analise"] != "ok").sum()
        incompletos = (contadores["cobertura"] != "completa").sum()
        print(f"Perf: {problemas} contadores inválidos; "
              f"{incompletos} com cobertura parcial, desconhecida ou inválida.")
