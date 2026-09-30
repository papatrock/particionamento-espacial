SELECT COUNT(*)
FROM (
    SELECT DISTINCT a.id AS id_a, b.id AS id_b
    FROM public.tabela_a_particionada a
    JOIN public.tabela_b_particionada b
      ON a.id_particao = b.id_particao
     AND ST_Intersects(a.geom, b.geom)
) pares;