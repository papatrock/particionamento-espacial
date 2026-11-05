"""PP5: algoritmos × número de partições, com workload, amostras, workers e GiST fixos."""
from argparse import Namespace
import json
from math import ceil
from pathlib import Path
import statistics
import tempfile
import time

from nucleo.amostras import WORKLOADS, carregar_config, validar_pares
from nucleo.argumentos import criar_parser, validar_argumentos
from nucleo.arquivos import salvar_json
from nucleo.consultas import SAIDA_A, SAIDA_B, consulta_direta, consulta_particionada
from nucleo.experimento import VARIANTES_SAMJ
from nucleo.execucao import execucao_amostrada
from nucleo.servidor import registrar_servidor, resumir_plano


def argumentos(argv=None):
    parser = criar_parser(particoes_lista=True, variantes_samj=True)
    parser.description = __doc__
    parser.add_argument("--particoes-masj", type=int, nargs="+",
                        help="Alvos de STR e Hilbert em MASJ, os casos mais lentos (padrão: todos de --particoes).")
    parser.set_defaults(workloads=["linha_poligono"], saida=Path("resultados/pp5"))
    args = validar_argumentos(argv, parser=parser)
    if len(args.workloads) != 1:
        parser.error("A PP5 fixa um workload por execução; informe apenas um em --workloads")
    args.particoes = sorted(set(args.particoes))
    if args.particoes_masj is not None:
        args.particoes_masj = sorted(set(args.particoes_masj))
        if not set(args.particoes_masj) <= set(args.particoes):
            parser.error("--particoes-masj precisa ser um subconjunto de --particoes")
    return args


def alvos_do_algoritmo(algoritmo, args):
    if algoritmo == "SEM_PARTICIONAMENTO":
        return [None]
    if algoritmo in ("STR", "HILBERT") and args.particoes_masj is not None:
        return args.particoes_masj
    return args.particoes


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
    # No SAMJ, o trabalho vem dos pares de grupos comparados, não só de cada grupo consigo mesmo.
    por_id = {o["id"]: o for o in ocupacoes}
    pares = ([por_id[p["a"]]["objetos_a"] * por_id[p["b"]]["objetos_b"] for p in metadata["pares_particoes"]]
             if metadata.get("modelo_join") == "SAMJ" else [o["objetos_a"] * o["objetos_b"] for o in ocupacoes])
    media, media_pares = statistics.mean(cargas), statistics.mean(pares)
    return {"particoes_vazias": cargas.count(0),
            "particoes_com_a_e_b": sum(o["objetos_a"] > 0 and o["objetos_b"] > 0 for o in ocupacoes),
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
        metadata = exp.particionar(VARIANTES_SAMJ.get(algoritmo, algoritmo), entradas, Path(temp_assoc), caso,
                                   associacao_unica=algoritmo in VARIANTES_SAMJ)
        meio = time.perf_counter()
        exp.materializar(dataset, Path(temp_assoc), metadata, caso)
        fim = time.perf_counter()
    validar_pares(exp, dataset, VARIANTES_SAMJ.get(algoritmo, algoritmo), caso, metadata)
    return metadata, {"particionamento_s": meio - inicio, "materializacao_s": fim - meio,
                      "tamanho_saidas_bytes": tamanho_saidas(exp, caso),
                      "pares_de_particoes": len(metadata["pares_particoes"]) if "pares_particoes" in metadata else ""}


def executar(args):
    config = carregar_config(args.config)
    workload = args.workloads[0]
    casos = [(algoritmo, alvo) for algoritmo in args.algoritmos
             for alvo in alvos_do_algoritmo(algoritmo, args)]
    if args.simular:
        for algoritmo, alvo in casos:
            print(f"{config['dataset']} / {workload} / {algoritmo}: alvo={alvo or 'N/A'}; "
                  f"workers={args.workers}; GiST=on; A={args.objetos_a}, B={args.objetos_b}; "
                  f"perf={'on' if args.perf else 'off'}")
        return
    # O particionador recebe um alvo escalar; a configuração da matriz permanece intacta.
    args_experimento = Namespace(**{**vars(args), "particoes": None})
    with execucao_amostrada("pp5", args, config, extras={"gist": "on"}, args_experimento=args_experimento) as run:
        exp = run.exp
        servidor = registrar_servidor(exp, run.pasta)
        if any(alvo is not None for _, alvo in casos):
            avisar_locks(servidor, args)
        escala = run.preparar()
        nome_a = WORKLOADS[workload]
        dataset = run.dataset(workload)
        destino = run.pasta / workload
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
                registro = run.iniciar_caso(workload=workload, algoritmo=algoritmo, particoes_alvo=alvo or "")
                if alvo is None:
                    metadata = {"particoes_efetivas": "", "capacidade": ""}
                    preparo = {"particionamento_s": "", "materializacao_s": "", "tamanho_saidas_bytes": "", "pares_de_particoes": ""}
                    balanceamento = dict.fromkeys(
                        ("particoes_vazias", "particoes_com_a_e_b", "carga_media", "carga_maxima",
                         "carga_max_sobre_media", "carga_cv", "fator_replicacao", "pares_candidatos",
                         "pares_max_sobre_media"), "")
                    consulta = consulta_direta(dataset)
                else:
                    exp.args.particoes = alvo
                    metadata, preparo = preparar_caso(exp, dataset, algoritmo, entradas, caso)
                    balanceamento = resumir_balanceamento(metadata)
                    consulta = consulta_particionada(VARIANTES_SAMJ.get(algoritmo, algoritmo), metadata)
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
                run.concluir_caso(registro, medicoes, contexto, esperado)


if __name__ == "__main__":
    executar(argumentos())
