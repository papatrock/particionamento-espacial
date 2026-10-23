# Guia dos arquivos de resultados do PP1

O `pp1.py` produz as medições e os registros que permitem conferir como elas foram obtidas. O ponto de entrada para a análise é o `consultas.csv` da raiz da execução, acompanhado de `manifesto.json` e `configuracao.json`.

O nome usado pelo script é **`consultas.csv`**, no plural. Os arquivos de preparação e os planos complementam esse CSV; seus tempos não são adicionados às medições.

Para analisar várias execuções em conjunto, use `acumulado/consultas_acumulado.csv` e `acumulado/perf_acumulado.csv`. Essa camada é reconstruída a partir dos resultados brutos concluídos; as pastas individuais descritas abaixo continuam preservadas para auditoria.

## Tabelas e figuras da análise

O código das análises fica em `analises/`, separado dos resultados e dos scripts que executam o benchmark. Com o ambiente virtual e as dependências de `requirements.txt` instaladas, rode na raiz do projeto:

```bash
python -m analises.pp1
```

Esse módulo substitui o antigo `analisar_pp1.py` da raiz. Lê `acumulado/consultas_acumulado.csv` e, quando disponível, `acumulado/perf_acumulado.csv`. A parte de perf fica em `analises/perf.py`, chamada automaticamente pela PP1.

| Arquivo gerado em `resultados/pp1/` | Conteúdo |
|---|---|
| `analise/resumo_tempos.csv` | Por dataset, cenário e algoritmo: número de repetições, média, mediana, desvio padrão amostral, mínimo, máximo e coeficiente de variação percentual. |
| `analise/speedup.csv` | Razão entre o tempo médio do baseline e o tempo médio de cada algoritmo no mesmo dataset/cenário. O baseline tem speedup 1. |
| `figuras/tempo_boxplot_<dataset>_<cenario>.pdf` / `.png` | Distribuição dos tempos por algoritmo, incluindo a indicação da média. |
| `figuras/tempo_medio_<dataset>_<cenario>.pdf` / `.png` | Média dos tempos por algoritmo com barras de desvio padrão. |
| `figuras/speedup_<dataset>_<cenario>.pdf` / `.png` | Speedup em relação ao baseline, com referência em 1. |
| `analise/contadores_perf.csv` | Uma linha por contador original, com contexto, PMU, evento, modificadores, valor médio por consulta e avaliação da qualidade. |
| `analise/metricas_perf.csv` | IPC e percentuais de falhas de cache/desvios, calculados por bloco e PMU, com status e menor cobertura dos contadores envolvidos. |
| `analise/qualidade_perf.csv` | Quantidade de contadores por bloco, PMU, status da análise e cobertura de coleta. |
| `figuras/perf/<pp1_run_id>/contador_<evento>_*.pdf` / `.png` | Comparação dos contadores médios por consulta, com séries separadas por PMU/modificadores. |
| `figuras/perf/<pp1_run_id>/metrica_<indicador>_*.pdf` / `.png` | Comparação de IPC e percentuais de falhas por algoritmo, com séries separadas por PMU/modificadores. |

As saídas da análise são derivadas e podem ser recriadas; os brutos e os acumulados não são modificados. Para usar outro diretório de resultados, informe `--resultados /caminho/da/raiz/pp1`. O padrão aponta para `resultados/pp1` do projeto. Os cálculos e agrupamentos do script original foram preservados: as repetições são reunidas por dataset, cenário e algoritmo; não há filtro adicional por máquina, commit, workers, rodada ou instrumentação perf. As barras de desvio padrão não são intervalos de confiança.

### Análise dos contadores de perf

As fórmulas usam os totais dos contadores no mesmo bloco de medições:

| Saída | Fórmula |
|---|---|
| `valor_por_consulta` | `valor / repeticoes` |
| `ipc` | `instructions / cycles` |
| `cache_miss_percentual` | `100 * cache-misses / cache-references` |
| `branch_miss_percentual` | `100 * branch-misses / branches` |

Os contadores por consulta abrangem todos os eventos coletados, incluindo trocas de contexto, migrações de CPU e falhas de página. A coluna original `valor` continua representando o total do bloco. O campo `tempo_ativo_ns` é preservado; ele não é usado como duração de uma consulta nem como divisor para obter eventos por segundo.

Em CPUs híbridas, o perf pode produzir `cpu_core/cycles/` e `cpu_atom/cycles/`. Cada PMU representa um grupo de unidades de monitoramento de desempenho. Os indicadores combinam somente eventos da mesma PMU, com os mesmos modificadores e identidade de bloco (`pp1_run_id`, `execucao`, dataset, cenário, algoritmo e rodada). Assim, instruções de `cpu_core` não são divididas pelos ciclos de `cpu_atom`, nem eventos `:u` por eventos `:k`. Não há soma automática das PMUs. Os eventos genéricos sem PMU explícita aparecem como `cpu`; os três eventos de software padrão aparecem como `software`.

Os gráficos de perf separam execuções globais, rodadas, escopo, máquina, commit, estado do Git, workers, GiST, partições-alvo e instrumentação. Os últimos quatro campos são ligados ao CSV de consultas pela identidade do bloco, sem replicar cada contador pelo número de consultas. O baseline `SEM_PARTICIONAMENTO`, que naturalmente tem partições-alvo vazias, aparece como referência em cada alvo da mesma configuração. A capacidade e o número efetivo de partições podem variar conforme o algoritmo; os detalhes continuam nas fontes. Um identificador no nome de cada figura distingue configurações diferentes. Dentro de uma faceta, blocos adicionais do mesmo algoritmo aparecem como séries separadas, sem média entre eles. Essa separação vale para perf; os gráficos de tempos acima mantêm o agrupamento original.

Eventos indisponíveis, inválidos ou duplicados, quantidades inválidas de repetições e denominadores zero ficam com valor derivado vazio e motivo em `status_analise`. Um zero realmente medido é preservado. Se um indicador tiver somente um dos eventos necessários, ele fica vazio com status `evento_ausente:<evento>`; indicadores sem nenhum dos dois eventos não são gerados. Em gráficos com dados válidos, barras indisponíveis aparecem como `N/D`; um evento inteiramente indisponível não gera gráfico, mas permanece nas tabelas.

O `percentual_ativo` indica a fração da janela na qual o contador esteve ativo. A análise classifica a cobertura como `completa` (100%), `multiplexado` (entre 0% e 100%), `desconhecida` (campo ausente/inválido) ou `invalida` (valor numérico fora do intervalo). O perf normalmente já escala contagens multiplexadas; a análise usa os valores reportados sem aplicar uma segunda escala. Indicadores multiplexados ou com cobertura desconhecida continuam calculados quando os contadores são válidos, com a condição registrada para revisão. Cobertura numérica inválida impede o cálculo. O CSV de qualidade ajuda a identificar coletas que precisam ser repetidas. [Documentação do perf stat](https://man7.org/linux/man-pages/man1/perf-stat.1.html).

**Limites da interpretação:** um bloco de dez consultas medido uma vez pelo perf fornece uma observação por contador. Dividir por dez fornece uma média por consulta, sem criar dez amostras independentes. Por isso, os gráficos de perf não mostram desvio padrão, intervalos de confiança ou testes de significância. Para estudar variabilidade, é preciso coletar novos blocos e comparar configurações equivalentes. A análise atual é descritiva; também não correlaciona automaticamente os contadores com balanceamento ou overhead do particionamento.

Como a coleta usa `perf stat -a`, os indicadores incluem toda a atividade da máquina durante a janela e algum overhead do cliente/controle, além do PostgreSQL e seus workers. IPC maior isoladamente não garante consulta mais rápida; use os contadores para explicar os tempos. O significado dos eventos genéricos de cache depende do hardware: o percentual calculado não deve ser descrito automaticamente como taxa de falhas de L1. Sem arquivo de perf, a análise de tempos continua normalmente; com acumulado de perf vazio, as três tabelas são produzidas somente com cabeçalhos.

## Camada acumulada de várias execuções

```text
resultados/pp1/
├── pp1_<dataUTC1>/           # resultados brutos de uma execução
├── pp1_<dataUTC2>/           # resultados brutos de outra execução
└── acumulado/
    ├── consultas_acumulado.csv
    ├── perf_acumulado.csv
    └── .consolidacao.lock   # controle local de concorrência; não é dado experimental
```

Ao terminar com sucesso, o `pp1.py` chama o consolidador depois de gravar o manifesto concluído. Para reconstruir manualmente, execute `python3 consolidar_pp1.py`. Com uma raiz diferente, use `python3 consolidar_pp1.py --entrada /caminho/da/raiz`, apontando para a pasta que contém os diretórios `pp1_*`.

| Arquivo | Conteúdo | Uso |
|---|---|---|
| `consultas_acumulado.csv` | Todas as repetições dos CSVs da raiz das execuções concluídas, com os metadados de origem. | Entrada para estatísticas, gráficos e tabelas de várias rodadas. Nenhuma repetição é substituída por média. |
| `perf_acumulado.csv` | Todas as linhas dos relatórios `perf.csv` dessas execuções, no formato longo original. | Análise posterior por evento/PMU. Os eventos não são transformados em colunas. |

O consolidador seleciona exclusivamente `manifesto.status == "concluido"`. Pastas com falha, em execução, sem manifesto ou com manifesto ilegível não entram nos acumulados. Uma execução concluída sem perf entra no acumulado de consultas sem contribuir com contadores. Um experimento concluído pode ter selecionado apenas um dataset ou alguns algoritmos: conclusão se refere à seleção daquela chamada, não exige sempre as dez combinações.

São lidos somente os `consultas.csv` e `perf.csv` da raiz de cada execução. Os CSVs individuais dentro de `medicoes/` já estão representados neles e não são importados novamente. Não junte os arquivos acumulados aos brutos para uma mesma análise, pois isso contaria as observações duas vezes.

### Metadados adicionados aos acumulados

| Coluna | Origem e significado |
|---|---|
| `pp1_run_id` | Nome da pasta bruta, como `pp1_20261022T143000123456Z`. Identifica a execução global. A coluna original `execucao` continua identificando uma chamada interna do coletor. |
| `hostname` | Nome da máquina registrado no `configuracao.json` da execução. |
| `git_commit` | Commit registrado no início da execução; pode ser desconhecido. |
| `git_dirty` | `true` ou `false` conforme o estado do Git registrado. Vazio quando desconhecido. |

Nas novas chamadas do PP1, esses quatro campos são adicionados ao `configuracao.json`. `git_commit` vem de `git rev-parse HEAD`; `git_dirty` vem de `git status --porcelain`, incluindo alterações não commitadas e arquivos não rastreados que não estejam ignorados. Se uma consulta ao Git falhar ou o Git estiver ausente, os campos que não puderam ser obtidos ficam `null`. Isso não interrompe o benchmark.

O hostname e o commit de execuções antigas não são inferidos da máquina ou do repositório atual. Se não estiverem registrados no arquivo de configuração original, ficam vazios no acumulado. Os arquivos antigos não são regravados para acrescentar campos. Um `git_dirty: true` indica que o commit registrado é uma referência de base, não uma descrição integral das alterações locais.

Todas as colunas dos CSVs de origem são preservadas. Se os cabeçalhos forem diferentes, o acumulado usa a união das colunas e deixa vazios os campos ausentes. Por exemplo, uma execução anterior à opção `--perf` pode não ter essa coluna. Não se inferem valores para ela durante a consolidação. Textos numéricos são copiados sem converter precisão, calcular estatísticas ou substituir contadores indisponíveis por zero.

### Reconstrução e proteção dos brutos

A consolidação sempre relê as fontes e recria as saídas; não usa append incremental. A ordem das pastas e das colunas é determinística, e executar o comando novamente sem alterar as fontes produz os mesmos CSVs. Valores iguais em repetições diferentes são mantidos como observações independentes.

Apenas arquivos em `acumulado/` são escritos pelo consolidador. Os dois arquivos temporários são preparados antes da substituição atômica de cada CSV. Se a leitura de um CSV concluído falhar, os acumulados anteriores são mantidos e o erro identifica a fonte problemática. Metadados de configuração indisponíveis geram aviso e campos vazios. Um CSV de consultas ausente ou inválido em uma execução concluída, ou `perf: true` sem o respectivo `perf.csv`, interrompe a reconstrução para evitar uma perda silenciosa de dados.

O arquivo oculto `.consolidacao.lock` serializa consolidações manuais e automáticas concorrentes no Linux. Ele não contém observações experimentais. Uma falha na consolidação automática não muda o manifesto concluído nem invalida os brutos já salvos. Para tentar novamente, use o script separado.

Sem execuções concluídas, o comando informa a situação e produz os dois CSVs somente com cabeçalhos. Ao final de uma reconstrução, o resumo mostra pastas encontradas, concluídas e ignoradas, além das quantidades de execuções e linhas em cada acumulado. Não são calculados médias, speedups, intervalos de confiança ou testes estatísticos nesta etapa.

## Estrutura das pastas

Uma execução completa tem uma estrutura como esta. Os nomes entre `<...>` variam a cada execução.

```text
resultados/pp1/pp1_<dataUTC>/
├── configuracao.json
├── manifesto.json
├── compilacao.log
├── consultas.csv
├── curitiba/
│   ├── entradas.json
│   ├── eixo_rua_validacao.{sql,stdout.log,stderr.log}
│   ├── arruamento_quadras_validacao.{sql,stdout.log,stderr.log}
│   ├── eixo_rua_gist.{sql,stdout.log,stderr.log}
│   ├── arruamento_quadras_gist.{sql,stdout.log,stderr.log}
│   ├── contagem_baseline.{sql,stdout.log,stderr.log}
│   ├── a_exportacao.{sql,stdout.log,stderr.log}
│   ├── b_exportacao.{sql,stdout.log,stderr.log}
│   ├── sem_particionamento/
│   ├── two_layer/
│   ├── str/
│   │   ├── java.log
│   │   ├── particionamento.json
│   │   ├── materializacao.{sql,stdout.log,stderr.log}
│   │   ├── consulta.sql
│   │   ├── coletor.log
│   │   ├── plano.sql
│   │   ├── plano.stdout.log
│   │   ├── plano.stderr.log
│   │   ├── plano.json
│   │   └── medicoes/<dataUTC>/
│   │       ├── consulta.sql
│   │       ├── consultas.csv
│   │       ├── psql.stdout.log
│   │       └── psql.stderr.log
│   ├── hilbert/
│   └── bsp/
└── brasil/
    └── ...
```

A notação `nome.{sql,stdout.log,stderr.log}` representa três arquivos separados. As pastas dos outros algoritmos seguem a mesma organização do STR. O baseline `sem_particionamento` não tem `java.log`, `particionamento.json` nem os arquivos de materialização, pois consulta diretamente as entradas.

Os horários dos nomes de pasta usam UTC; `Z` indica esse fuso. A pasta externa identifica a execução do PP1, e a pasta dentro de `medicoes` identifica a chamada do coletor para uma combinação.

Uma execução interrompida pode ter pastas incompletas ou nenhum resultado de um dataset. Consulte o manifesto antes de considerar que toda a matriz foi executada.

## Arquivos da raiz da execução

| Arquivo | Conteúdo | Para que consultar |
|---|---|---|
| `configuracao.json` | Parâmetros solicitados: banco, conexão explícita, datasets, algoritmos, workers, alvo de partições, aquecimentos, repetições, rodada, bits Hilbert e tentativas BSP. | Identificar as condições da execução e comparar rodadas. |
| `manifesto.json` | Status global, combinações iniciadas/concluídas, contagens validadas, partições efetivas e eventual erro. | Saber se o experimento terminou e onde houve interrupção. |
| `compilacao.log` | Saída padrão do Maven na compilação dos particionadores. Pode ficar vazio quando o Maven não emite mensagens no modo silencioso. | Diagnosticar problemas de compilação. Não é gerado se a seleção contiver somente o baseline. |
| `consultas.csv` | Consolidação das medições das combinações concluídas. | Calcular estatísticas, comparar algoritmos e montar os gráficos do PP1. |

Em `configuracao.json`, `pedir_senha: true` registra apenas que a opção foi usada; a senha não é gravada. Valores `null` em host, porta ou usuário significam que o argumento foi omitido e o `psql` usou seus padrões ou variáveis de ambiente. Esse arquivo registra os argumentos da execução, não um inventário completo da máquina ou de todas as configurações do PostgreSQL.

Nas novas execuções, o arquivo também registra `pp1_run_id`, `hostname`, `git_commit` e `git_dirty`, usados na camada acumulada. Eles não mudam a identificação interna `execucao` dos coletores.

O status global do manifesto pode ser `em_execucao`, `concluido` ou `falhou`. Uma falha posterior não apaga as medições já consolidadas. Portanto, um CSV existente não comprova que os dois datasets terminaram.

### Colunas de `consultas.csv`

Cada linha corresponde a uma repetição medida. Os aquecimentos não viram linhas no CSV.

| Coluna | Significado |
|---|---|
| `execucao` | Identificador UTC da chamada do coletor. Varia entre combinações da mesma execução do PP1. |
| `cenario` | Identificador do join, como `ruas_quadras` ou `brasil_line_polygon`. |
| `algoritmo` | Estratégia medida, incluindo `SEM_PARTICIONAMENTO`. |
| `rodada` | Número informado para identificar a rodada do experimento. |
| `repeticao` | Posição da execução medida, de 1 até o número de repetições. |
| `aquecimentos` | Quantidade de consultas executadas antes das repetições medidas. |
| `tempo_cliente_ms` | Tempo em milissegundos reportado pelo `\timing` do `psql` para aquela consulta. Inclui a espera do cliente pela resposta; não é o tempo total do processo Python ou da preparação. |
| `workers_por_gather` | Limite configurado em `max_parallel_workers_per_gather`. Não informa quantos workers efetivamente participaram. |
| `indexacao` | Opção dos métodos de acesso por índice no coletor. No PP1 é `on`; o preparador também garante GiST disponível. |
| `intersecoes` | Contagem de pares retornada pelo join, conferida contra o baseline. Não é o número de partições nem de geometrias de entrada. |
| `perf` | `on` quando os tempos foram obtidos com instrumentação perf no bloco de repetições; `off` caso contrário. Presente nas novas coletas. |
| `dataset` | `curitiba` ou `brasil`. Presente no CSV consolidado. |
| `particoes_alvo` | Granularidade solicitada, normalmente 64. Presente no consolidado; vazia no baseline. |
| `particoes_efetivas` | Quantidade realmente produzida pelo algoritmo, contando também as regiões sem objetos. Presente no consolidado; vazia no baseline. |
| `capacidade` | Capacidade usada por STR, Hilbert ou BSP. Presente no consolidado; vazia para Two-Layer e baseline. |

O `consultas.csv` dentro de `medicoes/<dataUTC>` contém as medições de uma única combinação e vai até a coluna `perf` nas novas coletas. O CSV da raiz copia essas linhas e acrescenta as quatro últimas colunas da tabela. Eles representam as mesmas medições: juntar ambos contaria as repetições duas vezes. Os exemplos históricos anteriores à instrumentação não têm a coluna `perf`.

O coletor independente pode ser executado sem `--contagem-esperada`; nesse caso, a coluna `intersecoes` fica vazia e a conferência contra o baseline não ocorre. O `pp1.py` sempre fornece essa referência.

## Arquivos de cada dataset

Curitiba usa A = `eixo_rua` e B = `arruamento_quadras`. Brasil usa A = `brasil_line` e B = `brasil_polygon`.

| Arquivo ou prefixo | Conteúdo | Utilidade |
|---|---|---|
| `<tabela>_validacao.sql` | Consulta que conta registros, IDs, geometrias nulas/vazias e SRIDs incorretos. | Conferir exatamente quais verificações foram feitas na entrada. |
| `<tabela>_validacao.stdout.log` | Resultado JSON dessa consulta. | Identificar IDs duplicados, nulos ou problemas de geometria/SRID. |
| `<tabela>_validacao.stderr.log` | Erros e avisos da validação. | Investigar tabela/coluna inexistente ou falha na execução da consulta. |
| `entradas.json` | Resumo das validações das duas tabelas, gravado após a preparação de ambas. | Consultar o volume e a consistência das entradas. Pode não existir se a preparação falhar antes de terminar. |
| `<tabela>_gist.sql` | Comandos para reutilizar um GiST válido, criar um quando necessário e executar `ANALYZE`. | Conferir a preparação da indexação e das estatísticas do baseline. |
| `<tabela>_gist.stdout.log` / `.stderr.log` | Saída padrão e mensagens dessa preparação. | Diagnosticar falhas de permissão, criação de índice ou análise. A saída padrão pode ficar vazia. |
| `contagem_baseline.sql` | Join direto das entradas, precedido das configurações de sessão. | Conferir a consulta usada como referência de correção. |
| `contagem_baseline.stdout.log` | Um número: a quantidade esperada de pares do join. | Comparar com o resultado de todos os algoritmos. Não contém uma medição usada no CSV. |
| `contagem_baseline.stderr.log` | Erros e avisos da consulta de referência. | Investigar falha no join direto. |
| `a_exportacao.sql` / `b_exportacao.sql` | Comandos `\copy` que exportam ID e WKT para arquivos temporários, com ordenação pelo ID. | Conferir quais dados foram entregues ao Java e em qual ordem, especialmente para BSP. |
| `a_exportacao.stdout.log` / `.stderr.log`, `b_exportacao.stdout.log` / `.stderr.log` | Saídas das exportações. | Diagnosticar falhas ao exportar os dados. Os WKTs são gravados em TSV temporário, não nesses logs. |

Os campos de `entradas.json` são:

| Campo | Significado |
|---|---|
| `tabela` | Nome da relação de entrada. |
| `registros` | Total de linhas, incluindo geometrias EMPTY. |
| `ids` | Quantidade de IDs não nulos. |
| `ids_distintos` | Quantidade de IDs distintos após conversão para `BIGINT`. Deve coincidir com o total de registros. |
| `geometrias_nulas` | Quantidade de geometrias SQL `NULL`. Deve ser zero. |
| `srid_incorreto` | Quantidade com SRID diferente do configurado para o dataset. Deve ser zero. |
| `geometrias_vazias` | Quantidade de geometrias EMPTY. Elas são excluídas da exportação para o Java, pois não contribuem para `ST_Intersects`. |

Essa validação não inclui um teste geral de validade topológica das geometrias.

## Preparação de cada algoritmo

| Arquivo | Conteúdo | Utilidade |
|---|---|---|
| `java.log` | Saída padrão da etapa Java: resultado do particionamento e eventuais mensagens das tentativas BSP. | Conferir a preparação e diagnosticar problemas do algoritmo. Parte dos erros do processo também pode aparecer apenas no terminal. |
| `particionamento.json` | Parâmetros efetivos, quantidade de regiões, objetos de entrada, ocupação e calibração BSP. | Explicar diferenças de granularidade, replicação e distribuição dos dados. |
| `materializacao.sql` | Transação que recria as tabelas particionadas, carrega as associações, cria GiST e executa `ANALYZE`. | Conferir como o particionamento Java foi transformado em tabelas PostgreSQL. |
| `materializacao.stdout.log` / `.stderr.log` | Saídas dessa transação. | Investigar problemas na carga, nos tipos geométricos, nas partições ou nos índices. |

### Campos de `particionamento.json`

| Campo | Significado |
|---|---|
| `algoritmo` | Nome da estratégia que produziu as associações. |
| `particoes_alvo` | Quantidade usada como referência para a normalização. |
| `particoes_efetivas` | Número de regiões efetivamente criadas. É a quantidade por relação; A e B compartilham as mesmas regiões. |
| `capacidade` | Capacidade escolhida para STR, Hilbert ou BSP. `null` no Two-Layer. |
| `hilbert_bits` | Precisão da curva Hilbert; `null` nos demais algoritmos. |
| `objetos_a` / `objetos_b` | Quantidade de objetos não vazios entregue ao particionador em cada entrada, antes da replicação. |
| `calibracao_bsp` | Tentativas de capacidade e quantidade de folhas no BSP. Nos outros algoritmos é uma lista vazia. Uma tentativa inválida pode conter `particoes: null` e `falha: true`; os detalhes aparecem em `java.log`. |
| `ocupacoes` | Lista com `id`, `objetos_a` e `objetos_b` para cada região, após a associação/replicação. Inclui ocupações zero. |

No STR e no Hilbert, a capacidade limita os grupos usados para construir as fronteiras. A ocupação final de uma região pode ultrapassar essa capacidade porque os objetos são associados às regiões por interseção de MBRs.

Para medir replicação, some as ocupações de uma entrada e divida pela quantidade original de objetos dessa entrada:

```text
fator de replicação de A = soma(ocupacoes[].objetos_a) / objetos_a
fator de replicação de B = soma(ocupacoes[].objetos_b) / objetos_b
```

Um fator 1 significa uma associação por objeto, em média. Um fator 1,5 significa 50% mais associações que objetos originais. Para uma entrada sem objetos, essa razão fica indefinida. As ocupações também permitem comparar mínimo, máximo, média e dispersão entre regiões; a contagem de objetos, sozinha, não representa toda a complexidade do processamento geométrico.

Os metadados guardam contagens e parâmetros, mas não guardam os WKTs das fronteiras nem todas as geometrias de saída.

## Arquivos da coleta

| Arquivo | Conteúdo | Utilidade |
|---|---|---|
| `<algoritmo>/consulta.sql` | Join selecionado pelo orquestrador. Two-Layer usa o filtro de classes A/B/C/D; STR, Hilbert e BSP deduplicam os pares de IDs; o baseline consulta as entradas. | Conferir o que está sendo comparado. |
| `<algoritmo>/coletor.log` | Saída padrão do processo Python do coletor, normalmente uma mensagem com o caminho do CSV gerado. | Localizar as medições e conferir que o coletor chegou a gravá-las. Erros do processo podem aparecer no terminal. |
| `medicoes/<dataUTC>/consulta.sql` | Cópia da consulta recebida pelo coletor. | Preservar o SQL associado àquela chamada específica. Não representa uma execução adicional. |
| `medicoes/<dataUTC>/consultas.csv` | Repetições medidas da combinação, após as verificações de contagem e quantidade de tempos. | Analisar uma combinação individualmente. |
| `medicoes/<dataUTC>/psql.stdout.log` | Saída do `psql`: configurações consultadas por `SHOW`, marcadores de contagem, resultados dos aquecimentos e repetições e linhas `Time: ... ms`. | Auditar as contagens e conferir a origem dos tempos do CSV. |
| `medicoes/<dataUTC>/psql.stderr.log` | Erros e avisos do `psql` durante a coleta. | Diagnosticar autenticação, SQL ou outra falha de execução. |

O marcador `__COLETAR_CONTAGEM__` identifica o início do resultado de cada consulta para a validação automática. Não é um resultado do join.

Os aquecimentos aparecem no log com seus resultados, mas a opção `\timing` é ativada somente para as repetições medidas. A criação dos índices, a exportação, a calibração, a materialização e a consulta adicional do plano ficam fora das linhas de tempo do CSV.

## Arquivos opcionais do perf

Quando o PP1 ou o coletor é chamado com `--perf`, o `perf stat -a` acompanha o bloco de repetições medidas. A configuração e os aquecimentos ocorrem com contadores desativados. Eles são habilitados antes das repetições e desabilitados ao fim, na mesma sessão de banco. Há algum overhead do cliente e dos comandos de controle dentro da janela. A coleta abrange todas as CPUs, incluindo PostgreSQL, workers, cliente e outras atividades da máquina. Deve ser executada no próprio servidor do banco.

Os contadores representam **o total do bloco**, por exemplo das dez repetições. Não são valores individuais por repetição e não devem ser copiados para cada linha do `consultas.csv`. Mantenha a quantidade de repetições igual ao comparar esses totais entre algoritmos. A contagem inicial de referência, a preparação e o plano adicional ficam fora da janela do perf. [Referência das opções de coleta e controle](https://man7.org/linux/man-pages/man1/perf-stat.1.html).

| Arquivo | Conteúdo | Utilidade |
|---|---|---|
| `perf_verificacao.csv` | Contadores brutos de um comando curto `true`, usado para conferir eventos e permissões. Pode existir na raiz do PP1 e na pasta de medições. | Diagnóstico da disponibilidade do perf; não representa o join. |
| `perf_verificacao.stdout.log` / `.stderr.log` | Saídas da verificação de acesso aos contadores. | Investigar erros de permissão, eventos ou perf indisponível antes dos joins longos. |
| `medicoes/<dataUTC>/perf_stat.csv` | Saída bruta de `perf stat`, com campos separados por `;`, comentários e possíveis métricas adicionais. | Preservar a resposta original da ferramenta. Não é o mesmo formato do CSV de tempos. |
| `medicoes/<dataUTC>/perf.csv` | Uma linha por evento/PMU, com o total do bloco e seu contexto. | Analisar os contadores da combinação. |
| `medicoes/<dataUTC>/perf.json` | Identificador, cenário, algoritmo, rodada, repetições, eventos solicitados, versão do perf, escopo, janela e status. | Saber exatamente a que conjunto de medições os contadores correspondem. |
| `medicoes/<dataUTC>/perf_sessao.psql` | Lote enviado ao `psql`, incluindo configurações, aquecimentos e comandos de habilitação/desabilitação do perf com confirmação. | Auditar a posição da janela de instrumentação. Menciona FIFOs temporários removidos ao terminar. |
| `<raiz da execução>/perf.csv` | Consolidação dos CSVs de contadores, acrescentando a coluna `dataset`. É gravado ao fim do PP1. | Comparar os totais das combinações concluídas. Em uma execução interrompida antes dessa etapa, consulte os CSVs individuais. |

As mensagens do perf durante a coleta compartilham o `psql.stderr.log` com as mensagens do cliente. O relatório de contadores propriamente dito é direcionado para `perf_stat.csv`.

O `perf.csv` contém:

| Coluna | Significado |
|---|---|
| `execucao`, `cenario`, `algoritmo`, `rodada` | Contexto da coleta; `execucao` permite relacionar os contadores às linhas de tempo do mesmo bloco. |
| `repeticoes` | Número de consultas medidas cobertas pelo total. |
| `escopo` | `sistema_inteiro`: os contadores não isolam somente o PostgreSQL. |
| `evento` | Nome reportado pelo perf; em CPUs híbridas pode haver nomes distintos por PMU. |
| `valor` | Total reportado pelo perf. Fica vazio quando o contador é indisponível. |
| `unidade` | Unidade informada pela ferramenta; pode ficar vazia para contagens de eventos. |
| `status` | `ok`, `nao_suportado` ou `nao_contado`. Ausência de contagem não equivale a zero. |
| `tempo_ativo_ns` | Tempo de atividade do contador reportado pelo perf, em nanossegundos. |
| `percentual_ativo` | Percentual da janela em que o contador esteve ativo. Valores abaixo de 100 ajudam a identificar multiplexação. |
| `dataset` | Presente apenas no consolidado do PP1. |

Quando há multiplexação, o perf pode reportar contagens escaladas. Preserve o percentual ativo e o relatório bruto ao interpretar os valores. Esses campos seguem o formato delimitado da ferramenta, descrito na [documentação de perf stat](https://man7.org/linux/man-pages/man1/perf-stat.1.html#CSV_FORMAT).

Em `perf.json`, `concluido` indica contadores disponíveis após validação da coleta; `contadores_indisponiveis` indica que pelo menos um evento não foi suportado ou contado. `falhou` indica falha do processo instrumentado. `aguardando_validacao` indica que o processo terminou, mas a validação do coletor ainda não finalizou; se permanecer assim, consulte os logs e confirme a existência do CSV de tempos.

## Arquivos do plano: por que existem quatro?

| Arquivo | Conteúdo | Quando abrir |
|---|---|---|
| `plano.sql` | Configurações de sessão e `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` aplicado ao join. | Para saber como o diagnóstico foi solicitado. |
| `plano.stdout.log` | Resposta original do `psql`, contendo o plano em JSON. | Para conferir a saída bruta da execução. |
| `plano.stderr.log` | Erros e avisos durante a captura do plano. | Se a etapa de diagnóstico falhar ou emitir mensagens. |
| `plano.json` | Mesmo plano interpretado e regravado com formatação pelo Python. | Para ler, explorar ou processar o plano automaticamente. |

`plano.stdout.log` e `plano.json` normalmente têm o mesmo conteúdo lógico, com possível diferença de formatação. São dois registros de uma única captura, não duas execuções do join.

O `EXPLAIN ANALYZE` executa a consulta **mais uma vez, depois das repetições medidas**. Assim, esse plano descreve uma execução adicional, não cada linha do CSV. Seu tempo pode diferir dos tempos medidos pelo coletor, inclusive pelo trabalho extra da instrumentação. Consulte a [documentação de EXPLAIN do PostgreSQL 17](https://www.postgresql.org/docs/17/using-explain.html) para detalhes de interpretação.

### Campos úteis de `plano.json`

O JSON é uma lista; o primeiro objeto contém `Plan`, além de campos como `Planning Time` e `Execution Time`. Dentro de `Plan`, `Plans` contém os nós filhos.

| Campo ou nó | Como interpretar |
|---|---|
| `Planning Time` | Tempo de planejamento dessa execução diagnóstica, em milissegundos. |
| `Execution Time` | Tempo de execução reportado pelo servidor para o diagnóstico, em milissegundos. Não substitui `tempo_cliente_ms` do CSV. |
| `Node Type` | Operação executada, como varredura, join, ordenação ou agregação. |
| `Index Scan`, `Bitmap Index Scan`, `Index Name` e `Index Cond` | Ajudam a identificar acessos por índice. Confira também o nome do índice para relacionar o acesso ao GiST criado. Ter GiST disponível não obriga seu uso em todo nó. |
| `Append` / `Parallel Append` | Combinam resultados de relações/partições; confira os nomes das tabelas nos nós filhos para identificar as regiões processadas. |
| `Gather` / `Gather Merge` | Nós que reúnem resultados dos workers. É onde procurar `Workers Planned` e `Workers Launched`. |
| `Workers Planned` / `Workers Launched` | Workers previstos e efetivamente lançados para aquele nó. O limite configurado pode ser maior que ambos. |
| `Plan Rows` / `Actual Rows` | Estimativa e quantidade de linhas emitidas pelo nó. Em um `COUNT(*)`, o nó final normalmente emite uma linha contendo a contagem, não uma linha para cada interseção. |
| `Actual Loops` | Número de execuções do nó. Tempos e linhas `Actual` por nó são expressos como médias por execução quando há múltiplos loops. |
| `Actual Total Time` | Tempo por execução do nó, em milissegundos. Não some os tempos de todos os nós: há trabalho de filhos incluído nos pais e possível paralelismo. |
| `Shared Hit Blocks` / `Shared Read Blocks` | Acessos a blocos encontrados nos buffers compartilhados ou lidos para eles. Uma leitura pode ser atendida pelo cache do sistema operacional; o campo não prova acesso físico ao disco. |
| `Temp Read Blocks` / `Temp Written Blocks` | Atividade em arquivos temporários, útil para identificar operações que ultrapassaram a memória disponível. |
| `JIT`, quando presente | Informações sobre compilação de expressões durante a execução. Seus tempos de trabalho podem se acumular entre workers e não devem ser simplesmente somados ao tempo de parede da consulta. |

Esses campos descrevem o plano e suas medições, não uma linha temporal em que todos os valores possam ser somados. As unidades de custo estimado (`Startup Cost`, `Total Cost`) também não são milissegundos. [Referência de interpretação de planos](https://www.postgresql.org/docs/17/using-explain.html).

## Exemplos da execução `pp1_20261016T143109212614Z`

Na validação de Curitiba foram encontrados 40.394 registros em `eixo_rua` e 13.627 em `arruamento_quadras`, sem geometrias nulas ou vazias. A contagem de referência do join foi **1.915 pares**, confirmada nos cinco modos.

O STR registrou capacidade 845 e 64 partições efetivas. Essa capacidade vem de `ceil((40394 + 13627) / 64)`. Suas ocupações somam 66.939 associações de A e 23.545 de B, indicando replicação. Portanto, esses totais não devem ser interpretados como novos objetos originais.

O BSP tinha alvo 64 e produziu 72 folhas com capacidade 1.260. A lista `calibracao_bsp` mostra as oito tentativas. A quantidade 72 foi a mais próxima de 64 entre as grades experimentadas nessa busca; não representa garantia de ótimo global.

No plano do STR, o `Gather Merge` registrou `Workers Planned: 7` e `Workers Launched: 7`, embora o limite solicitado no coletor fosse 24. A execução diagnóstica registrou `Planning Time: 43.177` ms e `Execution Time: 346.797` ms. Esses valores pertencem ao plano adicional, e não às dez repetições do CSV.

O manifesto dessa execução está como **`falhou`**: Curitiba terminou, mas Brasil parou na primeira validação porque a coluna `geom` não existe no banco usado. O erro está em `brasil/brasil_line_validacao.stderr.log`. O CSV consolidado contém as medições concluídas de Curitiba; ele não constitui uma execução completa dos dois datasets.

## Como consultar os resultados e investigar falhas

1. Abra `manifesto.json` para identificar o status e as combinações concluídas.
2. Confira `configuracao.json` para saber quais condições foram solicitadas.
3. Use o CSV consolidado para analisar os tempos, sem adicionar os CSVs individuais novamente.
4. Consulte `particionamento.json` para explicar granularidade, ocupação e replicação.
5. Consulte `plano.json` para investigar índices, paralelismo e operações do join.
6. Se houver falha, leia o `.stderr.log` da etapa indicada e o respectivo `.sql`; para Java ou coletor, veja também os logs e a mensagem no terminal.

Um `.stderr.log` vazio é normal. Um arquivo não vazio pode conter apenas `NOTICE` ou avisos, como mensagens de `DROP TABLE IF EXISTS`; confira o tipo da mensagem e o status da execução. Uma saída padrão vazia também é normal em comandos executados pelo `psql` em modo silencioso.

## Arquivos temporários e reprodução

Durante a execução são criadas pastas temporárias `.entradas-*` com os TSVs de ID/WKT e `.associacoes-*` com as associações calculadas pelo Java. O script remove essas pastas ao sair dos respectivos blocos, inclusive em falhas tratadas.

Por isso, comandos `\copy` guardados em `a_exportacao.sql`, `b_exportacao.sql` e `materializacao.sql` podem mencionar caminhos que já não existem. Esses SQLs documentam a preparação; sozinhos, não constituem um pacote de restauração dos dados.

As tabelas particionadas no banco também são compartilhadas e substituídas pelo próximo algoritmo. Um `consulta.sql` antigo sempre consulta as tabelas que existem **agora**, não uma versão histórica daquele particionamento.

Para refazer um caso, execute novamente o `pp1.py` com o dataset, algoritmo e parâmetros desejados, usando as mesmas entradas. Preserve a pasta completa de resultados junto da versão do código e da identificação dos datasets usados; apenas o CSV não documenta todas as condições do experimento.
