"""Amostras com cardinalidade fixa, criadas a partir das fontes do JSON de configuração."""
import json
from pathlib import Path

from nucleo.arquivos import salvar_json
from nucleo.consultas import SAIDA_A, SAIDA_B, identificador, literal, pares_samj

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


def tabela(relacao):
    return identificador(relacao["schema"]) + "." + identificador(relacao["tabela"])


def sql_amostra(relacao, destino, quantidade, semente, pular=0):
    id_, geom = identificador(relacao["id"]), identificador(relacao["geom"])
    return (f"CREATE TABLE {destino} AS SELECT {id_}::bigint AS id, ST_Multi({geom}) AS geom "
            f"FROM {tabela(relacao)} WHERE NOT ST_IsEmpty({geom}) "
            f"ORDER BY md5({id_}::text || ':' || {literal(semente)}), {id_}::bigint LIMIT {quantidade} OFFSET {pular};")


def objetos_a_pular(config, args, nome):
    """A da mesma fonte de B começa depois de B na ordem sorteada: sem isso, B ficaria contido em A."""
    relacoes = config["relacoes"]
    return args.objetos_b if nome != "poligonos_b" and relacoes[nome] == relacoes["poligonos_b"] else 0


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
        n = (args.objetos_b if nome == "poligonos_b" else args.objetos_a) + objetos_a_pular(config, args, nome)
        if info["registros"] != info["ids"] or info["ids"] != info["ids_distintos"]:
            raise ValueError(f"{nome}: IDs devem ser inteiros únicos e não nulos; configure uma chave adequada no JSON")
        if info["invalidos"] or info["validos"] < n:
            raise ValueError(f"{nome}: requer {n} geometrias válidas, não vazias, 2D, SRID/tipo corretos; encontrado {info}")
    comandos = ["BEGIN ISOLATION LEVEL REPEATABLE READ;"]
    for nome in nomes:
        n = args.objetos_b if nome == "poligonos_b" else args.objetos_a
        destino = identificador(schema) + "." + identificador(nome)
        comandos.append(sql_amostra(config["relacoes"][nome], destino, n, args.semente,
                                    objetos_a_pular(config, args, nome)))
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


def sql_pares_particionados(algoritmo, metadata):
    if metadata and metadata.get("modelo_join") == "SAMJ":
        # No SAMJ, os pares podem estar em grupos diferentes: percorre os mesmos pares da consulta medida.
        return "\nUNION ALL\n".join(f"SELECT a.id AS id_a,b.id AS id_b FROM public.tabela_a_p{x} a "
                                     f"JOIN public.tabela_b_p{y} b ON ST_Intersects(a.geom,b.geom)"
                                     for x, y in pares_samj(algoritmo, metadata)) or "SELECT NULL::bigint,NULL::bigint WHERE false"
    condicao = "a.id_particao=b.id_particao AND ST_Intersects(a.geom,b.geom)"
    if algoritmo == "TWO_LAYER":
        condicao += " AND (a.classe='A' OR b.classe='A' OR (a.classe='B' AND b.classe='C') OR (a.classe='C' AND b.classe='B'))"
    return f"SELECT a.id AS id_a,b.id AS id_b FROM {SAIDA_A} a JOIN {SAIDA_B} b ON {condicao}"


def validar_pares(exp, dataset, algoritmo, pasta, metadata=None):
    a, b = (identificador(dataset["schema"]) + "." + identificador(t) for t in dataset["tabelas"])
    sql = f"""WITH original AS (SELECT a.id AS id_a,b.id AS id_b FROM {a} a JOIN {b} b ON ST_Intersects(a.geom,b.geom)),
        particionado AS ({sql_pares_particionados(algoritmo, metadata)})
        SELECT json_build_object(
          'extras', (SELECT count(*) FROM (SELECT * FROM particionado EXCEPT SELECT * FROM original) e),
          'faltantes', (SELECT count(*) FROM (SELECT * FROM original EXCEPT SELECT * FROM particionado) f));"""
    resultado = json.loads(exp.sql(sql, pasta / "validacao_pares"))
    if resultado != {"extras": 0, "faltantes": 0}:
        raise RuntimeError(f"Pares diferentes do baseline: {resultado}")
