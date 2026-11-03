package benchmark;

import benchmark.algoritmos.*;
import benchmark.execucao.EstrategiaExecucao;

import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.HashMap;

/** Runner compartilhado pelas PPs: lê COPY TSV, aplica os algoritmos e exporta associações, sem JDBC. */
public final class ParticionamentoRunner {
    private record Entrada(List<Long> ids, List<String> wkts) { }
    private record GradeBsp(List<ParticaoMetadata> grade, int capacidade, String tentativas) { }

    public static void main(String[] args) throws Exception {
        var estrategia = EstrategiaExecucao.valueOf(obrigatoria("pp1.algoritmo"));
        int alvo = Integer.parseInt(obrigatoria("pp1.particoes"));
        int bits = Integer.parseInt(System.getProperty("pp1.hilbertBits", "16"));
        int tentativas = Integer.parseInt(System.getProperty("pp1.bspTentativas", "8"));
        String modelo = System.getProperty("pp1.modeloJoin", "MASJ");
        boolean samj = modelo.equals("SAMJ");
        if (!modelo.equals("MASJ") && !samj) throw new IllegalArgumentException("Modelo de join inválido");
        if (samj && estrategia != EstrategiaExecucao.STR && estrategia != EstrategiaExecucao.HILBERT)
            throw new IllegalArgumentException("SAMJ disponível somente para STR e Hilbert");
        if (alvo < 1 || tentativas < 1) throw new IllegalArgumentException("Alvo e tentativas devem ser positivos");
        var a = ler(Path.of(obrigatoria("pp1.entradaA")));
        var b = ler(Path.of(obrigatoria("pp1.entradaB")));
        Path saida = Path.of(obrigatoria("pp1.saida"));
        Files.createDirectories(saida);
        long n = (long) a.wkts.size() + b.wkts.size();
        int capacidade = (int) Math.max(1, (n + alvo - 1) / alvo);
        SpatialPartitioner particionador;
        List<ParticaoMetadata> grade;
        ParticionamentoConjunto conjunto = null;
        String calibracao = "[]";
        switch (estrategia) {
            case TWO_LAYER -> {
                int eixo = (int) Math.sqrt(alvo);
                if ((long) eixo * eixo != alvo) throw new IllegalArgumentException("Two-Layer requer alvo quadrado perfeito");
                var algoritmo = new TwoLayerPartitioner(eixo);
                particionador = algoritmo;
                grade = algoritmo.criarGrade(a.wkts, b.wkts);
            }
            case STR -> {
                var algoritmo = new SortTileRecursive(capacidade);
                particionador = algoritmo;
                if (samj) conjunto = algoritmo.processarConjunto(a.wkts, b.wkts);
                grade = samj ? conjunto.grade() : algoritmo.criarGrade(a.wkts, b.wkts);
            }
            case HILBERT -> {
                var algoritmo = new HilbertCurvePartitioner(capacidade, bits);
                particionador = algoritmo;
                if (samj) conjunto = algoritmo.processarConjunto(a.wkts, b.wkts);
                grade = samj ? conjunto.grade() : algoritmo.criarGrade(a.wkts, b.wkts);
            }
            case BSP -> {
                var escolha = calibrarBsp(a.wkts, b.wkts, alvo, capacidade, tentativas);
                capacidade = escolha.capacidade;
                grade = escolha.grade;
                calibracao = escolha.tentativas;
                particionador = new BinarySplitPartitioner(capacidade);
            }
            default -> throw new IllegalArgumentException("Estratégia não particionada ou não suportada: " + estrategia);
        }
        var resultadoA = samj ? conjunto.a() : particionador.processar(a.wkts, grade);
        long[] ocupacaoA = salvar(saida.resolve("a.tsv"), a, resultadoA, grade.size());
        var resultadoB = samj ? conjunto.b() : particionador.processar(b.wkts, grade);
        long[] ocupacaoB = salvar(saida.resolve("b.tsv"), b, resultadoB, grade.size());
        String plano = samj ? planoSamj(conjunto) : "";
        var ocupacoes = new ArrayList<String>();
        for (int i = 0; i < grade.size(); i++) {
            ocupacoes.add("{\"id\":" + grade.get(i).getIdParticao()
                    + ",\"objetos_a\":" + ocupacaoA[i] + ",\"objetos_b\":" + ocupacaoB[i] + "}");
        }
        String json = "{\"algoritmo\":\"" + estrategia + "\",\"particoes_alvo\":" + alvo
                + ",\"modelo_join\":\"" + modelo + "\""
                + ",\"particoes_efetivas\":" + grade.size()
                + ",\"capacidade\":" + (estrategia == EstrategiaExecucao.TWO_LAYER ? "null" : capacidade)
                + ",\"hilbert_bits\":" + (estrategia == EstrategiaExecucao.HILBERT ? bits : "null")
                + ",\"objetos_a\":" + a.ids.size() + ",\"objetos_b\":" + b.ids.size()
                + ",\"calibracao_bsp\":" + calibracao + ",\"ocupacoes\":[" + String.join(",", ocupacoes) + "]" + plano + "}";
        Files.writeString(saida.resolve("particionamento.json"), json + "\n", StandardCharsets.UTF_8);
        System.out.println("Preparado " + estrategia.name() + " / " + modelo + ": " + grade.size() + " partições; alvo=" + alvo);
    }

    private static String obrigatoria(String nome) {
        String valor = System.getProperty(nome);
        if (valor == null || valor.isBlank()) throw new IllegalArgumentException("Propriedade obrigatória: " + nome);
        return valor;
    }

    private static Entrada ler(Path arquivo) throws Exception {
        var ids = new ArrayList<Long>();
        var wkts = new ArrayList<String>();
        try (var reader = Files.newBufferedReader(arquivo, StandardCharsets.UTF_8)) {
            String linha;
            while ((linha = reader.readLine()) != null) {
                int tab = linha.indexOf('\t');
                if (tab < 1) throw new IllegalArgumentException("Entrada TSV inválida: " + arquivo);
                ids.add(Long.parseLong(linha.substring(0, tab)));
                wkts.add(linha.substring(tab + 1));
            }
        }
        return new Entrada(ids, wkts);
    }

    private static long[] salvar(Path arquivo, Entrada entrada, ResultadoParticionamento resultado, int particoes) throws Exception {
        long[] ocupacao = new long[particoes];
        boolean[] vistos = resultado.isAssociacaoUnica() ? new boolean[entrada.ids.size()] : null;
        try (BufferedWriter writer = Files.newBufferedWriter(arquivo, StandardCharsets.UTF_8)) {
            for (var objeto : resultado.getDados()) {
                int origem = objeto.getIndiceOrigem();
                if (origem < 0) throw new IllegalStateException("Associação sem índice de origem");
                if (vistos != null) {
                    if (vistos[origem]) throw new IllegalStateException("Objeto associado a mais de um grupo SAMJ");
                    vistos[origem] = true;
                }
                ocupacao[objeto.getIdParticao() - 1]++;
                writer.write(entrada.ids.get(origem) + "\t" + objeto.getIdParticao()
                        + "\t" + objeto.getClasse().name() + "\t" + objeto.getWkt());
                writer.newLine();
            }
        }
        return ocupacao;
    }

    /** Persiste envelopes por relação e pares únicos; pontos/linhas e contatos são conservados. */
    private static String planoSamj(ParticionamentoConjunto conjunto) throws Exception {
        var a = new HashMap<Integer, String>();
        var b = new HashMap<Integer, String>();
        for (var meta : conjunto.a().getGrades()) a.put(meta.getIdParticao(), meta.getWktFronteira());
        for (var meta : conjunto.b().getGrades()) {
            b.put(meta.getIdParticao(), meta.getWktFronteira());
        }
        var pares = new ArrayList<String>();
        for (var par : PlanoSamj.criar(conjunto).pares()) {
            pares.add("{\"a\":" + par.a() + ",\"b\":" + par.b() + "}");
        }
        var fronteiras = new ArrayList<String>();
        for (var meta : conjunto.grade()) fronteiras.add("{\"id\":" + meta.getIdParticao()
                + ",\"mbr\":" + wktJson(meta.getWktFronteira())
                + ",\"mbr_a\":" + wktJson(a.get(meta.getIdParticao()))
                + ",\"mbr_b\":" + wktJson(b.get(meta.getIdParticao())) + "}");
        return ",\"fronteiras\":[" + String.join(",", fronteiras)
                + "],\"pares_particoes\":[" + String.join(",", pares) + "]";
    }

    private static String wktJson(String wkt) { return wkt == null ? "null" : "\"" + wkt + "\""; }

    /** Busca limitada por capacidade; a replicação impede prometer monotonicidade ou 64 folhas. */
    private static GradeBsp calibrarBsp(List<String> a, List<String> b, int alvo, int inicial, int limite) throws Exception {
        int inferior = 1;
        int superior = (int) Math.min(Integer.MAX_VALUE, Math.max(1, (long) a.size() + b.size()));
        int capacidade = inicial;
        GradeBsp melhor = null;
        var tentativas = new ArrayList<String>();
        for (int i = 0; i < limite && inferior <= superior; i++) {
            try {
                var grade = new BinarySplitPartitioner(capacidade).criarGrade(a, b);
                tentativas.add("{\"capacidade\":" + capacidade + ",\"particoes\":" + grade.size() + "}");
                if (melhor == null || Math.abs((long) grade.size() - alvo) < Math.abs((long) melhor.grade.size() - alvo)) {
                    melhor = new GradeBsp(grade, capacidade, "");
                }
                if (grade.size() == alvo) break;
                if (grade.size() > alvo) inferior = capacidade + 1;
                else superior = capacidade - 1;
            } catch (IllegalArgumentException e) {
                // Capacidade maior pode evitar uma divisão sem mediana válida.
                tentativas.add("{\"capacidade\":" + capacidade + ",\"particoes\":null,\"falha\":true}");
                System.out.println("BSP b=" + capacidade + ": " + e.getMessage());
                inferior = capacidade + 1;
            }
            capacidade = inferior + (superior - inferior) / 2;
        }
        if (melhor == null) throw new IllegalArgumentException("BSP sem grade válida nas tentativas de calibração");
        return new GradeBsp(melhor.grade, melhor.capacidade, "[" + String.join(",", tentativas) + "]");
    }
}
