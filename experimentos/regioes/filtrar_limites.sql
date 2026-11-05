-- Cria cópias das tabelas de polígonos sem limites administrativos e de fuso. Mantém as tabelas atuais.
-- Regra e motivo: seção "Tratamento dos dados" de definicao-testes.md.
-- Uso, depois de criar_regioes.sql: psql benchmark -v ON_ERROR_STOP=1 -f experimentos/regioes/filtrar_limites.sql
-- Se uma tabela já existir, o comando falha e nada é criado.

BEGIN;
CREATE TABLE regioes.es_sul_polygon_mapa AS SELECT * FROM regioes.es_sul_polygon WHERE boundary IS NULL OR boundary NOT IN ('administrative', 'timezone');
CREATE TABLE regioes.ms_campo_grande_polygon_mapa AS SELECT * FROM regioes.ms_campo_grande_polygon WHERE boundary IS NULL OR boundary NOT IN ('administrative', 'timezone');
CREATE TABLE regioes.pr_centro_polygon_mapa AS SELECT * FROM regioes.pr_centro_polygon WHERE boundary IS NULL OR boundary NOT IN ('administrative', 'timezone');
CREATE TABLE regioes.pr_curitiba_polygon_mapa AS SELECT * FROM regioes.pr_curitiba_polygon WHERE boundary IS NULL OR boundary NOT IN ('administrative', 'timezone');
COMMIT;

ANALYZE regioes.es_sul_polygon_mapa;
ANALYZE regioes.ms_campo_grande_polygon_mapa;
ANALYZE regioes.pr_centro_polygon_mapa;
ANALYZE regioes.pr_curitiba_polygon_mapa;

-- Quantidades para a metodologia.
SELECT 'es_sul' AS regiao, (SELECT count(*) FROM regioes.es_sul_polygon) AS poligonos, (SELECT count(*) FROM regioes.es_sul_polygon_mapa) AS mantidos, (SELECT count(*) FROM regioes.es_sul_polygon) - (SELECT count(*) FROM regioes.es_sul_polygon_mapa) AS removidos
 UNION ALL SELECT 'ms_campo_grande' AS regiao, (SELECT count(*) FROM regioes.ms_campo_grande_polygon) AS poligonos, (SELECT count(*) FROM regioes.ms_campo_grande_polygon_mapa) AS mantidos, (SELECT count(*) FROM regioes.ms_campo_grande_polygon) - (SELECT count(*) FROM regioes.ms_campo_grande_polygon_mapa) AS removidos
 UNION ALL SELECT 'pr_centro' AS regiao, (SELECT count(*) FROM regioes.pr_centro_polygon) AS poligonos, (SELECT count(*) FROM regioes.pr_centro_polygon_mapa) AS mantidos, (SELECT count(*) FROM regioes.pr_centro_polygon) - (SELECT count(*) FROM regioes.pr_centro_polygon_mapa) AS removidos
 UNION ALL SELECT 'pr_curitiba' AS regiao, (SELECT count(*) FROM regioes.pr_curitiba_polygon) AS poligonos, (SELECT count(*) FROM regioes.pr_curitiba_polygon_mapa) AS mantidos, (SELECT count(*) FROM regioes.pr_curitiba_polygon) - (SELECT count(*) FROM regioes.pr_curitiba_polygon_mapa) AS removidos
ORDER BY 1;
