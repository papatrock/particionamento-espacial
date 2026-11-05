# Regiões candidatas

Saída de `medir_regioes.py`, executado em novembro de 2026 no `jatoba2`, com os filtros padrão: no máximo 10% de blocos vazios e proporção de até 3:1 entre linhas e polígonos. Janelas sem sobreposição dentro de cada lista, em `brasil_line`, `brasil_polygon` e `brasil_point`.

**Situação:** regiões escolhidas, em `criar_regioes.sql`. A faixa de 500 mil ainda depende de um piloto.

| Faixa | Papel | Região | Tabelas e JSON | Janela em SRID 3857 (xmin, ymin, xmax, ymax) |
| ----- | ----- | ------ | -------------- | -------------------------------------------- |
| 54 mil | Menor CV | Sul do Espírito Santo | `es_sul` | -4578000, -2352000, -4530000, -2304000 |
| 54 mil | Maior CV | Entorno de Campo Grande | `ms_campo_grande` | -6090000, -2400000, -5850000, -2160000 |
| 500 mil | Menor CV | Centro do Paraná | `pr_centro` | -5904000, -3072000, -5520000, -2688000 |
| 500 mil | Maior CV | Região de Curitiba | `pr_curitiba` | -5568000, -3048000, -5376000, -2856000 |

As janelas do centro do Paraná e da região de Curitiba se sobrepõem em 48 km (em SRID 3857) na longitude.

### Contagens finais, com `ST_Intersects`

| Região | Linhas | Polígonos | Total | Razão | Pontos |
| ------ | ------ | --------- | ----- | ----- | ------ |
| `es_sul` | 31.163 | 29.558 | 60.721 | 1,05 | 1.891 |
| `ms_campo_grande` | 34.603 | 25.625 | 60.228 | 1,35 | 13.838 |
| `pr_centro` | 288.114 | 272.686 | 560.800 | 1,06 | 66.348 |
| `pr_curitiba` | 225.443 | 333.219 | 558.662 | 1,48 | 476.404 |

### Limites administrativos

As quatro tabelas de polígonos têm limites administrativos aninhados: Brasil (4.387 km de largura em SRID 3857), fuso `America/Sao_Paulo`, macrorregiões, estados, regiões geográficas e municípios.

Join entre linhas e polígonos em `es_sul`, medido com `ST_Intersects`:

| Polígonos | Quantidade | Interseções | % das interseções |
| --------- | ---------- | ----------- | ----------------- |
| `boundary` = `administrative` ou `timezone` | 53 (0,18%) | 252.393 | 78,7% |
| `boundary` = `protected_area` | 14 | 330 | 0,1% |
| Sem `boundary` | 29.491 | 68.110 | 21,2% |
| **Total** | **29.558** | **320.833** | **100%** |

Os níveis 2, 3 e 4 e o fuso intersectam todas as 31.163 linhas. Cada linha tem, em média, 10,3 interseções.

**Decisão:** esses polígonos saem nas tabelas `<região>_polygon_mapa`, criadas por `filtrar_limites.sql`. A regra e o motivo estão na seção "Tratamento dos dados" de `definicao-testes.md`. A medição das interseções é só de `es_sul`.

| Região | Polígonos | Removidos | Mantidos | Linhas | Total usado | Razão | Pontos |
| ------ | --------- | --------- | -------- | ------ | ----------- | ----- | ------ |
| `es_sul_mapa` | 29.558 | 53 (0,18%) | 29.505 | 31.163 | 60.668 | 1,06 | 1.891 |
| `ms_campo_grande_mapa` | 25.625 | 254 (0,99%) | 25.371 | 34.603 | 59.974 | 1,36 | 13.838 |
| `pr_centro_mapa` | 272.686 | 735 (0,27%) | 271.951 | 288.114 | 560.065 | 1,06 | 66.348 |
| `pr_curitiba_mapa` | 333.219 | 708 (0,21%) | 332.511 | 225.443 | 557.954 | 1,47 | 476.404 |

As coordenadas exatas (`xmin`, `ymin`, `xmax`, `ymax`) estão em `/disk1/pol21/resultados/regioes/regioes_candidatas.csv`. Os nomes de lugares são aproximados, deduzidos das coordenadas, e precisam ser conferidos no mapa.

## Como ler

- **CV:** coeficiente de variação dos objetos de linhas + polígonos em 8 × 8 blocos. Vai de 0 (uniforme) até cerca de 7,94 (tudo em um bloco).
- **Lado:** medido em SRID 3857, que infla as distâncias (cerca de 10% na latitude de São Paulo).
- **Total:** linhas + polígonos. Cada objeto entra pelo centro do seu retângulo. Com a seleção por `ST_Intersects`, o total pode aumentar, porque objetos longos que só tocam a região também entram.
- **Razão:** maior relação dividida pela menor.

## Faixa de 54 mil objetos

**Par sugerido:** sul do Espírito Santo e entorno de Campo Grande. Os totais são quase iguais (60.023 e 60.001), e a proporção é parecida (1,06 e 1,35).

### Menor CV

| Região aproximada | Lon, lat do centro | CV | Vazios | Lado | Linhas | Polígonos | Total | Razão | Pontos |
| ----------------- | ------------------ | -- | ------ | ---- | ------ | --------- | ----- | ----- | ------ |
| Norte do Espírito Santo | -40,748; -18,890 | 0,177 | 0% | 48 km | 27.706 | 22.209 | 49.915 | 1,25 | 819 |
| **Sul do Espírito Santo (sugerida)** | -40,909; -20,463 | 0,182 | 0% | 48 km | 30.855 | 29.168 | 60.023 | 1,06 | 1.891 |
| Norte do Espírito Santo | -40,694; -19,298 | 0,201 | 0% | 48 km | 26.677 | 23.140 | 49.817 | 1,15 | 1.186 |
| Divisa do Espírito Santo com Minas Gerais | -41,502; -20,564 | 0,212 | 0% | 48 km | 38.126 | 23.667 | 61.793 | 1,61 | 1.452 |
| Centro do Espírito Santo | -40,640; -19,755 | 0,236 | 0% | 48 km | 32.862 | 27.871 | 60.733 | 1,18 | 1.662 |

### Maior CV

| Região aproximada | Lon, lat do centro | CV | Vazios | Lado | Linhas | Polígonos | Total | Razão | Pontos | Observação |
| ----------------- | ------------------ | -- | ------ | ---- | ------ | --------- | ----- | ----- | ------ | ---------- |
| Oeste de Manaus | -60,367; -3,412 | 6,887 | 9,4% | 80 km | 15.452 | 40.916 | 56.368 | 2,65 | 5.848 | Cidade em um canto da janela |
| Norte de Cuiabá | -56,414; -15,267 | 6,309 | 1,6% | 80 km | 18.365 | 34.667 | 53.032 | 1,89 | 18.434 | Cidade em um canto da janela |
| **Entorno de Campo Grande (sugerida)** | -53,629; -20,059 | 6,278 | 0% | 240 km | 34.416 | 25.585 | 60.001 | 1,35 | 13.838 | Sem blocos vazios |
| Nordeste do Pará | -47,970; -1,725 | 5,892 | 0% | 96 km | 16.768 | 44.076 | 60.844 | 2,63 | 4.729 | |
| Sudoeste de Mato Grosso | -57,205; -16,718 | 5,672 | 1,6% | 256 km | 20.483 | 29.575 | 50.058 | 1,44 | 7.646 | |

## Faixa de 500 mil objetos

Ainda precisa de um piloto, para confirmar que termina no tempo disponível.

**Par sugerido:** centro do Paraná e região de Curitiba. Os totais são quase iguais (559.241 e 558.059), as duas têm muitos pontos para o PP2 e o CV difere cerca de 5 vezes. Ressalvas: a proporção não é igual (1,05 e 1,48) e as janelas se sobrepõem em uma faixa estreita, de cerca de 0,4° de longitude.

**Alternativa:** norte do Espírito Santo e centro de Minas Gerais. Os totais são quase iguais (441.958 e 440.845) e a proporção é mais próxima (1,15 e 1,05), mas o Espírito Santo tem poucos pontos para o PP2.

**Proporção:** com o limite padrão de 3:1, todas as janelas de maior CV tinham cerca de 2,4 polígonos ou mais para cada linha, o que misturaria skew e proporção. Por isso, a tabela "Maior CV com proporção equilibrada" é a que deve ser usada na escolha.

### Menor CV

| Região aproximada | Lon, lat do centro | CV | Vazios | Lado | Linhas | Polígonos | Total | Razão | Pontos |
| ----------------- | ------------------ | -- | ------ | ---- | ------ | --------- | ----- | ----- | ------ |
| Sul do Espírito Santo | -41,233; -20,564 | 0,439 | 3,1% | 144 km | 272.218 | 201.857 | 474.075 | 1,35 | 15.227 |
| Norte do Espírito Santo | -40,514; -19,009 | 0,521 | 0% | 176 km | 236.276 | 205.682 | 441.958 | 1,15 | 14.942 |
| Centro do Paraná | -51,312; -25,035 | 0,610 | 0% | 384 km | 286.908 | 272.333 | 559.241 | 1,05 | 66.348 |
| Sul de Minas Gerais e divisa com São Paulo | -46,353; -21,068 | 0,714 | 0% | 320 km | 303.360 | 234.895 | 538.255 | 1,29 | 82.817 |
| Noroeste de São Paulo | -49,156; -20,564 | 0,762 | 0% | 288 km | 240.853 | 235.187 | 476.040 | 1,02 | 65.082 |

### Maior CV com proporção equilibrada (`--razao-max 1.5`)

Lista em `/disk1/pol21/resultados/regioes_razao15/regioes_candidatas.csv`.

| Região aproximada | Lon, lat do centro | CV | Vazios | Lado | Linhas | Polígonos | Total | Razão | Pontos |
| ----------------- | ------------------ | -- | ------ | ---- | ------ | --------- | ----- | ----- | ------ |
| Centro de Minas Gerais, com Belo Horizonte perto do canto | -44,916; -18,703 | 3,333 | 0% | 320 km | 225.763 | 215.082 | 440.845 | 1,05 | 89.977 |
| **Região de Curitiba (sugerida)** | -49,156; -25,619 | 3,131 | 0% | 192 km | 225.073 | 332.986 | 558.059 | 1,48 | 476.404 |
| Centro de Goiás, sul de Goiânia | -48,293; -16,993 | 3,124 | 0% | 256 km | 187.831 | 274.764 | 462.595 | 1,46 | 45.896 |
| Região do Rio de Janeiro e serra | -42,257; -22,303 | 2,993 | 6,2% | 224 km | 213.449 | 291.332 | 504.781 | 1,36 | 91.483 |
| Rondônia e oeste de Mato Grosso | -59,361; -11,985 | 2,919 | 6,2% | 896 km | 184.640 | 254.945 | 439.585 | 1,38 | 105.461 |

### Maior CV com o limite padrão (3:1)

| Região aproximada | Lon, lat do centro | CV | Vazios | Lado | Linhas | Polígonos | Total | Razão | Pontos |
| ----------------- | ------------------ | -- | ------ | ---- | ------ | --------- | ----- | ----- | ------ |
| Leste do Pará e Amazônia | -52,318; -1,006 | 5,015 | 1,6% | 896 km | 114.229 | 340.029 | 454.258 | 2,98 | 71.035 |
| Goiânia e Anápolis | -48,671; -16,425 | 4,889 | 0% | 144 km | 126.677 | 365.664 | 492.341 | 2,89 | 34.802 |
| Sudeste de São Paulo e litoral | -47,647; -24,447 | 4,784 | 6,2% | 208 km | 124.430 | 319.995 | 444.425 | 2,57 | 43.552 |
| Vale do Paraíba | -45,850; -23,066 | 4,426 | 0% | 128 km | 130.776 | 315.621 | 446.397 | 2,41 | 48.643 |
| Serra Gaúcha e norte de Porto Alegre | -50,611; -29,489 | 3,675 | 0% | 144 km | 145.193 | 361.196 | 506.389 | 2,49 | 53.886 |

## PP2

Precisa de pontos suficientes para usar o mesmo A nos três workloads, e as regiões de menor CV da faixa de 54 mil têm menos de 2 mil. Sugestão: usar as regiões do par da faixa de 500 mil, centro do Paraná e região de Curitiba, com A e B em cerca de 60 mil. As duas têm pontos suficientes.

A região de Curitiba vem do OSM. Não é o mesmo dado do dataset Curitiba, de outra fonte, então a comparação entre os dois não é direta.

## Descartadas

- **Primeira execução, sem filtros:** janelas de `maior_cv` com CV saturado ou muitos blocos vazios, em grande parte no mar ou fora do país (ao largo da Bahia, do Espírito Santo e do Ceará, e sobre o Paraguai).
- **Pelo filtro de proporção:** centro de São Paulo (-46,623; -23,544; 1:6,9) e norte de Goiás (-49,156; -14,781; 1:4,2).

## Próximos passos

1. Medir a faixa de 54 mil com e sem o filtro (`rodar_tudo.py`).
2. Avaliar o piloto da faixa de 500 mil, com o filtro (`rodar_tudo.py`).
