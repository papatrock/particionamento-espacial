"""Propõe regiões do Brasil para os experimentos, comparando homogeneidade e skew. Só lê o banco.

    python3 medir_regioes.py --banco benchmark --saida /disk1/pol21/resultados/regioes

O skew é o coeficiente de variação (CV) dos objetos de A + B em 8 × 8 blocos da janela. A divisão
é sempre a mesma, então o CV é comparável entre janelas de tamanhos diferentes.
"""
import argparse
import csv
from math import atan, degrees, sinh
from pathlib import Path
import statistics
import subprocess

from nucleo.amostras import carregar_config, tabela
from nucleo.arquivos import RAIZ
from nucleo.consultas import identificador

BLOCOS = 8
# Em células da grade; saltos grandes deixariam regiões inteiras fora da tolerância.
TAMANHOS_BLOCO = (*range(1, 17), 18, 20, 24, 28, 32, 40, 48, 56, 64, 80)
RAIO_TERRA_M = 6378137
CAMPOS = ("faixa", "perfil", "cv", "blocos_vazios_pct", "lado_km_em_3857", "total_a_b", "linhas", "poligonos",
          "pontos", "lon_centro", "lat_centro", "xmin", "ymin", "xmax", "ymax")


def argumentos():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=RAIZ / "experimentos/pp2/brasil.json")
    p.add_argument("--banco", default="benchmark")
    p.add_argument("--saida", type=Path, default=Path("resultados/regioes"))
    p.add_argument("--faixas", type=int, nargs="+", default=[54000, 500000],
                   help="Total de objetos de A + B em cada faixa (padrão: Curitiba e cerca de 10 vezes isso).")
    p.add_argument("--tolerancia", type=float, default=0.15, help="Diferença aceita em relação à faixa (padrão: 0,15).")
    p.add_argument("--celula-m", type=int, default=2000, help="Lado da célula da grade, em unidades do SRID 3857.")
    p.add_argument("--candidatas", type=int, default=5, help="Regiões listadas por perfil em cada faixa.")
    p.add_argument("--histograma", type=Path, help="Reaproveita um histograma já calculado, sem consultar o banco.")
    return p.parse_args()


def sql_histograma(config, celula):
    partes = []
    for tipo, nome in (("l", "linhas"), ("p", "poligonos_b"), ("o", "pontos")):
        relacao = config["relacoes"][nome]
        g = identificador(relacao["geom"])
        partes.append(f"SELECT '{tipo}' AS tipo, floor(((ST_XMin({g}) + ST_XMax({g})) / 2) / {celula})::int AS x, "
                      f"floor(((ST_YMin({g}) + ST_YMax({g})) / 2) / {celula})::int AS y, count(*) AS n "
                      f"FROM {tabela(relacao)} WHERE NOT ST_IsEmpty({g}) GROUP BY 2, 3")
    uniao = " UNION ALL ".join(partes)
    return f"SET default_transaction_read_only = on;\n\\copy ({uniao}) TO STDOUT WITH (FORMAT csv, HEADER)\n"


def calcular_histograma(args, config, destino):
    print("Contando objetos por célula (varre as três tabelas)...", flush=True)
    resultado = subprocess.run(["psql", "-X", "-q", "--set=ON_ERROR_STOP=1", "--dbname", args.banco],
                               input=sql_histograma(config, args.celula_m), text=True, capture_output=True)
    if resultado.returncode:
        raise SystemExit(f"psql falhou: {resultado.stderr.strip()}")
    destino.write_text(resultado.stdout, encoding="utf-8")


def ler_histograma(arquivo):
    celulas = {"l": {}, "p": {}, "o": {}}
    with arquivo.open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            celulas[linha["tipo"]][(int(linha["x"]), int(linha["y"]))] = int(linha["n"])
    return celulas


def agrupar(celulas, tamanho):
    blocos = {}
    for (x, y), n in celulas.items():
        chave = (x // tamanho, y // tamanho)
        blocos[chave] = blocos.get(chave, 0) + n
    return blocos


def janelas(celulas, tamanho, minimo, maximo):
    """Percorre janelas de 8 × 8 blocos que caibam na faixa, avançando um bloco por vez."""
    linhas, poligonos = agrupar(celulas["l"], tamanho), agrupar(celulas["p"], tamanho)
    pontos = agrupar(celulas["o"], tamanho)
    origens = {(x - dx, y - dy) for x, y in set(linhas) | set(poligonos) for dx in range(BLOCOS) for dy in range(BLOCOS)}
    posicoes = [(dx, dy) for dx in range(BLOCOS) for dy in range(BLOCOS)]
    for bx, by in origens:
        valores, a, b, o = [], 0, 0, 0
        for dx, dy in posicoes:
            chave = (bx + dx, by + dy)
            va, vb = linhas.get(chave, 0), poligonos.get(chave, 0)
            a, b, o = a + va, b + vb, o + pontos.get(chave, 0)
            valores.append(va + vb)
        total = a + b
        # Exige as duas relações, para o join não virar um caso degenerado.
        if minimo <= total <= maximo and min(a, b) >= 0.1 * total:
            yield bx, by, a, b, o, total, statistics.pstdev(valores) / (total / len(valores)), valores.count(0)


def sem_sobreposicao(candidatas, limite):
    escolhidas = []
    for c in candidatas:
        livre = all(c["xmax"] <= e["xmin"] or e["xmax"] <= c["xmin"] or c["ymax"] <= e["ymin"] or e["ymax"] <= c["ymin"]
                    for e in escolhidas)
        if livre:
            escolhidas.append(c)
        if len(escolhidas) == limite:
            break
    return escolhidas


def propor(celulas, faixa, args):
    minimo, maximo = faixa * (1 - args.tolerancia), faixa * (1 + args.tolerancia)
    candidatas = []
    for tamanho in TAMANHOS_BLOCO:
        lado = tamanho * args.celula_m
        for bx, by, a, b, o, total, cv, vazios in janelas(celulas, tamanho, minimo, maximo):
            x, y = bx * lado, by * lado
            candidatas.append({"faixa": faixa, "cv": round(cv, 3), "blocos_vazios_pct": round(100 * vazios / BLOCOS ** 2, 1),
                               "lado_km_em_3857": lado * BLOCOS / 1000, "total_a_b": total, "linhas": a, "poligonos": b,
                               "pontos": o, "xmin": x, "ymin": y, "xmax": x + lado * BLOCOS, "ymax": y + lado * BLOCOS})
    candidatas.sort(key=lambda c: c["cv"])
    resultado = []
    for perfil, ordem in (("menor_cv", candidatas), ("maior_cv", candidatas[::-1])):
        for c in sem_sobreposicao(ordem, args.candidatas):
            centro_x, centro_y = (c["xmin"] + c["xmax"]) / 2, (c["ymin"] + c["ymax"]) / 2
            resultado.append({**c, "perfil": perfil, "lon_centro": round(degrees(centro_x / RAIO_TERRA_M), 3),
                              "lat_centro": round(degrees(atan(sinh(centro_y / RAIO_TERRA_M))), 3)})
    return resultado


def main():
    args = argumentos()
    config = carregar_config(args.config)
    if config["srid"] != 3857:
        raise SystemExit("O script assume coordenadas em SRID 3857")
    args.saida.mkdir(parents=True, exist_ok=True)
    histograma = args.histograma or args.saida / "histograma.csv"
    if not args.histograma:
        calcular_histograma(args, config, histograma)
    celulas = ler_histograma(histograma)
    linhas = []
    for faixa in args.faixas:
        print(f"Avaliando janelas com cerca de {faixa} objetos...", flush=True)
        propostas = propor(celulas, faixa, args)
        if not propostas:
            print("  Nenhuma janela nessa faixa; tente outra --tolerancia ou --celula-m.", flush=True)
        linhas.extend(propostas)
    destino = args.saida / "regioes_candidatas.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)
    for c in linhas:
        print(f"{c['faixa']:>7} {c['perfil']:<8} cv={c['cv']:<6} vazios={c['blocos_vazios_pct']:>5}% lado={c['lado_km_em_3857']:>6}km "
              f"A={c['linhas']:<7} B={c['poligonos']:<7} pontos={c['pontos']:<7} centro=({c['lon_centro']}, {c['lat_centro']})")
    print(f"Candidatas: {destino}")


if __name__ == "__main__":
    main()
