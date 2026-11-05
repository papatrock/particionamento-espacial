"""Argumentos comuns às PPs com amostras (PP2 a PP5)."""
import argparse
from math import isqrt
from pathlib import Path

from nucleo.amostras import WORKLOADS
from nucleo.arquivos import RAIZ
from nucleo.experimento import ALGORITMOS
from nucleo.perf_coleta import argumentos_perf


def criar_parser(workers_lista=False, particoes_lista=False):
    p = argparse.ArgumentParser()
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
        p.add_argument("--workers", type=int, default=8)
    p.add_argument("--aquecimentos", type=int, default=3)
    p.add_argument("--repeticoes", type=int, default=10)
    p.add_argument("--rodada", type=int, default=1)
    p.add_argument("--hilbert-bits", type=int, default=16)
    p.add_argument("--bsp-tentativas", type=int, default=8)
    p.add_argument("--saida", type=Path, default=Path("resultados/pp2"))
    p.add_argument("--simular", action="store_true")
    argumentos_perf(p)
    return p


def validar_argumentos(argv=None, parser=None):
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
