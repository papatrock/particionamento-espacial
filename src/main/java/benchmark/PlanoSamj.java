package benchmark;

import org.locationtech.jts.index.strtree.STRtree;
import org.locationtech.jts.io.WKTReader;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/** Pares de grupos candidatos para associação única, compartilhados pelo Main e pela PP1. */
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

    /** Cada objeto pertence a um único grupo; cada par de grupos é consultado uma vez. */
    public String consulta() {
        if (pares.isEmpty()) return "SELECT 0::bigint";
        return "SELECT SUM(total)::bigint FROM (\n" + pares.stream()
                .map(par -> "SELECT COUNT(*) AS total FROM public.tabela_a_p" + par.a()
                        + " a JOIN public.tabela_b_p" + par.b() + " b ON ST_Intersects(a.geom, b.geom)")
                .collect(Collectors.joining("\nUNION ALL\n")) + "\n) pares";
    }
}
