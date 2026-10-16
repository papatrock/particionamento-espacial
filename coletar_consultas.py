import argparse
import csv
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument("--cenario", required=True) #pp1: brasil_line x brasil_polygon
parser.add_argument("--algoritmo", required=True)
parser.add_argument("--sql", type=Path, required=True)
parser.add_argument("--banco", default="benchmark")
parser.add_argument("--host", help="Host do PostgreSQL; omitido, usa o padrão do psql (conexão local).")
parser.add_argument("--porta", type=int, help="Porta do PostgreSQL; omitida, usa o padrão do psql.")
parser.add_argument("--usuario", help="Usuário do PostgreSQL; omitido, usa o padrão do psql (usuário do sistema).")
parser.add_argument("--indexacao", choices=("on", "off"), default="on",
                    help="Habilita/desabilita métodos de acesso por índice; não cria nem remove GiST.")
parser.add_argument("--workers", type=int, default=24,
                    help="Limite de workers paralelos por Gather (padrão: 24; 0 desabilita paralelismo).")
parser.add_argument("--aquecimentos", type=int, default=3)
parser.add_argument("--repeticoes", type=int, default=10)
parser.add_argument("--rodada", type=int, default=1)
parser.add_argument("--contagem-esperada", type=int,
                    help="Valida o COUNT escalar de cada aquecimento e repetição contra este valor.")
parser.add_argument("--saida", type=Path, default=Path("resultados/pp1"))
args = parser.parse_args()

if args.aquecimentos < 0 or args.repeticoes < 1:
    parser.error("Use aquecimentos >= 0 e repeticoes >= 1.")
if args.workers < 0:
    parser.error("Use workers >= 0.")
if args.porta is not None and not 1 <= args.porta <= 65535:
    parser.error("Use uma porta entre 1 e 65535.")
if args.contagem_esperada is not None and args.contagem_esperada < 0:
    parser.error("Use contagem-esperada >= 0.")

# O arquivo deve conter uma única consulta SELECT terminada em ponto e vírgula.
consulta = args.sql.read_text(encoding="utf-8").strip()
if not consulta:
    parser.error("O arquivo SQL está vazio.")
if not consulta.endswith(";"):
    consulta += ";"

execucao = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
pasta = args.saida / execucao
pasta.mkdir(parents=True, exist_ok=False)
(pasta / "consulta.sql").write_text(consulta, encoding="utf-8")

# Tudo é enviado ao mesmo processo psql: a conexão permanece aberta.
comandos = [
    r"\pset pager off",
    r"\timing off",
    f"SET max_parallel_workers_per_gather = {args.workers};",
    "SET enable_partitionwise_join = on;",
    "SET enable_seqscan = on;",
    f"SET enable_indexscan = {args.indexacao};",
    f"SET enable_indexonlyscan = {args.indexacao};",
    f"SET enable_bitmapscan = {args.indexacao};",
    "SHOW max_parallel_workers_per_gather;",
    "SHOW max_parallel_workers;",
    "SHOW max_worker_processes;",
]

marcador = "__COLETAR_CONTAGEM__"
consulta_marcada = [rf"\echo {marcador}", consulta] if args.contagem_esperada is not None else [consulta]
comandos.extend(consulta_marcada * args.aquecimentos)
comandos.append(r"\timing on")
comandos.extend(consulta_marcada * args.repeticoes)

ambiente = os.environ.copy()
ambiente["LC_ALL"] = "C"  # Padroniza a saída: "Time: ... ms".

comando_psql = [
    "psql",
    "-X",                       # Ignora personalizações do .psqlrc.
    "-A", "-t",                 # Resultados escalares sem cabeçalho nem rodapé.
    "--set=ON_ERROR_STOP=1",
    "--dbname", args.banco,
]
# Sem overrides, preserva socket local, usuário e autenticação padrão do psql.
for opcao, valor in (("--host", args.host), ("--port", args.porta), ("--username", args.usuario)):
    if valor is not None:
        comando_psql.extend([opcao, str(valor)])

resultado = subprocess.run(
    comando_psql,
    input="\n".join(comandos) + "\n",
    text=True,
    capture_output=True,
    env=ambiente,
)

(pasta / "psql.stdout.log").write_text(
    resultado.stdout, encoding="utf-8"
)
(pasta / "psql.stderr.log").write_text(
    resultado.stderr, encoding="utf-8"
)

if resultado.returncode != 0:
    raise SystemExit(
        f"A execução falhou. Consulte os logs em {pasta}."
    )

if args.contagem_esperada is not None:
    blocos = resultado.stdout.split(marcador + "\n")[1:]
    total_consultas = args.aquecimentos + args.repeticoes
    contagens = []
    for bloco in blocos:
        primeira_linha = bloco.strip().splitlines()[0] if bloco.strip() else ""
        if not re.fullmatch(r"[0-9]+", primeira_linha):
            raise SystemExit(f"A consulta precisa retornar um COUNT escalar. Confira os logs em {pasta}.")
        contagens.append(int(primeira_linha))
    if len(contagens) != total_consultas or any(c != args.contagem_esperada for c in contagens):
        raise SystemExit(f"Contagem diferente do baseline ({args.contagem_esperada}) ou resultados ausentes: "
                         f"{contagens}. Confira os logs em {pasta}.")

tempos = [
    float(valor)
    for valor in re.findall(
        r"^Time:\s+([0-9]+(?:\.[0-9]+)?)\s+ms",
        resultado.stdout,
        flags=re.MULTILINE,
    )
]

if len(tempos) != args.repeticoes:
    raise SystemExit(
        f"Esperava {args.repeticoes} medições, encontrei {len(tempos)}. "
        f"Confira o SQL e os logs em {pasta}."
    )

with (pasta / "consultas.csv").open(
    "w", newline="", encoding="utf-8"
) as arquivo:
    writer = csv.writer(arquivo)
    writer.writerow([
        "execucao", "cenario", "algoritmo", "rodada",
        "repeticao", "aquecimentos", "tempo_cliente_ms",
        "workers_por_gather", "indexacao",
        "intersecoes",
    ])

    for repeticao, tempo in enumerate(tempos, start=1):
        writer.writerow([
            execucao, args.cenario, args.algoritmo, args.rodada,
            repeticao, args.aquecimentos, tempo,
            args.workers, args.indexacao,
            args.contagem_esperada,
        ])

print(f"{len(tempos)} medições salvas em {pasta / 'consultas.csv'}")
