package benchmark.cenarios;

import java.util.List;

import benchmark.CenarioTeste;
import benchmark.configuracao.DatasetEspacial;

public class CenariosBrasil {
    private CenariosBrasil () {}

    public static List<CenarioTeste> listar() {
        var linhas = new DatasetEspacial(
                "public", "brasil_line",
                "osm_id", "geom", "MultiLineString", 3857);

        var pontos = new DatasetEspacial(
                "public", "brasil_point",
                "osm_id", "geom", "MultiPoint", 3857);

        var poligonos = new DatasetEspacial(
                "public", "brasil_polygon",
                "osm_id", "geom", "MultiPolygon", 3857);

        return List.of(
                new CenarioTeste("Brasil: Linhas x Polígonos", linhas, poligonos),
                new CenarioTeste("Brasil: Pontos x Polígonos", pontos, poligonos)
        );
    }

}
