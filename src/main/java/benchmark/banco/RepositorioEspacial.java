package benchmark.banco;

import benchmark.*;
import benchmark.algoritmos.TwoLayerPartitioner;
import benchmark.configuracao.DatasetEspacial;
import benchmark.execucao.EstrategiaExecucao;
import java.sql.*;
import java.util.ArrayList;
import java.util.List;

/** Todo o SQL do pipeline. A conexão e sua duração pertencem ao executor. */
public final class RepositorioEspacial {
    private static final String SAIDA_A = "public.tabela_a_particionada";
    private static final String SAIDA_B = "public.tabela_b_particionada";
    private static final String GRADE = "public.grade_metadados";
    private final Connection conn;

    public RepositorioEspacial(Connection conn) { this.conn = conn; }

    public record DadosEspaciais(List<Integer> ids, List<String> wkts) { }
    public record MedicaoJoin(long intersecoes, double tempoMs) { }

    public DadosEspaciais extrair(DatasetEspacial dataset) throws SQLException {
        List<Integer> ids = new ArrayList<>();
        List<String> wkts = new ArrayList<>();
        String geom = citar(dataset.colunaGeometria());
        String sql = "SELECT " + citar(dataset.colunaId()) + " AS id, ST_AsText(" + geom
                + ") AS wkt, ST_SRID(" + geom + ") AS srid FROM " + tabela(dataset);
        try (Statement stmt = conn.createStatement(); ResultSet rs = stmt.executeQuery(sql)) {
            while (rs.next()) {
                int id = rs.getInt("id");
                if (rs.wasNull()) throw new SQLException("ID nulo em " + tabela(dataset));
                String wkt = rs.getString("wkt");
                if (wkt == null || rs.getInt("srid") != dataset.srid()) {
                    throw new SQLException("Geometria nula ou SRID diferente do configurado em " + tabela(dataset) + ", id=" + id);
                }
                ids.add(id);
                wkts.add(wkt);
            }
        }
        return new DadosEspaciais(ids, wkts);
    }

    /** Substitui apenas as saídas compartilhadas, com rollback se qualquer etapa falhar. */
    public void substituirSaidas(CenarioTeste cenario, DadosEspaciais a, DadosEspaciais b,
                                 ResultadoParticionamento resA, ResultadoParticionamento resB) throws SQLException {
        validarEntrada(cenario.datasetA());
        validarEntrada(cenario.datasetB());
        conn.setAutoCommit(false);
        try {
            recriar(cenario, resA.getGrades());
            salvar(SAIDA_A, cenario.datasetA().srid(), a.ids(), resA.getDados());
            salvar(SAIDA_B, cenario.datasetB().srid(), b.ids(), resB.getDados());
            try (PreparedStatement stmt = conn.prepareStatement("INSERT INTO " + GRADE
                    + " (id_particao, geom) VALUES (?, ST_Multi(ST_GeomFromText(?, ?)))")) {
                for (ParticaoMetadata meta : resA.getGrades()) {
                    stmt.setInt(1, meta.getIdParticao());
                    stmt.setString(2, meta.getWktFronteira());
                    stmt.setInt(3, cenario.datasetA().srid());
                    stmt.executeUpdate();
                }
            }
            conn.commit();
        } catch (SQLException | RuntimeException e) {
            try { conn.rollback(); } catch (SQLException rollback) { e.addSuppressed(rollback); }
            throw e;
        } finally {
            conn.setAutoCommit(true);
        }
    }

    private static void validarEntrada(DatasetEspacial dataset) {
        if (dataset.schema().equals("public") && (List.of("tabela_a_particionada", "tabela_b_particionada", "grade_metadados")
                .contains(dataset.tabela()) || dataset.tabela().matches("tabela_[ab]_p[0-9]+"))) {
            throw new IllegalArgumentException("A entrada não pode ser uma tabela reservada de saída");
        }
    }

    private void recriar(CenarioTeste cenario, List<ParticaoMetadata> grades) throws SQLException {
        try (Statement stmt = conn.createStatement()) {
            stmt.execute("DROP TABLE IF EXISTS " + SAIDA_A + " CASCADE");
            stmt.execute("DROP TABLE IF EXISTS " + SAIDA_B + " CASCADE");
            stmt.execute("DROP TABLE IF EXISTS " + GRADE + " CASCADE");
            criarMae(stmt, SAIDA_A, cenario.datasetA());
            criarMae(stmt, SAIDA_B, cenario.datasetB());
            stmt.execute("CREATE TABLE " + GRADE + " (id_particao INTEGER PRIMARY KEY, geom geometry(MultiPolygon, "
                    + cenario.datasetA().srid() + "))");
            for (ParticaoMetadata grade : grades) {
                int id = grade.getIdParticao();
                stmt.execute("CREATE TABLE public.tabela_a_p" + id + " PARTITION OF " + SAIDA_A + " FOR VALUES IN (" + id + ")");
                stmt.execute("CREATE TABLE public.tabela_b_p" + id + " PARTITION OF " + SAIDA_B + " FOR VALUES IN (" + id + ")");
            }
            stmt.execute("CREATE INDEX idx_tabela_a_geom ON " + SAIDA_A + " USING GIST (geom)");
            stmt.execute("CREATE INDEX idx_tabela_b_geom ON " + SAIDA_B + " USING GIST (geom)");
        }
    }

    private void criarMae(Statement stmt, String tabela, DatasetEspacial dataset) throws SQLException {
        stmt.execute("CREATE TABLE " + tabela + " (id INTEGER, id_particao INTEGER, "
                + "classe CHAR(1) NOT NULL CHECK (classe IN ('A','B','C','D')), geom geometry("
                + dataset.tipoGeometria() + ", " + dataset.srid() + ")) PARTITION BY LIST (id_particao)");
    }

    private void salvar(String tabela, int srid, List<Integer> ids, List<ParticaoResult> resultados) throws SQLException {
        String sql = "INSERT INTO " + tabela + " (id, id_particao, classe, geom) VALUES (?, ?, ?, ST_Multi(ST_GeomFromText(?, ?)))";
        try (PreparedStatement stmt = conn.prepareStatement(sql)) {
            for (int i = 0; i < resultados.size(); i++) {
                ParticaoResult resultado = resultados.get(i);
                int origem = resultado.getIndiceOrigem() >= 0 ? resultado.getIndiceOrigem() : i;
                stmt.setInt(1, ids.get(origem));
                stmt.setInt(2, resultado.getIdParticao());
                stmt.setString(3, resultado.getClasse().name());
                stmt.setString(4, resultado.getWkt());
                stmt.setInt(5, srid);
                stmt.addBatch();
                if ((i + 1) % 500 == 0) stmt.executeBatch();
            }
            stmt.executeBatch();
        }
    }

    public MedicaoJoin joinDireto(CenarioTeste cenario) throws SQLException {
        DatasetEspacial a = cenario.datasetA(), b = cenario.datasetB();
        analisar(tabela(a), tabela(b));
        return medir("SELECT COUNT(*) FROM " + tabela(a) + " a JOIN " + tabela(b)
                + " b ON ST_Intersects(a." + citar(a.colunaGeometria()) + ", b." + citar(b.colunaGeometria()) + ")");
    }

    public MedicaoJoin joinParticionado(EstrategiaExecucao estrategia) throws SQLException {
        analisar(SAIDA_A, SAIDA_B);
        try (Statement stmt = conn.createStatement()) { stmt.execute("SET enable_partitionwise_join = on"); }
        if (estrategia == EstrategiaExecucao.FIXED_GRID) {
            return medir("SELECT COUNT(*) FROM (SELECT DISTINCT a.id AS id_a, b.id AS id_b FROM "
                    + SAIDA_A + " a JOIN " + SAIDA_B
                    + " b ON a.id_particao = b.id_particao AND ST_Intersects(a.geom, b.geom)) pares");
        }
        return medir("SELECT COUNT(*) FROM " + SAIDA_A + " a JOIN " + SAIDA_B
                + " b ON " + TwoLayerPartitioner.condicaoJoinSql("a", "b"));
    }

    private void analisar(String a, String b) throws SQLException {
        try (Statement stmt = conn.createStatement()) {
            stmt.execute("ANALYZE " + a);
            stmt.execute("ANALYZE " + b);
        }
    }

    private MedicaoJoin medir(String sql) throws SQLException {
        try (Statement stmt = conn.createStatement()) {
            long inicio = System.nanoTime();
            long total;
            try (ResultSet rs = stmt.executeQuery(sql)) { rs.next(); total = rs.getLong(1); }
            return new MedicaoJoin(total, (System.nanoTime() - inicio) / 1_000_000.0);
        }
    }

    private static String tabela(DatasetEspacial dataset) { return citar(dataset.schema()) + "." + citar(dataset.tabela()); }
    private static String citar(String nome) { return "\"" + nome.replace("\"", "\"\"") + "\""; }
}
