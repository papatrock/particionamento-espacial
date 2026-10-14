# Benchmark Espacial

Aplicação Java para executar benchmarks de joins espaciais usando PostgreSQL/PostGIS.

## Requisitos

- JDK 17 ou superior
- Maven 3.6 ou superior
- PostgreSQL com PostGIS
- Banco criado, extensão PostGIS habilitada e tabelas de entrada carregadas

O Maven baixa as dependências Java na primeira execução.

## Preparar o banco

Crie o banco e habilite o PostGIS:

```sql
CREATE DATABASE tcc_espacial;
```

Conectado ao banco:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Carregue no schema `public` as tabelas de entrada do cenário desejado. Para os cenários de Curitiba: `eixo_rua`, `arruamento_quadras`, `divisa_de_bairros` e `divisa_de_regionais`. Para os cenários do Brasil: `brasil_line`, `brasil_point` e `brasil_polygon`.

## Executar

Na raiz do projeto, configure a conexão com o banco:

```bash
export DB_URL='jdbc:postgresql://localhost:5432/tcc_espacial'
export DB_USER='postgres'
export DB_PASSWORD='sua_senha'
```

Compile e inicie o programa:

```bash
mvn compile exec:java -Dexec.mainClass=benchmark.CenarioTesteRunner
```

Selecione o cenário e o algoritmo nos menus apresentados. Ao final, o programa mostra o resultado do join e seu tempo de execução.

As variáveis de conexão são opcionais se os valores padrão (`localhost:5432/tcc_espacial`, usuário `postgres` e senha `1234`) forem adequados. Também podem ser configuradas como propriedades Java: `-Ddb.url=...`, `-Ddb.user=...` e `-Ddb.password=...`.
