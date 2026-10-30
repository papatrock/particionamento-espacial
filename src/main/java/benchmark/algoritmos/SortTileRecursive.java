package benchmark.algoritmos;

import benchmark.ParticaoMetadata;
import benchmark.ParticionamentoConjunto;
import benchmark.algoritmos.AgrupamentoDop.Objeto;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;

import java.util.Comparator;
import java.util.List;

/**
 * STR bidimensional, Data-Oriented Partitioning (DOP).
 * Gera apenas os MBRs do nível folha, sem construir os níveis superiores da R-tree.
 * Ordena pelos centros dos MBRs: X globalmente e Y dentro de cada faixa.
 *
 * Referências: Leutenegger, Edgington e Lopez (1997),
 * https://doi.org/10.1109/ICDE.1997.582015; Aji, Vo e Wang,
 * https://arxiv.org/abs/1509.00910 (seção 4.2).
 *
 * processarConjunto preserva os membros de cada grupo (SAMJ), com capacidade
 * combinada de A+B. O contrato legado processar(wkts, molde) continua replicando
 * por MBR (MASJ), para os demais experimentos. MBRs podem se sobrepor e deixar lacunas.
 */
public class SortTileRecursive implements SpatialPartitioner {
    private static final boolean DEBUG = Boolean.getBoolean("str.debug");
    public static final int CAPACIDADE_PADRAO = 1000;
    private final int capacidade;

    public SortTileRecursive() { this(CAPACIDADE_PADRAO); }

    public SortTileRecursive(int capacidade) {
        if (capacidade <= 0) throw new IllegalArgumentException("Capacidade STR deve ser positiva");
        this.capacidade = capacidade;
    }

    /** Para joins, construa um único molde com ambas as relações completas. */
    public List<ParticaoMetadata> criarGrade(List<String> a, List<String> b) throws Exception {
        return construir(a, b, false).grade();
    }

    /** Associação única: o membro mantém o grupo em que foi colocado pela ordenação STR. */
    @Override
    public ParticionamentoConjunto processarConjunto(List<String> a, List<String> b) throws Exception {
        return construir(a, b, true);
    }

    private ParticionamentoConjunto construir(List<String> a, List<String> b, boolean preservarMembros) throws Exception {
        List<Objeto> objetos = AgrupamentoDop.ler(a, b, false);
        var grupos = new AgrupamentoDop(a, b, preservarMembros);
        if (objetos.isEmpty()) return grupos.resultado();

        int particoes = (int) ((objetos.size() + (long) capacidade - 1) / capacidade);
        int faixas = (int) Math.ceil(Math.sqrt(particoes));

        long tamanhoFaixa = (long) faixas * capacidade;

        if (DEBUG) {
            System.out.println("=== STR ===");
            System.out.println("N (objetos): " + objetos.size());
            System.out.println("b (capacidade): " + capacidade);
            System.out.println("P (partições): " + particoes);
            System.out.println("m (faixas): " + faixas);
            System.out.println("m * b (tamanho da faixa): " + tamanhoFaixa);
        }

        objetos.sort(Comparator.comparingDouble(Objeto::x)
                .thenComparingDouble(Objeto::y));

        Comparator<Objeto> porY = Comparator.comparingDouble(Objeto::y)
                .thenComparingDouble(Objeto::x);
        for (int inicio = 0; inicio < objetos.size();) {
            int fim = (int) Math.min(objetos.size(), inicio + tamanhoFaixa);
            objetos.subList(inicio, fim).sort(porY);
            for (int grupo = inicio; grupo < fim;) {
                int fimGrupo = (int) Math.min(fim, grupo + (long) capacidade);
                grupos.adicionarGrupo(objetos.subList(grupo, fimGrupo));
                grupo = fimGrupo;
            }
            inicio = fim;
        }
        return grupos.resultado();
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts) throws Exception {
        return processar(wkts, criarGrade(wkts, List.of()));
    }

    /** Reutiliza as fronteiras sem recalculá-las e preserva o índice original de cada objeto. */
    @Override
    public ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception {
        return ParticionamentoPorMbr.processar(wkts, molde, "STR");
    }

}
