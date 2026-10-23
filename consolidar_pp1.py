"""Reconstrói os acumulados a partir dos CSVs brutos de execuções PP1 concluídas."""

import argparse
import csv
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile


METADADOS = ("pp1_run_id", "hostname", "git_commit", "git_dirty")
CONSULTAS = (
    "execucao", "cenario", "algoritmo", "rodada", "repeticao", "aquecimentos",
    "tempo_cliente_ms", "workers_por_gather", "indexacao", "intersecoes", "perf",
    "dataset", "particoes_alvo", "particoes_efetivas", "capacidade",
)
PERF = (
    "execucao", "cenario", "algoritmo", "rodada", "repeticoes", "escopo", "evento",
    "valor", "unidade", "status", "tempo_ativo_ns", "percentual_ativo", "dataset",
)


class ErroConsolidacao(RuntimeError):
    pass


@dataclass(frozen=True)
class Fonte:
    caminho: Path
    colunas: tuple
    metadados: dict


@dataclass(frozen=True)
class Resumo:
    encontradas: int
    concluidas: int
    ignoradas: int
    execucoes_consultas: int
    linhas_consultas: int
    execucoes_perf: int
    linhas_perf: int
    arquivo_consultas: Path
    arquivo_perf: Path
    avisos: tuple


def ler_json(caminho):
    with caminho.open(encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, dict):
        raise ValueError("Era esperado um objeto JSON")
    return dados


def fonte_csv(caminho, metadados):
    try:
        with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
            colunas = csv.DictReader(arquivo, strict=True).fieldnames
        if not colunas or any(not coluna for coluna in colunas) or len(set(colunas)) != len(colunas):
            raise ValueError("Cabeçalho ausente, vazio ou com colunas repetidas")
    except (OSError, ValueError, csv.Error) as erro:
        raise ErroConsolidacao(f"CSV de execução concluída inválido: {caminho}: {erro}") from erro
    return Fonte(caminho, tuple(colunas), metadados)


def listar_fontes(base):
    pastas = sorted(p for p in base.glob("pp1_*") if p.is_dir())
    consultas, perf, avisos = [], [], []
    concluidas = 0
    for pasta in pastas:
        try:
            manifesto = ler_json(pasta / "manifesto.json")
        except (OSError, ValueError) as erro:
            avisos.append(f"Ignorada {pasta.name}: manifesto ausente ou inválido ({erro}).")
            continue
        if manifesto.get("status") != "concluido":
            continue
        concluidas += 1
        try:
            config = ler_json(pasta / "configuracao.json")
        except (OSError, ValueError) as erro:
            config = {}
            avisos.append(f"{pasta.name}: metadados indisponíveis ({erro}); campos desconhecidos ficam vazios.")
        # O nome da pasta é a origem global; nunca inferir host/commit antigos da máquina atual.
        metadados = {"pp1_run_id": pasta.name}
        for campo in ("hostname", "git_commit"):
            valor = config.get(campo)
            metadados[campo] = valor if isinstance(valor, str) else None
        dirty = config.get("git_dirty")
        metadados["git_dirty"] = str(dirty).lower() if isinstance(dirty, bool) else None
        consultas.append(fonte_csv(pasta / "consultas.csv", metadados))
        arquivo_perf = pasta / "perf.csv"
        if arquivo_perf.exists():
            perf.append(fonte_csv(arquivo_perf, metadados))
        elif config.get("perf") is True:
            raise ErroConsolidacao(f"Execução concluída com perf habilitado, mas sem {arquivo_perf}.")
    return pastas, concluidas, consultas, perf, avisos


def preparar_csv(destino, nome, fontes, colunas_padrao):
    # União estável dos cabeçalhos: mantém colunas de versões antigas e futuras.
    colunas = list(METADADOS)
    for fonte in fontes:
        colunas.extend(c for c in fonte.colunas if c not in colunas)
    if not fontes:
        colunas.extend(c for c in colunas_padrao if c not in colunas)
    linhas, execucoes = 0, 0
    with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8",
                                     prefix=f".{nome}-", suffix=".tmp", dir=destino, delete=False) as arquivo:
        temporario = Path(arquivo.name)
        try:
            writer = csv.DictWriter(arquivo, fieldnames=colunas)
            writer.writeheader()
            for fonte in fontes:
                quantidade = 0
                try:
                    with fonte.caminho.open(newline="", encoding="utf-8-sig") as entrada:
                        reader = csv.DictReader(entrada, strict=True)
                        if tuple(reader.fieldnames or ()) != fonte.colunas:
                            raise ValueError("O cabeçalho mudou durante a consolidação")
                        for linha in reader:
                            if None in linha or any(valor is None for valor in linha.values()):
                                raise ValueError(f"Linha {reader.line_num} com quantidade de campos diferente do cabeçalho")
                            writer.writerow({**linha, **fonte.metadados})
                            quantidade += 1
                except (OSError, ValueError, csv.Error) as erro:
                    raise ErroConsolidacao(f"Não foi possível ler {fonte.caminho}: {erro}") from erro
                linhas += quantidade
                execucoes += quantidade > 0
            arquivo.flush()
            os.fsync(arquivo.fileno())
        except BaseException:
            temporario.unlink(missing_ok=True)
            raise
    return temporario, linhas, execucoes


def consolidar(base=Path("resultados/pp1")):
    base = Path(base).resolve()
    if base.name.startswith("pp1_") and (
        re.fullmatch(r"pp1_[0-9]{8}T[0-9]{6,}Z", base.name)
        or any((base / nome).exists() for nome in ("manifesto.json", "configuracao.json", "consultas.csv", "perf.csv"))
    ):
        raise ErroConsolidacao("Informe a pasta que contém as execuções PP1, não uma execução bruta individual.")
    destino = base / "acumulado"
    if destino.is_symlink():
        raise ErroConsolidacao(f"A pasta de saída não pode ser um link simbólico: {destino}")
    destino.mkdir(parents=True, exist_ok=True)
    arquivo_consultas = destino / "consultas_acumulado.csv"
    arquivo_perf = destino / "perf_acumulado.csv"
    # Serializa reconstruções manuais/automáticas que possam ocorrer ao mesmo tempo no Linux.
    with (destino / ".consolidacao.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pastas, concluidas, consultas, perf, avisos = listar_fontes(base)
        temporarios = []
        try:
            consultas_tmp, linhas_consultas, execucoes_consultas = preparar_csv(
                destino, "consultas", consultas, CONSULTAS)
            temporarios.append(consultas_tmp)
            perf_tmp, linhas_perf, execucoes_perf = preparar_csv(destino, "perf", perf, PERF)
            temporarios.append(perf_tmp)
            # Ambos são construídos antes de substituir qualquer acumulado existente.
            os.replace(consultas_tmp, arquivo_consultas)
            os.replace(perf_tmp, arquivo_perf)
        finally:
            for caminho in temporarios:
                caminho.unlink(missing_ok=True)
    return Resumo(len(pastas), concluidas, len(pastas) - concluidas, execucoes_consultas,
                  linhas_consultas, execucoes_perf, linhas_perf, arquivo_consultas, arquivo_perf, tuple(avisos))


def imprimir_resumo(resumo):
    print(f"Execuções PP1 encontradas: {resumo.encontradas}")
    print(f"Execuções concluídas: {resumo.concluidas}")
    print(f"Execuções ignoradas: {resumo.ignoradas}")
    if not resumo.concluidas:
        print("Não existem resultados PP1 concluídos para consolidar; foram criados CSVs apenas com cabeçalhos.")
    print(f"\nconsultas_acumulado.csv:\n  execuções: {resumo.execucoes_consultas}\n  linhas: {resumo.linhas_consultas}")
    print(f"\nperf_acumulado.csv:\n  execuções com perf: {resumo.execucoes_perf}\n  linhas: {resumo.linhas_perf}")
    print(f"\nArquivos:\n  {resumo.arquivo_consultas}\n  {resumo.arquivo_perf}")
    for aviso in resumo.avisos:
        print(f"Aviso: {aviso}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path("resultados/pp1"),
                        help="Pasta que contém pp1_* (padrão: resultados/pp1); saída em acumulado/.")
    args = parser.parse_args()
    try:
        imprimir_resumo(consolidar(args.entrada))
    except (ErroConsolidacao, OSError) as erro:
        parser.exit(1, f"Consolidação PP1 não concluída: {erro}\n")


if __name__ == "__main__":
    main()
