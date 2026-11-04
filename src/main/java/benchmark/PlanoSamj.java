package benchmark;

import org.locationtech.jts.index.strtree.STRtree;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Pares de grupos candidatos para associação única, usados pelas variantes SAMJ da PP1. */
public record PlanoSamj(List<Par> pares) {
    public record Par(int a, int b) { }

    public PlanoSamj {
        pares = List.copyOf(pares);
    }

    public static PlanoSamj criar(ParticionamentoConjunto conjunto) throws Exception {
        var reader = new WKTReader();
        var indice = new STRtree();
        for (var meta : conjunto.b().getGrades()) {
            indice.insert(reader.read(meta.getWktFronteira()).getEnvelopeInternal(), meta.getIdParticao());
        }
        indice.build();
        var pares = new ArrayList<Par>();
        for (var meta : conjunto.a().getGrades()) {
            indice.query(reader.read(meta.getWktFronteira()).getEnvelopeInternal(),
                    destino -> pares.add(new Par(meta.getIdParticao(), (Integer) destino)));
        }
        pares.sort(Comparator.comparingInt(Par::a).thenComparingInt(Par::b));
        return new PlanoSamj(pares);
    }
}
