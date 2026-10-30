package benchmark.algoritmos;

import benchmark.ParticaoMetadata;
import benchmark.ParticionamentoConjunto;
import benchmark.algoritmos.AgrupamentoDop.Objeto;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.shape.fractal.HilbertCode;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Hilbert Curve Partitioning (HC), conforme Aji, Vo e Wang, seção 4.2:
 * https://arxiv.org/abs/1509.00910.
 * Ordena centroides geométricos pela curva e cria MBRs de grupos de até b objetos.
 * Não constrói uma Hilbert R-tree. processarConjunto preserva os grupos de A+B
 * para SAMJ; processar(wkts, molde) mantém a associação múltipla legada (MASJ).
 */
public final class HilbertCurvePartitioner implements SpatialPartitioner {
    public static final int CAPACIDADE_PADRAO = 1000;
    public static final int BITS_PADRAO = 16;
    private final int capacidade;
    private final int bits;

    public HilbertCurvePartitioner() { this(CAPACIDADE_PADRAO); }
    public HilbertCurvePartitioner(int capacidade) { this(capacidade, BITS_PADRAO); }

    public HilbertCurvePartitioner(int capacidade, int bits) {
        if (capacidade <= 0) throw new IllegalArgumentException("Capacidade Hilbert deve ser positiva");
        if (bits < 1 || bits > HilbertCode.MAX_LEVEL)
            throw new IllegalArgumentException("Bits Hilbert devem estar entre 1 e 16");
        this.capacidade = capacidade;
        this.bits = bits;
    }

    private record Chave(Objeto objeto, long valor) { }

    /** O domínio de normalização é o envelope conjunto das geometrias de A e B. */
    public List<ParticaoMetadata> criarGrade(List<String> a, List<String> b) throws Exception {
        return construir(a, b, false).grade();
    }

    /** Uma associação por objeto, preservada desde a ordenação Hilbert. */
    @Override
    public ParticionamentoConjunto processarConjunto(List<String> a, List<String> b) throws Exception {
        return construir(a, b, true);
    }

    private ParticionamentoConjunto construir(List<String> a, List<String> b, boolean preservarMembros) throws Exception {
        var objetos = AgrupamentoDop.ler(a, b, true);
        var grupos = new AgrupamentoDop(a, b, preservarMembros);
        if (objetos.isEmpty()) return grupos.resultado();
        Envelope dominio = new Envelope();
        for (Objeto objeto : objetos) dominio.expandToInclude(objeto.mbr());

        int max = (1 << bits) - 1;
        var chaves = new ArrayList<Chave>(objetos.size());
        for (Objeto objeto : objetos) {
            int x = quantizar(objeto.x(), dominio.getMinX(), dominio.getMaxX(), max);
            int y = quantizar(objeto.y(), dominio.getMinY(), dominio.getMaxY(), max);
            // O índice JTS tem 32 bits sem sinal no nível 16; comparar como int seria incorreto.
            long valor = Integer.toUnsignedLong(HilbertCode.encode(bits, x, y));
            chaves.add(new Chave(objeto, valor));
        }
        // Desempate espacial torna as fronteiras independentes da ordem de leitura do banco.
        // Objetos com centro e MBR idênticos são intercambiáveis para formar as fronteiras.
        chaves.sort(Comparator.comparingLong(Chave::valor)
                .thenComparingDouble(c -> c.objeto.x()).thenComparingDouble(c -> c.objeto.y())
                .thenComparingDouble(c -> c.objeto.mbr().getMinX())
                .thenComparingDouble(c -> c.objeto.mbr().getMinY())
                .thenComparingDouble(c -> c.objeto.mbr().getMaxX())
                .thenComparingDouble(c -> c.objeto.mbr().getMaxY()));

        for (int inicio = 0; inicio < chaves.size();) {
            int fim = (int) Math.min(chaves.size(), inicio + (long) capacidade);
            var membros = new ArrayList<Objeto>(fim - inicio);
            for (int i = inicio; i < fim; i++) membros.add(chaves.get(i).objeto);
            grupos.adicionarGrupo(membros);
            inicio = fim;
        }
        return grupos.resultado();
    }

    /** Normaliza cada eixo separadamente; eixo degenerado fica em zero. */
    private static int quantizar(double valor, double min, double max, int limite) {
        if (min == max) return 0;
        double amplitude = max - min;
        double proporcao = Double.isFinite(amplitude) ? (valor - min) / amplitude
                : (valor / 2 - min / 2) / (max / 2 - min / 2);
        return (int) Math.floor(Math.max(0, Math.min(1, proporcao)) * limite);
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts) throws Exception {
        return processar(wkts, criarGrade(wkts, List.of()));
    }

    /** b limita o agrupamento inicial; após replicação a ocupação pode superar b. */
    @Override
    public ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception {
        return ParticionamentoPorMbr.processar(wkts, molde, "Hilbert");
    }
}
