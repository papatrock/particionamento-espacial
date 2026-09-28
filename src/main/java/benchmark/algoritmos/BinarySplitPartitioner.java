package benchmark.algoritmos;

import benchmark.ParticaoMetadata;
import benchmark.ResultadoParticionamento;
import benchmark.SpatialPartitioner;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.geom.GeometryFactory;
import org.locationtech.jts.io.WKTReader;

import java.math.BigDecimal;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Binary Split Partitioning de Aji, Vo e Wang (2015), seção 4.2, Algoritmo 3,
 * https://arxiv.org/abs/1509.00910. Variante específica, não uma BSP tree genérica.
 * A Tabela 1 o classifica como top-down, non-overlapping e space-oriented,
 * embora o corte específico seja a mediana dos centros dos MBRs (seção 4.1).
 *
 * Usa inserção incremental, compara o produto das áreas dos dois filhos para
 * os candidatos X/Y e replica MBRs que intersectem ambos os filhos na construção.
 * Folhas bem-sucedidas respeitam b; a quantidade de folhas não é predefinida.
 *
 * Ressalvas do pseudocódigo: usa-se {@code > b} conforme o texto, em vez do {@code <= c} impresso;
 * a raiz é persistente e todos os objetos de uma folha dividida são redistribuídos.
 * Convenções não especificadas: mediana par é a média, empate favorece X,
 * contatos contam como interseção, cortes precisam ser estritamente interiores.
 * Sem candidato válido, lança exceção: não inventa cortes nem retorna folha excedente.
 *
 * Adaptações ao benchmark: R é A seguida de B, sem amostragem; o executor lê cada
 * relação por ID. WKT completo é conservado na materialização posterior por MBR;
 * o SQL deve deduplicar pares. A ordem de inserção pode alterar as regiões.
 * Ver docs/bsp-referencia.md para evidências, ambiguidades e limites.
 */
public final class BinarySplitPartitioner implements SpatialPartitioner {
    public static final int CAPACIDADE_PADRAO = 1000;
    private final int capacidade;

    public BinarySplitPartitioner() { this(CAPACIDADE_PADRAO); }

    public BinarySplitPartitioner(int capacidade) {
        if (capacidade <= 0) throw new IllegalArgumentException("Capacidade BSP deve ser positiva");
        this.capacidade = capacidade;
    }

    private static final class No {
        final Envelope regiao;
        List<Envelope> objetos = new ArrayList<>();
        No primeiro;
        No segundo;

        No(Envelope regiao) { this.regiao = regiao; }
        boolean folha() { return primeiro == null; }
    }

    private record Insercao(No no, Envelope objeto) { }
    enum Eixo { X, Y }
    record Corte(Eixo eixo, double posicao, Envelope primeiro, Envelope segundo, BigDecimal produto) { }

    /** A seguida de B, sem ordenar por centroide ou usar amostras. */
    public List<ParticaoMetadata> criarGrade(List<String> a, List<String> b) throws Exception {
        List<Envelope> objetos = new ArrayList<>();
        Envelope universo = new Envelope();
        WKTReader reader = new WKTReader();
        for (List<String> entrada : List.of(a, b)) {
            for (String wkt : entrada) {
                var geometria = ParticionamentoPorMbr.ler(reader, wkt);
                if (geometria.isEmpty()) continue;
                Envelope mbr = geometria.getEnvelopeInternal();
                objetos.add(mbr);
                universo.expandToInclude(mbr);
            }
        }
        if (objetos.isEmpty()) return List.of();
        // Alg. 3, linhas 1–4: uma raiz para U, reutilizada entre inserções.
        No raiz = new No(universo);
        for (Envelope objeto : objetos) adicionarObjeto(raiz, objeto);
        return extrairFolhas(raiz);
    }

    /** Pilha explícita preserva a ordem recursiva sem depender da pilha da JVM. */
    private void adicionarObjeto(No raiz, Envelope objeto) {
        var pendentes = new ArrayDeque<Insercao>();
        pendentes.push(new Insercao(raiz, objeto));
        while (!pendentes.isEmpty()) {
            Insercao insercao = pendentes.pop();
            No no = insercao.no;
            if (!no.folha()) {
                encaminhar(pendentes, no, insercao.objeto);
                continue;
            }
            // Alg. 3, linhas 7–10; > b segue o texto da seção 4.2 (correção interpretativa explicitada).
            no.objetos.add(insercao.objeto);
            if (no.objetos.size() <= capacidade) continue;
            Corte corte = escolherCorte(no.regiao, no.objetos);
            if (corte == null) {
                throw new IllegalArgumentException("BSP não consegue satisfazer b=" + capacidade
                        + " na região " + no.regiao + " com " + no.objetos.size()
                        + " MBRs: nenhuma mediana produz duas sub-regiões estritas. "
                        + "A referência não especifica este caso; nenhuma grade foi retornada.");
            }
            // Alg. 3, linha 13: regiões-filhas são divisões de U, não envelopes apertados dos objetos.
            no.primeiro = new No(corte.primeiro);
            no.segundo = new No(corte.segundo);
            List<Envelope> anteriores = no.objetos;
            no.objetos = null;
            // children(n, split) não explicita a redistribuição: conservar todos os objetos
            // é uma complementação necessária. Ordem original, filho 1 antes do filho 2.
            for (int i = anteriores.size() - 1; i >= 0; i--) encaminhar(pendentes, no, anteriores.get(i));
        }
    }

    private static void encaminhar(ArrayDeque<Insercao> pendentes, No no, Envelope objeto) {
        // Alg. 3, linhas 14–18: interseção com cada filho; um objeto pode ir para ambos.
        if (no.segundo.regiao.intersects(objeto)) pendentes.push(new Insercao(no.segundo, objeto));
        if (no.primeiro.regiao.intersects(objeto)) pendentes.push(new Insercao(no.primeiro, objeto));
    }

    static Corte escolherCorte(Envelope regiao, List<Envelope> objetos) {
        // Alg. 3, linha 11: centros dos MBRs originais, sem recorte na região atual.
        double[] xs = new double[objetos.size()];
        double[] ys = new double[objetos.size()];
        for (int i = 0; i < objetos.size(); i++) {
            Envelope mbr = objetos.get(i);
            xs[i] = meio(mbr.getMinX(), mbr.getMaxX());
            ys[i] = meio(mbr.getMinY(), mbr.getMaxY());
        }
        Corte x = candidato(regiao, Eixo.X, mediana(xs));
        Corte y = candidato(regiao, Eixo.Y, mediana(ys));
        if (x == null) return y;
        if (y == null) return x;
        // Alg. 3, linha 12: argmax do produto das áreas; empate X é convenção local.
        return x.produto.compareTo(y.produto) >= 0 ? x : y;
    }

    private static Corte candidato(Envelope regiao, Eixo eixo, double posicao) {
        double min = eixo == Eixo.X ? regiao.getMinX() : regiao.getMinY();
        double max = eixo == Eixo.X ? regiao.getMaxX() : regiao.getMaxY();
        // Política explícita para medianas na borda/fora da célula; não deslocar nem recortar medianas.
        if (!(posicao > min && posicao < max)) return null;
        Envelope primeiro = eixo == Eixo.X
                ? new Envelope(min, posicao, regiao.getMinY(), regiao.getMaxY())
                : new Envelope(regiao.getMinX(), regiao.getMaxX(), min, posicao);
        Envelope segundo = eixo == Eixo.X
                ? new Envelope(posicao, max, regiao.getMinY(), regiao.getMaxY())
                : new Envelope(regiao.getMinX(), regiao.getMaxX(), posicao, max);
        return new Corte(eixo, posicao, primeiro, segundo, area(primeiro).multiply(area(segundo)));
    }

    private static BigDecimal area(Envelope regiao) {
        // Produto exato dos valores double representados: evita overflow/underflow e empates artificiais.
        BigDecimal largura = new BigDecimal(regiao.getMaxX()).subtract(new BigDecimal(regiao.getMinX()));
        BigDecimal altura = new BigDecimal(regiao.getMaxY()).subtract(new BigDecimal(regiao.getMinY()));
        return largura.multiply(altura);
    }

    private static double mediana(double[] valores) {
        Arrays.sort(valores);
        int meio = valores.length / 2;
        return valores.length % 2 == 1 ? valores[meio] : meio(valores[meio - 1], valores[meio]);
    }

    private static double meio(double a, double b) {
        // O primeiro caminho preserva subnormais; o segundo evita overflow de b-a.
        return Double.isFinite(b - a) ? a + (b - a) / 2 : a / 2 + b / 2;
    }

    private static List<ParticaoMetadata> extrairFolhas(No raiz) {
        var folhas = new ArrayList<ParticaoMetadata>();
        var pendentes = new ArrayDeque<No>();
        GeometryFactory factory = new GeometryFactory();
        pendentes.push(raiz);
        while (!pendentes.isEmpty()) {
            No no = pendentes.pop();
            if (no.folha()) {
                folhas.add(new ParticaoMetadata(folhas.size() + 1, factory.toGeometry(no.regiao).toText()));
            } else {
                pendentes.push(no.segundo);
                pendentes.push(no.primeiro);
            }
        }
        return List.copyOf(folhas);
    }

    @Override
    public ResultadoParticionamento processar(List<String> wkts) throws Exception {
        return processar(wkts, criarGrade(wkts, List.of()));
    }

    /** Associação posterior não altera os cortes. Use molde criado com as duas entradas completas. */
    @Override
    public ResultadoParticionamento processar(List<String> wkts, List<ParticaoMetadata> molde) throws Exception {
        return ParticionamentoPorMbr.processar(wkts, molde, "BSP");
    }
}
