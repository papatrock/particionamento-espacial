"""PP3: particionamento × presença física de GiST, sobre um workload fixo."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from pp1 import (Experimento, identificador, literal, salvar_json, metadados_execucao,
                 consulta_direta, consulta_particionada)
from pp2 import (criar_parser, argumentos as argumentos_base, carregar_config, preparar_amostras,
                 validar_pares, anexar_csv, WORKLOADS, MULTI)
from perf_coleta import verificar_perf
from consolidar_pp1 import consolidar, imprimir_resumo


def argumentos(argv=None):
    parser = criar_parser()
    parser.description = __doc__
    parser.add_argument("--gist", nargs="+", choices=("off", "on"), default=["off", "on"],
                        help="Presença física do índice em ambas as entradas, inclusive nas partições.")
    parser.set_defaults(workloads=["linha_poligono"], saida=Path("resultados/pp3"))
    args = argumentos_base(argv, parser=parser)
    if len(args.workloads) != 1:
        parser.error("A PP3 fixa um workload por execução; informe apenas um em --workloads")
    args.gist = list(dict.fromkeys(args.gist))
    return args


def configurar_gist(exp, tabelas, gist, pasta):
    """Somente tabelas criadas pelo experimento; nunca receber aqui as fontes originais."""
    comandos = ["BEGIN;"]
    raizes = []
    for schema, nome in tabelas:
        tabela = identificador(schema) + "." + identificador(nome)
        indice = identificador("idx_pp3_" + nome + "_geom")
        raizes.append(f"({literal(tabela)}::regclass::oid)")
        # DROP no índice pai também remove os índices vinculados nas partições.
        comandos.append(f"DROP INDEX IF EXISTS {identificador(schema)}.{indice};")
        if gist == "on":
            comandos.append(f"CREATE INDEX {indice} ON {tabela} USING GIST (geom);")
    comandos.append("COMMIT;")
    exp.sql("\n".join(comandos), pasta / "configurar_gist")
    # Inclui os pais e todos os descendentes: checar só o pai esconderia índices locais.
    consulta = f"""WITH RECURSIVE relacoes(oid) AS (
        VALUES {','.join(raizes)}
        UNION SELECT i.inhrelid FROM pg_inherits i JOIN relacoes r ON r.oid=i.inhparent
    ) SELECT coalesce(json_agg(row_to_json(t) ORDER BY t.tabela), '[]'::json) FROM (
        SELECT r.oid::regclass::text AS tabela, count(i.indexrelid) AS indices,
            count(i.indexrelid) FILTER (WHERE am.amname='gist' AND i.indisvalid AND i.indisready
                AND i.indpred IS NULL AND i.indexprs IS NULL
                AND (SELECT attnum FROM pg_attribute WHERE attrelid=r.oid AND attname='geom') = ANY(i.indkey)
            ) AS gist_validos,
            coalesce(sum(pg_relation_size(i.indexrelid)),0) AS bytes_indices
        FROM relacoes r LEFT JOIN pg_index i ON i.indrelid=r.oid
        LEFT JOIN pg_class c ON c.oid=i.indexrelid LEFT JOIN pg_am am ON am.oid=c.relam
        GROUP BY r.oid
    ) t;"""
    indices = json.loads(exp.sql(consulta, pasta / "verificacao_indices"))
    salvar_json(pasta / "indices.json", {"gist": gist, "relacoes": indices})
    if not indices or any(r["gist_validos"] != 1 if gist == "on" else r["indices"] != 0 for r in indices):
        raise RuntimeError(f"Estado físico dos índices não corresponde a GiST={gist}; consulte {pasta / 'indices.json'}")
    return sum(r["bytes_indices"] for r in indices)


def executar(args):
    config = carregar_config(args.config)
    workload = args.workloads[0]
    if args.simular:
        for algoritmo in args.algoritmos:
            for gist in args.gist:
                print(f"{config['dataset']} / {workload} / {algoritmo}: GiST={gist}; "
                      f"A={args.objetos_a}, B={args.objetos_b}; workers={args.workers}; "
                      f"alvo={args.particoes if algoritmo != 'SEM_PARTICIONAMENTO' else 'N/A'}; "
                      f"perf={'on' if args.perf else 'off'}")
        return
    pasta = args.saida.resolve() / ("pp3_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True)
    schema = pasta.name.lower()
    meta = metadados_execucao(pasta.name)
    meta["pp3_run_id"] = meta.pop("pp1_run_id")
    salvar_json(pasta / "configuracao.json", {**vars(args), "config": str(args.config.resolve()),
                "saida": str(pasta), "fontes": config, "indexacao": "on", **meta})
    manifesto = {"status": "em_execucao", "combinacoes": [], "schema_amostras": schema}
    salvar_json(pasta / "manifesto.json", manifesto)
    criado = False
    exp = Experimento(args, pasta)
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
        nome_a = WORKLOADS[workload]
        dataset = {"schema": schema, "cenario": workload, "tabelas": (nome_a, "poligonos_b"),
                   "id": "id", "geom": "geom", "srid": config["srid"], "tipos": (MULTI[nome_a], "MultiPolygon")}
        destino = pasta / workload
        destino.mkdir()
        exp.preparar_entradas(dataset, destino, criar_gist=False)
        # GiST na referência evita um join potencialmente quadrático só para validar.
        # Os índices destas cópias serão configurados novamente em cada caso baseline.
        referencia = destino / "referencia"
        referencia.mkdir()
        tabelas_base = [(schema, nome) for nome in dataset["tabelas"]]
        configurar_gist(exp, tabelas_base, "on", referencia)
        esperado = int(exp.sql(exp.configuracao_sessao() + "\n" + consulta_direta(dataset), referencia / "contagem"))
        with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temp:
            entradas = Path(temp)
            if particionados:
                exp.exportar(dataset, entradas, destino)
            for algoritmo in args.algoritmos:
                algoritmo_dir = destino / algoritmo.lower()
                algoritmo_dir.mkdir()
                metadata = {"particoes_efetivas": None, "capacidade": None}
                consulta = consulta_direta(dataset)
                tabelas = tabelas_base
                if algoritmo != "SEM_PARTICIONAMENTO":
                    print(f"Preparando {algoritmo}...", flush=True)
                    with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=algoritmo_dir) as temp_assoc:
                        metadata = exp.particionar(algoritmo, entradas, Path(temp_assoc), algoritmo_dir)
                        exp.materializar(dataset, Path(temp_assoc), metadata, algoritmo_dir, criar_gist=False)
                    consulta = consulta_particionada(algoritmo)
                    tabelas = [("public", "tabela_a_particionada"), ("public", "tabela_b_particionada")]
                # Materialização e associações são as mesmas nos dois estados de GiST.
                for gist in args.gist:
                    print(f"PP3 {config['dataset']} / {workload} / {algoritmo} / GiST={gist}", flush=True)
                    caso = algoritmo_dir / ("gist_" + gist)
                    caso.mkdir()
                    registro = {"workload": workload, "algoritmo": algoritmo, "gist": gist, "status": "em_execucao"}
                    manifesto["combinacoes"].append(registro)
                    salvar_json(pasta / "manifesto.json", manifesto)
                    bytes_indices = configurar_gist(exp, tabelas, gist, caso)
                    if algoritmo != "SEM_PARTICIONAMENTO":
                        validar_pares(exp, dataset, algoritmo, caso)
                    medicoes = exp.medir(dataset, algoritmo, consulta, esperado, caso)
                    contexto = {"dataset": config["dataset"], "workload": workload, "gist": gist,
                                "objetos_a": args.objetos_a, "objetos_b": args.objetos_b, "semente": args.semente,
                                "ids_a_md5": escala[nome_a]["ids_md5"], "ids_b_md5": escala["poligonos_b"]["ids_md5"],
                                "seletividade": esperado / (args.objetos_a * args.objetos_b),
                                "bytes_indices": bytes_indices,
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
        raise SystemExit(f"PP3 interrompida: {erro}\nLogs: {pasta}") from erro
    finally:
        if criado:
            try:
                exp.sql(f"DROP SCHEMA {identificador(schema)} CASCADE;", pasta / "limpeza")
                manifesto["amostras_removidas"] = True
            except Exception as erro:
                manifesto["erro_limpeza"] = str(erro)
                print(f"Aviso: schema de amostras mantido: {schema}; {erro}")
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP3 concluída: {pasta}")
    try:
        imprimir_resumo(consolidar(pasta.parent, "pp3"), "pp3")
    except Exception as erro:
        print(f"Aviso: consolidação falhou; brutos preservados: {erro}")


if __name__ == "__main__":
    executar(argumentos())
