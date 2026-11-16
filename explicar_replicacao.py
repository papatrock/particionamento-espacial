"""Testa as hipóteses E2, E3 e E4 (docs/hipoteses-explicacao.md) rodando só os particionadores Java.

    .venv/bin/python explicar_replicacao.py --banco tcc_espacial --host localhost --usuario postgres --pedir-senha

Exporta cada região do schema `regioes`, particiona com o mesmo ParticionamentoRunner dos experimentos
e grava as tabelas em <saida>/. Não mede consultas e não altera o banco (só lê o schema `regioes`).
Os arquivos intermediários são apagados; ficam os particionamento.json e as tabelas.

- E2: nos grupos de STR e Hilbert, quanto o retângulo encolhe sem o seu maior objeto; e a replicação
  em MASJ quando os maiores objetos da região são retirados.
- E3: replicação de STR e Hilbert em MASJ com 4, 16, 64 e 256 partições.
- E4: cobertura (soma das áreas das partições ÷ área ocupada pelos dados) de todos os algoritmos.
"""
import argparse
from argparse import Namespace
import csv
import json
from pathlib import Path
import re
import shutil
import statistics
import tempfile

import numpy as np

from nucleo.arquivos import RAIZ, salvar_json
from nucleo.consultas import identificador
from nucleo.experimento import Experimento

REGIOES = ["es_sul", "ms_campo_grande", "pr_centro", "pr_curitiba"]
ALVOS = [4, 16, 64, 256]
NUMERO = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def envelope(wkt):
    valores = np.array(NUMERO.findall(wkt), dtype=float)
    xs, ys = valores[0::2], valores[1::2]
    return xs.min(), ys.min(), xs.max(), ys.max()


def ler_tsv(arquivo, colunas_id=1):
    """Lê id(s) e o envelope de cada linha de um TSV do particionador ou da exportação."""
    ids, caixas = [], []
    with open(arquivo, encoding="utf-8") as f:
        for linha in f:
            partes = linha.rstrip("\n").split("\t")
            ids.append(tuple(partes[:colunas_id]))
            caixas.append(envelope(partes[-1]))
    return ids, np.array(caixas)


def area(caixas):
    return (caixas[:, 2] - caixas[:, 0]) * (caixas[:, 3] - caixas[:, 1])


def particionar(exp, algoritmo, alvo, entradas, pasta, samj=False):
    """Roda o Java e devolve o JSON; os TSVs de associação ficam em pasta/associacoes."""
    exp.args.particoes = alvo
    destino = pasta / "associacoes"
    destino.mkdir(parents=True, exist_ok=True)
    metadata = exp.particionar(algoritmo, entradas, destino, pasta, associacao_unica=samj)
    return metadata, destino


def replicacao(metadata):
    copias = sum(o["objetos_a"] + o["objetos_b"] for o in metadata["ocupacoes"])
    return copias / (metadata["objetos_a"] + metadata["objetos_b"])


def cobertura(metadata, extensao):
    """Quantas vezes, em média, cada ponto da área dos dados é coberto por partições."""
    regioes = np.array([envelope(o["regiao"]) for o in metadata["ocupacoes"]])
    xmin, ymin, xmax, ymax = extensao
    regioes[:, [0, 2]] = regioes[:, [0, 2]].clip(xmin, xmax)
    regioes[:, [1, 3]] = regioes[:, [1, 3]].clip(ymin, ymax)
    return area(regioes).sum() / ((xmax - xmin) * (ymax - ymin))


def encolhimento_sem_maior(associacoes):
    """Em cada grupo do SAMJ, a área do retângulo sem o maior objeto ÷ a área com ele."""
    grupos = {}
    for lado in ("a", "b"):
        ids, caixas = ler_tsv(associacoes / f"{lado}.tsv", colunas_id=2)
        for (_, grupo), caixa in zip(ids, caixas):
            grupos.setdefault(int(grupo), []).append(caixa)
    razoes = []
    for caixas in grupos.values():
        c = np.array(caixas)
        if len(c) < 2:
            continue
        maior = int(np.argmax(np.maximum(c[:, 2] - c[:, 0], c[:, 3] - c[:, 1])))
        restantes = np.delete(c, maior, axis=0)
        def a(x): return (x[:, 2].max() - x[:, 0].min()) * (x[:, 3].max() - x[:, 1].min())
        total = a(c)
        razoes.append(a(restantes) / total if total > 0 else 1.0)
    return razoes


def sem_maiores(entradas, destino, fracao):
    """Copia os TSVs de entrada sem a fração de objetos de maior extensão (maior lado do envelope)."""
    destino.mkdir(parents=True, exist_ok=True)
    tamanhos, linhas = [], {}
    for lado in ("a", "b"):
        with open(entradas / f"{lado}.tsv", encoding="utf-8") as f:
            linhas[lado] = f.readlines()
        for i, l in enumerate(linhas[lado]):
            x0, y0, x1, y1 = envelope(l.split("\t", 1)[1])
            tamanhos.append((max(x1 - x0, y1 - y0), lado, i))
    tamanhos.sort(reverse=True)
    corte = max(1, round(fracao * len(tamanhos)))
    removidos = {(lado, i) for _, lado, i in tamanhos[:corte]}
    for lado in ("a", "b"):
        with open(destino / f"{lado}.tsv", "w", encoding="utf-8") as f:
            f.writelines(l for i, l in enumerate(linhas[lado]) if (lado, i) not in removidos)
    ids = {lado: [linhas[lado][i].split("\t", 1)[0] for _, l2, i in tamanhos[:corte] if l2 == lado] for lado in ("a", "b")}
    return corte, tamanhos[corte - 1][0], ids


def descrever(exp, regiao, ids, pasta):
    """Atributos do OSM dos maiores objetos, para saber o que eles são."""
    descricoes = []
    for lado, sufixo in (("a", "line"), ("b", "polygon_mapa")):
        if not ids[lado]:
            continue
        tabela = identificador("regioes") + "." + identificador(f"{regiao}_{sufixo}")
        lista = ",".join(str(int(i)) for i in ids[lado][:10])
        saida = exp.sql(f"""SELECT coalesce(json_agg(json_build_object('id', benchmark_id,
            'extensao_km', round((greatest(ST_XMax(geom) - ST_XMin(geom), ST_YMax(geom) - ST_YMin(geom)) / 1000)::numeric, 1),
            'atributos', (SELECT jsonb_object_agg(k, v) FROM jsonb_each_text(to_jsonb(t) - 'geom') AS e(k, v)
                          WHERE v IS NOT NULL AND k NOT IN ('benchmark_id', 'osm_id', 'way_area', 'z_order')))), '[]')
            FROM {tabela} t WHERE benchmark_id IN ({lista});""", pasta / f"maiores_{lado}")
        descricoes += [{"relacao": sufixo, **d} for d in json.loads(saida)]
    return descricoes


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--banco", default="tcc_espacial")
    p.add_argument("--host")
    p.add_argument("--porta", type=int)
    p.add_argument("--usuario")
    p.add_argument("--pedir-senha", action="store_true")
    p.add_argument("--regioes", nargs="+", choices=REGIOES, default=REGIOES)
    p.add_argument("--fracoes", type=float, nargs="+", default=[0.001, 0.01],
                   help="Frações dos maiores objetos retiradas no teste da E2 (padrão: 0,1% e 1%).")
    p.add_argument("--saida", type=Path, default=RAIZ / "resultados/lab/explicacao")
    args = p.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    exp = Experimento(Namespace(banco=args.banco, host=args.host, porta=args.porta, usuario=args.usuario,
                                pedir_senha=args.pedir_senha, particoes=64, hilbert_bits=16, bsp_tentativas=8,
                                workers=8, perf=False), args.saida)
    print("Compilando os particionadores Java...", flush=True)
    exp.processo(["mvn", "-q", "compile"], args.saida / "compilacao.log")
    linhas_e3, linhas_e2, linhas_maiores = [], [], []
    for regiao in args.regioes:
        pasta = args.saida / regiao
        dataset = {"schema": "regioes", "tabelas": (f"{regiao}_line", f"{regiao}_polygon_mapa"),
                   "geom": "geom", "id": "benchmark_id"}
        with tempfile.TemporaryDirectory(prefix=".entradas-", dir=args.saida) as temp:
            entradas = Path(temp)
            print(f"\n{regiao}: exportando...", flush=True)
            exp.exportar(dataset, entradas, pasta / "exportacao")
            caixas = np.vstack([ler_tsv(entradas / "a.tsv")[1], ler_tsv(entradas / "b.tsv")[1]])
            extensao = (caixas[:, 0].min(), caixas[:, 1].min(), caixas[:, 2].max(), caixas[:, 3].max())
            # E3 e E4: replicação e cobertura por algoritmo e número de partições.
            for algoritmo in ("TWO_LAYER", "BSP", "STR", "HILBERT"):
                for alvo in ALVOS:
                    print(f"  {algoritmo} com {alvo} partições...", flush=True)
                    caso = pasta / f"{algoritmo.lower()}_{alvo}"
                    metadata, associacoes = particionar(exp, algoritmo, alvo, entradas, caso)
                    shutil.rmtree(associacoes)
                    linhas_e3.append({"regiao": regiao, "algoritmo": algoritmo, "particoes_alvo": alvo,
                                      "particoes_efetivas": metadata["particoes_efetivas"],
                                      "replicacao_masj": round(replicacao(metadata), 4),
                                      "cobertura": round(cobertura(metadata, extensao), 4)})
            # E2: grupos do SAMJ (mesmas regiões do MASJ) e retirada dos maiores objetos.
            for algoritmo in ("STR", "HILBERT"):
                caso = pasta / f"{algoritmo.lower()}_samj_64"
                _, associacoes = particionar(exp, algoritmo, 64, entradas, caso, samj=True)
                razoes = encolhimento_sem_maior(associacoes)
                shutil.rmtree(associacoes)
                base = next(l for l in linhas_e3 if l["regiao"] == regiao and l["algoritmo"] == algoritmo
                            and l["particoes_alvo"] == 64)
                linha = {"regiao": regiao, "algoritmo": algoritmo, "replicacao_64": base["replicacao_masj"],
                         "grupos": len(razoes), "area_sem_maior_mediana": round(statistics.median(razoes), 3),
                         "grupos_encolhem_mais_50pct": sum(r < 0.5 for r in razoes)}
                for fracao in args.fracoes:
                    filtradas = pasta / f"sem_maiores_{fracao}"
                    corte, limite_m, ids = sem_maiores(entradas, filtradas, fracao)
                    metadata, associacoes = particionar(exp, algoritmo, 64, filtradas,
                                                        pasta / f"{algoritmo.lower()}_64_sem_{fracao}")
                    shutil.rmtree(associacoes)
                    shutil.rmtree(filtradas)
                    linha[f"replicacao_sem_{fracao}"] = round(replicacao(metadata), 4)
                    linha[f"retirados_{fracao}"] = corte
                    linha[f"menor_extensao_retirada_km_{fracao}"] = round(limite_m / 1000, 2)
                    if algoritmo == "STR" and fracao == min(args.fracoes):
                        linhas_maiores += [{"regiao": regiao, **d} for d in descrever(exp, regiao, ids, pasta)]
                linhas_e2.append(linha)
    for nome, linhas in (("e3_e4_replicacao_cobertura", linhas_e3), ("e2_maiores_objetos", linhas_e2)):
        with (args.saida / f"{nome}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for l in linhas for k in l)))
            writer.writeheader()
            writer.writerows(linhas)
    salvar_json(args.saida / "e2_maiores_objetos_atributos.json", linhas_maiores)
    print("\nE3/E4: replicação em MASJ e cobertura")
    for l in linhas_e3:
        print(f"  {l['regiao']:16} {l['algoritmo']:10} {l['particoes_alvo']:>4} ({l['particoes_efetivas']:>3})"
              f"  replicação={l['replicacao_masj']:7.3f}  cobertura={l['cobertura']:6.2f}")
    print("\nE2: maiores objetos (64 partições)")
    for l in linhas_e2:
        print("  " + "  ".join(f"{k}={v}" for k, v in l.items()))
    print(f"\nTabelas em {args.saida}")


if __name__ == "__main__":
    main()
