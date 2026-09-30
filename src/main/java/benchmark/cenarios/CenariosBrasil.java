package benchmark.cenarios;

import java.util.List;

import benchmark.CenarioTeste;
import benchmark.configuracao.DatasetEspacial;

public class CenariosBrasil {
    private CenariosBrasil () {}

    public static List<CenarioTeste> listar() {
        var linhas = new DatasetEspacial(
                "public", "brasil_osm_line",
                "osm_id", "way", "MultiLineString", 3857);

        var pontos = new DatasetEspacial(
                "public", "brasil_osm_point",
                "osm_id", "way", "MultiPoint", 3857);

        var poligonos = new DatasetEspacial(
                "public", "brasil_osm_polygon",
                "osm_id", "way", "Geometry", 3857);

        return List.of(
                new CenarioTeste("Brasil: Linhas x Polígonos", linhas, poligonos),
                new CenarioTeste("Brasil: Pontos x Polígonos", pontos, poligonos)
        );
    }

}
