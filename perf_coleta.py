"""Perf system-wide, habilitado somente no bloco de repetições do coletor."""

import csv
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import tempfile


EVENTOS_PADRAO = (
    "cycles,instructions,cache-references,cache-misses,branches,branch-misses,"
    "context-switches,cpu-migrations,page-faults"
)


def argumentos_perf(parser):
    parser.add_argument("--perf", action="store_true",
                        help="Coleta perf stat -a no bloco de repetições; execute no servidor PostgreSQL.")
    parser.add_argument("--perf-eventos", default=EVENTOS_PADRAO,
                        help="Seletores de eventos do perf, separados por vírgula.")


def verificar_perf(eventos, pasta, ambiente):
    """Falha antes dos joins longos se perf ou suas permissões estiverem ausentes."""
    if not shutil.which("perf", path=ambiente.get("PATH")):
        raise RuntimeError("perf não está instalado ou não está no PATH.")
    if not eventos.strip():
        raise RuntimeError("Informe ao menos um evento em --perf-eventos.")
    ajuda = subprocess.run(["perf", "stat", "-h"], text=True, capture_output=True, env=ambiente)
    if "--control" not in ajuda.stdout + ajuda.stderr:
        raise RuntimeError("Esta versão de perf stat não oferece --control; atualize o perf para excluir os aquecimentos.")
    resultado = subprocess.run([
        "perf", "stat", "-a", "--no-big-num", "-x", ";", "-e", eventos,
        "-o", str(pasta / "perf_verificacao.csv"), "--", "true",
    ], text=True, capture_output=True, env=ambiente)
    (pasta / "perf_verificacao.stdout.log").write_text(resultado.stdout, encoding="utf-8")
    (pasta / "perf_verificacao.stderr.log").write_text(resultado.stderr, encoding="utf-8")
    if resultado.returncode:
        raise RuntimeError("Perf indisponível: verifique eventos e permissão para perf stat -a. "
                           f"Detalhes: {pasta / 'perf_verificacao.stderr.log'}\n{resultado.stderr.strip()}")


def controlar(acao, controle, resposta, timeout=15):
    r"""Espera ACK com prazo limitado; usado pelo psql via \! antes/depois das medições."""
    if acao not in ("enable", "disable"):
        raise ValueError("Comando de controle perf inválido")
    flags = os.O_RDWR | os.O_NONBLOCK
    ctl = os.open(controle, flags)
    ack = os.open(resposta, flags)
    try:
        os.write(ctl, (acao + "\n").encode("ascii"))
        if not select.select([ack], [], [], timeout)[0]:
            raise RuntimeError(f"Perf não confirmou {acao} em {timeout:g} segundos")
        mensagem = os.read(ack, 64)
        if mensagem.strip(b" \t\r\n\0") != b"ack":
            raise RuntimeError(f"Resposta inesperada do controle perf: {mensagem!r}")
    finally:
        os.close(ctl)
        os.close(ack)


def comandos_controle(acao, controle, resposta):
    # shlex.join protege caminhos e o interpretador: psql executa \! por um shell.
    comando = shlex.join([sys.executable, str(Path(__file__).resolve()), acao, str(controle), str(resposta)])
    return [
        r"\! " + comando,
        r"\if :SHELL_ERROR",
        # ON_ERROR_STOP do psql não abrange \!; transformar a falha em erro SQL.
        "SELECT 1 / 0 AS falha_controle_perf;",
        r"\endif",
    ]


def executar_perf(comando_psql, preparacao, medicoes, ambiente, pasta, contexto):
    verificar_perf(contexto["eventos"], pasta, ambiente)
    versao = subprocess.run(["perf", "--version"], text=True, capture_output=True, env=ambiente).stdout.strip()
    metadata = {
        **contexto, "versao": versao, "escopo": "sistema_inteiro", "janela": "bloco_repeticoes",
        "inclui_aquecimentos": False, "inclui_overhead_cliente_controle": True, "status": "em_execucao",
    }
    (pasta / "perf.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Caminhos curtos sem vírgula: --control usa vírgula para separar os dois FIFOs.
    with tempfile.TemporaryDirectory(prefix="tcc-perf-", dir="/tmp") as temporario:
        controle, resposta = Path(temporario) / "controle", Path(temporario) / "resposta"
        os.mkfifo(controle, 0o600)
        os.mkfifo(resposta, 0o600)
        comandos = [*preparacao, *comandos_controle("enable", controle, resposta), r"\timing on",
                    *medicoes, r"\timing off", *comandos_controle("disable", controle, resposta)]
        (pasta / "perf_sessao.psql").write_text("\n".join(comandos) + "\n", encoding="utf-8")
        comando = [
            "perf", "stat", "-a", "--no-big-num", "-x", ";", "-e", contexto["eventos"],
            "--delay=-1", f"--control=fifo:{controle},{resposta}",
            "-o", str(pasta / "perf_stat.csv"), "--", *comando_psql,
        ]
        resultado = subprocess.run(comando, input="\n".join(comandos) + "\n", text=True,
                                   capture_output=True, env=ambiente)
    metadata["status"] = "aguardando_validacao" if resultado.returncode == 0 else "falhou"
    metadata["codigo_retorno"] = resultado.returncode
    (pasta / "perf.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


def finalizar_perf(pasta):
    """Converte o relatório delimitado do perf, preservando valores indisponíveis."""
    metadata = json.loads((pasta / "perf.json").read_text(encoding="utf-8"))
    linhas = []
    with (pasta / "perf_stat.csv").open(encoding="utf-8") as arquivo:
        for campos in csv.reader(arquivo, delimiter=";"):
            if len(campos) < 5 or campos[0].startswith("#") or not campos[2].strip():
                continue
            valor, unidade, evento, tempo_ativo, percentual = (c.strip() for c in campos[:5])
            # Linhas adicionais de métricas não possuem valor de contador.
            if not valor:
                continue
            status = {"<not supported>": "nao_suportado", "<not counted>": "nao_contado"}.get(valor, "ok")
            linhas.append({
                "execucao": metadata["execucao"], "cenario": metadata["cenario"],
                "algoritmo": metadata["algoritmo"], "rodada": metadata["rodada"],
                "repeticoes": metadata["repeticoes"], "escopo": metadata["escopo"],
                "evento": evento, "valor": valor if status == "ok" else "", "unidade": unidade,
                "status": status, "tempo_ativo_ns": tempo_ativo, "percentual_ativo": percentual,
            })
    if not linhas:
        raise RuntimeError(f"Perf não produziu contadores; confira {pasta / 'perf_stat.csv'}.")
    with (pasta / "perf.csv").open("w", newline="", encoding="utf-8") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        writer.writeheader()
        writer.writerows(linhas)
    metadata["status"] = "concluido" if all(l["status"] == "ok" for l in linhas) else "contadores_indisponiveis"
    (pasta / "perf.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata["status"]


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Uso interno: perf_coleta.py enable|disable controle resposta")
        controlar(*sys.argv[1:])
    except (OSError, RuntimeError, ValueError) as erro:
        print(f"Falha no controle perf: {erro}", file=sys.stderr)
        raise SystemExit(1) from erro
