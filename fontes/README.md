# `fontes/` — universo monitorado

Este diretório responde a duas perguntas distintas, uma por arquivo:

| Arquivo | Pergunta que responde |
| ------- | --------------------- |
| `fontes.json` | **quem** o monitoramento observa (órgãos, bancas, portais, imprensa), com `tipo`, `esfera`, `prioridade` e marca de coleta automática |
| `municipios-es.json` | **por onde cada município publica** vaga, edital, concurso e processo seletivo — o cadastro canônico dos 78 municípios do ES e dos órgãos vinculados a eles |

Nenhum dos dois é dado curado de oportunidade: isso vive em `dados/`, governado por
`dados/ESQUEMA.md`.

## `fontes.json`

Catálogo de fontes. `tipo` ∈ `comum.TIPOS_FONTE_VALIDOS`
(`oficial`, `banca`, `diario_oficial`, `portal_concursos`, `imprensa`).

`esfera` usa o vocabulário **do catálogo**, que é mais largo que o dos registros de `dados/`:
`comum.ESFERAS_FONTE_VALIDAS` = `federal`, `estadual`, `municipal`, `intermunicipal` e
`nao_se_aplica`. A regra é verificável: fonte cujo `tipo` está em
`comum.TIPOS_FONTE_COM_ESFERA` (`oficial`, `diario_oficial`) declara a esfera de governo real;
toda outra declara `nao_se_aplica`. Uma banca ou um portal de concursos não pertence a nenhuma
esfera de governo, e `nao_se_aplica` diz isso — ao contrário de `"não informado"`, que
significaria "não sabemos".

## `municipios-es.json`

Cabeçalho com `descricao`, `fonte_da_verdade` (IBGE, UF 32), `ibge_consultado_em`,
`total_esperado` e `ultima_atualizacao`; depois `municipios` (exatamente `total_esperado`
entradas, uma por unidade territorial) e `orgaos_vinculados` (lista aberta).

O `slug` **nunca** é escrito à mão: ele é `comum.slug(nome)`, e o validador recalcula e compara.
O `total_esperado` vive só aqui — o literal `78` não aparece no código, para que a criação de um
79º município por lei seja detectada como divergência contra o IBGE em vez de reprovar o CI.

### Canais: vocabulário de `tipo` e regra de precedência

Cada município tem uma lista `canais`, porque a pergunta "por onde este município publica?" tem
mais de uma resposta, com ordem de prevalência. `tipo` ∈ `comum.TIPOS_CANAL`:

| `tipo` | O que é |
| ------ | ------- |
| `diario_oficial_proprio` | diário oficial do próprio município |
| `diario_oficial_agregador` | agregador onde os atos do município saem (DOM/AMUNES, Caderno dos Municípios do DIO) |
| `portal_prefeitura` | site institucional da prefeitura |
| `secao_concursos` | seção de concursos / editais / "trabalhe conosco" dentro de um portal |
| `plataforma_inscricao` | plataforma de terceiro usada para inscrição |
| `banca` | banca organizadora historicamente usada, só com evidência |

**Precedência.** `precedencia` é um inteiro ≥ 1, único dentro do município. `precedencia: 1` é
sempre um canal de diário quando existir algum, porque é o canal onde o ato tem fé pública — é o
ato publicado ali que a coleta encontra e que a cobertura conta. Tendo o município os dois tipos
de diário, o próprio recebe `1` e o agregador `2`. Os demais canais recebem `2, 3, …` na ordem de
utilidade para a curadoria humana. A precedência orienta o humano e **não** muda o comportamento
do coletor, que lê os dois escopos do IOES de qualquer modo.

**Publicar só pelo agregador não é lacuna.** A maior parte dos 78 municípios não tem diário
próprio: o DOM/AMUNES **é** o canal correto deles. Lacuna de cadastro é município sem nenhum
canal confirmado, ou com `canais:nao_encontrado`.

**`evidencia` é obrigatória em todo canal** e diz de onde o canal veio (registro de `dados/`,
fonte catalogada, ato observado na coleta, ou sondagem com o resultado medido). É o campo que
impede canal inventado: sem evidência, não se escreve o canal. Endereço não alcançável vira
pendência declarada, nunca link falso.

### Pendências de verificação, e quem produz cada motivo

Item de `pendencias_verificacao` tem a forma `campo` ou `campo:motivo`, com `campo` entre as
chaves da entrada e `motivo` ∈ `comum.MOTIVOS_PENDENCIA`. Motivo sem produtor seria vocabulário
morto — exigido pelo validador e nunca escrito no dado:

| Motivo | Quem produz | Significado |
| ------ | ----------- | ----------- |
| `conferir_manual` | `ferramentas/sondar_prefeituras.py` com 403/406/429 (e todo canal `pendente` sem resultado de sondagem conclusivo) | o host existe e responde, mas bloqueia robô; o canal **é** registrado, com `estado: "pendente"` |
| `nao_responde` | `ferramentas/sondar_prefeituras.py` com 404 / NXDOMAIN / timeout nas duas tentativas / erro TLS | a URL sondada não vira canal `confirmado`: fica `pendente` quando é URL catalogada, e não entra quando era candidato derivado |
| `nao_encontrado` | curadoria, em três campos: `canais` sem nenhum canal de diário identificado, `municipios_slugs` de órgão intermunicipal sem composição apurada e `url` de órgão vinculado sem endereço institucional localizado | foi procurado e nada foi achado — distinto de "não foi procurado" |

As formas que aparecem no dado são `canais:conferir_manual`, `canais:nao_responde`,
`canais:nao_encontrado`, `municipios_slugs:nao_encontrado` e `url:nao_encontrado`.

`estado: "confirmado"` exige `verificado_em` não nula e não futura; `verificado_em: null` obriga
`estado: "pendente"`.

### Sondagem dos candidatos de portal e seção

`python3 ferramentas/sondar_prefeituras.py` é de **uso único** na curadoria: não é chamado pelo
workflow e não escreve no cadastro. Ele deriva `https://www.<slug sem hífens>.es.gov.br/`,
substitui pelo candidato catalogado quando há fonte elegível (`tipo: "oficial"`,
`esfera: "municipal"`, `id` com prefixo `prefeitura-` e host institucional) e imprime uma linha
TSV por município: `slug`, `tipo`, `status`, `url`, `estado`, `pendência`.

O **`User-Agent` fica registrado aqui porque o resultado depende dele** — o mesmo endereço
responde 200 para um navegador e 403 para um robô:

```
Mozilla/5.0 (X11; Linux x86_64) Python-urllib monitoramento-concursos-es
```

Só `https://`, sem seguir redirecionamento, timeout de 12 s e **duas tentativas** antes de
concluir falha de rede (timeout isolado é ruído, não fato). Classificação: 2xx/3xx →
`confirmado`; 403/406/429 → `pendente` + `canais:conferir_manual`; 404/NXDOMAIN/timeout/TLS →
candidato derivado não entra, candidato catalogado entra `pendente` + `canais:nao_responde`.

### Órgãos vinculados

`orgaos_vinculados` existe para **duas** finalidades, e não como unidade de cadastro: reconhecer
o órgão no texto do diário e atribuir o ato ao(s) município(s) dele. Por isso a entrada **não tem
`canais`** — o órgão publica no mesmo diário do município — e tem um único `url` institucional.

`natureza` ∈ `comum.NATUREZAS_ORGAO_VINCULADO`. A aridade de `municipios_slugs` é por natureza:
câmara, autarquia, fundação e empresa municipal têm exatamente 1 slug; consórcio intermunicipal e
agência reguladora exigem `esfera: "intermunicipal"` e aceitam 0..N — com 0 slugs e pendência
declarada enquanto a composição não for apurada documentalmente. Órgão sem slug **é monitorado** e
**não credita** cobertura a município nenhum: atribuir cobertura a município adivinhado inflaria a
métrica com dado inventado.

### Regra de admissão de alias

`aliases` só recebe variante que muda a cadeia **já normalizada** por `comum.normalizar()`
(troca de preposição, encurtamento usual, abreviação de título, grafia consonantal divergente).
Variante puramente ortográfica é gratuita e seria ruído: `Guaçuí` → `guacui`,
`Marataízes` → `marataizes`, `Vila Pavão` → `vila-pavao` já casam sem alias.

Entra como alias **somente a variante observada** em (a) registro de `dados/`,
(b) `fontes/fontes.json`, (c) texto real de diário coletado ou (d) campo do próprio IBGE — e a
evidência tem de estar dita na descrição do PR. **O validador não consegue conferir evidência**,
então esta regra é imposta na revisão do PR; é limitação aceita e declarada. A lista cresce pelo
mecanismo de `municipios_nao_mapeados` da coleta, que entrega o nome observado com URL e trecho
de exemplo, isto é, com a evidência junto.
