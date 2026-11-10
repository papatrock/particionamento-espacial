"""Roda as PPs em sequência, sem supervisão: uma etapa que falha não impede as seguintes.

    nohup python3 rodar_tudo.py --plano perf --saida /disk1/pol21/resultados/perf > /disk1/pol21/rodada_perf.log 2>&1 &
    python3 rodar_tudo.py --plano perf --mostrar     # só lista o plano
    pkill -f rodar_tudo.py                           # interrompe a etapa atual e encerra
"""
import argparse
import csv
from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

RAIZ = Path(__file__).resolve().parent
ALVOS = ["--particoes", "4", "16", "64", "256"]  # 1024 exige aumentar max_locks_per_transaction


def amostra(a, b):
    return ["--objetos-a", str(a), "--objetos-b", str(b)]


# Tamanhos das tabelas _mapa: linhas e polígonos de cada região, usados por inteiro.
ES_SUL = amostra(31_163, 29_505)
MS = amostra(34_603, 25_371)
PR_CENTRO = amostra(288_114, 271_951)
PR_CURITIBA = amostra(225_443, 332_511)
AMOSTRA_60MIL = amostra(60_000, 60_000)


def config(regiao):
    return ["--config", f"experimentos/regioes/{regiao}_mapa.json"]


MASJ_REDUZIDO = ["--particoes-masj", "4", "64"]  # STR e Hilbert em MASJ pioram com mais partições e são os mais lentos.

# (nome, script, argumentos, horas no máximo, respeita o prazo de início)
# Argumentos da etapa vêm depois dos padrões, então um --saida aqui substitui o padrão.
SO_BASELINE = ["--algoritmos", "SEM_PARTICIONAMENTO"]
PERF = ["--perf"]

# Contadores de hardware para explicar os tempos da rodada principal (05/11). Os tempos medidos aqui
# não substituem os oficiais: o perf -a conta a máquina inteira e só as razões entre casos importam.
PLANO_PERF = [
    # Replicação: STR e Hilbert em MASJ executam mais instruções na proporção da replicação?
    # es_sul replica ~9x e pr_centro ~3,5x; o baseline aqui usa as tabelas originais da região.
    ("perf_pp1_es_sul", "pp1", ["--datasets", "es_sul_mapa", *PERF], 1, False),
    ("perf_pp1_pr_centro", "pp1", ["--datasets", "pr_centro_mapa", *PERF], 1.5, False),
    # Ordem física: os mesmos objetos de pr_centro, gravados em três ordens; só o baseline é medido.
    *[(f"perf_ordem_pr_centro_{ordem}", "pp5",
       [*config("pr_centro"), *PR_CENTRO, *SO_BASELINE, "--particoes", "64", "--ordem-amostra", ordem, *PERF], 1, False)
      for ordem in ("sorteio", "id", "espacial")],
    # SAMJ no PP4: o salto com 1 worker (um Gather por par de partições) aparece nas trocas de contexto?
    ("perf_pp4_es_sul_samj", "pp4",
     [*config("es_sul"), *ES_SUL, "--algoritmos", "SEM_PARTICIONAMENTO", "STR_SAMJ", "HILBERT_SAMJ",
      "--workers", "0", "1", "2", "8", *PERF], 1, False),
]

# Refaz só os baselines de PP2 a PP5, com as amostras gravadas por id. Os particionados não mudam.
PLANO_BASELINES = [
    ("pp2_pr_centro_baseline", "pp2", [*config("pr_centro"), *AMOSTRA_60MIL, *SO_BASELINE], 1, False),
    ("pp2_pr_curitiba_baseline", "pp2", [*config("pr_curitiba"), *AMOSTRA_60MIL, *SO_BASELINE], 1, False),
    ("pp3_es_sul_baseline", "pp3", [*config("es_sul"), *ES_SUL, *SO_BASELINE], 1, False),
    ("pp3_pr_centro_baseline", "pp3", [*config("pr_centro"), *AMOSTRA_60MIL, *SO_BASELINE], 2, False),
    ("pp4_es_sul_baseline", "pp4", [*config("es_sul"), *ES_SUL, *SO_BASELINE], 1, False),
    ("pp4_ms_campo_grande_baseline", "pp4", [*config("ms_campo_grande"), *MS, *SO_BASELINE], 1, False),
    ("pp5_pr_centro_baseline", "pp5", [*config("pr_centro"), *PR_CENTRO, *SO_BASELINE], 1, False),
    ("pp5_pr_curitiba_baseline", "pp5", [*config("pr_curitiba"), *PR_CURITIBA, *SO_BASELINE], 1, False),
]
PLANOS = {"perf": PLANO_PERF, "baselines": PLANO_BASELINES}
ESPERA_LIMPEZA_S = 600
parar = False


def pedir_parada(*_):
    global parar
    parar = True


def livre_gb(caminho):
    return shutil.disk_usage(caminho).free / 1024 ** 3


def pastas_vigiadas(saida):
    """Vigia os resultados e, se o usuário puder consultar, a pasta de dados do PostgreSQL."""
    pastas = [saida]
    consulta = subprocess.run(["psql", "-X", "-A", "-t", "-d", "benchmark", "-c", "SHOW data_directory"],
                              text=True, capture_output=True)
    dados = Path(consulta.stdout.strip())
    try:
        if consulta.returncode or not dados.is_absolute():
            raise OSError(consulta.stderr.strip() or "resposta vazia")
        livre_gb(dados)
        pastas.append(dados)
    except OSError as erro:
        print(f"Aviso: disco do PostgreSQL não será vigiado ({erro}). Confira com df antes de sair.", flush=True)
    return pastas


def verificar_perf_disponivel():
    """Sem permissão para perf stat -a, todas as etapas falhariam uma a uma; melhor parar antes."""
    if not shutil.which("perf"):
        return "perf não está instalado ou não está no PATH"
    teste = subprocess.run(["perf", "stat", "-a", "-e", "cycles,instructions", "--", "true"],
                           text=True, capture_output=True)
    if teste.returncode:
        return (f"perf stat -a falhou ({teste.stderr.strip().splitlines()[-1] if teste.stderr.strip() else 'sem mensagem'}). "
                "Confira /proc/sys/kernel/perf_event_paranoid (precisa ser <= 0) ou peça permissão ao administrador")
    return None


def interromper(processo):
    """SIGINT deixa a PP marcar a execução como falhou e remover as amostras."""
    os.killpg(processo.pid, signal.SIGINT)
    try:
        processo.wait(ESPERA_LIMPEZA_S)
    except subprocess.TimeoutExpired:
        os.killpg(processo.pid, signal.SIGKILL)
        processo.wait()


def executar_etapa(script, argumentos, horas, saida, log, pastas, disco_minimo):
    comando = [sys.executable, f"{script}.py", "--banco", "benchmark", "--saida", str(saida / script), *argumentos]
    limite = time.monotonic() + horas * 3600
    with log.open("w", encoding="utf-8") as arquivo:
        # Grupo próprio: o sinal alcança psql e Maven. Em segundo plano, o SIGINT herdado pode estar ignorado.
        processo = subprocess.Popen(comando, cwd=RAIZ, stdout=arquivo, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True,
                                    preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        while processo.poll() is None:
            time.sleep(min(15, max(0.1, limite - time.monotonic())))
            motivo = None
            if parar:
                motivo = "interrompida_pelo_usuario"
            elif time.monotonic() >= limite:
                motivo = "tempo_maximo"
            elif any(livre_gb(p) < disco_minimo for p in pastas):
                motivo = "pouco_disco"
            if motivo and processo.poll() is None:
                interromper(processo)
                return motivo
    return "concluida" if processo.returncode == 0 else f"falhou_codigo_{processo.returncode}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", type=Path, default=Path("/disk1/pol21/resultados"))
    parser.add_argument("--prazo-horas", type=float, default=6,
                        help="Depois disso, só as etapas do PP1 ainda começam (padrão: 6).")
    parser.add_argument("--disco-minimo-gb", type=float, default=20,
                        help="Interrompe a etapa se o espaço livre ficar abaixo disso (padrão: 20).")
    parser.add_argument("--plano", choices=PLANOS, default="perf",
                        help="perf: contadores de hardware; baselines: repetição dos baselines de 08/11.")
    parser.add_argument("--mostrar", action="store_true")
    args = parser.parse_args()
    etapas = PLANOS[args.plano]
    if args.mostrar:
        for nome, script, argumentos, horas, _ in etapas:
            print(f"{nome}: python3 {script}.py {' '.join(argumentos)} (máximo {horas:g} h)")
        return
    if any("--perf" in argumentos for _, _, argumentos, _, _ in etapas):
        problema = verificar_perf_disponivel()
        if problema:
            parser.exit(1, f"Plano não iniciado: {problema}.\n")
    signal.signal(signal.SIGTERM, pedir_parada)
    pasta = args.saida / ("noite_" + datetime.now().strftime("%Y%m%d_%H%M"))
    pasta.mkdir(parents=True)
    prazo = datetime.now() + timedelta(hours=args.prazo_horas)
    pastas = pastas_vigiadas(args.saida)
    resumo = pasta / "resumo.csv"
    with resumo.open("w", newline="", encoding="utf-8") as arquivo:
        writer = csv.writer(arquivo)
        writer.writerow(["etapa", "status", "inicio", "minutos", "log"])
        for nome, script, argumentos, horas, respeita_prazo in etapas:
            inicio = datetime.now()
            if parar or (respeita_prazo and inicio > prazo):
                status, minutos, log = "nao_iniciada", 0, ""
            else:
                print(f"{inicio:%H:%M} iniciando {nome} (máximo {horas:g} h)", flush=True)
                log = pasta / f"{nome}.log"
                status = executar_etapa(script, argumentos, horas, args.saida, log, pastas, args.disco_minimo_gb)
                minutos = round((datetime.now() - inicio).total_seconds() / 60, 1)
            print(f"{datetime.now():%H:%M} {nome}: {status} ({minutos} min)", flush=True)
            writer.writerow([nome, status, f"{inicio:%Y-%m-%d %H:%M}", minutos, log])
            arquivo.flush()
    print(f"Fim. Resumo: {resumo}", flush=True)


if __name__ == "__main__":
    main()
