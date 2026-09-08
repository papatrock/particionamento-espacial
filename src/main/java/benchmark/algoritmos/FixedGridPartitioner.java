package benchmark.algoritmos;

import benchmark.algoritmos.TwoLayerPartitioner.ClasseTwoLayer;
import benchmark.ParticaoMetadata;
import benchmark.ParticaoResult;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.Geometry;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
import java.util.List;

/** Grade fixa 2 × 2 com replicação por MBR. O join elimina pares de IDs duplicados. */
public class FixedGridPartitioner implements SpatialPartitioner {
    public List<ParticaoMetadata> criarGrade(List<String> a, List<String> b) throws Exception {
        Envelope dominio = new Envelope();
        WKTReader reader = new WKTReader();
        for (List<String> entrada : List.of(a, b)) {
            for (String wkt : entrada) dominio.expandToInclude(ler(reader, wkt).getEnvelopeInternal());
        }
        if (dominio.isNull()) return List.of();
        double[] xs = limites(dominio.getMinX(), dominio.getMaxX());
        double[] ys = limites(dominio.getMinY(), dominio.getMaxY());
        List<ParticaoMetadata> grade = new ArrayList<>();
        GeometryFactory factory = new GeometryFactory();
        for (int y = 0; y < 2; y++) for (int x = 0; x < 2; x++) {
            grade.add(new ParticaoMetadata(y * 2 + x + 1,
                    factory.toGeometry(new Envelope(xs[x], xs[x + 1], ys[y], ys[y + 1])).toText()));
        }
        return List.copyOf(grade);
    }

    private static double[] limites(double min, double max) {
        if (min == max) max = min + 1;
        double meio = min / 2 + max / 2;
        if (!Double.isFinite(max) || !(min < meio && meio < max)) {
            throw new IllegalArgumentException("Extensão da grade não representável em double");
        }
        return new double[]{min, meio, max};
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts) throws Exception {
        return processar(wkts, criarGrade(wkts, List.of()));
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception {
        if (!molde.isEmpty() && molde.size() != 4) {
            throw new IllegalArgumentException("Fixed Grid requer quatro células");
        }
        WKTReader reader = new WKTReader();
        List<Envelope> cells = new ArrayList<>();
        Envelope dominio = new Envelope();
        for (int i = 0; i < molde.size(); i++) {
            Geometry cell = ler(reader, molde.get(i).getWktFronteira());
            Envelope env = cell.getEnvelopeInternal();
            if (molde.get(i).getIdParticao() != i + 1 || env.getWidth() <= 0 || env.getHeight() <= 0
                    || !cell.equalsTopo(cell.getFactory().toGeometry(env))) {
                throw new IllegalArgumentException("Molde inválido para Fixed Grid");
            }
            cells.add(env);
            dominio.expandToInclude(env);
        }
        if (!cells.isEmpty()) {
            double[] xs = limites(dominio.getMinX(), dominio.getMaxX());
            double[] ys = limites(dominio.getMinY(), dominio.getMaxY());
            for (int y = 0; y < 2; y++) for (int x = 0; x < 2; x++) {
                if (!cells.get(y * 2 + x).equals(new Envelope(xs[x], xs[x + 1], ys[y], ys[y + 1]))) {
                    throw new IllegalArgumentException("Molde deve ser uma grade 2 × 2 ordenada por linha");
                }
            }
        }
        List<ParticaoResult> resultados = new ArrayList<>();
        for (int origem = 0; origem < wkts.size(); origem++) {
            Geometry geom = ler(reader, wkts.get(origem));
            if (geom.isEmpty()) continue;
            Envelope mbr = geom.getEnvelopeInternal();
            if (!dominio.contains(mbr)) {
                throw new IllegalArgumentException("Geometria fora da grade; inclua ambas as entradas no domínio");
            }
            for (int i = 0; i < cells.size(); i++) {
                // Inclui contatos nas bordas. Duplicações são removidas no join por IDs.
                if (cells.get(i).intersects(mbr)) {
                    resultados.add(new ParticaoResult(wkts.get(origem), molde.get(i).getIdParticao(),
                            origem, ClasseTwoLayer.A));
                }
            }
        }
        return new ResultadoParticionamento(resultados, List.copyOf(molde));
    }

    private static Geometry ler(WKTReader reader, String wkt) throws Exception {
        if (wkt == null) throw new IllegalArgumentException("WKT nulo");
        Geometry geom = reader.read(wkt);
        for (var c : geom.getCoordinates()) {
            if (!Double.isFinite(c.x) || !Double.isFinite(c.y)) {
                throw new IllegalArgumentException("Coordenada não finita");
            }
        }
        return geom;
    }
}
