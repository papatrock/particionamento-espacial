package benchmark.algoritmos;

import benchmark.*;
import benchmark.algoritmos.TwoLayerPartitioner.ClasseTwoLayer;
import org.locationtech.jts.geom.*;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
import java.util.List;

/** Conserva a origem durante a ordenação e materializa os membros dos grupos, sem reassociação espacial. */
final class AgrupamentoDop {
    record Objeto(int lado, int origem, Envelope mbr, double x, double y) { }

    static List<Objeto> ler(List<String> a, List<String> b, boolean centroide) throws Exception {
        var objetos = new ArrayList<Objeto>();
        var reader = new WKTReader();
        var entradas = List.of(a, b);
        for (int lado = 0; lado < entradas.size(); lado++) {
            var entrada = entradas.get(lado);
            for (int origem = 0; origem < entrada.size(); origem++) {
                Geometry geom = ParticionamentoPorMbr.ler(reader, entrada.get(origem));
                if (geom.isEmpty()) continue;
                Envelope mbr = geom.getEnvelopeInternal();
                double x = mbr.getMinX() / 2 + mbr.getMaxX() / 2;
                double y = mbr.getMinY() / 2 + mbr.getMaxY() / 2;
                if (centroide) {
                    Coordinate centro = geom.getCentroid().getCoordinate();
                    if (centro == null) throw new IllegalArgumentException("Centroide Hilbert ausente");
                    x = centro.x;
                    y = centro.y;
                }
                if (!Double.isFinite(x) || !Double.isFinite(y))
                    throw new IllegalArgumentException("Centro não finito");
                objetos.add(new Objeto(lado, origem, mbr, x, y));
            }
        }
        return objetos;
    }

    private final List<List<String>> entradas;
    private final List<List<ParticaoResult>> dados = List.of(new ArrayList<>(), new ArrayList<>());
    private final List<List<ParticaoMetadata>> grades = List.of(new ArrayList<>(), new ArrayList<>());
    private final List<ParticaoMetadata> conjunta = new ArrayList<>();
    private final GeometryFactory factory = new GeometryFactory();
    private final boolean preservarMembros;

    AgrupamentoDop(List<String> a, List<String> b, boolean preservarMembros) {
        entradas = List.of(a, b);
        this.preservarMembros = preservarMembros;
    }

    void adicionarGrupo(List<Objeto> objetos) {
        int id = conjunta.size() + 1;
        Envelope[] envelopes = {new Envelope(), new Envelope()};
        Envelope combinado = new Envelope();
        for (Objeto objeto : objetos) {
            combinado.expandToInclude(objeto.mbr);
            if (preservarMembros) {
                envelopes[objeto.lado].expandToInclude(objeto.mbr);
                dados.get(objeto.lado).add(new ParticaoResult(
                        entradas.get(objeto.lado).get(objeto.origem), id, objeto.origem, ClasseTwoLayer.A));
            }
        }
        conjunta.add(new ParticaoMetadata(id, factory.toGeometry(combinado).toText()));
        for (int lado = 0; lado < 2; lado++) {
            if (!envelopes[lado].isNull())
                grades.get(lado).add(new ParticaoMetadata(id, factory.toGeometry(envelopes[lado]).toText()));
        }
    }

    ParticionamentoConjunto resultado() {
        return new ParticionamentoConjunto(
                new ResultadoParticionamento(dados.get(0), List.copyOf(grades.get(0)), preservarMembros),
                new ResultadoParticionamento(dados.get(1), List.copyOf(grades.get(1)), preservarMembros),
                List.copyOf(conjunta));
    }
}
