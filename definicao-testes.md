

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