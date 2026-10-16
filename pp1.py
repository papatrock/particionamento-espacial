"""Prepara e mede as combinações do PP1 usando psql e os particionadores Java."""

import argparse
import csv
from datetime import datetime, timezone
from getpass import getpass
import json
from math import isqrt
import os
from pathlib import Path
import subprocess
import sys
import tempfile


RAIZ = Path(__file__).resolve().parent
ALGORITMOS = ("SEM_PARTICIONAMENTO", "TWO_LAYER", "STR", "HILBERT", "BSP")
SAIDA_A = 'public."tabela_a_particionada"'
SAIDA_B = 'public."tabela_b_particionada"'
DATASETS = {
    "curitiba": {"cenario": "ruas_quadras", "tabelas": ("eixo_rua", "arruamento_quadras"),
                 "geom": "geom", "id": "gid", "srid": 31982,
                 "tipos": ("MultiLineString", "MultiPolygon")},
    "brasil": {"cenario": "brasil_line_polygon", "tabelas": ("brasil_line", "brasil_polygon"),
               "geom": "geom", "id": "osm_id", "srid": 3857,
               "tipos": ("MultiLineString", "MultiPolygon")},
}


def identificador(nome):
    return '"' + nome.replace('"', '""') + '"'


def literal(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def salvar_json(caminho, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", default="benchmark")
    parser.add_argument("--host")
    parser.add_argument("--porta", type=int)
    parser.add_argument("--usuario")
    parser.add_argument("--pedir-senha", action="store_true", help="Solicita a senha uma vez para todos os processos psql.")
    parser.add_argument("--datasets", nargs="+", choices=DATASETS, default=list(DATASETS))
    parser.add_argument("--algoritmos", nargs="+", choices=ALGORITMOS, default=list(ALGORITMOS))
    parser.add_argument("--particoes", type=int, default=64, help="Granularidade-alvo (padrão: 64).")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--aquecimentos", type=int, default=3)
    parser.add_argument("--repeticoes", type=int, default=10)
    parser.add_argument("--rodada", type=int, default=1)
    parser.add_argument("--hilbert-bits", type=int, default=16)
    parser.add_argument("--bsp-tentativas", type=int, default=8)
    parser.add_argument("--id-curitiba", default="gid", help="Coluna de ID único nas duas entradas de Curitiba.")
    parser.add_argument("--id-brasil", default="osm_id", help="Coluna de ID único nas duas entradas do Brasil.")
    parser.add_argument("--saida", type=Path, default=Path("resultados/pp1"))
    parser.add_argument("--simular", action="store_true", help="Mostra a matriz sem conectar, compilar ou alterar tabelas.")
    args = parser.parse_args()
    if args.workers < 0 or args.aquecimentos < 0 or args.repeticoes < 1:
        parser.error("Use workers >= 0, aquecimentos >= 0 e repeticoes >= 1.")
    if args.particoes < 1 or args.bsp_tentativas < 1:
        parser.error("Partições e tentativas BSP devem ser positivas.")
    if not 1 <= args.hilbert_bits <= 16:
        parser.error("Bits Hilbert devem estar entre 1 e 16.")
    if args.porta is not None and not 1 <= args.porta <= 65535:
        parser.error("Porta deve estar entre 1 e 65535.")
    if "TWO_LAYER" in args.algoritmos and isqrt(args.particoes) ** 2 != args.particoes:
        parser.error("Two-Layer requer --particoes igual a um quadrado perfeito, como 16, 64 ou 256.")
    args.datasets = list(dict.fromkeys(args.datasets))
    args.algoritmos = list(dict.fromkeys(args.algoritmos))
    return args


class Experimento:
    def __init__(self, args, pasta):
        self.args = args
        self.pasta = pasta
        self.ambiente = os.environ.copy()
        self.ambiente["LC_ALL"] = "C"
        if args.pedir_senha:
            self.ambiente["PGPASSWORD"] = getpass("Senha do PostgreSQL: ")
        self.psql = ["psql", "-X", "-q", "-A", "-t", "--set=ON_ERROR_STOP=1", "--dbname", args.banco]
        self.conexao = ["--banco", args.banco]
        for flag, nome, valor in (("--host", "--host", args.host), ("--port", "--porta", args.porta),
                                   ("--username", "--usuario", args.usuario)):
            if valor is not None:
                self.psql.extend([flag, str(valor)])
                self.conexao.extend([nome, str(valor)])

    def sql(self, consulta, destino):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.with_suffix(".sql").write_text(consulta + "\n", encoding="utf-8")
        resultado = subprocess.run(self.psql, input=consulta + "\n", text=True,
                                   capture_output=True, env=self.ambiente)
        destino.with_suffix(".stdout.log").write_text(resultado.stdout, encoding="utf-8")
        destino.with_suffix(".stderr.log").write_text(resultado.stderr, encoding="utf-8")
        if resultado.returncode:
            raise RuntimeError(f"psql falhou: {resultado.stderr.strip()} (logs: {destino.parent})")
        return resultado.stdout.strip()

    def processo(self, comando, destino):
        # stderr herdado permite ao psql solicitar senha no terminal.
        with destino.open("w", encoding="utf-8") as log:
            resultado = subprocess.run(comando, cwd=RAIZ, stdout=log, env=self.ambiente)
        if resultado.returncode:
            raise RuntimeError(f"Processo falhou; consulte {destino} e a saída de erro no terminal.")

    def configuracao_sessao(self):
        return (f"SET max_parallel_workers_per_gather = {self.args.workers};\n"
                "SET enable_partitionwise_join = on;\nSET enable_seqscan = on;\n"
                "SET enable_indexscan = on;\nSET enable_indexonlyscan = on;\nSET enable_bitmapscan = on;")

    def preparar_entradas(self, dataset, pasta):
        registros = []
        for nome in dataset["tabelas"]:
            tabela = "public." + identificador(nome)
            geom, coluna_id = identificador(dataset["geom"]), identificador(dataset["id"])
            consulta = f"""SELECT json_build_object(
                'registros', COUNT(*), 'ids', COUNT({coluna_id}),
                'ids_distintos', COUNT(DISTINCT {coluna_id}::bigint),
                'geometrias_nulas', COUNT(*) FILTER (WHERE {geom} IS NULL),
                'srid_incorreto', COUNT(*) FILTER (WHERE ST_SRID({geom}) <> {dataset['srid']}),
                'geometrias_vazias', COUNT(*) FILTER (WHERE ST_IsEmpty({geom}))) FROM {tabela};"""
            info = json.loads(self.sql(consulta, pasta / (nome + "_validacao")))
            if info["registros"] != info["ids"] or info["ids"] != info["ids_distintos"]:
                raise RuntimeError(f"{tabela}: a coluna {dataset['id']} precisa ter IDs únicos e não nulos. "
                                   "Use --id-curitiba ou --id-brasil para indicar uma chave adequada.")
            if info["geometrias_nulas"] or info["srid_incorreto"]:
                raise RuntimeError(f"{tabela}: geometria nula ou SRID diferente de {dataset['srid']}.")
            registros.append({"tabela": nome, **info})
            # Reutiliza GiST válido sobre a coluna; evita duplicar um índice já existente.
            indice = identificador(f"idx_pp1_{nome}_geom")
            sql_indice = f"""DO $pp1$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                    JOIN pg_am am ON am.oid = c.relam
                    WHERE i.indrelid = {literal(tabela)}::regclass
                    AND i.indisvalid AND i.indisready AND i.indpred IS NULL AND i.indexprs IS NULL
                    AND am.amname = 'gist'
                    AND (SELECT attnum FROM pg_attribute WHERE attrelid = i.indrelid
                         AND attname = {literal(dataset['geom'])}) = ANY(i.indkey)
                ) THEN CREATE INDEX {indice} ON {tabela} USING GIST ({geom}); END IF;
                END $pp1$;
                ANALYZE {tabela};"""
            self.sql(sql_indice, pasta / (nome + "_gist"))
        salvar_json(pasta / "entradas.json", registros)

    def exportar(self, dataset, trabalho, pasta):
        for lado, nome in zip(("a", "b"), dataset["tabelas"]):
            tabela = "public." + identificador(nome)
            geom, coluna_id = identificador(dataset["geom"]), identificador(dataset["id"])
            # ST_AsText retorna WKT em uma linha; ordem estável é necessária para BSP.
            consulta = (f"\\copy (SELECT {coluna_id}::bigint, ST_AsText({geom}) FROM {tabela} "
                        f"WHERE NOT ST_IsEmpty({geom}) ORDER BY {coluna_id}) TO "
                        f"{literal(trabalho / (lado + '.tsv'))}")
            self.sql(consulta, pasta / (lado + "_exportacao"))

    def particionar(self, algoritmo, entradas, trabalho, pasta):
        comando = ["mvn", "-q", "exec:java", "-Dexec.mainClass=benchmark.PP1ExperimentRunner",
                   f"-Dpp1.algoritmo={algoritmo}", f"-Dpp1.particoes={self.args.particoes}",
                   f"-Dpp1.hilbertBits={self.args.hilbert_bits}", f"-Dpp1.bspTentativas={self.args.bsp_tentativas}",
                   f"-Dpp1.entradaA={entradas / 'a.tsv'}", f"-Dpp1.entradaB={entradas / 'b.tsv'}",
                   f"-Dpp1.saida={trabalho}"]
        self.processo(comando, pasta / "java.log")
        metadados = json.loads((trabalho / "particionamento.json").read_text(encoding="utf-8"))
        salvar_json(pasta / "particionamento.json", metadados)
        print(f"  Partições efetivas: {metadados['particoes_efetivas']}; alvo: {self.args.particoes}", flush=True)
        return metadados

    def materializar(self, dataset, trabalho, metadados, pasta):
        comandos = ["BEGIN;", f"DROP TABLE IF EXISTS {SAIDA_A} CASCADE;",
                    f"DROP TABLE IF EXISTS {SAIDA_B} CASCADE;"]
        for lado, tabela, tipo in zip(("a", "b"), (SAIDA_A, SAIDA_B), dataset["tipos"]):
            comandos.append(f"CREATE TABLE {tabela} (id BIGINT NOT NULL, id_particao INTEGER NOT NULL, "
                            "classe CHAR(1) NOT NULL CHECK (classe IN ('A','B','C','D')), "
                            f"geom geometry({tipo}, {dataset['srid']})) PARTITION BY LIST (id_particao);")
            for ocupacao in metadados["ocupacoes"]:
                particao = int(ocupacao["id"])
                comandos.append(f"CREATE TABLE public.tabela_{lado}_p{particao} PARTITION OF {tabela} "
                                f"FOR VALUES IN ({particao});")
            comandos.extend([
                "CREATE TEMP TABLE pp1_carga (id BIGINT, id_particao INTEGER, classe CHAR(1), wkt TEXT) ON COMMIT DROP;",
                f"\\copy pp1_carga FROM {literal(trabalho / (lado + '.tsv'))}",
                f"INSERT INTO {tabela} SELECT id, id_particao, classe, "
                f"ST_Multi(ST_GeomFromText(wkt, {dataset['srid']})) FROM pp1_carga;",
                "DROP TABLE pp1_carga;",
                f"CREATE INDEX idx_tabela_{lado}_geom ON {tabela} USING GIST (geom);",
                f"ANALYZE {tabela};",
            ])
        comandos.append("COMMIT;")
        self.sql("\n".join(comandos), pasta / "materializacao")

    def medir(self, dataset, algoritmo, consulta, esperado, pasta):
        arquivo = pasta / "consulta.sql"
        arquivo.write_text(consulta + "\n", encoding="utf-8")
        self.processo([
            sys.executable, str(RAIZ / "coletar_consultas.py"), *self.conexao,
            "--cenario", dataset["cenario"], "--algoritmo", algoritmo, "--sql", str(arquivo),
            "--workers", str(self.args.workers), "--indexacao", "on",
            "--aquecimentos", str(self.args.aquecimentos), "--repeticoes", str(self.args.repeticoes),
            "--rodada", str(self.args.rodada), "--contagem-esperada", str(esperado),
            "--saida", str(pasta / "medicoes"),
        ], pasta / "coletor.log")
        plano = self.sql(self.configuracao_sessao() + "\nEXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + consulta,
                         pasta / "plano")
        salvar_json(pasta / "plano.json", json.loads(plano))
        return next((pasta / "medicoes").glob("*/consultas.csv"))


def consulta_direta(dataset):
    a, b = ("public." + identificador(t) for t in dataset["tabelas"])
    geom = identificador(dataset["geom"])
    return f"SELECT COUNT(*) FROM {a} a JOIN {b} b ON ST_Intersects(a.{geom}, b.{geom});"


def consulta_particionada(algoritmo):
    condicao = "a.id_particao = b.id_particao AND ST_Intersects(a.geom, b.geom)"
    if algoritmo == "TWO_LAYER":
        classes = "(a.classe = 'A' OR b.classe = 'A' OR (a.classe = 'B' AND b.classe = 'C') OR (a.classe = 'C' AND b.classe = 'B'))"
        return f"SELECT COUNT(*) FROM {SAIDA_A} a JOIN {SAIDA_B} b ON {condicao} AND {classes};"
    return (f"SELECT COUNT(*) FROM (SELECT DISTINCT a.id AS id_a, b.id AS id_b FROM {SAIDA_A} a "
            f"JOIN {SAIDA_B} b ON {condicao}) pares;")


def executar(args):
    if args.simular:
        for nome in args.datasets:
            for algoritmo in args.algoritmos:
                print(f"{nome}: {DATASETS[nome]['cenario']} / {algoritmo}; "
                      f"GiST=on; workers={args.workers}; alvo={args.particoes if algoritmo != 'SEM_PARTICIONAMENTO' else 'N/A'}")
        return
    pasta = args.saida.resolve() / ("pp1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True, exist_ok=False)
    config = {**vars(args), "saida": str(pasta), "indexacao": "on"}
    salvar_json(pasta / "configuracao.json", config)
    experimento = Experimento(args, pasta)
    manifesto = {"status": "em_execucao", "combinacoes": []}
    try:
        if any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos):
            print("Compilando os particionadores Java...", flush=True)
            experimento.processo(["mvn", "-q", "compile"], pasta / "compilacao.log")
        # Todas as combinações são sequenciais: as saídas SQL são compartilhadas.
        with (pasta / "consultas.csv").open("w", newline="", encoding="utf-8") as consolidado:
            writer = None
            for nome in args.datasets:
                dataset = {**DATASETS[nome], "id": getattr(args, "id_" + nome)}
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
                            with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=caso) as trabalho:
                                metadata = experimento.particionar(algoritmo, entradas, Path(trabalho), caso)
                                experimento.materializar(dataset, Path(trabalho), metadata, caso)
                            consulta = consulta_particionada(algoritmo)
                        medicoes = experimento.medir(dataset, algoritmo, consulta, esperado, caso)
                        with medicoes.open(newline="", encoding="utf-8") as arquivo:
                            for linha in csv.DictReader(arquivo):
                                linha.update(dataset=nome, particoes_alvo=args.particoes if algoritmo != "SEM_PARTICIONAMENTO" else "",
                                             particoes_efetivas=metadata["particoes_efetivas"], capacidade=metadata["capacidade"])
                                if writer is None:
                                    writer = csv.DictWriter(consolidado, fieldnames=list(linha))
                                    writer.writeheader()
                                writer.writerow(linha)
                        consolidado.flush()
                        registro.update(status="concluido", intersecoes=esperado,
                                        particoes_efetivas=metadata["particoes_efetivas"])
                        salvar_json(pasta / "manifesto.json", manifesto)
        manifesto["status"] = "concluido"
    except (RuntimeError, OSError, ValueError, StopIteration, KeyboardInterrupt) as erro:
        manifesto.update(status="falhou", erro=str(erro))
        if manifesto["combinacoes"] and manifesto["combinacoes"][-1]["status"] == "em_execucao":
            manifesto["combinacoes"][-1]["status"] = "falhou"
        raise SystemExit(f"PP1 interrompido: {erro}\nResultados e logs: {pasta}") from erro
    finally:
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP1 concluído. CSV consolidado: {pasta / 'consultas.csv'}", flush=True)


if __name__ == "__main__":
    executar(argumentos())
