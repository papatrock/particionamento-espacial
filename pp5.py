"""PP5: algoritmos × número de partições, com workload, amostras, workers e GiST fixos."""
from argparse import Namespace
from datetime import datetime, timezone
import json
from math import ceil
from pathlib import Path
import statistics
import tempfile
import time

from pp1 import (Experimento, SAIDA_A, SAIDA_B, identificador, salvar_json, metadados_execucao,
                 consulta_direta, consulta_particionada)
from pp2 import (criar_parser, argumentos as argumentos_base, carregar_config, preparar_amostras,
                 validar_pares, anexar_csv, WORKLOADS, MULTI)
from pp4 import registrar_servidor, resumir_plano
from perf_coleta import verificar_perf
from consolidar_pp1 import consolidar, imprimir_resumo


def argumentos(argv=None):
    parser = criar_parser(particoes_lista=True)
    parser.description = __doc__
    parser.set_defaults(workloads=["linha_poligono"], saida=Path("resultados/pp5"))
    args = argumentos_base(argv, parser=parser)
    if len(args.workloads) != 1:
        parser.error("A PP5 fixa um workload por execução; informe apenas um em --workloads")
    args.particoes = sorted(set(args.particoes))
    return args


def avisar_locks(servidor, args):
    """Cada processo bloqueia 2 tabelas e 2 GiST por partição; a falha só surgiria durante a medição."""
    necessarios = 4 * max(args.particoes) * (args.workers + 1)
    processos = int(servidor["max_connections"]) + int(servidor["max_worker_processes"])
    # Estimativa do dimensionamento do PostgreSQL: 2 entradas de processo por lock previsto.
    if necessarios > 2 * int(servidor["max_locks_per_transaction"]) * processos:
        print(f"Aviso: {max(args.particoes)} partições com {args.workers} workers podem causar 'out of shared memory'. "
              f"Estimativa: max_locks_per_transaction >= {ceil(necessarios / (2 * processos))} "
              f"(atual: {servidor['max_locks_per_transaction']}; alterar exige reiniciar o servidor).", flush=True)


def resumir_balanceamento(metadata):
    """Mede a distribuição das associações; a replicação entra na carga de cada partição."""
    ocupacoes = metadata["ocupacoes"]
    cargas = [o["objetos_a"] + o["objetos_b"] for o in ocupacoes]
    pares = [o["objetos_a"] * o["objetos_b"] for o in ocupacoes]
    media, media_pares = statistics.mean(cargas), statistics.mean(pares)
    return {"particoes_vazias": cargas.count(0),
            "particoes_com_a_e_b": sum(p > 0 for p in pares),
            "carga_media": media, "carga_maxima": max(cargas),
            "carga_max_sobre_media": max(cargas) / media if media else "",
            "carga_cv": statistics.pstdev(cargas) / media if media else "",
            "fator_replicacao": sum(cargas) / (metadata["objetos_a"] + metadata["objetos_b"]),
            "pares_candidatos": sum(pares),
            "pares_max_sobre_media": max(pares) / media_pares if media_pares else ""}


def medir_planejamento(exp, consulta, repeticoes, pasta):
    """Planeja sem executar, na mesma sessão: a primeira vez inclui o custo de carregar o catálogo."""
    comandos = "\n".join(["EXPLAIN (SUMMARY ON, FORMAT JSON) " + consulta] * repeticoes)
    saida = exp.sql(exp.configuracao_sessao() + "\n" + comandos, pasta / "planejamento")
    decodificador, tempos, posicao = json.JSONDecoder(), [], 0
    while posicao < len(saida):
        plano, fim = decodificador.raw_decode(saida, posicao)
        tempos.append(plano[0]["Planning Time"])
        posicao = fim
        while posicao < len(saida) and saida[posicao].isspace():
            posicao += 1
    if len(tempos) != repeticoes:
        raise RuntimeError(f"Esperava {repeticoes} planos, encontrei {len(tempos)} (logs: {pasta})")
    return {"planejamento_primeiro_ms": tempos[0], "planejamento_mediana_ms": statistics.median(tempos)}


def tamanho_saidas(exp, pasta):
    """Bytes das partições nas duas relações, incluindo GiST e TOAST."""
    return int(exp.sql(f"""SELECT sum(pg_total_relation_size(relid))::bigint FROM (
        SELECT relid FROM pg_partition_tree('{SAIDA_A}') UNION ALL
        SELECT relid FROM pg_partition_tree('{SAIDA_B}')) t;""", pasta / "tamanho"))


def preparar_caso(exp, dataset, algoritmo, entradas, caso):
    """Particiona e materializa fora das medições, separando o custo de cada etapa."""
    with tempfile.TemporaryDirectory(prefix=".associacoes-", dir=caso) as temp_assoc:
        inicio = time.perf_counter()
        metadata = exp.particionar(algoritmo, entradas, Path(temp_assoc), caso)
        meio = time.perf_counter()
        exp.materializar(dataset, Path(temp_assoc), metadata, caso)
        fim = time.perf_counter()
    validar_pares(exp, dataset, algoritmo, caso)
    return metadata, {"particionamento_s": meio - inicio, "materializacao_s": fim - meio,
                      "tamanho_saidas_bytes": tamanho_saidas(exp, caso)}


def executar(args):
    config = carregar_config(args.config)
    workload = args.workloads[0]
    casos = [(algoritmo, alvo) for algoritmo in args.algoritmos
             for alvo in ([None] if algoritmo == "SEM_PARTICIONAMENTO" else args.particoes)]
    if args.simular:
        for algoritmo, alvo in casos:
            print(f"{config['dataset']} / {workload} / {algoritmo}: alvo={alvo or 'N/A'}; "
                  f"workers={args.workers}; GiST=on; A={args.objetos_a}, B={args.objetos_b}; "
                  f"perf={'on' if args.perf else 'off'}")
        return
    pasta = args.saida.resolve() / ("pp5_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True)
    schema = pasta.name.lower()
    meta = metadados_execucao(pasta.name)
    meta["pp5_run_id"] = meta.pop("pp1_run_id")
    salvar_json(pasta / "configuracao.json", {**vars(args), "config": str(args.config.resolve()),
                "saida": str(pasta), "fontes": config, "indexacao": "on", "gist": "on", **meta})
    # O particionador recebe um alvo escalar; a configuração da matriz permanece intacta.
    exp = Experimento(Namespace(**{**vars(args), "particoes": None}), pasta)
    manifesto = {"status": "em_execucao", "combinacoes": [], "schema_amostras": schema}
    salvar_json(pasta / "manifesto.json", manifesto)
    criado = False
    try:
        if args.perf:
            verificar_perf(args.perf_eventos, pasta, exp.ambiente)
        servidor = registrar_servidor(exp, pasta)
        if any(alvo is not None for _, alvo in casos):
            avisar_locks(servidor, args)
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
            if any(alvo is not None for _, alvo in casos):
                exp.exportar(dataset, entradas, destino)
            for algoritmo, alvo in casos:
                print(f"PP5 {config['dataset']} / {workload} / {algoritmo} / alvo={alvo or 'N/A'}", flush=True)
                caso = destino / algoritmo.lower() / (f"particoes_{alvo}" if alvo else "sem_particoes")
                caso.mkdir(parents=True)
                registro = {"workload": workload, "algoritmo": algoritmo, "particoes_alvo": alvo or "",
                            "status": "em_execucao"}
                manifesto["combinacoes"].append(registro)
                salvar_json(pasta / "manifesto.json", manifesto)
                if alvo is None:
                    metadata = {"particoes_efetivas": "", "capacidade": ""}
                    preparo = {"particionamento_s": "", "materializacao_s": "", "tamanho_saidas_bytes": ""}
                    balanceamento = dict.fromkeys(
                        ("particoes_vazias", "particoes_com_a_e_b", "carga_media", "carga_maxima",
                         "carga_max_sobre_media", "carga_cv", "fator_replicacao", "pares_candidatos",
                         "pares_max_sobre_media"), "")
                    consulta = consulta_direta(dataset)
                else:
                    exp.args.particoes = alvo
                    metadata, preparo = preparar_caso(exp, dataset, algoritmo, entradas, caso)
                    balanceamento = resumir_balanceamento(metadata)
                    consulta = consulta_particionada(algoritmo)
                atual = registrar_servidor(exp, caso)
                if atual != servidor:
                    raise RuntimeError("Configuração do servidor mudou entre casos; confira os arquivos servidor.json")
                medicoes = exp.medir(dataset, algoritmo, consulta, esperado, caso)
                plano = json.loads((caso / "plano.json").read_text(encoding="utf-8"))
                diagnostico = resumir_plano(plano)
                salvar_json(caso / "paralelismo.json", diagnostico)
                planejamento = medir_planejamento(exp, consulta, args.repeticoes, caso)
                # anexar_csv grava por nome de coluna: todos os casos precisam ter as mesmas chaves.
                contexto = {"dataset": config["dataset"], "workload": workload, "gist": "on",
                            "objetos_a": args.objetos_a, "objetos_b": args.objetos_b, "semente": args.semente,
                            "ids_a_md5": escala[nome_a]["ids_md5"], "ids_b_md5": escala["poligonos_b"]["ids_md5"],
                            "seletividade": esperado / (args.objetos_a * args.objetos_b),
                            "particoes_alvo": alvo or "", "particoes_efetivas": metadata["particoes_efetivas"],
                            "capacidade": metadata["capacidade"], **balanceamento, **preparo, **planejamento,
                            "plano_execucao_ms": plano[0]["Execution Time"],
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
        raise SystemExit(f"PP5 interrompida: {erro}\nLogs: {pasta}") from erro
    finally:
        if criado:
            try:
                exp.sql(f"DROP SCHEMA {identificador(schema)} CASCADE;", pasta / "limpeza")
                manifesto["amostras_removidas"] = True
            except Exception as erro:
                manifesto["erro_limpeza"] = str(erro)
                print(f"Aviso: schema de amostras mantido: {schema}; {erro}")
        salvar_json(pasta / "manifesto.json", manifesto)
    print(f"PP5 concluída: {pasta}")
    try:
        imprimir_resumo(consolidar(pasta.parent, "pp5"), "pp5")
    except Exception as erro:
        print(f"Aviso: consolidação falhou; brutos preservados: {erro}")


if __name__ == "__main__":
    executar(argumentos())
