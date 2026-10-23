
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

Algoritmos: SEM_PARTICIONAMENTO, TWO_LAYER, STR, HILBERT, BSP
dataset: Curitiba (pequeno), Brasil (gigantesco)

GiST: Ativo
Workers: limite de 24 por Gather, configurável por `--workers`; o uso efetivo depende do plano e dos limites do servidor.
Granularidade-alvo: aproximadamente 64 regiões/grupos por relação, usando um molde compartilhado entre as duas relações.

- Two-Layer: 8 × 8 células.
- STR e Hilbert: capacidade inicial `max(1, ceil(N / 64))`, com N igual ao total de geometrias não vazias de A e B; registrar a quantidade efetiva de grupos.
- BSP: a implementação atual divide por capacidade, sem profundidade fixa. Calibrar a capacidade em uma preparação prévia para aproximar o alvo, registrando capacidade e quantidade efetiva de folhas. Seis níveis completos não são um parâmetro disponível nesta implementação.

Workload:
	W1: Intersects(eixo_rua × arruamento_quadras)  (linha × polígono)
	W2: Intersects(brasil_line × brasil_polygon)  (linha × polígono)
