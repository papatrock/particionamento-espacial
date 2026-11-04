"""PP4: algoritmos × limites de workers, com workload, amostras e GiST fixos."""
from argparse import Namespace
import json
from pathlib import Path
import tempfile

from nucleo.amostras import WORKLOADS, carregar_config, validar_pares
from nucleo.argumentos import criar_parser, validar_argumentos
from nucleo.arquivos import salvar_json
from nucleo.consultas import consulta_direta, consulta_particionada
from nucleo.execucao import execucao_amostrada
from nucleo.servidor import registrar_servidor, resumir_plano


def argumentos(argv=None):
    parser = criar_parser(workers_lista=True)
    parser.description = __doc__
    parser.set_defaults(workloads=["linha_poligono"], saida=Path("resultados/pp4"))
    args = validar_argumentos(argv, parser=parser)
    if len(args.workloads) != 1:
        parser.error("A PP4 fixa um workload por execução; informe apenas um em --workloads")
    args.workers = list(dict.fromkeys(args.workers))
    if 0 not in args.workers:
        parser.error("Inclua 0 em --workers para medir a referência serial de cada algoritmo")
    return args


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
    # O executor/coletor recebe um limite escalar; a configuração da matriz permanece intacta.
    args_experimento = Namespace(**{**vars(args), "workers": 0})
    with execucao_amostrada("pp4", args, config, extras={"gist": "on"}, args_experimento=args_experimento) as run:
        exp = run.exp
        servidor = registrar_servidor(exp, run.pasta)
        limite = min(int(servidor["max_parallel_workers"]), int(servidor["max_worker_processes"]))
        if max(args.workers) > limite:
            print(f"Aviso: a matriz solicita até {max(args.workers)} workers, mas os limites globais permitem "
                  f"no máximo {limite}; a disponibilidade pode ser menor. Confira os planos.", flush=True)
        escala = run.preparar()
        nome_a = WORKLOADS[workload]
        dataset = run.dataset(workload)
        destino = run.pasta / workload
        destino.mkdir()
        exp.preparar_entradas(dataset, destino)
        esperado = int(exp.sql(exp.configuracao_sessao() + "\n" + consulta_direta(dataset), destino / "referencia"))
        with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temp:
            entradas = Path(temp)
            if any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos):
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
                    registro = run.iniciar_caso(workload=workload, algoritmo=algoritmo, workers_por_gather=workers)
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
                    run.concluir_caso(registro, medicoes, contexto, esperado)


if __name__ == "__main__":
    executar(argumentos())
