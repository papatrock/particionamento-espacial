package benchmark;

import java.util.List;

/** Grupos de A+B, com uma associação por objeto e envelopes próprios de cada relação. */
public record ParticionamentoConjunto(ResultadoParticionamento a, ResultadoParticionamento b,
                                     List<ParticaoMetadata> grade) { }
