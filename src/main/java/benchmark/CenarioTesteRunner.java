package benchmark;

import benchmark.cenarios.CenariosBrasil;
import benchmark.cenarios.CenariosCuritiba;
import benchmark.configuracao.ConfiguracaoBanco;
import benchmark.execucao.EstrategiaExecucao;
import benchmark.execucao.ExecutorBenchmark;
import benchmark.resultados.ResultadoBenchmark;

import java.util.ArrayList;
import java.util.Scanner;

/** Entrada interativa: seleciona configurações, chama o executor e apresenta o resultado. */
public class CenarioTesteRunner {
    public static void main(String[] args) throws Exception {
        var cenarios = new ArrayList<CenarioTeste>();
        cenarios.addAll(CenariosCuritiba.listar());
        cenarios.addAll(CenariosBrasil.listar());

        Scanner scanner = new Scanner(System.in);
        
        System.out.println("\n=== CENÁRIOS DE TESTE ===");

        for (int i = 0; i < cenarios.size(); i++) {
            System.out.println((i + 1) + " - " + cenarios.get(i));
        }

        int escolhido = escolher(scanner, "Selecione o cenário: ", cenarios.size());
        var cenario = cenarios.get(escolhido - 1);
        String tabelaA = ConfiguracaoBanco.valor("tabela.a", "TABELA_A", cenario.datasetA().tabela());
        String tabelaB = ConfiguracaoBanco.valor("tabela.b", "TABELA_B", cenario.datasetB().tabela());
        cenario = new CenarioTeste(cenario.nomeCenario(),
                cenario.datasetA().comTabela(tabelaA), cenario.datasetB().comTabela(tabelaB));
        System.out.println("\nCenário selecionado: " + cenario);

        var estrategias = EstrategiaExecucao.values();
        System.out.println("\nSelecione o modo de execução:");
        for (int i = 0; i < estrategias.length; i++) {
            System.out.println((i + 1) + " - " + estrategias[i]);
        }
        var estrategia = estrategias[escolher(scanner, "Opção: ", estrategias.length) - 1];
        int celulas = estrategia == EstrategiaExecucao.TWO_LAYER
                ? Integer.parseInt(System.getProperty("twoLayer.celulasPorEixo", "10")) : 10;
        var executor = new ExecutorBenchmark(ConfiguracaoBanco.doAmbiente(), System.out::println);
        exibir(executor.executar(cenario, estrategia, celulas));
    }

    private static int escolher(Scanner scanner, String prompt, int limite) {
        while (true) {
            System.out.print(prompt);
            if (!scanner.hasNextLine()) throw new IllegalArgumentException("Entrada encerrada antes da seleção");
            try {
                int valor = Integer.parseInt(scanner.nextLine().trim());
                if (valor >= 1 && valor <= limite) return valor;
            } catch (NumberFormatException ignored) { }
            System.out.println("Escolha uma opção de 1 a " + limite + ".");
        }
    }

    private static void exibir(ResultadoBenchmark resultado) {
        System.out.println("\n=== RESULTADO DO CENÁRIO ===");
        System.out.println("Cenário: " + resultado.cenario());
        System.out.println("Modo: " + resultado.estrategia());
        System.out.println("Partições: " + (resultado.particoes() == null ? "não se aplica" : resultado.particoes()));
        System.out.println("Interseções encontradas: " + resultado.intersecoes());
        System.out.printf("Tempo do Spatial Join: %.3f ms%n", resultado.tempoJoinMs());
    }
}
