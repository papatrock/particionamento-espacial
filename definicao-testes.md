
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

Modelo de join: STR, Hilbert e BSP usam MASJ em todas as PPs, como em Aji, Vo e Wang (2015), seções 2.2 e 3.1. STR_SAMJ e HILBERT_SAMJ são variantes medidas à parte em PP1, PP4 e PP5. Comparar os algoritmos pelo MASJ; os resultados anteriores com `modelo_pp1 = str_hilbert_samj_v1` correspondem às variantes SAMJ, não ao caso principal.

Limite: `--limite-consulta-min` (padrão 120). O caso que estoura fica como `nao_concluiu` no manifesto e a execução continua.

GiST: Ativo
Workers: exatamente 8 por Gather, configurável por `--workers`, salvo falta de workers no servidor.
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
Fixar: dataset, workload, workers (`--workers`, padrão 8), GiST

Modelo de join: MASJ, com as variantes STR_SAMJ e HILBERT_SAMJ medidas à parte. `--particoes-masj` limita os alvos de STR e Hilbert em MASJ, os casos mais lentos. O fator de replicação do resumo corresponde a `1 + α` no modelo de custo de Aji, Vo e Wang (2015), seção 2.3.

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

Amostras de polígonos: em `poligono_poligono`, A e B vêm da mesma tabela. B fica com os primeiros polígonos da ordem sorteada e A com os seguintes, sem repetir nenhum, para um polígono não intersectar a própria cópia. O B é o mesmo nos três workloads, e `brasil_polygon` precisa ter ao menos `--objetos-a` + `--objetos-b` polígonos. Resultados anteriores desse workload usavam amostras sobrepostas e não são comparáveis.

## Número de workers fixado em 8

PP1, PP2, PP3 e PP5 usam exatamente 8 workers (`--workers`, padrão 8). O PP4 continua variando esse número.

Justificativa:

- **Ganho até 8:** no PP4 de 04/11 (100 mil/50 mil, `linha_poligono`), passar do limite 4 para o limite 8 reduziu a mediana em 24% no Two-Layer, 23% no STR, 30% no Hilbert e 23% no BSP. Com o limite 8, o planejador lançou 7 workers nesses casos, o que limita a precisão dessa comparação.
- **Próximo do observado:** no PP4 e no PP5 de 04/11, com 64 partições, o planejador escolheu 7 workers. Fixar 8 muda pouco esse nível de paralelismo e o torna igual em todos os casos.
- **Locks:** com 256 partições, a estimativa no `jatoba2` (`max_locks_per_transaction` = 64) é de 9.216 entradas com 8 workers e 25.600 com 24, para uma capacidade estimada de 16.896. Com 8, não é preciso reiniciar o servidor.
- **Indicativo em dados sintéticos:** em um teste com 10 mil/5 mil e uma repetição, o limite 8 foi mais rápido que o 24: baseline com 34 ms contra 55 ms, e STR com 64 partições com 67 ms contra 111 ms. Por serem dados pequenos, isso não vale como resultado.

Limitação: 8 não foi medido como o melhor valor, porque nas execuções de 04/11 nenhum caso passou de 9 workers. O PP4 com workers fixos testa 16 e 24 de verdade. Se ele mostrar outro valor claramente melhor, rever esta escolha e repetir as PPs afetadas.


## Tratamento dos dados

As tabelas originais (`brasil_line`, `brasil_polygon` e `brasil_point`) não são alteradas. O tratamento vale para as regiões, em tabelas próprias do schema `regioes`, nesta ordem:

1. **Recorte (`experimentos/regioes/criar_regioes.sql`):** seleciona os objetos que tocam a janela da região, com `ST_Intersects`. As geometrias ficam inteiras, sem corte na borda.
2. **Remoção de limites (`experimentos/regioes/filtrar_limites.sql`):** cria as tabelas `<região>_polygon_mapa`, sem os polígonos com `boundary` igual a `administrative` ou `timezone`. As tabelas sem esse filtro continuam disponíveis para comparação.

**Regra:** é a mesma para todas as regiões e usa o atributo do OSM, não o tamanho. Saem todos os níveis administrativos, do país aos bairros, e o fuso. Ficam os demais objetos, inclusive os grandes, como rios, áreas protegidas, terras indígenas e parques.

**Motivo:** esses limites ficam aninhados, então uma mesma linha intersecta vários deles, e os maiores intersectam praticamente tudo. Assim, a junção passaria a medir em grande parte se a linha está dentro do país, e não a relação entre os objetos do mapa. Na região `es_sul`:

| Polígonos | Quantidade | Interseções com as linhas | % |
| --------- | ---------- | ------------------------- | - |
| `administrative` e `timezone` | 53 (0,18%) | 252.393 | 78,7% |
| `protected_area` | 14 | 330 | 0,1% |
| Sem `boundary` | 29.491 | 68.110 | 21,2% |
| **Total** | **29.558** | **320.833** | **100%** |

**Limites e cuidados:**

- A medição é só de `es_sul`. Nas outras regiões, só se sabe que esses polígonos existem. Foram removidos 53 polígonos em `es_sul`, 254 em `ms_campo_grande` (0,99%, a maior proporção), 735 em `pr_centro` e 708 em `pr_curitiba`.
- O CV e a escolha das regiões vêm de `medir_regioes.py`, antes deste filtro. Como sai menos de 1% dos polígonos em cada região, o efeito esperado no total é pequeno, mas o CV não foi recalculado.
- Remover objetos muda o dataset. Por isso, a metodologia precisa declarar a regra e a quantidade removida, e a faixa de 54 mil é medida com e sem o filtro, para mostrar o efeito.
- As amostras do Brasil, o PP1 Brasil e os resultados de 04/11 não têm este filtro. Falta decidir se a rodada do Brasil completo também o usará.
- **Validade das geometrias:** nenhum tratamento adicional foi necessário. PP2 a PP5 validam a fonte antes de amostrar (geometria válida, 2D, SRID e tipo corretos) e param se encontrarem problema. As execuções de 04/11 passaram por essa validação.


# Erros

## Número de workers decidido pelo planejador (corrigido)

Encontrado nas execuções de 04/11/2026, feitas no `jatoba2` com o commit `5efa1a8` (`pp1_*`, `pp2_*`, `pp3_*`, `pp4_*` e `pp5_*` de 20261104, em `resultados/lab`).

**Problema:** `--workers` definia apenas o limite `max_parallel_workers_per_gather`. Abaixo dele, o PostgreSQL escolhia a quantidade, conforme o tamanho da tabela e, nas tabelas particionadas, o número de partições: `log2(partições) + 1`.

| Partições        | 4 | 15 | 16 | 64 | 66 | 256 | 380 |
| ---------------- | - | -- | -- | -- | -- | --- | --- |
| Workers lançados | 3 | 4  | 5  | 7  | 7  | 9   | 9   |

Observado no PP5 com 100 mil/50 mil, com limite de 24 workers.

| PP  | Efeito nos resultados | Situação dos resultados de 04/11 |
| --- | --------------------- | -------------------------------- |
| PP1 | Curitiba e Brasil: o baseline e os particionados podem ter usado quantidades diferentes de workers, e o speedup pode misturar particionamento e paralelismo. | Exploratórios |
| PP2 | Com 100 mil/50 mil, o baseline usou 2 workers em `linha_poligono`, contra 7 dos particionados; o speedup mistura os dois efeitos. | Exploratórios |
| PP3 | A comparação entre baseline e particionados, usada na H1, tem a mesma mistura. | Exploratórios |
| PP4 | Os limites 16 e 24 não foram testados: os particionados pararam em 7 workers e o baseline em 2. O speedup para em 8 por causa disso, então não é um limite de escalabilidade. Com 2 workers, o baseline também troca a ordem do join e fica mais lento que com 1. | Inválidos acima de 8 workers; o restante é exploratório |
| PP5 | Mais partições significavam mais workers, então o efeito da granularidade (H4) ficou misturado com o do paralelismo. | Exploratórios |

**Correção:** `Experimento.medir` agora define `parallel_workers` nas tabelas medidas: nas partições ou, no baseline, nas entradas. Como esse valor é igual ao limite, o caso usa exatamente o número pedido. No PP1, as tabelas originais voltam ao padrão depois do baseline.

**Como conferir:** o script avisa quando o plano lança um número diferente do pedido, e `plano_workers_lancados_max` registra o valor no PP4 e no PP5. Execuções novas têm `workers_fixos = sim` nos CSVs de PP2 a PP5 e `modelo_pp1 = masj_variantes_samj_workers_fixos_v3` no PP1.

**Limitação:** o valor é fixado antes das repetições, mas o `EXPLAIN` roda depois delas. Se faltarem workers no servidor durante uma repetição, ela pode usar menos do que o pedido.
