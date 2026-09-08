r# Benchmark Espacial — Java e PostgreSQL/PostGIS

Executa joins de interseção espacial em três modos: Fixed Grid, Two-Layer e sem particionamento. Os runners selecionam os experimentos; um executor compartilhado coordena a extração, o particionamento, a carga e a consulta.

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
1 - Fixed Grid
2 - Two-Layer SOP
3 - Sem particionamento
```

O programa exibe cenário, modo, número de partições, interseções encontradas e tempo do join. Entradas inválidas no menu pedem uma nova seleção.

`Main` é um atalho para o mesmo menu, mantido para funcionar com configurações antigas da IDE. Ele não possui mais um pipeline próprio. Use `TABELA_A`/`TABELA_B` em lugar das antigas opções `TABELA_QUADRAS`/`TABELA_RUAS`.

## Fluxo e resultados no banco

Nas opções 1 e 2, o executor extrai as duas entradas, aplica o particionador e substitui as saídas em uma transação, com rollback se a carga falhar. Todos os runners que usam esse executor escrevem nas mesmas tabelas do schema `public`:

- `tabela_a_particionada` e `tabela_b_particionada`: tabelas-mãe com `id`, `id_particao`, `classe` e `geom`.
- `tabela_a_p1…pN` e `tabela_b_p1…pN`: partições filhas.
- `grade_metadados`: ID e geometria de cada célula.

**Uma execução particionada substitui a anterior**, inclusive as partições filhas, usando `DROP TABLE ... CASCADE`. Não há histórico automático nem suporte a execuções concorrentes sobre essas mesmas saídas. O Two-Layer com 10 células por eixo cria 100 partições por tabela; o Fixed Grid cria quatro.

Na opção 3, o join roda diretamente nas entradas, usando seus índices existentes. Não há extração para Java, carga ou alteração das tabelas de saída. `Partições` aparece como “não se aplica”.

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

Para consultar pares do Fixed Grid, use `SELECT DISTINCT a.id, b.id` com igualdade de `id_particao` e `ST_Intersects(a.geom, b.geom)`, sem o filtro de classes.

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
│   └── EstrategiaExecucao.java       # Fixed Grid, Two-Layer ou direto
├── banco/
│   └── RepositorioEspacial.java      # Extração, DDL, carga, joins e medição
├── resultados/
│   └── ResultadoBenchmark.java      # Resultado retornado ao runner
├── algoritmos/
│   ├── FixedGridPartitioner.java
│   └── TwoLayerPartitioner.java
├── SpatialPartitioner.java
├── ClasseTwoLayer.java
├── ParticaoMetadata.java
├── ParticaoResult.java
└── ResultadoParticionamento.java
```

Os modelos e interfaces de particionamento permanecem no pacote `benchmark`. Não há dependências nem arquivos de testes automatizados.

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


## Contexto acadêmico

Projeto de TCC — UFPR.
