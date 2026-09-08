package benchmark;

import benchmark.configuracao.DatasetEspacial;
import java.util.Objects;

/** Par de datasets para um join de interseção espacial. Não contém SQL. */
public record CenarioTeste(String nomeCenario, DatasetEspacial datasetA, DatasetEspacial datasetB) {
    public CenarioTeste {
        Objects.requireNonNull(nomeCenario);
        Objects.requireNonNull(datasetA);
        Objects.requireNonNull(datasetB);
        if (datasetA.srid() != datasetB.srid()) {
            throw new IllegalArgumentException("As duas entradas devem usar o mesmo SRID");
        }
    }

    @Override
    public String toString() {
        return nomeCenario + " [" + datasetA.schema() + "." + datasetA.tabela()
                + " x " + datasetB.schema() + "." + datasetB.tabela() + "]";
    }
}
