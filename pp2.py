"""PP2: algoritmos × workloads reais, com cardinalidades A/B fixadas explicitamente."""
from pathlib import Path
import tempfile

from nucleo.amostras import WORKLOADS, carregar_config, validar_pares
from nucleo.argumentos import criar_parser, validar_argumentos
from nucleo.consultas import consulta_direta, consulta_particionada
from nucleo.execucao import execucao_amostrada


def argumentos(argv=None):
    parser = criar_parser()
    parser.description = __doc__
    return validar_argumentos(argv, parser=parser)


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
    with execucao_amostrada("pp2", args, config) as run:
        exp = run.exp
        escala = run.preparar()
        for workload in args.workloads:
            nome_a = WORKLOADS[workload]
            dataset = run.dataset(workload)
            destino = run.pasta / workload
            destino.mkdir()
            exp.preparar_entradas(dataset, destino)
            esperado = int(exp.sql(exp.configuracao_sessao() + "\n" + consulta_direta(dataset), destino / "baseline"))
            with tempfile.TemporaryDirectory(prefix=".entradas-", dir=destino) as temp:
                entradas = Path(temp)
                if any(a != "SEM_PARTICIONAMENTO" for a in args.algoritmos):
                    exp.exportar(dataset, entradas, destino)
                for algoritmo in args.algoritmos:
                    print(f"PP2 {config['dataset']} / {workload} / {algoritmo}", flush=True)
                    caso = destino / algoritmo.lower()
                    caso.mkdir()
                    registro = run.iniciar_caso(workload=workload, algoritmo=algoritmo)
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
                    run.concluir_caso(registro, medicoes, contexto, esperado)


if __name__ == "__main__":
    executar(argumentos())
