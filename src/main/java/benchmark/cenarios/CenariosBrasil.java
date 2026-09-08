package benchmark.cenarios;

import java.util.List;

import benchmark.CenarioTeste;
import benchmark.configuracao.DatasetEspacial;

public class CenariosBrasil {
    private CenariosBrasil () {}

        public static List<CenarioTeste> listar() {
        var ruas = new DatasetEspacial("teste", "MultiLineString", 31982);
        var quadras = new DatasetEspacial("teste", "MultiPolygon", 31982);
        return List.of(
                new CenarioTeste("teste", ruas, quadras),
                new CenarioTeste("teste", quadras, ruas)
        );
    }
    
}
