package benchmark.algoritmos;

import benchmark.*;
import benchmark.algoritmos.TwoLayerPartitioner.ClasseTwoLayer;
import org.locationtech.jts.geom.*;
import org.locationtech.jts.index.strtree.STRtree;
import org.locationtech.jts.io.WKTReader;
import java.util.*;

/** Associação comum aos particionadores com regiões MBR sobrepostas (STR e Hilbert). */
final class ParticionamentoPorMbr {
    private ParticionamentoPorMbr() { }

    static ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde,
                                               String nome) throws Exception {
        WKTReader reader = new WKTReader();
        STRtree indice = new STRtree();
        var ids = new HashSet<Integer>();
        for (ParticaoMetadata meta : molde) {
            Geometry fronteira = ler(reader, meta.getWktFronteira());
            Envelope mbr = fronteira.getEnvelopeInternal();
            if (meta.getIdParticao() <= 0 || !ids.add(meta.getIdParticao()) || fronteira.isEmpty()
                    || !fronteira.equalsTopo(fronteira.getFactory().toGeometry(mbr))) {
                throw new IllegalArgumentException("Molde " + nome + " requer MBRs não vazios e IDs positivos únicos");
            }
            indice.insert(mbr, meta.getIdParticao());
        }
        indice.build();
        List<ParticaoResult> resultados = new ArrayList<>();
        for (int origem = 0; origem < wkts.size(); origem++) {
            String wkt = wkts.get(origem);
            Geometry geom = ler(reader, wkt);
            if (geom.isEmpty()) continue;
            List<Integer> destinos = new ArrayList<>();
            // O índice apenas acelera a busca pelas fronteiras já calculadas acima.
            indice.query(geom.getEnvelopeInternal(), item -> destinos.add((Integer) item));
            if (destinos.isEmpty()) {
                throw new IllegalArgumentException("Objeto no índice " + origem
                        + " fora das partições " + nome + "; crie o molde com ambas as entradas completas");
            }
            destinos.sort(Integer::compareTo);
            for (int id : destinos) resultados.add(new ParticaoResult(wkt, id, origem, ClasseTwoLayer.A));
        }
        return new ResultadoParticionamento(resultados, List.copyOf(molde));
    }

    static Geometry ler(WKTReader reader, String wkt) throws Exception {
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
