"""Informações do servidor PostgreSQL: configurações e paralelismo dos planos."""
import json

from nucleo.arquivos import salvar_json


def registrar_servidor(exp, pasta):
    sql = """SELECT json_object_agg(name, setting ORDER BY name) FROM pg_settings WHERE name IN (
        'server_version', 'max_parallel_workers_per_gather', 'max_parallel_workers', 'max_worker_processes',
        'parallel_leader_participation', 'min_parallel_table_scan_size', 'min_parallel_index_scan_size',
        'parallel_setup_cost', 'parallel_tuple_cost', 'enable_parallel_append', 'enable_parallel_hash',
        'enable_partitionwise_join', 'enable_partitionwise_aggregate', 'work_mem', 'shared_buffers',
        'effective_cache_size', 'max_locks_per_transaction', 'max_connections', 'jit', 'enable_seqscan', 'enable_indexscan', 'enable_indexonlyscan',
        'enable_bitmapscan', 'debug_parallel_query', 'force_parallel_mode');"""
    info = json.loads(exp.sql(exp.configuracao_sessao() + "\n" + sql, pasta / "servidor"))
    salvar_json(pasta / "servidor.json", info)
    return info


def resumir_plano(plano):
    """Diagnóstico de um EXPLAIN posterior; não representa cada repetição cronometrada."""
    if not isinstance(plano, list) or len(plano) != 1 or "Plan" not in plano[0]:
        raise ValueError("Formato de EXPLAIN JSON inesperado")
    gathers = []

    def visitar(no, caminho):
        if no.get("Node Type") in ("Gather", "Gather Merge"):
            gathers.append({"caminho": caminho, "tipo": no["Node Type"],
                            "planejados": no.get("Workers Planned"), "lancados": no.get("Workers Launched"),
                            "loops": no.get("Actual Loops")})
        for i, filho in enumerate(no.get("Plans", [])):
            visitar(filho, f"{caminho}.Plans[{i}]")

    visitar(plano[0]["Plan"], "Plan")

    def maximo(campo):
        if not gathers:
            return 0
        valores = [g[campo] for g in gathers]
        return max(valores) if all(v is not None for v in valores) else None

    resumo = {"plano_gathers": len(gathers), "plano_workers_planejados_max": maximo("planejados"),
              "plano_workers_lancados_max": maximo("lancados"),
              "plano_gathers_com_deficit": sum(1 for g in gathers if g["loops"] is not None and g["loops"] > 0
                  and g["planejados"] is not None and g["lancados"] is not None and g["lancados"] < g["planejados"])}
    return {"escopo": "explain_analyze_posterior_as_medicoes", "gathers": gathers, "resumo": resumo}
