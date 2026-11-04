"""Esqueleto das PPs com amostras (PP2 a PP5): pasta, manifesto, schema temporário e limpeza."""
from contextlib import contextmanager
from datetime import datetime, timezone

from nucleo.amostras import MULTI, WORKLOADS, preparar_amostras
from nucleo.arquivos import anexar_csv, metadados_execucao, salvar_json
from nucleo.consolidacao import consolidar, imprimir_resumo
from nucleo.consultas import identificador
from nucleo.experimento import Experimento
from nucleo.perf_coleta import verificar_perf


class ExecucaoAmostrada:
    def __init__(self, args, config, pasta, exp):
        self.args = args
        self.config = config
        self.pasta = pasta
        self.exp = exp
        self.schema = pasta.name.lower()
        self.schema_criado = False
        self.manifesto = {"status": "em_execucao", "combinacoes": [], "schema_amostras": self.schema}
        self.salvar_manifesto()

    def salvar_manifesto(self):
        salvar_json(self.pasta / "manifesto.json", self.manifesto)

    def preparar(self):
        """Compila os particionadores, se forem usados, e cria as amostras; retorna as características delas."""
        if any(a != "SEM_PARTICIONAMENTO" for a in self.args.algoritmos):
            print("Compilando os particionadores Java...", flush=True)
            self.exp.processo(["mvn", "-q", "compile"], self.pasta / "compilacao.log")
        self.exp.sql(f"CREATE SCHEMA {identificador(self.schema)};", self.pasta / "schema")
        self.schema_criado = True
        return preparar_amostras(self.exp, self.config, self.args, self.schema, self.pasta)

    def dataset(self, workload):
        nome_a = WORKLOADS[workload]
        return {"schema": self.schema, "cenario": workload, "tabelas": (nome_a, "poligonos_b"),
                "id": "id", "geom": "geom", "srid": self.config["srid"], "tipos": (MULTI[nome_a], "MultiPolygon")}

    def iniciar_caso(self, **campos):
        registro = {**campos, "status": "em_execucao"}
        self.manifesto["combinacoes"].append(registro)
        self.salvar_manifesto()
        return registro

    def concluir_caso(self, registro, medicoes, contexto, intersecoes):
        anexar_csv(medicoes, self.pasta / "consultas.csv", contexto)
        if self.args.perf:
            anexar_csv(medicoes.parent / "perf.csv", self.pasta / "perf.csv", contexto)
        registro.update(status="concluido", intersecoes=intersecoes, **contexto)
        self.salvar_manifesto()

    def remover_schema(self):
        try:
            self.exp.sql(f"DROP SCHEMA {identificador(self.schema)} CASCADE;", self.pasta / "limpeza")
            self.manifesto["amostras_removidas"] = True
        except Exception as erro:
            self.manifesto["erro_limpeza"] = str(erro)
            print(f"Aviso: schema de amostras mantido: {self.schema}; {erro}")


@contextmanager
def execucao_amostrada(nome, args, config, extras=None, args_experimento=None):
    """Registra sucesso ou falha no manifesto, remove as amostras e atualiza os acumulados.

    args_experimento substitui args no Experimento quando a PP varia um parâmetro que ele lê como escalar.
    """
    pasta = args.saida.resolve() / (f"{nome}_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    pasta.mkdir(parents=True)
    meta = metadados_execucao(pasta.name)
    meta[f"{nome}_run_id"] = meta.pop("pp1_run_id")
    salvar_json(pasta / "configuracao.json", {**vars(args), "config": str(args.config.resolve()),
                "saida": str(pasta), "fontes": config, "indexacao": "on", **(extras or {}), **meta})
    exp = Experimento(args_experimento if args_experimento is not None else args, pasta)
    run = ExecucaoAmostrada(args, config, pasta, exp)
    try:
        if args.perf:
            verificar_perf(args.perf_eventos, pasta, exp.ambiente)
        yield run
        run.manifesto["status"] = "concluido"
    except (Exception, KeyboardInterrupt) as erro:
        run.manifesto.update(status="falhou", erro=str(erro))
        combinacoes = run.manifesto["combinacoes"]
        if combinacoes and combinacoes[-1]["status"] == "em_execucao":
            combinacoes[-1]["status"] = "falhou"
        raise SystemExit(f"{nome.upper()} interrompida: {erro}\nLogs: {pasta}") from erro
    finally:
        if run.schema_criado:
            run.remover_schema()
        run.salvar_manifesto()
    print(f"{nome.upper()} concluída: {pasta}")
    try:
        imprimir_resumo(consolidar(pasta.parent, nome), nome)
    except Exception as erro:
        print(f"Aviso: consolidação falhou; brutos preservados: {erro}")
