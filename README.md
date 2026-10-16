## Requisitos

- JDK 17 ou superior
- Maven 3.6 ou superior
- PostgreSQL com PostGIS
- Banco criado, extensão PostGIS habilitada e tabelas de entrada carregadas

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
