package benchmark.cenarios;

import benchmark.CenarioTeste;
import benchmark.configuracao.DatasetEspacial;
import java.util.List;

/** Catálogo separado da interface de console; também pode ser usado por outros runners. */
public final class CenariosCuritiba {
    private CenariosCuritiba() { }

    public static List<CenarioTeste> listar() {
        var ruas = new DatasetEspacial("eixo_rua", "MultiLineString", 31982);
        var quadras = new DatasetEspacial("arruamento_quadras", "MultiPolygon", 31982);
        var bairros = new DatasetEspacial("divisa_de_bairros", "MultiPolygon", 31982);
        var regionais = new DatasetEspacial("divisa_de_regionais", "MultiPolygon", 31982);
        return List.of(
                new CenarioTeste("Ruas x Quadras", ruas, quadras),
                new CenarioTeste("Quadras x Bairros", quadras, bairros),
                new CenarioTeste("Ruas x Bairros", ruas, bairros),
                new CenarioTeste("Quadras x Regionais", quadras, regionais));
    }
}
