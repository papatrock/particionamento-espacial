-- Cria as regiões escolhidas em tabelas próprias. Não altera as tabelas originais.
-- Uso: psql benchmark -v ON_ERROR_STOP=1 -f experimentos/regioes/criar_regioes.sql
-- Se uma tabela já existir, o comando falha e nada é criado.

BEGIN;
CREATE SCHEMA IF NOT EXISTS regioes;

-- Sul do Espírito Santo (54 mil, menor CV). Estimativa pelo centro dos objetos: 30855 linhas, 29168 polígonos, 1891 pontos.
CREATE TABLE regioes.es_sul_line AS SELECT * FROM public.brasil_line WHERE ST_Intersects(geom, ST_MakeEnvelope(-4578000, -2352000, -4530000, -2304000, 3857));
CREATE TABLE regioes.es_sul_polygon AS SELECT * FROM public.brasil_polygon WHERE ST_Intersects(geom, ST_MakeEnvelope(-4578000, -2352000, -4530000, -2304000, 3857));
CREATE TABLE regioes.es_sul_point AS SELECT * FROM public.brasil_point WHERE ST_Intersects(geom, ST_MakeEnvelope(-4578000, -2352000, -4530000, -2304000, 3857));

-- Entorno de Campo Grande (54 mil, maior CV). Estimativa pelo centro dos objetos: 34416 linhas, 25585 polígonos, 13838 pontos.
CREATE TABLE regioes.ms_campo_grande_line AS SELECT * FROM public.brasil_line WHERE ST_Intersects(geom, ST_MakeEnvelope(-6090000, -2400000, -5850000, -2160000, 3857));
CREATE TABLE regioes.ms_campo_grande_polygon AS SELECT * FROM public.brasil_polygon WHERE ST_Intersects(geom, ST_MakeEnvelope(-6090000, -2400000, -5850000, -2160000, 3857));
CREATE TABLE regioes.ms_campo_grande_point AS SELECT * FROM public.brasil_point WHERE ST_Intersects(geom, ST_MakeEnvelope(-6090000, -2400000, -5850000, -2160000, 3857));

-- Centro do Paraná (500 mil, menor CV). Estimativa pelo centro dos objetos: 286908 linhas, 272333 polígonos, 66348 pontos.
CREATE TABLE regioes.pr_centro_line AS SELECT * FROM public.brasil_line WHERE ST_Intersects(geom, ST_MakeEnvelope(-5904000, -3072000, -5520000, -2688000, 3857));
CREATE TABLE regioes.pr_centro_polygon AS SELECT * FROM public.brasil_polygon WHERE ST_Intersects(geom, ST_MakeEnvelope(-5904000, -3072000, -5520000, -2688000, 3857));
CREATE TABLE regioes.pr_centro_point AS SELECT * FROM public.brasil_point WHERE ST_Intersects(geom, ST_MakeEnvelope(-5904000, -3072000, -5520000, -2688000, 3857));

-- Região de Curitiba (500 mil, maior CV). Estimativa pelo centro dos objetos: 225073 linhas, 332986 polígonos, 476404 pontos.
CREATE TABLE regioes.pr_curitiba_line AS SELECT * FROM public.brasil_line WHERE ST_Intersects(geom, ST_MakeEnvelope(-5568000, -3048000, -5376000, -2856000, 3857));
CREATE TABLE regioes.pr_curitiba_polygon AS SELECT * FROM public.brasil_polygon WHERE ST_Intersects(geom, ST_MakeEnvelope(-5568000, -3048000, -5376000, -2856000, 3857));
CREATE TABLE regioes.pr_curitiba_point AS SELECT * FROM public.brasil_point WHERE ST_Intersects(geom, ST_MakeEnvelope(-5568000, -3048000, -5376000, -2856000, 3857));

COMMIT;

ANALYZE regioes.es_sul_line;
ANALYZE regioes.es_sul_polygon;
ANALYZE regioes.es_sul_point;
ANALYZE regioes.ms_campo_grande_line;
ANALYZE regioes.ms_campo_grande_polygon;
ANALYZE regioes.ms_campo_grande_point;
ANALYZE regioes.pr_centro_line;
ANALYZE regioes.pr_centro_polygon;
ANALYZE regioes.pr_centro_point;
ANALYZE regioes.pr_curitiba_line;
ANALYZE regioes.pr_curitiba_polygon;
ANALYZE regioes.pr_curitiba_point;

-- Contagens finais, para registrar na metodologia. Objetos longos que só tocam a região também entram.
SELECT 'es_sul' AS regiao, 'line' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.es_sul_line
 UNION ALL SELECT 'es_sul' AS regiao, 'polygon' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.es_sul_polygon
 UNION ALL SELECT 'es_sul' AS regiao, 'point' AS tabela, count(*) AS objetos, count(DISTINCT osm_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.es_sul_point
 UNION ALL SELECT 'ms_campo_grande' AS regiao, 'line' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.ms_campo_grande_line
 UNION ALL SELECT 'ms_campo_grande' AS regiao, 'polygon' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.ms_campo_grande_polygon
 UNION ALL SELECT 'ms_campo_grande' AS regiao, 'point' AS tabela, count(*) AS objetos, count(DISTINCT osm_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.ms_campo_grande_point
 UNION ALL SELECT 'pr_centro' AS regiao, 'line' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_centro_line
 UNION ALL SELECT 'pr_centro' AS regiao, 'polygon' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_centro_polygon
 UNION ALL SELECT 'pr_centro' AS regiao, 'point' AS tabela, count(*) AS objetos, count(DISTINCT osm_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_centro_point
 UNION ALL SELECT 'pr_curitiba' AS regiao, 'line' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_curitiba_line
 UNION ALL SELECT 'pr_curitiba' AS regiao, 'polygon' AS tabela, count(*) AS objetos, count(DISTINCT benchmark_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_curitiba_polygon
 UNION ALL SELECT 'pr_curitiba' AS regiao, 'point' AS tabela, count(*) AS objetos, count(DISTINCT osm_id) AS ids_distintos, round(max(ST_XMax(geom) - ST_XMin(geom))::numeric / 1000) AS maior_largura_km FROM regioes.pr_curitiba_point
ORDER BY 1, 2;
