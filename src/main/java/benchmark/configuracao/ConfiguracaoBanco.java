package benchmark.configuracao;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

/** Configuração de conexão independente do cenário e dos algoritmos. */
public final class ConfiguracaoBanco {
    private final String url;
    private final String usuario;
    private final String senha;

    public ConfiguracaoBanco(String url, String usuario, String senha) {
        this.url = url;
        this.usuario = usuario;
        this.senha = senha;
    }

    public static ConfiguracaoBanco doAmbiente() {
        return new ConfiguracaoBanco(
                valor("db.url", "DB_URL", "jdbc:postgresql://localhost:5432/tcc_espacial"),
                valor("db.user", "DB_USER", "postgres"),
                valor("db.password", "DB_PASSWORD", "1234"));
    }

    public static String valor(String propriedade, String ambiente, String padrao) {
        return System.getProperty(propriedade, System.getenv().getOrDefault(ambiente, padrao));
    }

    public Connection abrirConexao() throws SQLException {
        return DriverManager.getConnection(url, usuario, senha);
    }
}
