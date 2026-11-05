"""Prepara e mede as combinações do PP1 usando psql e os particionadores Java."""

import argparse
import csv
from datetime import datetime, timezone
from math import isqrt
from pathlib import Path
import sys
import tempfile

from nucleo.arquivos import metadados_execucao, salvar_json
from nucleo.consolidacao import CONSULTAS, PERF, consolidar, imprimir_resumo
from nucleo.consultas import consulta_direta, consulta_particionada
from nucleo.experimento import ALGORITMOS, Experimento, LimiteExcedido
from nucleo.perf_coleta import argumentos_perf, verificar_perf


# STR, Hilbert e BSP seguem o MASJ de Aji, Vo e Wang (2015); as variantes medem a associação única à parte.
VARIANTES_SAMJ = {"STR_SAMJ": "STR", "HILBERT_SAMJ": "HILBERT"}
MODELO_PP1 = "masj_variantes_samj_workers_fixos_v3"
DATASETS = {
    "curitiba": {"cenario": "ruas_quadras", "tabelas": ("eixo_rua", "arruamento_quadras"),
                 "geom": "geom", "id": "gid", "srid": 31982,
                 "tipos": ("MultiLineString", "MultiPolygon"),
                 "tipos_origem": ("MultiLineString", "MultiPolygon")},
    "brasil": {"cenario": "brasil_line_polygon", "tabelas": ("brasil_line", "brasil_polygon"),
               "geom": "geom", "id": "benchmark_id", "srid": 3857,
               "tipos": ("MultiLineString", "MultiPolygon"),
               "tipos_origem": ("LineString", "Polygon")},
    # Recortes de experimentos/regioes/criar_regioes.sql.
    # O sufixo _mapa usa os polígonos sem limites administrativos (filtrar_limites.sql).
    **{nome + sufixo: {"cenario": "linha_poligono", "schema": "regioes",
                       "tabelas": (f"{nome}_line", f"{nome}_polygon{sufixo}"),
                       "geom": "geom", "id": "benchmark_id", "srid": 3857,
                       "tipos": ("MultiLineString", "MultiPolygon"), "tipos_origem": ("LineString", "Polygon")}
       for nome in ("es_sul", "ms_campo_grande", "pr_centro", "pr_curitiba") for sufixo in ("", "_mapa")},
}


def atualizar_acumulados(base):
    try:
        imprimir_resumo(consolidar(base))
    except Exception as erro:
        # Pós-processamento: o manifesto concluído e os arquivos brutos já estão salvos.
        print(f"Aviso: não foi possível atualizar os acumulados: {erro}. "
              f"Os resultados brutos permanecem concluídos. Tente python3 consolidar.py pp1 --entrada {base}",
              file=sys.stderr)


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", default="benchmark")
    parser.add_argument("--host")
    parser.add_argument("--porta", type=int)
    parser.add_argument("--usuario")
    parser.add_argument("--pedir-senha", action="store_true", help="Solicita a senha uma vez para todos os processos psql.")
    parser.add_argument("--datasets", nargs="+", choices=DATASETS, default=["curitiba", "brasil"])
    parser.add_argument("--algoritmos", nargs="+", choices=(*ALGORITMOS, *VARIANTES_SAMJ),
                        default=[*ALGORITMOS, *VARIANTES_SAMJ])
    parser.add_argument("--limite-consulta-min", type=float, default=120,
                        help="Tempo máximo de cada consulta medida, em minutos; ao estourar, o caso é registrado "
                             "como nao_concluiu e a execução segue (padrão: 120; 0 desativa).")
    parser.add_argument("--particoes", type=int, default=64, help="Granularidade-alvo (padrão: 64).")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--aquecimentos", type=int, default=3)
    parser.add_argument("--repeticoes", type=int, default=10)
    parser.add_argument("--rodada", type=int, default=1)
    parser.add_argument("--hilbert-bits", type=int, default=16)
    parser.add_argument("--bsp-tentativas", type=int, default=8)
    parser.add_argument("--id-curitiba", default="gid", help="Coluna de ID único nas duas entradas de Curitiba.")
    parser.add_argument("--id-brasil", default="benchmark_id", help="Coluna de ID único nas duas entradas do Brasil.")
    parser.add_argument("--saida", type=Path, default=Path("resultados/pp1"))
    parser.add_argument("--simular", action="store_true", help="Mostra a matriz sem conectar, compilar ou alterar tabelas.")
    argumentos_perf(parser)
    args = parser.parse_args()
    if args.workers < 0 or args.aquecimentos < 0 or args.repeticoes < 1 or args.limite_consulta_min < 0:
        parser.error("Use workers >= 0, aquecimentos >= 0, repeticoes >= 1 e limite-consulta-min >= 0.")
    if args.particoes < 1 or args.bsp_tentativas < 1:
        parser.error("Partições e tentativas BSP devem ser positivas.")
    if not 1 <= args.hilbert_bits <= 16:
        parser.error("Bits Hilbert devem estar entre 1 e 16.")
    if args.porta is not None and not 1 <= args.porta <= 65535:
        parser.error("Porta deve estar entre 1 e 65535.")
    if "TWO_LAYER" in args.algoritmos and isqrt(args.particoes) ** 2 != args.particoes:
        parser.error("Two-Layer requer --particoes igual a um quadrado perfeito, como 16, 64 ou 256.")
    if args.perf and not args.perf_eventos.strip():
        parser.error("Informe ao menos um evento em --perf-eventos.")
    args.datasets = list(dict.fromkeys(args.datasets))
    args.algoritmos = list(dict.fromkeys(args.algoritmos))
    return args


def executar(args):
    if args.simular:
        for nome in args.datasets:
            for algoritmo in args.algoritmos:
                print(f"{nome}: {DATASETS[nome]['cenario']} / {algoritmo}; "
                      f"GiST=on; workers={args.workers}; alvo={args.particoes if algoritmo != 'SEM_PARTICIONAMENTO' else 'N/A'}; "
                      f"limite={args.limite_consulta_min:g} min; perf={'on' if args.perf else 'off'}")
        return
    pasta = args.saida.resolve() / ("pp1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True, exist_ok=False)
    config = {**vars(args), "saida": str(pasta), "indexacao": "on", "modelo_pp1": MODELO_PP1,
              **metadados_execucao(pasta.name)}
    salvar_json(pasta / "configuracao.json", config)
    experimento = Experimento(args, pasta)
    manifesto = {"status": "em_execucao", "combinacoes": []}
    try:
        if args.perf:
            print("Verificando eventos e permissões do perf antes da preparação...", flush=True)
            verificar_perf(args.perf_eventos, pasta, experimento.ambiente)
        if any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos):
            print("Compilando os particionadores Java...", flush=True)
            experimento.processo(["mvn", "-q", "compile"], pasta / "compilacao.log")
        # Todas as combinações são sequenciais: as saídas SQL são compartilhadas.
        with (pasta / "consultas.csv").open("w", newline="", encoding="utf-8") as consolidado:
            writer = None
            for nome in args.datasets:
                dataset = {**DATASETS[nome], "id": getattr(args, "id_" + nome, DATASETS[nome]["id"])}
                destino = pasta / nome
                destino.mkdir()
                print(f"Validando entradas e GiST de {nome}...", flush=True)
                experimento.preparar_entradas(dataset, destino)
                esperado = int(experimento.sql(experimento.configuracao_sessao() + "\n" + consulta_direta(dataset),
                                               destino / "contagem_baseline"))
                with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temporario:
                    entradas = Path(temporario)
                    if any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos):
                        experimento.exportar(dataset, entradas, destino)
                    for algoritmo in args.algoritmos:
                        print(f"Executando {nome} / {algoritmo}...", flush=True)
                        caso = destino / algoritmo.lower()
                        caso.mkdir()
                        registro = {"dataset": nome, "algoritmo": algoritmo, "status": "em_execucao"}
                        manifesto["combinacoes"].append(registro)
                        salvar_json(pasta / "manifesto.json", manifesto)
                        metadata = {"particoes_efetivas": None, "capacidade": None}
                        consulta = consulta_direta(dataset)
                        if algoritmo != "SEM_PARTICIONAMENTO":
                            base = VARIANTES_SAMJ.get(algoritmo, algoritmo)
                            with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=caso) as trabalho:
                                metadata = experimento.particionar(
                                    base, entradas, Path(trabalho), caso,
                                    associacao_unica=algoritmo in VARIANTES_SAMJ)
                                experimento.materializar(dataset, Path(trabalho), metadata, caso, normalizar_multi=False)
                            consulta = consulta_particionada(base, metadata)
                        try:
                            medicoes = experimento.medir(dataset, algoritmo, consulta, esperado, caso)
                        except LimiteExcedido as erro:
                            print(f"  Não concluiu: {erro}", flush=True)
                            registro.update(status="nao_concluiu", limite_consulta_min=args.limite_consulta_min,
                                            modelo_join=metadata.get("modelo_join", "DIRETO"),
                                            particoes_efetivas=metadata["particoes_efetivas"])
                            salvar_json(pasta / "manifesto.json", manifesto)
                            continue
                        finally:
                            if algoritmo == "SEM_PARTICIONAMENTO":
                                experimento.restaurar_workers(dataset, caso)
                        with medicoes.open(newline="", encoding="utf-8") as arquivo:
                            for linha in csv.DictReader(arquivo):
                                linha.update(dataset=nome, particoes_alvo=args.particoes if algoritmo != "SEM_PARTICIONAMENTO" else "",
                                             particoes_efetivas=metadata["particoes_efetivas"], capacidade=metadata["capacidade"],
                                             modelo_pp1=MODELO_PP1,
                                             modelo_join=metadata.get("modelo_join", "DIRETO"))
                                if writer is None:
                                    writer = csv.DictWriter(consolidado, fieldnames=list(linha))
                                    writer.writeheader()
                                writer.writerow(linha)
                        consolidado.flush()
                        registro.update(status="concluido", intersecoes=esperado,
                                        particoes_efetivas=metadata["particoes_efetivas"])
                        salvar_json(pasta / "manifesto.json", manifesto)
            # Se nenhum caso terminou, o cabeçalho mantém a execução válida para a consolidação.
            if writer is None:
                csv.writer(consolidado).writerow(CONSULTAS)
        if args.perf:
            arquivos_perf = sorted(pasta.glob("*/*/medicoes/*/perf.csv"))
            with (pasta / "perf.csv").open("w", newline="", encoding="utf-8") as consolidado:
                writer_perf = None
                if not arquivos_perf:
                    csv.writer(consolidado).writerow(PERF)
                for arquivo_perf in arquivos_perf:
                    with arquivo_perf.open(newline="", encoding="utf-8") as arquivo:
                        for linha in csv.DictReader(arquivo):
                            linha["dataset"] = arquivo_perf.relative_to(pasta).parts[0]
                            linha["modelo_pp1"] = MODELO_PP1
                            if writer_perf is None:
                                writer_perf = csv.DictWriter(consolidado, fieldnames=list(linha))
                                writer_perf.writeheader()
                            writer_perf.writerow(linha)
        manifesto["status"] = "concluido"
    except (RuntimeError, OSError, ValueError, StopIteration, KeyboardInterrupt) as erro:
        manifesto.update(status="falhou", erro=str(erro))
        if manifesto["combinacoes"] and manifesto["combinacoes"][-1]["status"] == "em_execucao":
            manifesto["combinacoes"][-1]["status"] = "falhou"
        raise SystemExit(f"PP1 interrompido: {erro}\nResultados e logs: {pasta}") from erro
    finally:
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP1 concluído. CSV consolidado: {pasta / 'consultas.csv'}", flush=True)
    for registro in manifesto["combinacoes"]:
        if registro["status"] == "nao_concluiu":
            print(f"Não concluiu em {args.limite_consulta_min:g} min: {registro['dataset']} / {registro['algoritmo']}", flush=True)
    atualizar_acumulados(pasta.parent)


if __name__ == "__main__":
    executar(argumentos())
