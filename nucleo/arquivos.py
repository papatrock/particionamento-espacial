"""Gravação de resultados e procedência da execução."""
import csv
import json
from pathlib import Path
import socket
import subprocess

RAIZ = Path(__file__).resolve().parent.parent


def salvar_json(caminho, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def metadados_execucao(pp1_run_id):
    dados = {"pp1_run_id": pp1_run_id, "hostname": socket.gethostname(), "git_commit": None, "git_dirty": None}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, text=True,
                                capture_output=True, timeout=5)
        if commit.returncode == 0:
            dados["git_commit"] = commit.stdout.strip() or None
            status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                                    cwd=RAIZ, text=True, capture_output=True, timeout=5)
            if status.returncode == 0:
                dados["git_dirty"] = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError, UnicodeError):
        # A procedência do Git é complementar e nunca impede o experimento.
        pass
    return dados


def anexar_csv(origem, destino, contexto):
    with Path(origem).open(newline="", encoding="utf-8") as entrada:
        reader = csv.DictReader(entrada)
        colunas = list(reader.fieldnames or []) + [k for k in contexto if k not in (reader.fieldnames or [])]
        novo = not destino.exists()
        with destino.open("a", newline="", encoding="utf-8") as saida:
            writer = csv.DictWriter(saida, fieldnames=colunas)
            if novo:
                writer.writeheader()
            for linha in reader:
                writer.writerow({**linha, **contexto})
