package benchmark;
import java.util.List;

public interface SpatialPartitioner {
    /** Grupos preservados para SAMJ; nenhum objeto é reassociado pelo envelope. */
    default ParticionamentoConjunto processarConjunto(List<String> a, List<String> b) throws Exception {
        throw new UnsupportedOperationException("Associação única indisponível para este particionador");
    }
    ResultadoParticionamento processar(List<String> wkts) throws Exception;
    ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception;
}
