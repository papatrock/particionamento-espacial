package benchmark.algoritmos;

import benchmark.ParticaoMetadata;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.Geometry;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
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
 * A capacidade limita os grupos que definem as fronteiras. A associação final
 * replica por interseção de MBRs, podendo exceder essa capacidade. O join deve
 * eliminar pares de IDs duplicados. MBRs podem se sobrepor e deixar lacunas.
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
        List<Envelope> objetos = new ArrayList<>();
        WKTReader reader = new WKTReader();
        for (List<String> entrada : List.of(a, b)) {
            for (String wkt : entrada) {
                Geometry geom = ler(reader, wkt);
                if (!geom.isEmpty()) objetos.add(geom.getEnvelopeInternal());
            }
        }
        if (objetos.isEmpty()) return List.of();

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

        objetos.sort(Comparator.comparingDouble(SortTileRecursive::centroX)
                .thenComparingDouble(SortTileRecursive::centroY));

        Comparator<Envelope> porY = Comparator.comparingDouble(SortTileRecursive::centroY)
                .thenComparingDouble(SortTileRecursive::centroX);
        GeometryFactory factory = new GeometryFactory();

        List<ParticaoMetadata> molde = new ArrayList<>(particoes);
        for (int inicio = 0; inicio < objetos.size();) {
            int fim = (int) Math.min(objetos.size(), inicio + tamanhoFaixa);
            objetos.subList(inicio, fim).sort(porY);
            for (int grupo = inicio; grupo < fim;) {
                int fimGrupo = (int) Math.min(fim, grupo + (long) capacidade);
                Envelope mbr = new Envelope();
                for (int i = grupo; i < fimGrupo; i++) mbr.expandToInclude(objetos.get(i));
                // Pontos/linhas são MBRs válidos; não se adiciona área artificial.
                molde.add(new ParticaoMetadata(molde.size() + 1, factory.toGeometry(mbr).toText()));
                grupo = fimGrupo;
            }
            inicio = fim;
        }
        return List.copyOf(molde);
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

    private static double centroX(Envelope mbr) { return mbr.getMinX() / 2 + mbr.getMaxX() / 2; }
    private static double centroY(Envelope mbr) { return mbr.getMinY() / 2 + mbr.getMaxY() / 2; }

    private static Geometry ler(WKTReader reader, String wkt) throws Exception {
        return ParticionamentoPorMbr.ler(reader, wkt);
    }
}
