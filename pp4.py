"""PP4: algoritmos × limites de workers, com workload, amostras e GiST fixos."""
from argparse import Namespace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from pp1 import (Experimento, identificador, salvar_json, metadados_execucao,
                 consulta_direta, consulta_particionada)
from pp2 import (criar_parser, argumentos as argumentos_base, carregar_config, preparar_amostras,
                 validar_pares, anexar_csv, WORKLOADS, MULTI)
from perf_coleta import verificar_perf
from consolidar_pp1 import consolidar, imprimir_resumo


def argumentos(argv=None):
    parser = criar_parser(workers_lista=True)
    parser.description = __doc__
    parser.set_defaults(workloads=["linha_poligono"], saida=Path("resultados/pp4"))
    args = argumentos_base(argv, parser=parser)
    if len(args.workloads) != 1:
        parser.error("A PP4 fixa um workload por execução; informe apenas um em --workloads")
    args.workers = list(dict.fromkeys(args.workers))
    if 0 not in args.workers:
        parser.error("Inclua 0 em --workers para medir a referência serial de cada algoritmo")
    return args


def registrar_servidor(exp, pasta):
    sql = """SELECT json_object_agg(name, setting ORDER BY name) FROM pg_settings WHERE name IN (
        'server_version', 'max_parallel_workers_per_gather', 'max_parallel_workers', 'max_worker_processes',
        'parallel_leader_participation', 'min_parallel_table_scan_size', 'min_parallel_index_scan_size',
        'parallel_setup_cost', 'parallel_tuple_cost', 'enable_parallel_append', 'enable_parallel_hash',
        'enable_partitionwise_join', 'enable_partitionwise_aggregate', 'work_mem', 'shared_buffers',
        'effective_cache_size', 'jit', 'enable_seqscan', 'enable_indexscan', 'enable_indexonlyscan',
        'enable_bitmapscan', 'debug_parallel_query', 'force_parallel_mode');"""
    info = json.loads(exp.sql(exp.configuracao_sessao() + "\n" + sql, pasta / "servidor"))
    salvar_json(pasta / "servidor.json", info)
    return info


def resumir_plano(plano):
    """Diagnóstico de um EXPLAIN posterior; não representa cada repetição cronometrada."""
    if not isinstance(plano, list) or len(plano) != 1 or "Plan" not in plano[0]:
        raise ValueError("Formato de EXPLAIN JSON inesperado")
    gathers = []

    def visitar(no, caminho):
        if no.get("Node Type") in ("Gather", "Gather Merge"):
            gathers.append({"caminho": caminho, "tipo": no["Node Type"],
                            "planejados": no.get("Workers Planned"), "lancados": no.get("Workers Launched"),
                            "loops": no.get("Actual Loops")})
        for i, filho in enumerate(no.get("Plans", [])):
            visitar(filho, f"{caminho}.Plans[{i}]")

    visitar(plano[0]["Plan"], "Plan")

    def maximo(campo):
        if not gathers:
            return 0
        valores = [g[campo] for g in gathers]
        return max(valores) if all(v is not None for v in valores) else None

    resumo = {"plano_gathers": len(gathers), "plano_workers_planejados_max": maximo("planejados"),
              "plano_workers_lancados_max": maximo("lancados"),
              "plano_gathers_com_deficit": sum(1 for g in gathers if g["loops"] is not None and g["loops"] > 0
                  and g["planejados"] is not None and g["lancados"] is not None and g["lancados"] < g["planejados"])}
    return {"escopo": "explain_analyze_posterior_as_medicoes", "gathers": gathers, "resumo": resumo}


def executar(args):
    config = carregar_config(args.config)
    workload = args.workloads[0]
    if args.simular:
        for algoritmo in args.algoritmos:
            for workers in args.workers:
                print(f"{config['dataset']} / {workload} / {algoritmo}: workers={workers}; GiST=on; "
                      f"A={args.objetos_a}, B={args.objetos_b}; "
                      f"alvo={args.particoes if algoritmo != 'SEM_PARTICIONAMENTO' else 'N/A'}; "
                      f"perf={'on' if args.perf else 'off'}")
        return
    pasta = args.saida.resolve() / ("pp4_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True)
    schema = pasta.name.lower()
    meta = metadados_execucao(pasta.name)
    meta["pp4_run_id"] = meta.pop("pp1_run_id")
    salvar_json(pasta / "configuracao.json", {**vars(args), "config": str(args.config.resolve()),
                "saida": str(pasta), "fontes": config, "indexacao": "on", "gist": "on", **meta})
    # O executor/coletor recebe um limite escalar; a configuração da matriz permanece intacta.
    exp = Experimento(Namespace(**{**vars(args), "workers": 0}), pasta)
    manifesto = {"status": "em_execucao", "combinacoes": [], "schema_amostras": schema}
    salvar_json(pasta / "manifesto.json", manifesto)
    criado = False
    try:
        if args.perf:
            verificar_perf(args.perf_eventos, pasta, exp.ambiente)
        servidor = registrar_servidor(exp, pasta)
        limite = min(int(servidor["max_parallel_workers"]), int(servidor["max_worker_processes"]))
        if max(args.workers) > limite:
            print(f"Aviso: a matriz solicita até {max(args.workers)} workers, mas os limites globais permitem "
                  f"no máximo {limite}; a disponibilidade pode ser menor. Confira os planos.", flush=True)
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
        exp.preparar_entradas(dataset, destino)
        esperado = int(exp.sql(exp.configuracao_sessao() + "\n" + consulta_direta(dataset), destino / "referencia"))
        with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temp:
            entradas = Path(temp)
            if particionados:
                exp.exportar(dataset, entradas, destino)
            for algoritmo in args.algoritmos:
                algoritmo_dir = destino / algoritmo.lower()
                algoritmo_dir.mkdir()
                metadata = {"particoes_efetivas": None, "capacidade": None}
                consulta = consulta_direta(dataset)
                if algoritmo != "SEM_PARTICIONAMENTO":
                    print(f"Preparando {algoritmo} uma vez para todos os limites de workers...", flush=True)
                    with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=algoritmo_dir) as temp_assoc:
                        metadata = exp.particionar(algoritmo, entradas, Path(temp_assoc), algoritmo_dir)
                        exp.materializar(dataset, Path(temp_assoc), metadata, algoritmo_dir)
                    validar_pares(exp, dataset, algoritmo, algoritmo_dir)
                    consulta = consulta_particionada(algoritmo)
                for workers in args.workers:
                    exp.args.workers = workers
                    print(f"PP4 {config['dataset']} / {workload} / {algoritmo} / workers={workers}", flush=True)
                    caso = algoritmo_dir / f"workers_{workers}"
                    caso.mkdir()
                    registro = {"workload": workload, "algoritmo": algoritmo, "workers_por_gather": workers,
                                "status": "em_execucao"}
                    manifesto["combinacoes"].append(registro)
                    salvar_json(pasta / "manifesto.json", manifesto)
                    atual = registrar_servidor(exp, caso)
                    if any(atual.get(k) != v for k, v in servidor.items() if k != "max_parallel_workers_per_gather"):
                        raise RuntimeError("Configuração do servidor mudou entre casos; confira os arquivos servidor.json")
                    medicoes = exp.medir(dataset, algoritmo, consulta, esperado, caso)
                    diagnostico = resumir_plano(json.loads((caso / "plano.json").read_text(encoding="utf-8")))
                    salvar_json(caso / "paralelismo.json", diagnostico)
                    contexto = {"dataset": config["dataset"], "workload": workload, "gist": "on",
                                "objetos_a": args.objetos_a, "objetos_b": args.objetos_b, "semente": args.semente,
                                "ids_a_md5": escala[nome_a]["ids_md5"], "ids_b_md5": escala["poligonos_b"]["ids_md5"],
                                "seletividade": esperado / (args.objetos_a * args.objetos_b),
                                "particoes_alvo": args.particoes if algoritmo != "SEM_PARTICIONAMENTO" else "",
                                "particoes_efetivas": metadata["particoes_efetivas"], "capacidade": metadata["capacidade"],
                                "workers_por_gather": workers,
                                **{k: atual[k] for k in ("max_parallel_workers", "max_worker_processes", "parallel_leader_participation")},
                                **diagnostico["resumo"]}
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
        raise SystemExit(f"PP4 interrompida: {erro}\nLogs: {pasta}") from erro
    finally:
        if criado:
            try:
                exp.sql(f"DROP SCHEMA {identificador(schema)} CASCADE;", pasta / "limpeza")
                manifesto["amostras_removidas"] = True
            except Exception as erro:
                manifesto["erro_limpeza"] = str(erro)
                print(f"Aviso: schema de amostras mantido: {schema}; {erro}")
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP4 concluída: {pasta}")
    try:
        imprimir_resumo(consolidar(pasta.parent, "pp4"), "pp4")
    except Exception as erro:
        print(f"Aviso: consolidação falhou; brutos preservados: {erro}")


if __name__ == "__main__":
    executar(argumentos())
