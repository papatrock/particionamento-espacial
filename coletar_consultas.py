import argparse
import csv
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument("--cenario", required=True) #pp1: brasil_roads x brasil_polygon
parser.add_argument("--algoritmo", required=True)
parser.add_argument("--sql", type=Path, required=True)
parser.add_argument("--banco", default="tcc_espacial")
parser.add_argument("--indexacao", choices=("on", "off"), default="on")
parser.add_argument("--aquecimentos", type=int, default=3)
parser.add_argument("--repeticoes", type=int, default=10)
parser.add_argument("--rodada", type=int, default=1)
parser.add_argument("--saida", type=Path, default=Path("resultados/pp1"))
args = parser.parse_args()

if args.aquecimentos < 0 or args.repeticoes < 1:
    parser.error("Use aquecimentos >= 0 e repeticoes >= 1.")

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
    "SET max_parallel_workers_per_gather = 0;",
    "SET enable_partitionwise_join = on;",
    "SET enable_seqscan = on;",
    f"SET enable_indexscan = {args.indexacao};",
    f"SET enable_indexonlyscan = {args.indexacao};",
    f"SET enable_bitmapscan = {args.indexacao};",
]

comandos.extend([consulta] * args.aquecimentos)
comandos.append(r"\timing on")
comandos.extend([consulta] * args.repeticoes)

ambiente = os.environ.copy()
ambiente["LC_ALL"] = "C"  # Padroniza a saída: "Time: ... ms".

resultado = subprocess.run(
    [
        "psql",
        "--host", "localhost",
        "--port", "5432",
        "--username", "postgres",
        "-X",                       # Ignora personalizações do .psqlrc.
        "--no-password",            # Falha em vez de esperar senha interativa.
        "--set=ON_ERROR_STOP=1",
        "--dbname", args.banco,
    ],
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
    ])

    for repeticao, tempo in enumerate(tempos, start=1):
        writer.writerow([
            execucao, args.cenario, args.algoritmo, args.rodada,
            repeticao, args.aquecimentos, tempo,
        ])

print(f"{len(tempos)} medições salvas em {pasta / 'consultas.csv'}")