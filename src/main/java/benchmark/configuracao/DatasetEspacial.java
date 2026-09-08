package benchmark.configuracao;

import java.util.Set;

/** Esquema físico da entrada; nomes são identificadores, não fragmentos de SQL. */
public record DatasetEspacial(String schema, String tabela, String colunaId,
                              String colunaGeometria, String tipoGeometria, int srid) {
    public DatasetEspacial {
        for (String nome : new String[]{schema, tabela, colunaId, colunaGeometria}) {
            if (nome == null || nome.isBlank()) throw new IllegalArgumentException("Identificador vazio");
        }
        if (!Set.of("MultiPolygon", "MultiLineString", "MultiPoint", "Geometry").contains(tipoGeometria)) {
            throw new IllegalArgumentException("Tipo de saída incompatível com ST_Multi: " + tipoGeometria);
        }
        if (srid <= 0) throw new IllegalArgumentException("SRID deve ser positivo");
    }

    public DatasetEspacial(String tabela, String tipoGeometria, int srid) {
        this("public", tabela, "ogc_fid", "wkb_geometry", tipoGeometria, srid);
    }

    public DatasetEspacial comTabela(String nome) {
        return new DatasetEspacial(schema, nome, colunaId, colunaGeometria, tipoGeometria, srid);
    }
}
