## Requisitos

- JDK 17 ou superior
- Maven 3.6 ou superior
- PostgreSQL com PostGIS
- Banco criado, extensão PostGIS habilitada e tabelas de entrada carregadas
- Python 3.11 ou superior para as análises com pandas e Matplotlib

O Maven baixa as dependências Java na primeira execução.

## Preparar o banco

Crie o banco e habilite o PostGIS:

```sql
CREATE DATABASE benchmark;
```

Conectado ao banco:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Carregue no schema `public` as tabelas de entrada do cenário desejado. Para os cenários de Curitiba: `eixo_rua`, `arruamento_quadras`, `divisa_de_bairros` e `divisa_de_regionais`. Para os cenários do Brasil: `brasil_line`, `brasil_point` e `brasil_polygon`.

| Tabela de entrada | Geometria | SRID |
|---|---|---|
| `eixo_rua` | `MultiLineString` | `31982` |
| `arruamento_quadras` | `MultiPolygon` | `31982` |
| `divisa_de_bairros` | `MultiPolygon` | `31982` |
| `divisa_de_regionais` | `MultiPolygon` | `31982` |
| `brasil_line` | `LineString` | `3857` |
| `brasil_point` | `Point` | `3857` |
| `brasil_polygon` | `Polygon` | `3857` |

O tipo geométrico configurado em `DatasetEspacial` descreve a saída particionada, gravada com `ST_Multi`. Por isso, o catálogo do Brasil usa `MultiLineString`, `MultiPoint` e `MultiPolygon` para as saídas, preservando o SRID `3857`. As tabelas de entrada mantêm seus tipos originais. O workload de linha × polígono do Brasil usa `brasil_line × brasil_polygon`.

## Executar

Na raiz do projeto, configure a conexão com o banco:

```bash
export DB_URL='jdbc:postgresql://localhost:5432/benchmark'
export DB_USER='postgres'
export DB_PASSWORD='sua_senha'
```

Compile e inicie o programa:

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner
```

Selecione o cenário e o algoritmo nos menus apresentados. Ao final, o programa mostra o resultado do join e seu tempo de execução.

## Executar o PP1 completo

`pp1.py` prepara e mede as dez combinações: Curitiba (`eixo_rua × arruamento_quadras`) e Brasil (`brasil_line × brasil_polygon`), cada uma com `SEM_PARTICIONAMENTO`, `TWO_LAYER`, `STR`, `HILBERT` e `BSP`.

Confira a matriz sem conectar ao banco nem alterar tabelas:

```bash
python3 pp1.py --simular
```

No servidor de testes, use a conexão local habitual do usuário do sistema:

```bash
python3 pp1.py --banco benchmark --workers 24 --particoes 64
```

No PC com autenticação TCP e outro nome de banco:

```bash
python3 pp1.py --banco SEU_BANCO --host localhost --usuario postgres --pedir-senha
```

`--pedir-senha` solicita a senha uma vez e a transmite aos processos `psql` pelo ambiente, sem gravá-la nos resultados. Também é possível usar a configuração habitual de autenticação do PostgreSQL. Todo o acesso ao banco é feito por `psql`; o Java recebe arquivos temporários e executa somente os particionadores. Assim, o orquestrador não depende de `ConfiguracaoBanco.java` ou das variáveis `DB_*`.

Para uma execução menor:

```bash
python3 pp1.py --datasets curitiba --algoritmos SEM_PARTICIONAMENTO STR \
  --aquecimentos 1 --repeticoes 2
```

Os padrões são 24 workers por Gather, 64 partições como alvo, 3 aquecimentos, 10 repetições, rodada 1 e GiST disponível. `--datasets`, `--algoritmos`, `--workers`, `--particoes`, `--aquecimentos`, `--repeticoes`, `--rodada` e `--saida` permitem selecionar a execução.

O orquestrador verifica IDs únicos, geometrias não nulas e SRIDs antes de preparar cada dataset. Assume `gid` em Curitiba e `osm_id` no Brasil; use `--id-curitiba` ou `--id-brasil` para indicar outra chave inteira única nas duas entradas do dataset. Na preparação do PP1, os IDs são preservados como `BIGINT`. O runner interativo anterior continua usando seu caminho de materialização original.

GiST válido existente nas entradas é reutilizado; se estiver ausente, o script cria um índice na coluna geométrica. As saídas `public.tabela_a_particionada`, `public.tabela_b_particionada` e suas partições são substituídas para cada algoritmo, com criação de GiST e `ANALYZE` antes da coleta. Execute uma instância por banco e não modifique as entradas durante o experimento. O usuário precisa poder criar índices nas entradas e recriar as saídas.

A preparação segue os parâmetros naturais dos algoritmos: Two-Layer usa uma grade quadrada; STR e Hilbert usam capacidade `max(1, ceil(N / alvo))`; BSP faz uma busca limitada por capacidade, retendo a grade válida mais próxima do alvo entre as tentativas. `--bsp-tentativas` controla essa busca (padrão 8). Ela é uma heurística, pois a replicação não garante monotonicidade nem atingir o alvo. As tentativas, a capacidade escolhida e a quantidade efetiva são registradas. `--hilbert-bits` tem padrão 16. N conta as geometrias não vazias das duas entradas.

Uma contagem direta de referência é calculada para cada dataset. O coletor confere o resultado de todos os aquecimentos e repetições contra essa referência e interrompe o experimento em caso de divergência. Two-Layer usa o filtro A/B/C/D; STR, Hilbert e BSP deduplicam os pares de IDs. Após as medições, uma execução adicional com `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` salva o plano. A ordem é sequencial, sem limpeza de cache.

Cada execução cria `resultados/pp1/pp1_<dataUTC>/` com:

- `consultas.csv`: todas as medições, incluindo dataset, granularidade-alvo, partições efetivas, capacidade e contagem validada.
- `configuracao.json` e `manifesto.json`: parâmetros, combinações concluídas e status de falha ou sucesso.
- Uma pasta por dataset e algoritmo com SQL, logs, medições, plano e metadados de ocupação das partições.

A exportação para arquivos e os algoritmos ainda exigem espaço temporário em disco e memória proporcional aos dados e à replicação. Se necessário, ajuste a memória do Maven/Java por `MAVEN_OPTS`. A preparação, os índices, a calibração e a captura do plano ficam fora dos tempos registrados no CSV.

### Acumular resultados de várias execuções

As pastas `pp1_<dataUTC>/` continuam sendo os resultados brutos de cada execução. O nome da pasta identifica a execução global (`pp1_run_id`); a coluna `execucao` dos CSVs continua identificando a chamada interna do coletor.

Nas novas execuções, `configuracao.json` registra automaticamente `pp1_run_id`, `hostname`, `git_commit` e `git_dirty`. O Git é consultado antes de iniciar o experimento; se estiver indisponível, o commit e o estado desconhecido ficam como `null`, sem impedir a execução. `git_dirty` indica alterações locais no código, inclusive arquivos não rastreados que não estejam ignorados.

Após um PP1 concluído, o script reconstrói automaticamente:

```text
resultados/pp1/
├── pp1_<dataUTC1>/
├── pp1_<dataUTC2>/
└── acumulado/
    ├── consultas_acumulado.csv
    └── perf_acumulado.csv
```

Também é possível reconstruir manualmente, sem acessar o banco nem executar consultas:

```bash
python3 consolidar_pp1.py
```

Se os experimentos usaram outro diretório com `pp1.py --saida`, informe esse mesmo diretório:

```bash
python3 consolidar_pp1.py --entrada /caminho/dos/resultados/pp1
```

O consolidador usa apenas a biblioteca padrão do Python e lê os CSVs da raiz de cada pasta `pp1_*` cujo manifesto global esteja como `concluido`. Ele não importa novamente os CSVs internos de `medicoes/`, não altera os brutos e não faz append nos acumulados. Repetir a consolidação produz o mesmo conteúdo enquanto as fontes não mudarem.

As repetições individuais e todas as colunas originais são preservadas, sem médias ou deduplicação de linhas de valores iguais. O perf permanece no formato longo, com uma linha por evento/PMU. Os dois acumulados acrescentam `pp1_run_id`, `hostname`, `git_commit` e `git_dirty`. Cabeçalhos diferentes são unidos e campos ausentes ficam vazios; execuções sem perf contribuem normalmente para o acumulado de consultas.

Execuções antigas sem metadados de procedência continuam elegíveis, mas hostname e Git desconhecidos ficam vazios no acumulado. Elas não são regravadas e não recebem a procedência da máquina atual. Execuções com status `falhou` ou `em_execucao` são excluídas por inteiro, mesmo que tenham medições parciais válidas.

Os CSVs são construídos em arquivos temporários dentro de `acumulado/` antes da substituição atômica de cada saída. Um lock local evita reconstruções concorrentes no Linux. Se um CSV de uma execução concluída estiver ausente ou malformado, a reconstrução informa o arquivo problemático e mantém os acumulados anteriores. Uma execução com `perf: true` também precisa ter seu `perf.csv`. Manifestos ausentes ou inválidos são ignorados com aviso.

Se não houver execuções concluídas, são criados CSVs somente com cabeçalhos e uma mensagem clara. Falhas da consolidação automática são informadas como aviso e não alteram o status concluído nem os arquivos brutos do experimento. A etapa de análise usa os acumulados; o detalhamento está no [guia dos resultados](arquivos-resultados-pp1.md#camada-acumulada-de-várias-execuções).

## Ambiente Python e análises

Os scripts de análise ficam no pacote `analises/`, com um módulo por pergunta de pesquisa. A PP1 está em `analises/pp1.py`; as análises dos próximos experimentos podem seguir o mesmo padrão (`analises/pp2.py`, `analises/pp3.py`, etc.). Os scripts de execução e coleta continuam com seus comandos atuais.

```text
requirements.txt
analises/
├── __init__.py
├── perf.py        # análise dos contadores e indicadores de perf
└── pp1.py
resultados/pp1/
├── acumulado/
├── analise/       # tabelas CSV geradas pela análise
└── figuras/       # gráficos PDF e PNG
```

Na raiz do projeto, crie e ative o ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Se `.venv` já existir, basta ativá-lo e instalar o arquivo de requisitos. As versões das dependências diretas estão fixadas conforme o ambiente validado: pandas 3.1.0 e Matplotlib 3.11.2. As dependências transitivas são resolvidas pelo pip. A pasta `.venv/` é ignorada pelo Git. A execução e a consolidação do benchmark continuam usando apenas a biblioteca padrão; essas bibliotecas são necessárias para a análise.

Depois de consolidar os resultados, gere as análises e os gráficos:

```bash
python consolidar_pp1.py
python -m analises.pp1
```

Também é possível executar diretamente `python analises/pp1.py`. Os caminhos padrão são relativos ao projeto, independentemente do diretório atual ao executar o arquivo. Para analisar uma raiz alternativa de resultados:

```bash
python -m analises.pp1 --resultados /caminho/dos/resultados/pp1
```

O módulo lê `acumulado/consultas_acumulado.csv` dessa raiz e grava `analise/resumo_tempos.csv`, `analise/speedup.csv` e três gráficos por dataset/cenário (boxplot, média com desvio padrão e speedup), cada um em PDF e PNG dentro de `figuras/`. As fórmulas e os agrupamentos dos tempos foram mantidos. A geração usa o backend Agg do Matplotlib e não precisa de interface gráfica. Importar o módulo não executa a análise; a função `analisar()` permite reutilizá-la em outros scripts.

Quando existe `acumulado/perf_acumulado.csv`, o mesmo comando também gera `analise/contadores_perf.csv`, `analise/metricas_perf.csv` e `analise/qualidade_perf.csv`. Inclui contadores médios por consulta, IPC, percentual de falhas de cache e de desvios; os gráficos ficam em `figuras/perf/<pp1_run_id>/`, em PDF e PNG. PMUs como `cpu_core` e `cpu_atom` ficam separadas, e valores indisponíveis não viram zero. Consulte [as fórmulas e os limites da análise de perf](arquivos-resultados-pp1.md#análise-dos-contadores-de-perf).

## Coletar contadores com perf

Para incluir `perf stat` nas medições, execute no mesmo servidor Linux em que o PostgreSQL está rodando:

```bash
python3 pp1.py --banco benchmark --datasets brasil --id-brasil benchmark_id --perf
```

A opção também está disponível em `coletar_consultas.py`. Sem `--perf`, a coleta continua somente com os tempos do `psql`.

Os eventos padrão são `cycles`, `instructions`, `cache-references`, `cache-misses`, `branches`, `branch-misses`, `context-switches`, `cpu-migrations` e `page-faults`. Para escolher outros eventos:

```bash
python3 pp1.py --datasets curitiba --perf --perf-eventos cycles,instructions
```

A coleta usa `perf stat -a`: cobre todas as CPUs e inclui os processos do PostgreSQL, seus workers, o cliente e qualquer outra atividade da máquina durante a janela. Medir somente o processo `psql` não cobre o trabalho do servidor. Por isso, use uma máquina com atividade controlada e mantenha o mesmo modo de instrumentação nas combinações comparadas.

Os contadores ficam desativados durante a configuração da sessão e os aquecimentos. O coletor usa `--control` e `--delay=-1` do perf para ativá-los antes das repetições e desativá-los ao final, preservando a conexão do `psql`. O intervalo inclui algum overhead do cliente e do controle. O resultado é um **total para o bloco de repetições de cada combinação**, não um contador individual por consulta. Preparação, contagem inicial de referência e captura posterior do plano ficam fora dessa janela. [Referência de perf stat](https://man7.org/linux/man-pages/man1/perf-stat.1.html).

Cada pasta de medições recebe `perf_stat.csv` (saída bruta delimitada por `;`), `perf.csv` (contadores com contexto e status), `perf.json` (eventos, versão e escopo) e `perf_sessao.psql` (comandos e pontos de controle). Quando o PP1 termina, cria também um `perf.csv` consolidado na raiz da execução. A coluna `perf` de `consultas.csv` identifica se a medição foi instrumentada. Veja [o guia dos arquivos de resultados](arquivos-resultados-pp1.md#arquivos-opcionais-do-perf) para interpretar esses registros.

O script verifica o perf antes de iniciar os joins longos. É necessário ter uma versão com `perf stat --control` e permissão para coleta em todas as CPUs. Para conferir o acesso no servidor:

```bash
perf stat -a -e cycles,instructions -- true
```

Se houver erro de acesso, a permissão de monitoramento precisa ser configurada pelo administrador; o script não usa `sudo` nem modifica `perf_event_paranoid`. Evite executar todo o PP1 como root, pois isso também muda o usuário da conexão local com PostgreSQL. A [documentação do kernel](https://www.kernel.org/doc/html/latest/admin-guide/perf-security.html) descreve o controle por capabilities e `perf_event_paranoid`.

Eventos não suportados ou não contados ficam explicitamente marcados no CSV, com valor vazio. Não são convertidos em zero. O percentual de tempo ativo ajuda a identificar multiplexação; contadores de hardware podem ser escalados pelo perf quando não ficam ativos durante toda a janela. O arquivo de verificação mede apenas um comando curto `true` e não deve ser usado na análise dos joins.

## Coletar uma combinação preparada

Depois de preparar as tabelas particionadas, execute o coletor com a consulta correspondente ao algoritmo. Exemplo para STR:

```bash
python3 coletar_consultas.py \
  --cenario ruas_quadras --algoritmo STR --sql consulta-teste.sql \
  --banco benchmark --workers 24 --indexacao on
```

Por padrão, o coletor usa o mesmo modo de conexão de `psql benchmark`: conexão local e usuário do sistema, respeitando também as variáveis `PGHOST`, `PGPORT` e `PGUSER` se estiverem configuradas. No `serra1`, executado como `pol21`, não é necessário informar host nem usuário.

No PC que exige conexão TCP como `postgres`, informe os parâmetros adicionais:

```bash
python3 coletar_consultas.py \
  --cenario ruas_quadras --algoritmo STR --sql consulta-teste.sql \
  --workers 24 --indexacao on --host localhost --usuario postgres
```

O `psql` pode solicitar a senha no terminal quando necessária. Para execuções sem interação, use a configuração habitual do PostgreSQL, como `~/.pgpass`. A opção `--porta` permite substituir a porta. Esses parâmetros são do coletor; a configuração JDBC do Java continua sendo feita por `DB_URL`, `DB_USER` e `DB_PASSWORD`.

`--workers` define `max_parallel_workers_per_gather` na mesma conexão das consultas, antes dos aquecimentos. O padrão é `24`; use `0` para desabilitar paralelismo ou outro inteiro não negativo para variar o limite. O CSV registra `workers_por_gather` e `indexacao`, e o log registra também `max_parallel_workers` e `max_worker_processes`. Esses limites do servidor podem restringir a quantidade disponível; os workers efetivamente usados devem ser conferidos com `EXPLAIN (ANALYZE, BUFFERS)`. A opção do coletor se aplica às consultas executadas pelo `psql`; ela não configura a conexão JDBC do runner Java.

Para o PP1, mantenha GiST disponível em ambas as entradas do baseline e nas duas relações particionadas. Antes de criar índices nas entradas, confira os existentes:

```sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('eixo_rua', 'arruamento_quadras', 'brasil_line', 'brasil_polygon')
ORDER BY tablename, indexname;
```

Crie apenas os índices GiST que estiverem ausentes nas colunas geométricas usadas pelo join. Com os nomes de colunas configurados no catálogo, os comandos são:

```sql
CREATE INDEX idx_pp1_eixo_rua_geom ON public.eixo_rua USING GIST (geom);
CREATE INDEX idx_pp1_arruamento_quadras_geom ON public.arruamento_quadras USING GIST (geom);
CREATE INDEX idx_pp1_brasil_line_geom ON public.brasil_line USING GIST (geom);
CREATE INDEX idx_pp1_brasil_polygon_geom ON public.brasil_polygon USING GIST (geom);
```

As saídas particionadas já recebem GiST em `geom` pelo executor Java, incluindo índices nas partições. A criação dos índices e o `ANALYZE` devem ocorrer na preparação, fora das medições. `--indexacao on` permite métodos de acesso por índice, mas não cria GiST nem obriga o plano a usá-lo. `--indexacao off` desabilita esses métodos no planejador e afeta outros índices também; não representa uma preparação física sem GiST.

O coletor aceita `--contagem-esperada N` para exigir que cada consulta retorne um COUNT escalar igual a N. O orquestrador já fornece esse valor automaticamente.

## Validar a automação

```bash
python3 -m unittest discover -s tests -v
```

O teste de integração opcional cria e remove um cluster PostgreSQL temporário em `/tmp`, com PostGIS e dados sintéticos. Ele percorre as dez combinações, incluindo contatos nas bordas, replicação, geometria EMPTY e IDs acima de 32 bits:

```bash
PP1_TEST_INTEGRACAO=1 python3 -m unittest discover -s tests -v
```

Requer os executáveis de servidor PostgreSQL e PostGIS instalados. `PG_BIN` permite informar o diretório de `initdb` e `pg_ctl` (padrão `/usr/lib/postgresql/17/bin`).

## Parâmetros

As propriedades Java (`-D...`) têm prioridade sobre as variáveis de ambiente. Se nenhuma for informada, a aplicação usa o padrão indicado:

| Propriedade Java | Variável de ambiente | Padrão | Uso |
|---|---|---|---|
| `db.url` | `DB_URL` | `jdbc:postgresql://localhost:5432/benchmark` | URL de conexão JDBC |
| `db.user` | `DB_USER` | `postgres` | Usuário do banco |
| `db.password` | `DB_PASSWORD` | `1234` | Senha do banco |
| `tabela.a` | `TABELA_A` | Tabela A do cenário | Substitui a tabela A selecionada |
| `tabela.b` | `TABELA_B` | Tabela B do cenário | Substitui a tabela B selecionada |
| `twoLayer.celulasPorEixo` | — | `10` | Células por eixo no Two-Layer |
| `str.capacidade` | — | `1000` | Capacidade do STR |
| `hilbert.capacidade` | — | `1000` | Capacidade do Hilbert |
| `hilbert.bits` | — | `16` | Precisão do Hilbert (de 1 a 16) |
| `bsp.capacidade` | — | `1000` | Capacidade do Binary Split |
| `str.debug` | — | `false` | Ativa diagnósticos e metadados de grade |

Os parâmetros de capacidade só afetam o algoritmo correspondente. Por exemplo, para alterar a capacidade do STR:

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner -Dstr.capacidade=500
```

## Modo debug

O modo debug é ativado pela propriedade `str.debug`. Ele exibe diagnósticos do STR e, nas execuções particionadas, cria e carrega a tabela `public.grade_metadados` com as fronteiras das partições.

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner -Dstr.debug=true
```

Para habilitar debug e ajustar a capacidade do STR na mesma execução:

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner \
  -Dstr.debug=true -Dstr.capacidade=500
```
