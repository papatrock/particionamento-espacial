package benchmark.execucao;

import benchmark.*;
import benchmark.algoritmos.FixedGridPartitioner;
import benchmark.algoritmos.TwoLayerPartitioner;
import benchmark.banco.RepositorioEspacial;
import benchmark.configuracao.ConfiguracaoBanco;
import benchmark.resultados.ResultadoBenchmark;

import java.sql.Connection;
import java.util.function.Consumer;

/** Pipeline compartilhado por runners interativos e experimentos programáticos. */
public final class ExecutorBenchmark {
    private final ConfiguracaoBanco banco;
    private final Consumer<String> progresso;

    public ExecutorBenchmark(ConfiguracaoBanco banco) { this(banco, mensagem -> { }); }

    public ExecutorBenchmark(ConfiguracaoBanco banco, Consumer<String> progresso) {
        this.banco = banco;
        this.progresso = progresso;
    }

    public ResultadoBenchmark executar(CenarioTeste cenario, EstrategiaExecucao estrategia,
                                       int celulasPorEixo) throws Exception {
        try (Connection conn = banco.abrirConexao()) {
            var repositorio = new RepositorioEspacial(conn);
            if (estrategia == EstrategiaExecucao.SEM_PARTICIONAMENTO) {
                progresso.accept("Executando Spatial Join diretamente nas entradas...");
                var medicao = repositorio.joinDireto(cenario);
                return new ResultadoBenchmark(cenario, estrategia, null, medicao.intersecoes(), medicao.tempoMs());
            }

            progresso.accept("Extraindo " + cenario.datasetA().tabela() + "...");
            var a = repositorio.extrair(cenario.datasetA());
            progresso.accept("Extraindo " + cenario.datasetB().tabela() + "...");
            var b = repositorio.extrair(cenario.datasetB());
            progresso.accept("Registros extraídos: A=" + a.ids().size() + ", B=" + b.ids().size());
            ResultadoParticionamento resA;
            ResultadoParticionamento resB;
            if (estrategia == EstrategiaExecucao.TWO_LAYER) {
                var twoLayer = new TwoLayerPartitioner(celulasPorEixo);
                var grade = twoLayer.criarGrade(a.wkts(), b.wkts());
                resA = twoLayer.processar(a.wkts(), grade);
                resB = twoLayer.processar(b.wkts(), grade);
            } else {
                var fixedGrid = new FixedGridPartitioner();
                var grade = fixedGrid.criarGrade(a.wkts(), b.wkts());
                resA = fixedGrid.processar(a.wkts(), grade);
                resB = fixedGrid.processar(b.wkts(), grade);
            }
            int particoes = resA.getGrades().size();
            progresso.accept("Substituindo saídas com " + particoes + " partições por tabela...");
            repositorio.substituirSaidas(cenario, a, b, resA, resB);
            progresso.accept("Executando Spatial Join particionado...");
            var medicao = repositorio.joinParticionado(estrategia);
            return new ResultadoBenchmark(cenario, estrategia, particoes, medicao.intersecoes(), medicao.tempoMs());
        }
    }
}
