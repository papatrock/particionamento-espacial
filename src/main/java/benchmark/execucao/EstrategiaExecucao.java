package benchmark.execucao;

public enum EstrategiaExecucao {
    FIXED_GRID("Fixed Grid"), TWO_LAYER("Two-Layer SOP"), SEM_PARTICIONAMENTO("Sem particionamento");

    private final String descricao;
    EstrategiaExecucao(String descricao) { this.descricao = descricao; }
    @Override public String toString() { return descricao; }
}
