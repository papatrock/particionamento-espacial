package benchmark.algoritmos;

import benchmark.ParticaoMetadata;
import benchmark.ParticaoResult;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.Geometry;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Two-layer Space-oriented Partitioning: replicação de MBRs e classes A/B/C/D.
 * Referência: https://github.com/dTsitsigkos/two-layer (partition.h).
 * Mantém coordenadas originais; a avaliação exata fica a cargo do PostGIS.
 */
public class TwoLayerPartitioner implements SpatialPartitioner {
    /** Posição da célula em relação à célula inicial do MBR (partition.h original). */
    public enum ClasseTwoLayer {
        A, B, C, D;

        /** As nove combinações do join original; cada par de MBRs é avaliado uma vez. */
        public boolean combinaCom(ClasseTwoLayer outra) {
            return this == A || outra == A
                    || (this == B && outra == C) || (this == C && outra == B);
        }

        public static String condicaoSql(String aliasA, String aliasB) {
            return "(" + aliasA + ".classe = 'A' OR " + aliasB + ".classe = 'A'"
                    + " OR (" + aliasA + ".classe = 'B' AND " + aliasB + ".classe = 'C')"
                    + " OR (" + aliasA + ".classe = 'C' AND " + aliasB + ".classe = 'B'))";
        }
    }

    /** Predicado do join Two-Layer: mesma célula, classes permitidas e teste exato. */
    public static String condicaoJoinSql(String aliasA, String aliasB) {
        return aliasA + ".id_particao = " + aliasB + ".id_particao AND "
                + ClasseTwoLayer.condicaoSql(aliasA, aliasB)
                + " AND ST_Intersects(" + aliasA + ".geom, " + aliasB + ".geom)";
    }

    private final int celulasPorEixo;

    public TwoLayerPartitioner() { this(10); }

    public TwoLayerPartitioner(int celulasPorEixo) {
        if (celulasPorEixo <= 0 || (long) celulasPorEixo * celulasPorEixo > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Número de células por eixo inválido");
        }
        this.celulasPorEixo = celulasPorEixo;
    }

    /** Para joins, o domínio deve incluir ambas as relações antes de classificá-las. */
    public List<ParticaoMetadata> criarGrade(List<String> wktsA, List<String> wktsB) throws Exception {
        Envelope dominio = new Envelope();
        WKTReader reader = new WKTReader();
        for (List<String> entrada : List.of(wktsA, wktsB)) {
            for (int i = 0; i < entrada.size(); i++) {
                dominio.expandToInclude(lerGeometria(reader, entrada.get(i), i).getEnvelopeInternal());
            }
        }
        if (dominio.isNull()) return List.of();
        // Equivalente a uma grade uniforme no domínio normalizado pelo maior eixo.
        double lado = Math.max(dominio.getWidth(), dominio.getHeight());
        if (lado == 0) lado = 1; // Pontos coincidentes precisam de células com área positiva.
        double[] xs = limites(dominio.getMinX(), lado);
        double[] ys = limites(dominio.getMinY(), lado);
        List<ParticaoMetadata> grade = new ArrayList<>();
        GeometryFactory factory = new GeometryFactory();
        for (int y = 0; y < celulasPorEixo; y++) {
            for (int x = 0; x < celulasPorEixo; x++) {
                Envelope cell = new Envelope(xs[x], xs[x + 1], ys[y], ys[y + 1]);
                grade.add(new ParticaoMetadata(y * celulasPorEixo + x + 1,
                        factory.toGeometry(cell).toText()));
            }
        }
        return List.copyOf(grade);
    }

    private double[] limites(double inicio, double lado) {
        double[] limites = new double[celulasPorEixo + 1];
        for (int i = 0; i <= celulasPorEixo; i++) {
            limites[i] = inicio + lado * ((double) i / celulasPorEixo);
            if (!Double.isFinite(limites[i]) || (i > 0 && limites[i] <= limites[i - 1])) {
                throw new IllegalArgumentException("Extensão/resolução da grade não representável em double");
            }
        }
        return limites;
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts) throws Exception {
        return processar(wkts, criarGrade(wkts, List.of()));
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception {
        List<ParticaoResult> resultados = new ArrayList<>();
        WKTReader reader = new WKTReader();
        if (molde.isEmpty()) {
            for (int i = 0; i < wkts.size(); i++) {
                if (!lerGeometria(reader, wkts.get(i), i).isEmpty()) {
                    throw new IllegalArgumentException("Grade vazia para uma entrada não vazia");
                }
            }
            return new ResultadoParticionamento(resultados, List.of());
        }
        Grade grade = new Grade(molde, reader);
        for (int origem = 0; origem < wkts.size(); origem++) {
            String wkt = wkts.get(origem);
            Geometry geom = lerGeometria(reader, wkt, origem);
            // EMPTY não participa de ST_Intersects; índices de origem são preservados.
            if (geom.isEmpty()) continue;
            Envelope mbr = geom.getEnvelopeInternal();
            int xInicio = indice(mbr.getMinX(), grade.xs);
            int xFim = indice(mbr.getMaxX(), grade.xs);
            int yInicio = indice(mbr.getMinY(), grade.ys);
            int yFim = indice(mbr.getMaxY(), grade.ys);
            for (int y = yInicio; y <= yFim; y++) {
                for (int x = xInicio; x <= xFim; x++) {
                    ClasseTwoLayer classe = y == yInicio
                            ? (x == xInicio ? ClasseTwoLayer.A : ClasseTwoLayer.C)
                            : (x == xInicio ? ClasseTwoLayer.B : ClasseTwoLayer.D);
                    resultados.add(new ParticaoResult(wkt, molde.get(y * grade.n + x).getIdParticao(),
                            origem, classe));
                }
            }
        }
        return new ResultadoParticionamento(resultados, List.copyOf(molde));
    }

    // Fronteiras internas pertencem à célula à direita/acima; o extremo global,
    // à última célula. A mesma regra para ambos os extremos preserva contatos.
    private static int indice(double valor, double[] limites) {
        if (valor < limites[0] || valor > limites[limites.length - 1]) {
            throw new IllegalArgumentException("Geometria fora da grade; crie o domínio com ambas as entradas");
        }
        int pos = Arrays.binarySearch(limites, valor);
        if (pos < 0) pos = -pos - 2;
        return Math.min(pos, limites.length - 2);
    }

    private static Geometry lerGeometria(WKTReader reader, String wkt, int origem) throws Exception {
        if (wkt == null) throw new IllegalArgumentException("WKT nulo no índice " + origem);
        Geometry geom = reader.read(wkt);
        for (var c : geom.getCoordinates()) {
            if (!Double.isFinite(c.x) || !Double.isFinite(c.y)) {
                throw new IllegalArgumentException("Coordenada não finita no índice " + origem);
            }
        }
        return geom;
    }

    /** Reconstrói os limites compartilhados, validando o contrato do molde. */
    private static class Grade {
        final int n;
        final double[] xs;
        final double[] ys;

        Grade(List<ParticaoMetadata> molde, WKTReader reader) throws Exception {
            n = (int) Math.sqrt(molde.size());
            if (n * n != molde.size()) throw new IllegalArgumentException("Grade deve conter N × N células");
            xs = new double[n + 1];
            ys = new double[n + 1];
            List<Envelope> cells = new ArrayList<>();
            for (int i = 0; i < molde.size(); i++) {
                Geometry geom = reader.read(molde.get(i).getWktFronteira());
                Envelope env = geom.getEnvelopeInternal();
                if (molde.get(i).getIdParticao() != i + 1 || geom.isEmpty()
                        || !geom.equalsTopo(geom.getFactory().toGeometry(env))) {
                    throw new IllegalArgumentException("Molde deve usar retângulos e IDs consecutivos por linha");
                }
                cells.add(env);
            }
            for (int i = 0; i < n; i++) {
                xs[i] = cells.get(i).getMinX();
                ys[i] = cells.get(i * n).getMinY();
            }
            xs[n] = cells.get(n - 1).getMaxX();
            ys[n] = cells.get((n - 1) * n).getMaxY();
            for (int y = 0; y < n; y++) {
                for (int x = 0; x < n; x++) {
                    if (!Double.isFinite(xs[x]) || !Double.isFinite(xs[x + 1])
                            || !Double.isFinite(ys[y]) || !Double.isFinite(ys[y + 1])
                            || xs[x] >= xs[x + 1] || ys[y] >= ys[y + 1]
                            || !cells.get(y * n + x).equals(new Envelope(xs[x], xs[x + 1], ys[y], ys[y + 1]))) {
                        throw new IllegalArgumentException("Grade possui lacunas, sobreposições ou células degeneradas");
                    }
                }
            }
        }
    }
}
