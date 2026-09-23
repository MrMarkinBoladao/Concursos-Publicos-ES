# Descobertas — área de quarentena da coleta automática

Este diretório **não contém dados curados**. É a saída bruta de
`ferramentas/coletar.py`, que roda todo dia pelo GitHub Actions.

## Por que existe

`dados/ESQUEMA.md` estabelece que o projeto **não inventa informação** e exige cerca
de 30 campos por registro: cargos com remuneração, jornada, requisitos e
escolaridade, taxa de inscrição, etapas de prova, banca, validade do certame.

Nenhuma fonte de listagem fornece isso. O portal Seleção ES devolve órgão, nome do
edital e datas de inscrição; um portal de concursos devolve órgão e número de vagas.
Despejar isso em `dados/` significaria preencher o resto com chute — exatamente o que
o esquema proíbe.

Então a coleta para aqui. `descobertas.json` responde **"o que existe lá fora que
ainda não está no repositório"**, sem se passar por dado conferido.

## O que tem no arquivo

`descobertas.json` traz o relatório da execução e a lista de achados.

| Campo | Significado |
| ----- | ----------- |
| `chave` | Identificador estável do achado na fonte. É o que permite diferenciar novidade de repetição entre execuções |
| `fonte_id` / `fonte_tipo` | Origem e confiabilidade, conforme `fontes/fontes.json` |
| `orgao`, `orgao_sigla`, `titulo` | Como a fonte nomeia a oportunidade |
| `inscricoes.inicio` / `.fim` | Datas informadas pela fonte. `null` quando ela não informa |
| `status_estimado` | **Derivado das datas**, não declarado pela fonte |
| `vagas_informadas` | Número de vagas segundo a fonte, ou `null` |
| `no_repositorio` | `true` quando o achado casa com um registro de `dados/` |
| `registro_repositorio` | `id` do registro correspondente, quando houver |
| `primeira_deteccao` | Primeira vez que a coleta viu este achado. Preservado entre execuções |
| `ultima_deteccao` | Última execução em que a fonte ainda listava o achado |
| `ausente_na_fonte` | `true` quando a fonte respondeu mas já não lista o achado |

## Fontes coletadas

| Fonte | Tipo | O que entrega |
| ----- | ---- | ------------- |
| `selecao-es` | `oficial` | Processos seletivos estaduais, com datas de inscrição reais. Endpoint JSON `POST /processos-seletivos/busca` do portal Seleção ES |
| `concursosnobrasil-es` | `portal_concursos` | Órgão e vagas de certames do ES, inclusive municipais que não passam pelo Seleção ES. Serve para **descobrir**, não para confirmar |

## Cobertura medida

Cobertura aferida comparando os achados com os registros que têm inscrições abertas
em `dados/` — ou seja, quanto da curadoria humana a coleta consegue reencontrar
sozinha:

| Recorte | Cobertura |
| ------- | --------- |
| Processos seletivos estaduais | 3/3 |
| Concursos federais (conselhos) | 2/2 |
| Concursos municipais | 2/2 |
| **Processos seletivos municipais** | **1/3** |

O ponto fraco é conhecido e tem causa estrutural: o Seleção ES cobre **apenas o
Estado**, então processos seletivos de prefeitura dependem só do portal de terceiros.
Nos dois casos não detectados:

- **Castelo** simplesmente não é listado pelo portal.
- **Vitória** aparece em **uma linha** do portal, que agrega três editais distintos
  (021, 022 e 007/008). Um item de origem não consegue casar com três registros —
  não é falha de casamento, é granularidade da fonte.

Não existe fonte única e estruturada para os municípios do ES: cada prefeitura
publica por conta própria. O caminho natural seria minerar o Diário Oficial dos
Municípios (`ioes.dio.es.gov.br`), que tem busca sobre um backend Elasticsearch —
mas devolve texto corrido de publicação, não campos, e exigiria extração pesada com
alto risco de ruído. Ficou fora de escopo deliberadamente.

## Janela de relevância

O Seleção ES devolve o acervo inteiro desde 2015 (mais de 250 processos). A coleta
descarta o que encerrou há mais de 90 dias — sem isso, o monitoramento afogaria em
histórico irrelevante. Ajuste com `--janela-dias`.

## Como um achado vira dado curado

Não automaticamente, e isso é deliberado. O caminho é:

1. Abrir a `url` do achado e ler o edital na fonte oficial.
2. Criar o registro em `dados/` seguindo `ESQUEMA.md`, com `fontes[]` apontando para
   o edital oficial — não para o portal que deu a dica.
3. Na próxima execução, a coleta reconhece o achado e marca `no_repositorio: true`.

## Rodando manualmente

```bash
python3 ferramentas/coletar.py --dry-run          # relata sem gravar
python3 ferramentas/coletar.py --fonte selecao-es # apenas uma fonte
python3 ferramentas/coletar.py --janela-dias 365  # amplia a janela
```

Uma fonte fora do ar **não interrompe** a execução: o erro fica registrado em
`fontes_consultadas` e a coleta segue com as demais.

## Detecção de coletor quebrado

O risco mais traiçoeiro numa coleta é o silencioso: o site muda de layout, a extração
passa a devolver **zero itens sem erro nenhum**, e o monitoramento segue "verde"
enquanto para de descobrir. Foi assim que a API pública que inspirou este coletor
morreu sem ninguém notar.

Por isso, quando uma fonte responde sem erro mas devolve zero itens **tendo trazido
itens na coleta anterior**, ela é marcada com `suspeita_extracao_vazia`, emite aviso
na execução do Actions e vira aviso do `validar.py`.
