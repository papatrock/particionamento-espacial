package benchmark.execucao;

public enum EstrategiaExecucao {
    SEM_PARTICIONAMENTO("Sem particionamento"), FIXED_GRID("Fixed Grid"), TWO_LAYER("Two-Layer SOP"), STR("STR DOP");

    private final String descricao;
    EstrategiaExecucao(String descricao) { this.descricao = descricao; }
    @Override public String toString() { return descricao; }
}
