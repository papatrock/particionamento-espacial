package benchmark;

import benchmark.algoritmos.TwoLayerPartitioner.ClasseTwoLayer;

public class ParticaoResult {
    private final String wkt;
    private final int idParticao;
    private final int indiceOrigem;
    private final ClasseTwoLayer classe;

    public ParticaoResult(String wkt, int idParticao) {
        this(wkt, idParticao, -1, ClasseTwoLayer.A);
    }

    public ParticaoResult(String wkt, int idParticao, int indiceOrigem, ClasseTwoLayer classe) {
        this.wkt = wkt;
        this.idParticao = idParticao;
        this.indiceOrigem = indiceOrigem;
        this.classe = classe;
    }

    public String getWkt() { return wkt; }
    public int getIdParticao() { return idParticao; }
    /** Índice na entrada original; -1 apenas para o particionador legado sem replicação. */
    public int getIndiceOrigem() { return indiceOrigem; }
    public ClasseTwoLayer getClasse() { return classe; }
}
