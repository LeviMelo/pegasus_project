# SIAC Mulher 2026: resumos

Versões densas, para corte posterior. Autores e afiliações a preencher.

Os números vêm de `results/` e foram gerados pelos scripts desta pasta com
pegasus_data (branch `linkage`, 2026-09-30); a proveniência e as ameaças à
validade estão em `JOURNAL.md`. Os IC95% de proporções são exatos
(Clopper–Pearson).

---

## Resumo 1 (EPI-01): Cardiopatia materna registrada e desfechos maternos e neonatais: coorte nacional vinculada SIH–SINASC, Brasil, 2022

**Introdução.** A doença cardiovascular é hoje uma das principais causas de
morbimortalidade materna, e as diretrizes (ESC 2025) recomendam estratificação
de risco por lesão e cuidado por equipe cardio-obstétrica. No Brasil, as
estimativas nacionais de desfechos em gestantes cardiopatas vêm de coortes
clínicas de referência. Os sistemas nacionais registram separadamente a
internação do parto (SIH) e o nascido vivo (SINASC), e raramente são
vinculados em escala nacional.

**Objetivo.** Estimar, em coorte nacional vinculada, a frequência de
cardiopatia materna registrada nas internações de parto do SUS e sua
associação com desfechos maternos (UTI, óbito hospitalar, permanência) e
neonatais (prematuridade, baixo peso, Apgar, anomalia congênita), por
fenótipo cardíaco.

**Métodos.**
- **Delineamento.** Coorte retrospectiva nacional, 2022.
- **Vinculação.** Os 2.520.744 nascidos vivos do SINASC foram vinculados às
  7,1 milhões de AIHs do SIH/SUS por vinculação determinística 1:1 em passos.
  As chaves foram a data de nascimento da mãe, o estabelecimento (CNES) e a
  data do nascimento contida no período da internação.
- **Validação da vinculação.**
  - A taxa de pares ao acaso foi estimada por controle negativo: a mesma
    junção com a data de nascimento materna deslocada em sete dias.
  - Os pares foram checados contra variáveis não usadas na vinculação:
    diagnóstico obstétrico e concordância do município de residência.
- **Exposição.** Código em qualquer das 11 posições diagnósticas da AIH
  (principal, secundário e DIAGSEC1–9), em oito fenótipos:
  - valvopatia (I05–I09, I34–I39);
  - cardiopatia congênita (Q20–Q28);
  - cardiomiopatia ou insuficiência cardíaca (I42, I50, O90.3);
  - hipertensão pulmonar (I27);
  - arritmia (I47–I49);
  - doença isquêmica (I20–I25);
  - aortopatia (I71);
  - O99.4 isolado.
  
  A síndrome hipertensiva da gestação (O10–O16) foi analisada à parte.
- **Desfechos.**
  - Maternos: UTI (dias de UTI maiores que 0), óbito hospitalar e permanência.
  - Neonatais (SINASC): prematuridade (menos de 37 semanas), baixo peso (menos
    de 2.500 g), Apgar de 5º minuto abaixo de 7 e anomalia congênita.
- **Análise.** Proporções com IC95% exatos. Razões de taxas (RT) por Poisson
  com erro robusto, ajustadas por faixa etária materna (menos de 20, 20–34 e
  35 anos ou mais), síndrome hipertensiva, gestação múltipla e macrorregião.
- **Qualidade do registro.** Medida pela proporção de AIHs com algum
  diagnóstico secundário, por hospital.

**Resultados.**
- **Vinculação.** Foram vinculados 1.515.701 nascimentos (60,1%) a 1.515.163
  internações.
  - Taxa de pares ao acaso de 0,53% (limite superior do IC95% 0,55%).
  - 98,0% das internações vinculadas tinham diagnóstico obstétrico e 95,6%
    concordavam no município de residência.
  - Os não vinculados incluem necessariamente os partos não financiados pelo
    SUS, que não constam do SIH.
- **Frequência registrada.** Havia cardiopatia materna registrada em 776
  nascimentos (0,05%):
  - O99.4 isolado: 452;
  - cardiomiopatia ou insuficiência cardíaca: 126;
  - arritmia: 76;
  - cardiopatia congênita: 64;
  - valvopatia: 43;
  - doença isquêmica: 11;
  - hipertensão pulmonar: 8.
  
  A síndrome hipertensiva sem cardiopatia estava registrada em 83.179 (5,5%).
- **Comparados aos nascimentos sem cardiopatia registrada** (N = 1.514.925):

  | desfecho | com cardiopatia | sem cardiopatia | RT ajustada |
  |---|---|---|---|
  | UTI materna | 10,6% (IC95% 8,5–12,9; 82/776) | 0,5% | 15,3 (11,6–20,2) |
  | prematuridade | 21,1% (18,3–24,1) | 11,1% | 1,75 (1,53–2,00) |
  | baixo peso | 19,5% (16,7–22,4) | 8,8% | 1,94 (1,67–2,25) |
  | Apgar 5' abaixo de 7 | 3,1% (2,0–4,6) | 1,0% | 2,91 (1,96–4,32) |
  | anomalia congênita no recém-nascido | 3,1% (2,0–4,6) | 1,0% | — |
  | óbito materno hospitalar | 0,8% (0,3–1,7; 6 óbitos) | 0,02% (0,018–0,022) | — |
  
  A mediana de permanência foi de 3 dias versus 2.
- **Gradientes por fenótipo.**
  - Cardiomiopatia ou insuficiência cardíaca: prematuridade de 33,6%, baixo
    peso de 26,2% e UTI de 11,1%.
  - Cardiopatia congênita materna: anomalia congênita no recém-nascido em
    12,5% (8/64), cerca de 13 vezes a frequência de base.
  - Hipertensão pulmonar: UTI em 25% e permanência mediana de 7 dias.
  - Síndrome hipertensiva sem cardiopatia: UTI em 5,1% e prematuridade em
    22,6%.
- **Registro.** Apenas 12,2% das AIHs de parto vinculadas tinham algum
  diagnóstico secundário. 2.251 dos 2.823 hospitais (80%), responsáveis por
  51,2% dos nascimentos, nunca registraram um.

**Conclusão.** Nesta coorte nacional vinculada SIH–SINASC, a
cardiopatia materna registrada associou-se a risco de UTI 15 vezes maior e a
risco quase duas vezes maior de prematuridade e baixo peso. Houve gradientes
por fenótipo, e a cardiopatia congênita materna associou-se a anomalia
congênita no recém-nascido. A prevalência
registrada (0,05%) é uma ordem de grandeza inferior à esperada (1–4%): o
diagnóstico secundário é sub-registrado e concentrado em poucos hospitais. As
associações valem para a cardiopatia registrada, e a qualificação da
codificação é condição para a vigilância cardio-obstétrica com dados
administrativos.

---

## Resumo 2 (EPI-02): Doença cardiovascular oculta na mortalidade materna: o que a investigação do óbito revela no SIM, Brasil, 2014–2023

**Introdução.** A investigação dos óbitos de mulheres em idade fértil pode
alterar a causa básica declarada. O SIM guarda a causa original
(CAUSABAS_O) e a final (CAUSABAS), o que permite medir essa reclassificação.
Sabe-se que ela aumenta a contagem de mortes maternas. Não se sabe quanto da
mortalidade materna cardiovascular só aparece após a investigação.

**Objetivo.** Quantificar a migração da causa básica cardiovascular nos óbitos
maternos entre a declaração original e a causa final, e estimar os óbitos
cardiovasculares na gestação e no puerpério não classificados como maternos.

**Métodos.**
- **Dados.** Estudo descritivo com todos os óbitos femininos do SIM-DO,
  2014–2023.
- **Óbito materno.** Causa básica O00–O95, O98–O99 ou A34, F53, M83.0, D39.2 e
  E23.0; foram excluídas as mortes maternas tardias (O96–O97).
- **Óbito materno cardiovascular.** Causa básica:
  - O99.4 (doenças do aparelho circulatório complicando gravidez, parto e
    puerpério);
  - O90.3 (cardiomiopatia periparto);
  - O88.2 (embolia obstétrica por coágulo);
  - O22.3, O22.5, O87.1, O87.3 (tromboses venosas, inclusive cerebrais).
  
  A síndrome hipertensiva (O10–O16) foi uma categoria à parte.
- **Transições.** A causa original foi comparada com a final.
- **Menção nas linhas.** Contaram-se as menções cardiovasculares nas linhas
  A–D e II da declaração, excluídos os modos de morrer (I46 parada cardíaca,
  I95 hipotensão, I99).
- **Óbitos possivelmente não classificados.** Óbitos na gestação (OBITOGRAV) ou
  no puerpério de até 42 dias (OBITOPUERP) com causa básica circulatória
  (I00–I99) não materna.
- **Análise.** Proporções com IC95% exatos, por ano, período pandêmico,
  macrorregião e raça/cor.

**Resultados.**
- **Universo.** Entre 6.282.106 óbitos femininos, 17.749 foram maternos (de
  1.717 em 2014 a 3.038 em 2021 e 1.332 em 2023).
- **Causa original e investigação.**
  - A causa original estava preenchida em 99,8%.
  - Mudou em 38,9% (IC95% 38,2–39,6) dos óbitos maternos.
  - 26,1% (25,5–26,8) dos óbitos maternos finais não eram maternos na
    declaração original.
  - O nível de investigação foi municipal em 81,6% e não informado em 6,8%.
- **Óbitos maternos cardiovasculares.** Foram 2.133: 12,0% (11,5–12,5) dos
  óbitos maternos.
  - Distribuição: O99.4 em 60,4%, embolia obstétrica (O88.2) em 22,6% e
    cardiomiopatia periparto (O90.3) em 12,6%.
  - Causa original: apenas 1.207 (56,6%) eram cardiovasculares.
  - 926 (43,4%; IC95% 41,3–45,5) só foram atribuídos após a investigação, dos
    quais 557 (26,1% do total) partiram de causa circulatória não materna
    (capítulo I).
  - Em sentido contrário, 254 óbitos originalmente cardiovasculares saíram da
    categoria.
  - A investigação elevou a contagem cardiovascular em 46% (de 1.461 para
    2.133).
- **Revelação por período.** A fração revelada foi de 41,3% em 2014–2019,
  48,9% em 2020–2021 e 46,2% em 2022–2023.
- **Revelação por macrorregião.** Variou de 34,0% no Norte a 48,1% no
  Centro-Oeste.
- **Participação cardiovascular por macrorregião.** Foi de 7,7% dos óbitos
  maternos no Norte a 13,6% no Sudeste.
- **Participação cardiovascular por raça/cor.** Foi de 13,0% entre brancas,
  12,4% entre pretas, 11,7% entre pardas e 3,4% entre indígenas.
- **Menção nas linhas.** Entre os óbitos maternos não cardiovasculares, 18,1%
  (17,5–18,7) mencionavam condição cardiovascular nas linhas da declaração. Ao
  todo, 27,9% dos óbitos maternos tinham doença cardiovascular como causa
  básica ou associada.
- **Óbitos possivelmente não classificados.** Outros 877 óbitos com causa
  básica circulatória não materna ocorreram durante a gestação (626) ou até 42
  dias pós-parto (251). Houve ainda 720 no puerpério tardio. Os 877
  equivalem a 41,1% dos óbitos maternos cardiovasculares contabilizados.

**Conclusão.** Quase metade da mortalidade materna cardiovascular brasileira
só se torna visível após a investigação do óbito. 43% dos óbitos cardiovasculares
finais não o eram na declaração original, e 26% dos óbitos maternos finais não
eram maternos; a fração revelada foi menor no Norte (34%). A causa cardiovascular
aparece em mais de um quarto dos óbitos maternos quando se consideram as causas
associadas. Centenas de óbitos circulatórios na gestação e no puerpério
permanecem fora da categoria materna, o que sugere subestimação persistente.
Qualificar a investigação e a codificação de O99.4 é prioridade para a
vigilância cardio-obstétrica.

---

## Resumo 3 (EPI-04): Deslocamento para o parto e concentração hospitalar das gestantes com cardiopatia registrada no SUS, Brasil, 2022

**Introdução.** Gestantes com cardiopatia de risco moderado a alto devem
parir em centros com equipe cardio-obstétrica. No SUS, a regionalização define
onde esse cuidado deveria ocorrer, mas a rede real de deslocamentos e a
concentração do atendimento são pouco descritas em escala nacional.

**Objetivo.** Descrever o deslocamento intermunicipal, inter-regional e
interestadual e a concentração hospitalar das internações obstétricas com
cardiopatia registrada, comparadas às demais internações obstétricas.

**Métodos.**
- **Delineamento.** Estudo transversal com todas as AIHs principais (IDENT 1)
  do SIH/SUS de 2022 com diagnóstico obstétrico (capítulo XV) em qualquer
  posição.
- **Cardiopatia.** Códigos em qualquer das 11 posições diagnósticas:
  valvopatia, cardiopatia congênita, cardiomiopatia ou insuficiência cardíaca
  (incluindo O90.3), hipertensão pulmonar, arritmia, doença isquêmica,
  aortopatia e O99.4.
- **Deslocamento.** Município de residência diferente do município do
  hospital, em três níveis: fora do município, fora da região de saúde (CIR)
  e fora da UF.
- **Concentração.** Número de hospitais que somam metade das internações,
  participação dos 50 maiores e índice de Herfindahl–Hirschman (HHI).
- **Gravidade.** UTI e óbito hospitalar.
- **Análise.** Proporções com IC95% exatos, por macrorregião de residência.

**Resultados.**
- **Universo.** Das 2.492.174 internações obstétricas, 2.047 (0,08%) tinham
  cardiopatia registrada. Foram atendidas em 356 hospitais de 258 municípios,
  contra 3.305 hospitais para as demais.
- **Deslocamento.** Comparadas às demais internações obstétricas, as
  internações com cardiopatia ocorreram:
  - fora do município de residência em 41,4% (IC95% 39,2–43,5) versus 30,8%;
  - fora da região de saúde em 27,8% (25,9–29,8) versus 14,6%, quase o dobro;
  - fora da UF em 1,3% em ambos os grupos.
- **Por macrorregião,** a proporção fora da região de saúde foi de:
  - Sul 42,4% (sem nenhum deslocamento interestadual);
  - Nordeste 39,6%;
  - Norte 30,2% (5,2% fora da UF);
  - Centro-Oeste 16,5% (4,5% fora da UF);
  - Sudeste 15,9%.
- **Concentração.**
  - Metade das internações concentrou-se em 22 hospitais, e 65,9% nos 50
    maiores (HHI 0,019).
  - Destinos principais: São Paulo (237; 34,6% de fora do município), Lages
    (132), Maceió (88; 55,7%), Salvador (80; 46,3%), Blumenau (72), Recife
    (60; 80,0%) e Florianópolis (56).
- **Gravidade.** UTI em 10,1% (8,8–11,5) versus 0,7%; óbito hospitalar em 0,6%
  (0,3–1,1) versus 0,04%.

**Conclusão.** Gestantes com cardiopatia registrada deixam sua região de
saúde para o parto com frequência quase duas vezes maior que as demais
gestantes, sobretudo no Sul e no Nordeste. O cuidado concentra-se em poucas
dezenas de hospitais, várias capitais atuando como polos regionais (em Recife,
80% das internações vêm de outros municípios). O registro do diagnóstico
secundário é raro e desigual entre hospitais, e polos inesperados, como Lages,
podem refletir a prática de codificação. O passo seguinte é cruzar esses
fluxos com a capacidade cardio-obstétrica cadastrada no CNES e com o desfecho
dos casos.
