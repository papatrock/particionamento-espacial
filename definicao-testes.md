

| Pergunta                        | Variar                         | Fixar                          |
| ------------------------------- | ------------------------------ | ------------------------------ |
| PP1 - algoritmos                | algoritmo, dataset, workload   | GiST, workers, nº partições    |
| PP2 - geometria                 | algoritmo, workload            | dataset/escala, GiST, workers  |
| PP3 -  índice × particionamento | com/sem particionamento e GiST | workload, workers              |
| PP4 - paralelismo               | algoritmo, workers             | dataset grande, GiST, workload |
| PP5 — granularidade             | algoritmo, nº partições        | dataset, workers, GiST         |

**PP1 - Particionamento:** diferentes estratégias de particionamento produzem diferenças significativas no tempo de execução de spatial joins?

**PP2 - Geometria:** o desempenho relativo dos particionadores muda conforme o workload seja ponto × polígono, linha × polígono ou polígono × polígono?

**PP3 - Indexação:** em quais condições a indexação espacial local já é suficiente, e quando o particionamento acrescenta ganho relevante?

**PP4 - Paralelismo:** quais estratégias de particionamento aproveitam melhor o aumento do paralelismo?

**PP5 - Granularidade:** como o número de partições afeta desempenho, balanceamento e overhead?


-----

ponto × polígono
linha × polígono
polígono × polígono


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

Variar: algoritmo, dataset
Fixar: GiST, workers, nº partições, workload

Algoritmos: SEM_PARTICIONAMENTO, TWO_LAYER, STR, HILBERT, BSP
dataset: Curitiba (pequeno), Brasil (gigantesco)

GiST: Ativo
Workers: 24 (numero de nucleos fisicos)
Numero de partições: 64
Workload:
	W1: Intersects(eixo_rua × arruamento_quadras)  (linha × polígono)
	W2: Intersects(brasil_line × brasil_polygon)  (linha × polígono)
