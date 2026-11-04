"""SQL gerado pelas PPs: identificadores e consultas de join."""

SAIDA_A = 'public."tabela_a_particionada"'
SAIDA_B = 'public."tabela_b_particionada"'


def identificador(nome):
    return '"' + nome.replace('"', '""') + '"'


def literal(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def consulta_direta(dataset):
    a, b = (identificador(dataset.get("schema", "public")) + "." + identificador(t) for t in dataset["tabelas"])
    geom = identificador(dataset["geom"])
    return f"SELECT COUNT(*) FROM {a} a JOIN {b} b ON ST_Intersects(a.{geom}, b.{geom});"


def consulta_particionada(algoritmo, metadados=None):
    if metadados and metadados.get("modelo_join") == "SAMJ":
        if algoritmo not in ("STR", "HILBERT"):
            raise ValueError("Join SAMJ disponível somente para STR e Hilbert")
        ids = {ocupacao["id"] for ocupacao in metadados["ocupacoes"]}
        pares = []
        for par in metadados["pares_particoes"]:
            a, b = par["a"], par["b"]
            if type(a) is not int or type(b) is not int or a <= 0 or b <= 0 or a not in ids or b not in ids:
                raise ValueError("Par de partições SAMJ inválido")
            pares.append((a, b))
        if len(pares) != len(set(pares)):
            raise ValueError("Pares de partições SAMJ duplicados")
        if not pares:
            return "SELECT 0::bigint;"
        # Cada objeto tem um único grupo e cada par de grupos aparece uma vez.
        # Joins nas tabelas filhas garantem que só os pares candidatos sejam lidos.
        consultas = [
            f"SELECT COUNT(*) AS total FROM public.tabela_a_p{a} a "
            f"JOIN public.tabela_b_p{b} b ON ST_Intersects(a.geom, b.geom)"
            for a, b in sorted(pares)
        ]
        return "SELECT SUM(total)::bigint FROM (\n" + "\nUNION ALL\n".join(consultas) + "\n) pares;"
    condicao = "a.id_particao = b.id_particao AND ST_Intersects(a.geom, b.geom)"
    if algoritmo == "TWO_LAYER":
        classes = "(a.classe = 'A' OR b.classe = 'A' OR (a.classe = 'B' AND b.classe = 'C') OR (a.classe = 'C' AND b.classe = 'B'))"
        return f"SELECT COUNT(*) FROM {SAIDA_A} a JOIN {SAIDA_B} b ON {condicao} AND {classes};"
    return (f"SELECT COUNT(*) FROM (SELECT DISTINCT a.id AS id_a, b.id AS id_b FROM {SAIDA_A} a "
            f"JOIN {SAIDA_B} b ON {condicao}) pares;")
