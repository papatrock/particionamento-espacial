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

## Parâmetros

As propriedades Java (`-D...`) têm prioridade sobre as variáveis de ambiente. Se nenhuma for informada, a aplicação usa o padrão indicado:

| Propriedade Java | Variável de ambiente | Padrão | Uso |
|---|---|---|---|
| `db.url` | `DB_URL` | `jdbc:postgresql://localhost:5432/tcc_espacial` | URL de conexão JDBC |
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
