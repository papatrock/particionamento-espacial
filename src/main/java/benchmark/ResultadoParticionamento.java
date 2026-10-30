package benchmark;
import java.util.List;

public class ResultadoParticionamento {
    private List<ParticaoResult> dados;
    private List<ParticaoMetadata> grades;
    private final boolean associacaoUnica;

    public ResultadoParticionamento(List<ParticaoResult> dados, List<ParticaoMetadata> grades) {
        this(dados, grades, false);
    }

    public ResultadoParticionamento(List<ParticaoResult> dados, List<ParticaoMetadata> grades,
                                   boolean associacaoUnica) {
        this.dados = dados;
        this.grades = grades;
        this.associacaoUnica = associacaoUnica;
    }

    public List<ParticaoResult> getDados() { return dados; }
    public List<ParticaoMetadata> getGrades() { return grades; }
    public boolean isAssociacaoUnica() { return associacaoUnica; }
}
