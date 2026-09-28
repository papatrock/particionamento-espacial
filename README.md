# Benchmark Espacial — Java e PostgreSQL/PostGIS

Executa joins de interseção espacial em cinco modos de benchmark: Two-Layer, STR, Hilbert Curve, Binary Split e sem particionamento. O Fixed Grid permanece como implementação histórica, fora do menu de benchmarks. Os runners selecionam os experimentos; um executor compartilhado coordena a extração, o particionamento, a carga e a consulta.


consulta.sql

```sql
SELECT COUNT(*)
FROM (
    SELECT DISTINCT a.id, b.id
    FROM public.tabela_a_particionada a
    JOIN public.tabela_b_particionada b
      ON a.id_particao = b.id_particao
     AND ST_Intersects(a.geom, b.geom)
) pares;
```

## Pré-requisitos

- Java (JDK) 17 ou superior e Maven 3.6+.
- PostgreSQL 12+ com PostGIS 3.0+.
- Dependências Maven: JTS `1.19.0` e JDBC PostgreSQL `42.7.2`.

## Preparar o banco

```sql
CREATE DATABASE tcc_espacial;
\c tcc_espacial
CREATE EXTENSION IF NOT EXISTS postgis;
```

As tabelas de entrada devem estar carregadas previamente. O catálogo `CenariosCuritiba` usa o schema `public`, ID inteiro `ogc_fid`, geometria `wkb_geometry` e SRID 31982:

| Cenário | Dataset A | Dataset B |
|---|---|---|
| Ruas x Quadras | `eixo_rua` (MultiLineString) | `arruamento_quadras` (MultiPolygon) |
| Quadras x Bairros | `arruamento_quadras` (MultiPolygon) | `divisa_de_bairros` (MultiPolygon) |
| Ruas x Bairros | `eixo_rua` (MultiLineString) | `divisa_de_bairros` (MultiPolygon) |
| Quadras x Regionais | `arruamento_quadras` (MultiPolygon) | `divisa_de_regionais` (MultiPolygon) |

Os dados de Curitiba ficam em `dados/curitiba/`. Os dumps em `dados/curitiba/despejo/` já usam esses nomes de colunas. Exemplo de importação:

```bash
psql -d tcc_espacial -f dados/curitiba/despejo/EIXO_RUA.sql
psql -d tcc_espacial -f dados/curitiba/despejo/ARRUAMENTO_QUADRAS.sql
```

Os dumps contêm comandos de remoção e recriação das respectivas tabelas. Ao importar por QGIS ou outra ferramenta, confira os nomes das colunas e o SRID.

## Configuração e execução

| Variável | Propriedade Java | Padrão |
|---|---|---|
| `DB_URL` | `db.url` | `jdbc:postgresql://localhost:5432/tcc_espacial` |
| `DB_USER` | `db.user` | `postgres` |
| `DB_PASSWORD` | `db.password` | `1234` |
| `TABELA_A` | `tabela.a` | Tabela A do cenário escolhido |
| `TABELA_B` | `tabela.b` | Tabela B do cenário escolhido |
| — | `twoLayer.celulasPorEixo` | `10` |
| — | `str.capacidade` | `1000` |
| — | `hilbert.capacidade` | `1000` |
| — | `hilbert.bits` | `16` (1 a 16) |
| — | `bsp.capacidade` | `1000` |
| — | `str.debug` | `false` |

Propriedades `-D` têm prioridade sobre variáveis de ambiente. As substituições de tabela preservam schema, colunas, tipo e SRID do cenário. Para alterar esses atributos, configure um `DatasetEspacial` em um catálogo ou runner próprio.

```bash
mvn compile exec:java -Dexec.mainClass="benchmark.CenarioTesteRunner"
```

Exemplo com outro banco e tabelas compatíveis com o cenário selecionado:

```bash
mvn compile exec:java -Dexec.mainClass="benchmark.CenarioTesteRunner" \
  -Ddb.url=jdbc:postgresql://localhost:5432/meu_banco \
  -Dtabela.a=minhas_ruas -Dtabela.b=minhas_quadras \
  -DtwoLayer.celulasPorEixo=10
```

Primeiro escolha o cenário; depois, o modo:

```text
1 - Sem particionamento
2 - Two-Layer SOP
3 - STR DOP
4 - Hilbert Curve DOP
5 - Binary Split SOP
```

O programa exibe cenário, modo, número de partições, interseções encontradas e tempo do join. Entradas inválidas no menu pedem uma nova seleção.

`Main` é um atalho para o mesmo menu, mantido para funcionar com configurações antigas da IDE. Ele não possui mais um pipeline próprio. Use `TABELA_A`/`TABELA_B` em lugar das antigas opções `TABELA_QUADRAS`/`TABELA_RUAS`.

### Modo debug

Para ativar as mensagens de diagnóstico do STR e a criação e carga da tabela `public.grade_metadados`, execute:

```bash
mvn compile exec:java -Dexec.mainClass="benchmark.CenarioTesteRunner" -Dstr.debug=true
```

Na IDE, adicione `-Dstr.debug=true` às opções da JVM (VM options). O botão Debug da IDE, sozinho, não ativa essa propriedade. Não é necessário recompilar para alternar o modo; reinicie a execução com o valor desejado.

Por padrão (`str.debug=false` ou propriedade ausente), os detalhes de N, capacidade, partições e faixas do STR não são impressos, e a tabela de metadados não é criada nem carregada. A propriedade também controla essa tabela nos modos Fixed Grid e Two-Layer. As fronteiras em memória continuam sendo calculadas para o particionamento.

Em toda execução particionada, uma `grade_metadados` anterior é removida na transação de substituição das saídas, mesmo com debug desativado, para evitar a visualização de fronteiras antigas. O modo sem particionamento não altera essa tabela.

## Fluxo e resultados no banco

Nas opções 2, 3, 4 e 5, o executor extrai as duas entradas, aplica o particionador e substitui as saídas em uma transação, com rollback se a carga falhar. Todos os runners que usam esse executor escrevem nas mesmas tabelas do schema `public`:

- `tabela_a_particionada` e `tabela_b_particionada`: tabelas-mãe com `id`, `id_particao`, `classe` e `geom`.
- `tabela_a_p1…pN` e `tabela_b_p1…pN`: partições filhas.
- `grade_metadados`: ID e geometria de cada célula, criada e carregada somente com `-Dstr.debug=true`.

**Uma execução particionada substitui a anterior**, inclusive as partições filhas, usando `DROP TABLE ... CASCADE`. Não há histórico automático nem suporte a execuções concorrentes sobre essas mesmas saídas. O Two-Layer com 10 células por eixo cria 100 partições por tabela; o Fixed Grid cria quatro.

Na opção 1, o join roda diretamente nas entradas, usando seus índices existentes. Não há extração para Java, carga ou alteração das tabelas de saída. `Partições` aparece como “não se aplica”.

As tabelas antigas `quadras_particionadas`, `ruas_particionadas` e suas filhas, produzidas pela versão anterior do `Main`, não são mais usadas nem removidas automaticamente. No QGIS, use as saídas compartilhadas acima; camadas já adicionadas ao projeto não são removidas por um refresh do mapa.

### Consulta das saídas Two-Layer

```sql
SET enable_partitionwise_join = on;
SELECT a.id AS id_a, b.id AS id_b
FROM public.tabela_a_particionada a
JOIN public.tabela_b_particionada b
  ON a.id_particao = b.id_particao
 AND (a.classe = 'A' OR b.classe = 'A'
      OR (a.classe = 'B' AND b.classe = 'C')
      OR (a.classe = 'C' AND b.classe = 'B'))
 AND ST_Intersects(a.geom, b.geom);
```

Para consultar pares do STR, Hilbert, BSP ou Fixed Grid legado, use `SELECT DISTINCT a.id, b.id` com igualdade de `id_particao` e `ST_Intersects(a.geom, b.geom)`, sem o filtro de classes.

### Medição

O tempo é medido com `System.nanoTime()` e inclui a consulta e a leitura de sua contagem. Extração, particionamento, DDL, carga e `ANALYZE` ficam fora dessa medição. A contagem usa `long`.

É uma medição por execução, sem aquecimento ou repetições automáticas. Compare também os pares encontrados, os índices disponíveis e o estado do cache antes de tirar conclusões sobre desempenho. O Fixed Grid usa uma grade 2 × 2 comum às entradas e replica cada geometria nas células tocadas por seu MBR, incluindo bordas. O join usa `DISTINCT` sobre o par de IDs originais para evitar contagem duplicada; essa deduplicação está incluída no tempo medido. Os IDs de cada entrada devem ser únicos e não nulos. Diferentemente do Two-Layer, o Fixed Grid não usa classes A/B/C/D para eliminar duplicações; a coluna `classe` recebe A apenas por compatibilidade com a estrutura de saída.

## Organização do código

```text
src/main/java/benchmark/
├── CenarioTesteRunner.java          # Menu e apresentação do resultado
├── BenchmarkRunner.java             # Atalho para o mesmo menu
├── CenarioTeste.java                # Nome e dois datasets, sem SQL
├── configuracao/
│   ├── ConfiguracaoBanco.java        # Conexão, propriedades e ambiente
│   └── DatasetEspacial.java         # Schema, tabela, colunas, tipo e SRID
├── cenarios/
│   └── CenariosCuritiba.java         # Catálogo reutilizável
├── execucao/
│   ├── ExecutorBenchmark.java        # Pipeline compartilhado
│   └── EstrategiaExecucao.java       # Fixed Grid, Two-Layer, STR ou direto
├── banco/
│   └── RepositorioEspacial.java      # Extração, DDL, carga, joins e medição
├── resultados/
│   └── ResultadoBenchmark.java      # Resultado retornado ao runner
├── algoritmos/
│   ├── FixedGridPartitioner.java
│   ├── TwoLayerPartitioner.java
│   └── SortTileRecursive.java
├── SpatialPartitioner.java
├── ClasseTwoLayer.java
├── ParticaoMetadata.java
├── ParticaoResult.java
└── ResultadoParticionamento.java
```

Os modelos e interfaces de particionamento permanecem no pacote `benchmark`. Os testes do STR usam JUnit 5; execute `mvn test`.

## Criar um cenário ou runner

Para uma combinação nova de tabelas na interface atual, acrescente um `CenarioTeste` a `CenariosCuritiba.listar()`. Para outra base, crie um catálogo com seus `DatasetEspacial`. Schema e tabela são campos separados; não coloque `schema.tabela` no campo `tabela`.

Um runner próprio deve configurar o experimento e chamar o executor. Exemplo em `src/main/java/benchmark/runners/MeuExperimentoRunner.java`:

```java
package benchmark.runners;

import benchmark.CenarioTeste;
import benchmark.configuracao.ConfiguracaoBanco;
import benchmark.configuracao.DatasetEspacial;
import benchmark.execucao.EstrategiaExecucao;
import benchmark.execucao.ExecutorBenchmark;

public class MeuExperimentoRunner {
    public static void main(String[] args) throws Exception {
        var ruas = new DatasetEspacial(
                "public", "eixo_rua", "ogc_fid", "wkb_geometry", "MultiLineString", 31982);
        var quadras = new DatasetEspacial(
                "public", "arruamento_quadras", "ogc_fid", "wkb_geometry", "MultiPolygon", 31982);
        var cenario = new CenarioTeste("Comparação de estratégias", ruas, quadras);
        var executor = new ExecutorBenchmark(ConfiguracaoBanco.doAmbiente());

        for (var estrategia : EstrategiaExecucao.values()) {
            var resultado = executor.executar(cenario, estrategia, 10);
            System.out.printf("%s: %d pares, %.3f ms%n",
                    resultado.estrategia(), resultado.intersecoes(), resultado.tempoJoinMs());
        }
    }
}
```

```bash
mvn compile exec:java -Dexec.mainClass="benchmark.runners.MeuExperimentoRunner"
```

O exemplo é um modelo para criar o arquivo, não uma classe já incluída. Um experimento de resolução pode repetir `executar` com `TWO_LAYER` e diferentes valores do terceiro argumento. O executor abre e fecha uma conexão por execução e retorna dados que o runner pode apresentar ou exportar.

`DatasetEspacial` aceita saídas `MultiPoint`, `MultiLineString`, `MultiPolygon` e `Geometry`, com IDs inteiros e geometrias 2D. Os dois datasets devem usar o mesmo SRID. Na extração para particionamento, um SRID diferente do configurado é rejeitado; não há reprojeção automática. O pipeline atual executa `ST_Intersects`; uma operação espacial diferente deve ser implementada no executor/repositório e selecionada pelo novo runner.

## Two-Layer: implementação e fidelidade

A referência é [Two-layer Space-oriented Partitioning for Non-point Data](https://github.com/dTsitsigkos/two-layer), de Tsitsigkos et al. ([TKDE, 2024](https://doi.org/10.1109/TKDE.2023.3297975)). A implementação Java adapta a distribuição de `partition.h` e as nove combinações de classes do join de `two_layer.h`.

1. **Primeira camada:** grade uniforme comum às duas entradas. Cada MBR é replicado nas células cobertas; a geometria completa é preservada em cada cópia.
2. **Segunda camada:** cada cópia recebe uma classe relativa à célula inicial do MBR: **A** na célula inicial; **B** na mesma coluna, acima; **C** na mesma linha, à direita; **D** acima e à direita.
3. **Join:** por célula, são permitidas apenas `A–A`, `A–B`, `A–C`, `A–D`, `B–A`, `B–C`, `C–A`, `C–B` e `D–A`. A regra evita pares duplicados entre células. Não se deve juntar as cópias usando apenas igualdade de `id_particao`.

As quatro classes existem em **cada célula**; não são quatro partições finais. As tabelas de saída agora incluem `classe CHAR(1)`. As cópias mantêm o mesmo ID de origem; portanto, `COUNT(*)` da tabela particionada mede cópias, não objetos originais.

### Adaptação ao PostGIS

O particionamento e a seleção dos pares de classes seguem o método original. O executor C++ com plane sweep e suas otimizações de memória/comparações não foram portados: a execução fica com o PostgreSQL, e `ST_Intersects` refina os candidatos usando as geometrias completas. O original opera sobre MBRs; tempos e contagens de MBRs não devem ser comparados diretamente aos resultados exatos do PostGIS.

A grade tem domínio quadrado baseado no maior eixo do envelope conjunto, equivalente à normalização espacial da referência, mas conserva as coordenadas no SRID original. Fronteiras internas pertencem à célula à direita/acima, inclusive para o extremo final do MBR; o extremo global pertence à última célula. A implementação usa os mesmos limites de grade para classificar os dois extremos, sem o `EPS` numérico do C++. Casos extremamente próximos de fronteiras podem ter atribuições diferentes das do C++.

Geometrias `EMPTY` não geram cópias porque não participam do join de interseção. Duas entradas vazias geram zero células. Pontos coincidentes recebem domínio de lado 1; conjuntos alinhados em um eixo usam a extensão do outro. WKT nulo, coordenadas XY não finitas, resolução não representável e geometrias fora de um molde fornecido são rejeitados. As entradas devem usar geometrias 2D válidas no SRID configurado nos datasets; os cenários de Curitiba usam **31982**.

A recriação e a carga ocorrem na mesma transação. Após a carga, os runners executam `ANALYZE`. O Fixed Grid mantém sua grade 2 × 2 e usa deduplicação por pares de IDs, sem a segunda camada do Two-Layer.


## STR: implementação e uso

O `SortTileRecursive` implementa **Data-Oriented Partitioning (DOP)** com base em [Leutenegger, Edgington e Lopez (1997)](https://doi.org/10.1109/ICDE.1997.582015) e na adaptação para particionamento espacial de [Aji, Vo e Wang, seção 4.2](https://arxiv.org/abs/1509.00910).

Para `N` geometrias não vazias e capacidade `b > 0`, calcula `P = ceil(N/b)` e `S = ceil(sqrt(P))`. Ordena pelo centro do MBR no eixo X, forma faixas de até `S*b` objetos, ordena cada faixa pelo centro do MBR em Y e agrupa em blocos de até `b`. Cada fronteira é o MBR completo do grupo. A última faixa e o último grupo podem ser incompletos. São geradas exatamente `P` partições, com IDs a partir de 1. A construção custa `O(N log N)` e usa `O(N)` memória.

A implementação para no nível folha: a recursão para criar os níveis superiores da R-tree não faz parte deste particionador. As fronteiras podem se sobrepor ou deixar lacunas. Pontos coincidentes e objetos alinhados podem gerar fronteiras pontuais ou lineares; `grade_metadados.geom` aceita esses tipos, além de polígonos.

No benchmark, o molde é construído sobre **A e B juntas**, considerando todos os objetos não vazios. Depois, cada entrada é associada a todos os MBRs que seu envelope intersecta, incluindo contatos nas bordas. Essa associação usa um índice espacial JTS e preserva o WKT e o índice de origem. O join usa `DISTINCT` nos pares de IDs, como no Fixed Grid. A coluna `classe` recebe A por compatibilidade com o modelo existente.

**`b` limita os grupos de construção, antes da replicação**; a ocupação final pode ultrapassá-lo. `N` considera as duas relações juntas, e a capacidade não representa um limite separado para cada tabela. O padrão 1000 é configurável, não um valor recomendado pelos artigos.

```bash
mvn compile exec:java -Dstr.capacidade=500
```

Escolha a opção `3 - STR DOP`. Para uso direto:

```java
var str = new SortTileRecursive(500);
var molde = str.criarGrade(wktsA, wktsB);
var resA = str.processar(wktsA, molde);
var resB = str.processar(wktsB, molde);
```

Para apenas uma entrada, use `str.processar(wkts)`. No executor programático, `executar(cenario, EstrategiaExecucao.STR, 10, 500)` define a capacidade no quarto argumento; o terceiro continua reservado ao Two-Layer. A chamada com três argumentos usa a capacidade padrão.

Geometrias `EMPTY` não participam; entradas sem objetos geram molde vazio. WKT nulo, XY não finito, capacidade inválida, fronteiras que não sejam MBRs e IDs de partição não positivos ou repetidos são rejeitados. Um objeto sem interseção com nenhuma fronteira também é rejeitado. Essa validação não comprova cobertura completa de um molde externo: para preservar o join, gere o molde com ambas as entradas completas, como faz o executor. Não se amplia automaticamente um molde amostrado.

Os testes cobrem ordenação, MBR completo, última faixa incompleta, pontos e linhas, replicação nas bordas, entradas inválidas e equivalência dos pares de um join direto com os de um join particionado em dados sintéticos usando JTS. A validação do pipeline SQL com PostGIS deve ser feita no ambiente do benchmark.


## Hilbert Curve: implementação e uso

`HilbertCurvePartitioner` implementa HC da seção 4.2 de [Aji, Vo e Wang](https://arxiv.org/abs/1509.00910).
Calcula o **centroide geométrico JTS** de cada objeto, ordena pelo índice Hilbert,
agrupa objetos consecutivos em blocos de até `b` e usa o MBR completo de cada grupo
como fronteira. Não constrói os níveis de uma Hilbert R-tree.

Escolhas de implementação explicitadas para reprodução dos experimentos:

- O molde é construído sobre **A e B completas**, como no STR; `N` soma seus objetos não vazios.
- O domínio é o envelope conjunto das geometrias. Cada eixo é normalizado separadamente
  para `[0, 2^bits - 1]`, com arredondamento para baixo; eixo degenerado recebe zero.
  A normalização serve apenas à ordenação: geometrias e fronteiras conservam as coordenadas originais.
- Usa `HilbertCode.encode` do JTS 1.19.0. `bits` varia de 1 a 16, com padrão 16.
  O índice de 32 bits é convertido em `long` sem sinal antes da ordenação.
  Precisão, normalização e desempate são escolhas desta implementação, não parâmetros prescritos no artigo.
- Empates são resolvidos por centroide X/Y e extremos do MBR (minX, minY, maxX, maxY).
  Objetos ainda empatados têm o mesmo MBR e são intercambiáveis na construção das regiões.
- São criadas `ceil(N/b)` regiões, IDs a partir de 1, podendo a última conter menos de `b` objetos.
  MBRs podem se sobrepor ou ser pontos/linhas. Não se acrescenta área artificial.
- Na associação final, cada geometria é replicada em todos os MBRs intersectados por seu envelope,
  incluindo bordas. `ParticionamentoPorMbr` compartilha essa etapa com STR; seu índice JTS
  apenas acelera a busca, não define o particionamento Hilbert.
- O join usa igualdade de partição, `ST_Intersects` e `DISTINCT` sobre os pares de IDs originais.
  A coluna `classe` recebe A por compatibilidade. **`b` limita o grupo inicial, não a ocupação após replicação.**
- Geometrias vazias são ignoradas; WKT nulo, XY não finito, centroide não finito,
  capacidade/precisão inválidas e moldes inválidos são rejeitados. As entradas devem ser geometrias 2D válidas.
  A validação de um molde externo verifica destinos existentes, mas não comprova cobertura integral;
  use o molde construído com ambas as entradas completas para preservar o join.

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner \
  -Dhilbert.capacidade=500 -Dhilbert.bits=16
```

Escolha o cenário e depois `4 - Hilbert Curve DOP`. As tabelas de saída são as mesmas
usadas pelas outras estratégias; uma execução substitui as saídas anteriores.
A propriedade legada `str.debug=true` também habilita a tabela de fronteiras para Hilbert.

Uso direto:

```java
var hc = new HilbertCurvePartitioner(500, 16);
var molde = hc.criarGrade(wktsA, wktsB);
var resA = hc.processar(wktsA, molde);
var resB = hc.processar(wktsB, molde);
```

No executor: `executar(cenario, EstrategiaExecucao.HILBERT, 10, 1000, 500, 16)`.
Os argumentos são cenário, estratégia, células por eixo Two-Layer, capacidade STR,
capacidade Hilbert e bits Hilbert. As sobrecargas antigas continuam válidas e usam os padrões de Hilbert.

A formação das regiões requer ordenação `O(N log N)` e memória `O(N)`, além do custo
para ler as coordenadas e calcular os centroides. A associação final depende das sobreposições
entre MBRs e da quantidade de cópias; seu custo não fica limitado pela capacidade `b`.

Execute `mvn test` para verificar ordem Hilbert conhecida (incluindo índices sem sinal),
centroide versus centro do MBR, grupos incompletos, desempates, entradas degeneradas,
replicação nas bordas, validações e equivalência dos pares com um join direto em dados sintéticos JTS.
Os testes também verificam essa equivalência para STR, cuja associação por MBR é compartilhada.
A validação do pipeline SQL com PostgreSQL/PostGIS exige o ambiente de banco do benchmark.


## Binary Split: referência e uso

`BinarySplitPartitioner` implementa a variante BSP de Aji, Vo e Wang (2015), seção 4.2,
Algoritmo 3: inserção incremental de MBRs, dois cortes candidatos pelas medianas de seus
centros e escolha do maior produto das áreas dos filhos. Regiões não se sobrepõem
interiormente; objetos que cruzam fronteiras são replicados, e o join deduplica pares.

**O pseudocódigo da fonte contém ambiguidades.** A implementação usa `> b` conforme o
texto (o algoritmo imprime `<= c`), uma raiz persistente e redistribuição dos objetos
anteriores. Todas as evidências, decisões e possíveis divergências estão no
[relatório de fidelidade BSP](docs/bsp-referencia.md).

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner -Dbsp.capacidade=1000
```

Escolha **5 — Binary Split SOP**. Usa molde A+B; o executor lê A por ID crescente e
então B por ID crescente para reproduzir a ordem incremental. IDs devem ser únicos
em cada relação. Não há amostragem. Uma construção bem-sucedida respeita a capacidade
por folha contando MBRs replicados; não existe número fixo de partições.
Se as medianas não permitirem novas divisões para satisfazer b, a execução falha com
diagnóstico antes de substituir as saídas, sem gerar cortes alternativos ou folhas
excedentes silenciosamente. Ordem, capacidade e política de falha fazem parte do protocolo experimental.

Validação: `mvn test`. Para incluir o teste real de pares no PostGIS:
`BSP_TEST_POSTGIS=true mvn test`, usando a configuração de conexão do projeto.
Esse teste usa somente tabelas temporárias, compara `EXCEPT` nos dois sentidos e faz rollback.
