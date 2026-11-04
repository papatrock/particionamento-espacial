"""PP2: algoritmos × workloads reais, com cardinalidades A/B fixadas explicitamente."""
import argparse
import csv
from datetime import datetime, timezone
import json
from math import isqrt
from pathlib import Path
import tempfile

from pp1 import (Experimento, ALGORITMOS, RAIZ, identificador, literal, salvar_json,
                 metadados_execucao, consulta_direta, consulta_particionada)
from perf_coleta import argumentos_perf, verificar_perf

WORKLOADS = {"ponto_poligono": "pontos", "linha_poligono": "linhas", "poligono_poligono": "poligonos_a"}
TIPOS = {"pontos": ("ST_Point", "ST_MultiPoint"), "linhas": ("ST_LineString", "ST_MultiLineString"),
         "poligonos_a": ("ST_Polygon", "ST_MultiPolygon"), "poligonos_b": ("ST_Polygon", "ST_MultiPolygon")}
MULTI = {"pontos": "MultiPoint", "linhas": "MultiLineString", "poligonos_a": "MultiPolygon"}


def carregar_config(caminho):
    config = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(config.get("dataset"), str) or not config["dataset"].strip():
        raise ValueError("Configuração requer nome do dataset")
    if not isinstance(config.get("srid"), int) or config["srid"] <= 0:
        raise ValueError("Configuração requer SRID positivo")
    for nome in TIPOS:
        relacao = config.get("relacoes", {}).get(nome, {})
        for campo in ("schema", "tabela", "id", "geom"):
            if not isinstance(relacao.get(campo), str) or not relacao[campo].strip():
                raise ValueError(f"Relação {nome}: campo {campo} obrigatório")
    return config


def criar_parser(workers_lista=False, particoes_lista=False):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=RAIZ / "experimentos/pp2/brasil.json")
    p.add_argument("--objetos-a", type=int, required=True, help="Quantidade exata de objetos em A em cada workload.")
    p.add_argument("--objetos-b", type=int, required=True, help="Quantidade exata de polígonos em B, compartilhados pelos workloads.")
    p.add_argument("--semente", type=int, default=42, help="Seleção determinística por hash do ID e semente.")
    p.add_argument("--workloads", nargs="+", choices=WORKLOADS, default=list(WORKLOADS))
    p.add_argument("--algoritmos", nargs="+", choices=ALGORITMOS, default=list(ALGORITMOS))
    p.add_argument("--banco", default="benchmark")
    p.add_argument("--host")
    p.add_argument("--porta", type=int)
    p.add_argument("--usuario")
    p.add_argument("--pedir-senha", action="store_true")
    if particoes_lista:
        p.add_argument("--particoes", type=int, nargs="+", default=[4, 16, 64, 256, 1024],
                       help="Alvos a comparar; quadrados perfeitos quando o Two-Layer participa.")
    else:
        p.add_argument("--particoes", type=int, default=64)
    if workers_lista:
        p.add_argument("--workers", type=int, nargs="+", default=[0, 1, 2, 4, 8, 16, 24],
                       help="Limites por Gather a comparar, incluindo 0 como referência serial.")
    else:
        p.add_argument("--workers", type=int, default=24)
    p.add_argument("--aquecimentos", type=int, default=3)
    p.add_argument("--repeticoes", type=int, default=10)
    p.add_argument("--rodada", type=int, default=1)
    p.add_argument("--hilbert-bits", type=int, default=16)
    p.add_argument("--bsp-tentativas", type=int, default=8)
    p.add_argument("--saida", type=Path, default=Path("resultados/pp2"))
    p.add_argument("--simular", action="store_true")
    argumentos_perf(p)
    return p


def argumentos(argv=None, parser=None):
    p = parser if parser is not None else criar_parser()
    a = p.parse_args(argv)
    particoes = a.particoes if isinstance(a.particoes, list) else [a.particoes]
    if min(a.objetos_a, a.objetos_b, *particoes, a.repeticoes, a.rodada, a.bsp_tentativas) < 1:
        p.error("Cardinalidades, partições, repetições, rodada e tentativas devem ser positivas")
    workers = a.workers if isinstance(a.workers, list) else [a.workers]
    if min(workers) < 0 or a.aquecimentos < 0 or not 1 <= a.hilbert_bits <= 16:
        p.error("Workers/aquecimentos >= 0 e bits entre 1 e 16")
    if a.porta is not None and not 1 <= a.porta <= 65535:
        p.error("Porta deve estar entre 1 e 65535")
    if "TWO_LAYER" in a.algoritmos and any(isqrt(alvo)**2 != alvo for alvo in particoes):
        p.error("Two-Layer requer alvo quadrado perfeito")
    if a.perf and not a.perf_eventos.strip():
        p.error("Informe eventos perf")
    a.workloads = list(dict.fromkeys(a.workloads))
    a.algoritmos = list(dict.fromkeys(a.algoritmos))
    return a


def tabela(relacao):
    return identificador(relacao["schema"]) + "." + identificador(relacao["tabela"])


def sql_amostra(relacao, destino, quantidade, semente):
    id_, geom = identificador(relacao["id"]), identificador(relacao["geom"])
    return (f"CREATE TABLE {destino} AS SELECT {id_}::bigint AS id, ST_Multi({geom}) AS geom "
            f"FROM {tabela(relacao)} WHERE NOT ST_IsEmpty({geom}) "
            f"ORDER BY md5({id_}::text || ':' || {literal(semente)}), {id_}::bigint LIMIT {quantidade};")


def preparar_amostras(exp, config, args, schema, pasta):
    """Valida fontes e cria snapshots; nunca cria índices nem altera as tabelas originais."""
    nomes = list(dict.fromkeys([WORKLOADS[w] for w in args.workloads] + ["poligonos_b"]))
    for nome in nomes:
        print(f"Validando fonte {nome}...", flush=True)
        r = config["relacoes"][nome]
        id_, geom = identificador(r["id"]), identificador(r["geom"])
        permitidos = ",".join(literal(t) for t in TIPOS[nome])
        info = json.loads(exp.sql(f"""SELECT json_build_object(
            'registros', count(*), 'ids', count({id_}), 'ids_distintos', count(DISTINCT {id_}::bigint),
            'validos', count(*) FILTER (WHERE NOT ST_IsEmpty({geom})),
            'invalidos', count(*) FILTER (WHERE {geom} IS NULL OR ST_SRID({geom}) <> {config['srid']}
              OR ST_NDims({geom}) <> 2 OR NOT ST_IsValid({geom})
              OR ST_GeometryType({geom}) NOT IN ({permitidos}))) FROM {tabela(r)};""",
            pasta / (nome + "_fonte")))
        n = args.objetos_b if nome == "poligonos_b" else args.objetos_a
        if info["registros"] != info["ids"] or info["ids"] != info["ids_distintos"]:
            raise ValueError(f"{nome}: IDs devem ser inteiros únicos e não nulos; configure uma chave adequada no JSON")
        if info["invalidos"] or info["validos"] < n:
            raise ValueError(f"{nome}: requer {n} geometrias válidas, não vazias, 2D, SRID/tipo corretos; encontrado {info}")
    comandos = ["BEGIN ISOLATION LEVEL REPEATABLE READ;"]
    for nome in nomes:
        n = args.objetos_b if nome == "poligonos_b" else args.objetos_a
        destino = identificador(schema) + "." + identificador(nome)
        comandos.append(sql_amostra(config["relacoes"][nome], destino, n, args.semente))
    comandos.append("COMMIT;")
    print("Criando amostras com as cardinalidades solicitadas...", flush=True)
    exp.sql("\n".join(comandos), pasta / "amostragem")
    caracteristicas = {}
    for nome in nomes:
        destino = identificador(schema) + "." + identificador(nome)
        caracteristicas[nome] = json.loads(exp.sql(f"""SELECT json_build_object(
            'objetos', count(*), 'vertices_total', sum(ST_NPoints(geom)),
            'vertices_media', avg(ST_NPoints(geom)), 'extensao', ST_Extent(geom)::text,
            'ids_md5', md5(string_agg(id::text, ',' ORDER BY id))) FROM {destino};""",
            pasta / (nome + "_escala")))
        esperado = args.objetos_b if nome == "poligonos_b" else args.objetos_a
        if caracteristicas[nome]["objetos"] != esperado:
            raise ValueError(f"{nome}: cardinalidade mudou durante preparação")
    salvar_json(pasta / "escala.json", caracteristicas)
    return caracteristicas


def validar_pares(exp, dataset, algoritmo, pasta):
    a, b = (identificador(dataset["schema"]) + "." + identificador(t) for t in dataset["tabelas"])
    from pp1 import SAIDA_A, SAIDA_B
    condicao = "a.id_particao=b.id_particao AND ST_Intersects(a.geom,b.geom)"
    if algoritmo == "TWO_LAYER":
        condicao += " AND (a.classe='A' OR b.classe='A' OR (a.classe='B' AND b.classe='C') OR (a.classe='C' AND b.classe='B'))"
    sql = f"""WITH original AS (SELECT a.id AS id_a,b.id AS id_b FROM {a} a JOIN {b} b ON ST_Intersects(a.geom,b.geom)),
        particionado AS (SELECT a.id AS id_a,b.id AS id_b FROM {SAIDA_A} a JOIN {SAIDA_B} b ON {condicao})
        SELECT json_build_object(
          'extras', (SELECT count(*) FROM (SELECT * FROM particionado EXCEPT SELECT * FROM original) e),
          'faltantes', (SELECT count(*) FROM (SELECT * FROM original EXCEPT SELECT * FROM particionado) f));"""
    resultado = json.loads(exp.sql(sql, pasta / "validacao_pares"))
    if resultado != {"extras": 0, "faltantes": 0}:
        raise RuntimeError(f"Pares diferentes do baseline: {resultado}")


def anexar_csv(origem, destino, contexto):
    with Path(origem).open(newline="", encoding="utf-8") as entrada:
        reader = csv.DictReader(entrada)
        colunas = list(reader.fieldnames or []) + [k for k in contexto if k not in (reader.fieldnames or [])]
        novo = not destino.exists()
        with destino.open("a", newline="", encoding="utf-8") as saida:
            writer = csv.DictWriter(saida, fieldnames=colunas)
            if novo:
                writer.writeheader()
            for linha in reader:
                writer.writerow({**linha, **contexto})


def executar(args):
    config = carregar_config(args.config)
    if args.simular:
        for w in args.workloads:
            for algoritmo in args.algoritmos:
                print(f"{config['dataset']} / {w} / {algoritmo}: A={args.objetos_a}, B={args.objetos_b}; "
                      f"GiST=on; workers={args.workers}; "
                      f"alvo={args.particoes if algoritmo != 'SEM_PARTICIONAMENTO' else 'N/A'}; "
                      f"perf={'on' if args.perf else 'off'}")
        return
    pasta = args.saida.resolve() / ("pp2_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True)
    schema = pasta.name.lower()
    meta = metadados_execucao(pasta.name)
    meta["pp2_run_id"] = meta.pop("pp1_run_id")
    salvar_json(pasta / "configuracao.json", {**vars(args), "config": str(args.config.resolve()),
                "saida": str(pasta), "fontes": config, "indexacao": "on", **meta})
    exp = Experimento(args, pasta)
    manifesto = {"status": "em_execucao", "combinacoes": [], "schema_amostras": schema}
    salvar_json(pasta / "manifesto.json", manifesto)
    criado = False
    try:
        if args.perf:
            verificar_perf(args.perf_eventos, pasta, exp.ambiente)
        particionados = any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos)
        if particionados:
            print("Compilando os particionadores Java...", flush=True)
            exp.processo(["mvn", "-q", "compile"], pasta / "compilacao.log")
        exp.sql(f"CREATE SCHEMA {identificador(schema)};", pasta / "schema")
        criado = True
        escala = preparar_amostras(exp, config, args, schema, pasta)
        for workload in args.workloads:
            nome_a = WORKLOADS[workload]
            dataset = {"schema": schema, "cenario": workload, "tabelas": (nome_a, "poligonos_b"),
                       "id": "id", "geom": "geom", "srid": config["srid"], "tipos": (MULTI[nome_a], "MultiPolygon")}
            destino = pasta / workload
            destino.mkdir()
            exp.preparar_entradas(dataset, destino)
            esperado = int(exp.sql(exp.configuracao_sessao() + "\n" + consulta_direta(dataset), destino / "baseline"))
            with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temp:
                entradas = Path(temp)
                if particionados:
                    exp.exportar(dataset, entradas, destino)
                for algoritmo in args.algoritmos:
                    print(f"PP2 {config['dataset']} / {workload} / {algoritmo}", flush=True)
                    caso = destino / algoritmo.lower()
                    caso.mkdir()
                    registro = {"workload": workload, "algoritmo": algoritmo, "status": "em_execucao"}
                    manifesto["combinacoes"].append(registro)
                    salvar_json(pasta / "manifesto.json", manifesto)
                    metadata = {"particoes_efetivas": None, "capacidade": None}
                    consulta = consulta_direta(dataset)
                    if algoritmo != "SEM_PARTICIONAMENTO":
                        with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=caso) as temp_assoc:
                            metadata = exp.particionar(algoritmo, entradas, Path(temp_assoc), caso)
                            exp.materializar(dataset, Path(temp_assoc), metadata, caso)
                        validar_pares(exp, dataset, algoritmo, caso)
                        consulta = consulta_particionada(algoritmo)
                    medicoes = exp.medir(dataset, algoritmo, consulta, esperado, caso)
                    contexto = {"dataset": config["dataset"], "workload": workload, "objetos_a": args.objetos_a,
                                "objetos_b": args.objetos_b, "semente": args.semente,
                                "ids_a_md5": escala[nome_a]["ids_md5"], "ids_b_md5": escala["poligonos_b"]["ids_md5"],
                                "seletividade": esperado / (args.objetos_a * args.objetos_b),
                                "particoes_alvo": args.particoes if algoritmo != "SEM_PARTICIONAMENTO" else "",
                                "particoes_efetivas": metadata["particoes_efetivas"], "capacidade": metadata["capacidade"]}
                    anexar_csv(medicoes, pasta / "consultas.csv", contexto)
                    if args.perf:
                        anexar_csv(medicoes.parent / "perf.csv", pasta / "perf.csv", contexto)
                    registro.update(status="concluido", intersecoes=esperado, **contexto)
                    salvar_json(pasta / "manifesto.json", manifesto)
        manifesto["status"] = "concluido"
    except (Exception, KeyboardInterrupt) as erro:
        manifesto.update(status="falhou", erro=str(erro))
        if manifesto["combinacoes"] and manifesto["combinacoes"][-1]["status"] == "em_execucao":
            manifesto["combinacoes"][-1]["status"] = "falhou"
        raise SystemExit(f"PP2 interrompida: {erro}\nLogs: {pasta}") from erro
    finally:
        if criado:
            try:
                exp.sql(f"DROP SCHEMA {identificador(schema)} CASCADE;", pasta / "limpeza")
                manifesto["amostras_removidas"] = True
            except Exception as erro:
                manifesto["erro_limpeza"] = str(erro)
                print(f"Aviso: schema de amostras mantido: {schema}; {erro}")
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP2 concluída: {pasta}")
    from consolidar_pp1 import consolidar, imprimir_resumo
    try:
        imprimir_resumo(consolidar(pasta.parent, "pp2"), "pp2")
    except Exception as erro:
        print(f"Aviso: consolidação falhou; brutos preservados: {erro}")


if __name__ == "__main__":
    executar(argumentos())
