package benchmark.resultados;

import benchmark.CenarioTeste;
import benchmark.execucao.EstrategiaExecucao;

/** Tempo somente da consulta do join; partições é null no modo direto. */
public record ResultadoBenchmark(CenarioTeste cenario, EstrategiaExecucao estrategia,
                                 Integer particoes, long intersecoes, double tempoJoinMs) { }
