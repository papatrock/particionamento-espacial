
Serão: 4 algoritimos, 2 datasets, 3 workload, 2 Gist (sem e com), X numero de partições

| Pergunta | Variar                         | Fixar                                 |
| -------- | ------------------------------ | ------------------------------------- |
| PP1      | algoritmo, dataset             | GiST, workers, granularidade-alvo, workload |
| PP2      | algoritmo, workload            | dataset/escala, GiST, workers         |
| PP3      | com/sem particionamento e GiST | workload, workers                     |
| PP4      | algoritmo, workers             | dataset grande, GiST, workload        |
| PP5      | algoritmo, nº partições        | dataset, workers, GiST                |

**PP1 - Particionamento:** diferentes estratégias de particionamento produzem diferenças significativas no tempo de execução de spatial joins?

**PP2 - Geometria:** o desempenho relativo dos particionadores muda conforme o workload seja ponto × polígono, linha × polígono ou polígono × polígono?

**PP3 - Indexação:** em quais condições a indexação espacial local já é suficiente, e quando o particionamento acrescenta ganho relevante?

**PP4 - Paralelismo:** quais estratégias de particionamento aproveitam melhor o aumento do paralelismo?

**PP5 - Granularidade:** como o número de partições afeta desempenho, balanceamento e overhead?


-----

workloads: o termo _workload_ refere-se à configuração da operação de junção espacial executada no benchmark. Mantendo-se o predicado espacial `ST_Intersects`, são considerados três workloads, definidos de acordo com os tipos geométricos das relações envolvidas: ponto–polígono, linha–polígono e polígono–polígono.

Dataset Curitiba

W1: pontos × bairros (ponto × polígono) PONTOS? QUE PONTOS CARA
W2: ruas × quadras  (linha × polígono)
W3: quadras × bairros (polígono × polígono)

**H1:** Para conjuntos de dados menores, a indexação espacial tende a reduzir o benefício adicional do particionamento; à medida que o volume e a complexidade espacial aumentam, o particionamento tende a produzir ganhos mais relevantes.

**H2:** O desempenho relativo dos algoritmos de particionamento varia de acordo com o tipo e a extensão espacial das geometrias processadas.

------

algoritmo -> distribuição dos objetos entre partições  ->balanceamento  -> utilização dos workers -> tempo de execução

**H3:** Estratégias que produzem partições mais balanceadas tendem a apresentar melhor escalabilidade com o aumento do paralelismo.

-----------------------------------------

Granularidade

**H4:** Existe um ponto de equilíbrio para o número de partições: poucas partições limitam poda e paralelismo, enquanto partições excessivamente numerosas aumentam overhead de planejamento, gerenciamento e execução.



# Script teste

## Parametros


| Parâmetro        | Obrigatório? | Finalidade esperada                                    | Exemplo                               |
| ---------------- | ------------ | ------------------------------------------------------ | ------------------------------------- |
| `--cenario`      | Sim          | Identificar o cenário/datasets avaliados               | `ruas_quadras`                        |
| `--algoritmo`    | Sim          | Identificar o algoritmo avaliado                       | `STR`,                                |
| `--sql`          | Sim          | Caminho do arquivo com a consulta                      | `consulta_str.sql`                    |
| `--banco`        | Não          | Banco ao qual conectar                                 | `benchmark`                           |
| `--host`         | Não          | Substituir o host padrão do psql                        | `localhost`                           |
| `--porta`        | Não          | Substituir a porta padrão do psql                       | `5432`                                |
| `--usuario`      | Não          | Substituir o usuário padrão do psql                     | `postgres`                            |
| `--workers`      | Não          | Limite de workers paralelos por Gather                  | `24`                                  |
| `--aquecimentos` | Não          | Execuções prévias para aquecimento, antes das medições | `3`                                   |
| `--repeticoes`   | Não          | Quantidade de execuções medidas                        | `10`                                  |
| `--rodada`       | Não          | Identificador da rodada do experimento                 | `1`                                   |
| `--saida`        | Não          | Destino dos resultados                                 | Depende do formato aceito pelo script |
| `-h`, `--help`   | Não          | Mostrar a ajuda                                        | `--help`                              |


|Parâmetro|Entrada válida|Padrão|
|---|---|---|
|`--cenario`|Qualquer texto. Use um identificador consistente, como `ruas_quadras`|Obrigatório|
|`--algoritmo`|Qualquer texto, como `STR`, `TWO_LAYER`, `HILBERT`, `BSP` ou `SEM_PARTICIONAMENTO`|Obrigatório|
|`--sql`|Caminho de um arquivo existente e legível, contendo uma única consulta `SELECT`|Obrigatório|
|`--banco`|Nome de um banco existente, acessível pelo usuário configurado|`benchmark`|
|`--host`|Host ou diretório de socket Unix|Padrão do psql, respeitando `PGHOST`|
|`--porta`|Inteiro de **1 a 65535**|Padrão do psql, respeitando `PGPORT`|
|`--usuario`|Nome do usuário do PostgreSQL|Usuário do sistema, respeitando `PGUSER`|
|`--workers`|Inteiro **≥ 0**; `0` desabilita paralelismo|`24`|
|`--perf`|Ativa perf stat em todas as CPUs durante o bloco de repetições; executar no servidor do PostgreSQL|Desativado|
|`--perf-eventos`|Seletores de eventos separados por vírgula|`cycles,instructions,cache-references,cache-misses,branches,branch-misses,context-switches,cpu-migrations,page-faults`|
|`--aquecimentos`|Inteiro **≥ 0**|`3`|
|`--repeticoes`|Inteiro **≥ 1**|`10`|
|`--rodada`|Qualquer inteiro; use `1`, `2`, `3`… para identificar as rodadas|`1`|
|`--saida`|Caminho de diretório onde você tenha permissão de escrita; o script cria se necessário|`resultados/pp1`|
|`--help`|Não recebe valor; exibe a ajuda|—|

### Cenarios

DataSet1: ruas_quadras (linha × polígono)  , quadras_bairros (polígono × polígono),  ruas_bairros, quadras_regionais


## Algoritmos

SEM_PARTICIONAMENTO
TWO_LAYER
STR
HILBERT
BSP


## Teste PP1 - Particionamento

Automação: `python3 pp1.py` executa os dois datasets e os cinco modos. `python3 pp1.py --simular` mostra a matriz sem acessar o banco. Consulte `python3 pp1.py --help` para selecionar datasets, algoritmos, conexão e repetições.

Contadores opcionais: `--perf` coleta o total de eventos do bloco de repetições de cada combinação, excluindo aquecimentos. Os resultados ficam em `perf.csv`, separados dos tempos individuais. A coleta usa `perf stat -a`, incluindo outras atividades da máquina; manter o mesmo modo de instrumentação entre combinações comparadas.

Variar: algoritmo, dataset
Fixar: GiST, workers, granularidade-alvo, workload

Algoritmos: SEM_PARTICIONAMENTO, TWO_LAYER, STR, HILBERT, BSP, STR_SAMJ, HILBERT_SAMJ
dataset: Curitiba (pequeno), Brasil (gigantesco)

Modelo de join: STR, Hilbert e BSP usam MASJ em todas as PPs, como em Aji, Vo e Wang (2015), seções 2.2 e 3.1. STR_SAMJ e HILBERT_SAMJ são variantes da PP1, medidas à parte. Comparar os algoritmos pelo MASJ; os resultados anteriores com `modelo_pp1 = str_hilbert_samj_v1` correspondem às variantes SAMJ, não ao caso principal.

Limite: `--limite-consulta-min` (padrão 120). O caso que estoura fica como `nao_concluiu` no manifesto e a execução continua.

GiST: Ativo
Workers: limite de 24 por Gather, configurável por `--workers`; o uso efetivo depende do plano e dos limites do servidor.
Granularidade-alvo: aproximadamente 64 regiões/grupos por relação, usando um molde compartilhado entre as duas relações.

- Two-Layer: 8 × 8 células.
- STR e Hilbert: capacidade inicial `max(1, ceil(N / 64))`, com N igual ao total de geometrias não vazias de A e B; registrar a quantidade efetiva de grupos.
- BSP: a implementação atual divide por capacidade, sem profundidade fixa. Calibrar a capacidade em uma preparação prévia para aproximar o alvo, registrando capacidade e quantidade efetiva de folhas. Seis níveis completos não são um parâmetro disponível nesta implementação.

Workload:
	W1: Intersects(eixo_rua × arruamento_quadras)  (linha × polígono)
	W2: Intersects(brasil_line × brasil_polygon)  (linha × polígono)


## Teste PP5 - Granularidade

Automação: `python3 pp5.py --objetos-a N --objetos-b M` usa as mesmas amostras em todos os casos. `--simular` mostra a matriz sem acessar o banco. Depois, `python3 -m analises.pp5` gera `resultados/pp5/analise/resumo_granularidade.csv`.

Variar: algoritmo, nº de partições (`--particoes`, padrão 4, 16, 64, 256 e 1024; Two-Layer exige quadrados perfeitos)
Fixar: dataset, workload, workers (`--workers`, padrão 24), GiST

Modelo de join: MASJ, como nas demais PPs. O fator de replicação do resumo corresponde a `1 + α` no modelo de custo de Aji, Vo e Wang (2015), seção 2.3.

SEM_PARTICIONAMENTO não depende do alvo: é medido uma vez, como referência. Comparar os algoritmos pelas partições efetivas, pois o BSP pode não atingir o alvo.

Métricas, uma linha por caso no resumo:

- Desempenho: tempos das repetições, speedup sobre o baseline e melhor alvo de cada algoritmo (H4).
- Balanceamento: carga (objetos de A + B na partição, com réplicas) máxima/média e coeficiente de variação, partições vazias, fator de replicação e pares candidatos (soma de A × B por partição).
- Overhead: tempo de particionamento (inclui a inicialização do Maven/JVM), tempo de materialização, tamanho das tabelas e índices, tempo de planejamento (`EXPLAIN` sem executar, primeira vez na sessão e mediana).

Muitas partições exigem locks: cada processo bloqueia 2 tabelas e 2 GiST por partição. Com 24 workers e `max_locks_per_transaction` padrão (64), 1024 partições falharam com `out of shared memory`, então o script avisa no início o valor estimado. Uma execução que falha fica fora do acumulado.


## Tamanhos das amostras (PP2 a PP5)

Proposta inicial, ainda a confirmar com o piloto do PP5 e com o total de linhas das tabelas `brasil_point`, `brasil_line` e `brasil_polygon`.

| Nome | A (`--objetos-a`) | B (`--objetos-b`) |
| ---- | ----------------- | ----------------- |
| P    | 100 mil           | 50 mil            |
| M    | 1 milhão          | 500 mil           |
| G    | 10 milhões        | 5 milhões         |

| PP  | Tamanho                       | Motivo                                                                                       | Consultas (3 aquecimentos + 10 repetições) |
| --- | ----------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------ |
| PP2 | M                             | A escala é fixa; basta um tamanho que termine nos 3 workloads                                | 15 casos, 195 consultas                    |
| PP3 | 10 mil/5 mil e 100 mil/50 mil | A H1 fala de volume, então precisa de mais de um tamanho; o caso sem GiST limita o máximo     | 10 casos, 130 consultas por tamanho        |
| PP4 | G ou o maior viável           | Dataset grande: com pouco trabalho, os workers quase não têm o que dividir                   | 35 casos, 455 consultas                    |
| PP5 | O mesmo do PP4                | Permite comparar as duas PPs                                                                 | 17 casos (4 alvos), 221 consultas          |

Cuidados:

- PP3: sem GiST, o baseline testa todos os pares. Em 100 mil × 50 mil são 5 bilhões de pares por consulta, repetidos 13 vezes, e o PP3 não tem limite de tempo. Começar em 10 mil × 5 mil (50 milhões de pares) e só subir depois de medir.
- O custo pode crescer mais que o tamanho, principalmente com replicação. Subir um degrau de cada vez, em vez de extrapolar a partir do P.
- Usar a mesma `--semente`: com os mesmos tamanhos e workload, PP4 e PP5 usam as mesmas amostras (conferir `ids_a_md5` e `ids_b_md5`).
- A proporção 2:1 entre A e B é provisória; preferir uma próxima da real entre linhas e polígonos quando as contagens forem conhecidas.

Pendência no PP2: em `poligono_poligono`, A e B vêm da mesma tabela, com a mesma semente e a mesma ordenação (`sql_amostra` em `pp2.py`), então B fica inteiramente contido em A e cada polígono de B intersecta a própria cópia em A. Isso infla as interseções e a seletividade desse workload. Decidir entre corrigir antes de rodar ou manter e explicar no texto.
