"""Roda as PPs em sequência, sem supervisão: uma etapa que falha não impede as seguintes.

    nohup python3 rodar_tudo.py --saida /disk1/pol21/resultados/final > /disk1/pol21/rodada_final.log 2>&1 &
    python3 rodar_tudo.py --mostrar     # só lista o plano
    pkill -f rodar_tudo.py              # interrompe a etapa atual e encerra
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
# Refaz só os baselines de PP2 a PP5, com as amostras gravadas por id. Os particionados não mudam.
SO_BASELINE = ["--algoritmos", "SEM_PARTICIONAMENTO"]
ETAPAS = [
    ("pp2_pr_centro_baseline", "pp2", [*config("pr_centro"), *AMOSTRA_60MIL, *SO_BASELINE], 1, False),
    ("pp2_pr_curitiba_baseline", "pp2", [*config("pr_curitiba"), *AMOSTRA_60MIL, *SO_BASELINE], 1, False),
    ("pp3_es_sul_baseline", "pp3", [*config("es_sul"), *ES_SUL, *SO_BASELINE], 1, False),
    ("pp3_pr_centro_baseline", "pp3", [*config("pr_centro"), *AMOSTRA_60MIL, *SO_BASELINE], 2, False),
    ("pp4_es_sul_baseline", "pp4", [*config("es_sul"), *ES_SUL, *SO_BASELINE], 1, False),
    ("pp4_ms_campo_grande_baseline", "pp4", [*config("ms_campo_grande"), *MS, *SO_BASELINE], 1, False),
    ("pp5_pr_centro_baseline", "pp5", [*config("pr_centro"), *PR_CENTRO, *SO_BASELINE], 1, False),
    ("pp5_pr_curitiba_baseline", "pp5", [*config("pr_curitiba"), *PR_CURITIBA, *SO_BASELINE], 1, False),
]
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
    parser.add_argument("--mostrar", action="store_true")
    args = parser.parse_args()
    if args.mostrar:
        for nome, script, argumentos, horas, _ in ETAPAS:
            print(f"{nome}: python3 {script}.py {' '.join(argumentos)} (máximo {horas:g} h)")
        return
    signal.signal(signal.SIGTERM, pedir_parada)
    pasta = args.saida / ("noite_" + datetime.now().strftime("%Y%m%d_%H%M"))
    pasta.mkdir(parents=True)
    prazo = datetime.now() + timedelta(hours=args.prazo_horas)
    pastas = pastas_vigiadas(args.saida)
    resumo = pasta / "resumo.csv"
    with resumo.open("w", newline="", encoding="utf-8") as arquivo:
        writer = csv.writer(arquivo)
        writer.writerow(["etapa", "status", "inicio", "minutos", "log"])
        for nome, script, argumentos, horas, respeita_prazo in ETAPAS:
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
