# Benchmark Espacial — Particionador Dinâmico para PostgreSQL/PostGIS

Middleware em Java que lê dados espaciais (quadras e ruas) do PostgreSQL/PostGIS, executa algoritmos de particionamento espacial na memória e transfere os resultados de volta ao banco, criando toda a estrutura de tabelas particionadas dinamicamente.

O objetivo final é realizar um **Spatial Join massivo** delegando o cruzamento ao motor relacional, tirando proveito da otimização de **Partition-wise Join** nativa do PostgreSQL.

---

## Pré-requisitos

| Componente | Versão mínima |
|---|---|
| **Java (JDK)** | 17 |
| **Apache Maven** | 3.6+ |
| **PostgreSQL** | 12+ (recomendado 15+) |
| **PostGIS** | 3.0+ |

### Dependências (gerenciadas pelo Maven)

- `org.locationtech.jts:jts-core:1.19.0` — Biblioteca de geometria JTS
- `org.postgresql:postgresql:42.7.2` — Driver JDBC do PostgreSQL

---

## Configuração do Banco de Dados

### 1. Criar o banco, habilitar PostGIS e configurar Partition-wise Join

```sql
CREATE DATABASE tcc_espacial;
\c tcc_espacial
CREATE EXTENSION IF NOT EXISTS postgis;
SET enable_partitionwise_join = on;
```

> **Dica:** Para tornar o `enable_partitionwise_join` permanente no banco, execute:
> ```sql
> ALTER DATABASE tcc_espacial SET enable_partitionwise_join = on;
> ```

### 2. Tabelas de dados de entrada (obrigatórias)

O programa espera que as seguintes tabelas já existam no banco com os dados carregados:

#### `arruamento_quadras`
Contém as geometrias das quadras urbanas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ogc_fid` | INTEGER | Identificador único |
| `wkb_geometry` | geometry (MultiPolygon, 31982) | Geometria da quadra |

#### `eixo_rua`
Contém as geometrias dos eixos de rua.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ogc_fid` | INTEGER | Identificador único |
| `wkb_geometry` | geometry (MultiLineString, 31982) | Geometria da rua |

> **Dica:** Os shapefiles estão disponíveis na pasta `dados/`. Para importá-los, use o `shp2pgsql` ou o QGIS:
> ```bash
> shp2pgsql -s 31982 dados/ARRUAMENTO_QUADRAS_SIRGAS/ARRUAMENTO_QUADRAS.shp arruamento_quadras | psql -d tcc_espacial
> shp2pgsql -s 31982 dados/EIXO_RUA_SIRGAS/EIXO_RUA.shp eixo_rua | psql -d tcc_espacial
> ```

### 3. Tabelas de saída (criadas automaticamente)

As seguintes tabelas são **criadas dinamicamente** pelo programa a cada execução (não é necessário criá-las manualmente):

- **`quadras_particionadas`** — Tabela-mãe particionada por `LIST (id_particao)` com geometria `MultiPolygon`.
- **`ruas_particionadas`** — Tabela-mãe particionada por `LIST (id_particao)` com geometria `MultiLineString`.
- **`grade_metadados`** — Tabela simples com a geometria de cada célula da grade de particionamento.
- **`quadras_p1`, `quadras_p2`, ..., `quadras_pN`** — Partições filhas das quadras.
- **`ruas_p1`, `ruas_p2`, ..., `ruas_pN`** — Partições filhas das ruas.

**Atenção:** A cada execução, essas tabelas são **removidas e recriadas** (`DROP CASCADE`). Qualquer dado anterior será perdido.

---

dados Brasil: https://download.geofabrik.de/south-america.html

## Configuração da Conexão

A configuração é feita via **variáveis de ambiente** ou **propriedades do sistema** (`-D`), com valores padrão embutidos:

| Variável de Ambiente | Propriedade `-D` | Padrão | Descrição |
|---|---|---|---|
| `DB_URL` | `db.url` | `jdbc:postgresql://localhost:5432/tcc_espacial` | URL de conexão JDBC |
| `DB_USER` | `db.user` | `postgres` | Usuário do banco |
| `DB_PASSWORD` | `db.password` | `1234` | Senha do banco |
| `TABELA_QUADRAS` | `tabela.quadras` | `arruamento_quadras` | Tabela de quadras (BenchmarkRunner) |
| `TABELA_RUAS` | `tabela.ruas` | `eixo_rua` | Tabela de ruas (BenchmarkRunner) |
| `TABELA_A` | `tabela.a` | *(do cenário)* | Tabela A (CenarioTesteRunner) |
| `TABELA_B` | `tabela.b` | *(do cenário)* | Tabela B (CenarioTesteRunner) |

Propriedades `-D` têm prioridade sobre variáveis de ambiente.

---

## Como Compilar e Executar

### Compilar

```bash
mvn clean compile
```

### Executar

```bash
mvn exec:java -Dexec.mainClass="benchmark.BenchmarkRunner"
```

Para customizar tabelas ou banco via propriedades:

```bash
mvn exec:java -Dexec.mainClass="benchmark.BenchmarkRunner" \
  -Dtabela.quadras=ARRUAMENTO_QUADRAS \
  -Dtabela.ruas=EIXO_RUA \
  -Ddb.url=jdbc:postgresql://localhost:5432/meu_banco
```

Ou via variáveis de ambiente:

```bash
export TABELA_QUADRAS=ARRUAMENTO_QUADRAS
export TABELA_RUAS=EIXO_RUA
mvn exec:java -Dexec.mainClass="benchmark.BenchmarkRunner"
```

---

## Uso

Ao executar o programa, o seguinte fluxo acontece:

### 1. Configuração
O programa exibe as tabelas e banco configurados (via variáveis de ambiente ou `-D`):

```
=== CONFIGURAÇÃO ===
Tabela de quadras: arruamento_quadras
Tabela de ruas: eixo_rua
Banco: jdbc:postgresql://localhost:5432/tcc_espacial
```

### 2. Extração de dados
O programa conecta ao PostgreSQL e lê todas as geometrias das tabelas configuradas.

### 3. Seleção do algoritmo
Um menu interativo é exibido no console:

```
Selecione o algoritmo de particionamento:
1 - Fixed Grid
2 - Two-Layer SOP
Opção: _
```

| Opção | Algoritmo | Descrição |
|---|---|---|
| **1** | Fixed Grid | Divide o espaço em uma grade regular fixa |
| **2** | Two-Layer SOP | Particionamento em duas camadas (Strip-based Optimal Partitioning) |
| Outro | Fixed Grid (padrão) | Qualquer valor diferente usa Fixed Grid como fallback |

### 4. Particionamento
O algoritmo escolhido processa as geometrias na memória e determina automaticamente o número ideal de partições (N).

### 5. Setup dinâmico do banco
O programa recria toda a estrutura DDL no PostgreSQL:
- Remove tabelas anteriores (`DROP CASCADE`)
- Cria as tabelas-mãe com `PARTITION BY LIST`
- Cria N partições filhas (`quadras_p1..pN`, `ruas_p1..pN`)
- Cria índices espaciais GiST

### 6. Inserção dos dados
Os dados particionados são inseridos nas tabelas correspondentes via batch INSERT.

### 7. Conclusão
Ao final, o banco está pronto para executar o Spatial Join com Partition-wise Join:

```sql
-- Exemplo de Spatial Join particionado
SET enable_partitionwise_join = on;

SELECT q.id AS id_quadra, r.id AS id_rua
FROM quadras_particionadas q
JOIN ruas_particionadas r
  ON q.id_particao = r.id_particao
 AND ST_Intersects(q.geom, r.geom);
```

---

## Cenários de Teste

O projeto inclui um runner separado (`CenarioTesteRunner`) que permite executar cenários de teste pré-definidos com diferentes combinações de tabelas espaciais.

### Executar

```bash
mvn exec:java -Dexec.mainClass="benchmark.CenarioTesteRunner"
```

### Cenários disponíveis

| # | Cenário | Tabela A | Tabela B |
|---|---|---|---|
| 1 | Ruas x Quadras | `eixo_rua` | `arruamento_quadras` |
| 2 | Quadras x Bairros | `arruamento_quadras` | `divisa_de_bairros` |
| 3 | Ruas x Bairros | `eixo_rua` | `divisa_de_bairros` |
| 4 | Quadras x Regionais | `arruamento_quadras` | `divisa_de_regionais` |

> Para adicionar novos cenários, basta criar uma nova instância de `CenarioTeste` no método `criarCenarios()` de `CenarioTesteRunner.java`.

### Fluxo do cenário

1. Seleciona o cenário via menu interativo
2. Aplica customização das tabelas (se definidas via `TABELA_A`/`TABELA_B` ou `-Dtabela.a`/`-Dtabela.b`)
3. Seleciona o algoritmo de particionamento
4. Extrai os dados das duas tabelas do cenário
5. Executa o particionamento espacial
6. Cria tabelas particionadas genéricas (`tabela_a_particionada`, `tabela_b_particionada`)
7. Insere os dados e executa o Spatial Join automaticamente
8. Exibe o resultado: número de interseções e tempo de execução

> ⚠️ As tabelas `tabela_a_particionada` e `tabela_b_particionada` são recriadas a cada execução do cenário.

---

## Estrutura do Projeto

```
src/main/java/benchmark/
├── BenchmarkRunner.java            # Classe principal (pipeline completo)
├── CenarioTeste.java               # Modelo de cenário de teste
├── CenarioTesteRunner.java         # Runner dos cenários de teste
├── ParticaoMetadata.java           # Metadados de cada célula da grade
├── ParticaoResult.java             # Resultado do particionamento por geometria
├── ResultadoParticionamento.java   # Agregador de resultados
├── SpatialPartitioner.java         # Interface dos algoritmos
└── algoritmos/
    ├── FixedGridPartitioner.java   # Algoritmo Fixed Grid
    └── TwoLayerPartitioner.java    # Algoritmo Two-Layer SOP
```

---

## Licença

Projeto acadêmico (TCC) — UFPR.
