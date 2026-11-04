"""Etapas de um experimento: psql, particionadores Java, materialização e medição."""
from getpass import getpass
import json
import os
import subprocess
import sys

from nucleo.arquivos import RAIZ, salvar_json
from nucleo.consultas import SAIDA_A, SAIDA_B, identificador, literal

ALGORITMOS = ("SEM_PARTICIONAMENTO", "TWO_LAYER", "STR", "HILBERT", "BSP")
CODIGO_LIMITE = 3  # Saída de coletar_consultas.py quando uma consulta excede o limite.


class ErroProcesso(RuntimeError):
    def __init__(self, mensagem, codigo):
        super().__init__(mensagem)
        self.codigo = codigo


class LimiteExcedido(RuntimeError):
    """A consulta não terminou no limite: é um resultado do caso, não uma falha da execução."""


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
            raise ErroProcesso(f"Processo falhou; consulte {destino} e a saída de erro no terminal.", resultado.returncode)

    def configuracao_sessao(self):
        return (f"SET max_parallel_workers_per_gather = {self.args.workers};\n"
                "SET enable_partitionwise_join = on;\nSET enable_seqscan = on;\n"
                "SET enable_indexscan = on;\nSET enable_indexonlyscan = on;\nSET enable_bitmapscan = on;")

    def preparar_entradas(self, dataset, pasta, criar_gist=True):
        registros = []
        for nome in dataset["tabelas"]:
            tabela = identificador(dataset.get("schema", "public")) + "." + identificador(nome)
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
            if criar_gist:
                self.sql(sql_indice, pasta / (nome + "_gist"))
            else:
                self.sql(f"ANALYZE {tabela};", pasta / (nome + "_analyze"))
        salvar_json(pasta / "entradas.json", registros)

    def exportar(self, dataset, trabalho, pasta):
        for lado, nome in zip(("a", "b"), dataset["tabelas"]):
            tabela = identificador(dataset.get("schema", "public")) + "." + identificador(nome)
            geom, coluna_id = identificador(dataset["geom"]), identificador(dataset["id"])
            # ST_AsText retorna WKT em uma linha; ordem estável é necessária para BSP.
            consulta = (f"\\copy (SELECT {coluna_id}::bigint, ST_AsText({geom}) FROM {tabela} "
                        f"WHERE NOT ST_IsEmpty({geom}) ORDER BY {coluna_id}) TO "
                        f"{literal(trabalho / (lado + '.tsv'))}")
            self.sql(consulta, pasta / (lado + "_exportacao"))

    def particionar(self, algoritmo, entradas, trabalho, pasta, associacao_unica=False):
        comando = ["mvn", "-q", "exec:java", "-Dexec.mainClass=benchmark.ParticionamentoRunner",
                   f"-Dpp1.algoritmo={algoritmo}", f"-Dpp1.particoes={self.args.particoes}",
                   f"-Dpp1.hilbertBits={self.args.hilbert_bits}", f"-Dpp1.bspTentativas={self.args.bsp_tentativas}",
                   f"-Dpp1.entradaA={entradas / 'a.tsv'}", f"-Dpp1.entradaB={entradas / 'b.tsv'}",
                   f"-Dpp1.saida={trabalho}"]
        if associacao_unica:
            if algoritmo not in ("STR", "HILBERT"):
                raise ValueError("Associação única disponível somente para STR e Hilbert")
            comando.append("-Dpp1.modeloJoin=SAMJ")
        self.processo(comando, pasta / "java.log")
        metadados = json.loads((trabalho / "particionamento.json").read_text(encoding="utf-8"))
        if associacao_unica and metadados.get("modelo_join") != "SAMJ":
            raise RuntimeError("O runner não retornou o modelo SAMJ solicitado")
        salvar_json(pasta / "particionamento.json", metadados)
        print(f"  Partições efetivas: {metadados['particoes_efetivas']}; alvo: {self.args.particoes}", flush=True)
        return metadados

    def materializar(self, dataset, trabalho, metadados, pasta, criar_gist=True, normalizar_multi=True):
        # PP1 preserva os tipos de origem; PP2–PP5 mantêm a normalização padrão.
        tipos = dataset["tipos"] if normalizar_multi else dataset["tipos_origem"]
        geometria = f"ST_GeomFromText(wkt, {dataset['srid']})"
        if normalizar_multi:
            geometria = f"ST_Multi({geometria})"
        comandos = ["BEGIN;", f"DROP TABLE IF EXISTS {SAIDA_A} CASCADE;",
                    f"DROP TABLE IF EXISTS {SAIDA_B} CASCADE;"]
        for lado, tabela, tipo in zip(("a", "b"), (SAIDA_A, SAIDA_B), tipos):
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
                f"{geometria} FROM pp1_carga;",
                "DROP TABLE pp1_carga;",
            ])
            if criar_gist:
                comandos.append(f"CREATE INDEX idx_tabela_{lado}_geom ON {tabela} USING GIST (geom);")
            comandos.append(f"ANALYZE {tabela};")
        comandos.append("COMMIT;")
        self.sql("\n".join(comandos), pasta / "materializacao")

    def medir(self, dataset, algoritmo, consulta, esperado, pasta):
        arquivo = pasta / "consulta.sql"
        arquivo.write_text(consulta + "\n", encoding="utf-8")
        comando = [
            sys.executable, str(RAIZ / "coletar_consultas.py"), *self.conexao,
            "--cenario", dataset["cenario"], "--algoritmo", algoritmo, "--sql", str(arquivo),
            "--workers", str(self.args.workers), "--indexacao", "on",
            "--aquecimentos", str(self.args.aquecimentos), "--repeticoes", str(self.args.repeticoes),
            "--rodada", str(self.args.rodada), "--contagem-esperada", str(esperado),
            "--saida", str(pasta / "medicoes"),
        ]
        if self.args.perf:
            comando.extend(["--perf", "--perf-eventos", self.args.perf_eventos])
        # Só a PP1 define o limite; as demais PPs medem sem interrupção.
        limite = getattr(self.args, "limite_consulta_min", 0)
        if limite:
            comando.extend(["--limite-consulta-ms", str(max(1, round(limite * 60000)))])
        try:
            self.processo(comando, pasta / "coletor.log")
        except ErroProcesso as erro:
            if erro.codigo == CODIGO_LIMITE:
                raise LimiteExcedido(f"{algoritmo} excedeu {limite:g} min por consulta") from erro
            raise
        plano = self.sql(self.configuracao_sessao() + "\nEXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + consulta,
                         pasta / "plano")
        salvar_json(pasta / "plano.json", json.loads(plano))
        return next((pasta / "medicoes").glob("*/consultas.csv"))
