# Design — Cobertura dos 78 municípios do ES

**Quarto passe — correções de especificação, arquitetura encerrada.** A revisão do terceiro passe
(`CHANGES_REQUESTED`: 2 HIGH, 11 MEDIUM, 8 NIT) **aprovou a arquitetura** e concentrou os
bloqueios em dois lugares onde duas seções do documento se contradiziam (a ordem do pipeline de
texto; a forma das chaves de casamento) e num conjunto de contadores definidos de um jeito e
exemplificados de outro. Nenhuma decisão de arquitetura foi reaberta neste passe: o que mudou é
**especificação** — ordem de estágios, forma de chave, valor de contador, regra de fusão, regra de
derivação de candidato, assinatura de função e linhas de validador. As respostas item a item estão
no **Anexo D**, e as duas divergências medidas contra o código real estão marcadas lá.

**Terceiro passe.** A revisão do segundo passe (`.agents/design-review.json`,
`CHANGES_REQUESTED`: 4 HIGH, 10 MEDIUM, 6 NIT) aceitou a arquitetura e concentrou os bloqueios
num único lugar: **o ponto onde o achado de diário encontra o código antigo de
`coletar.main()`**. As 20 findings foram endereçadas; as respostas item a item estão no
**Anexo C**. O Anexo B, com as respostas às 26 findings do primeiro passe, foi mantido porque
as decisões que ele justifica continuam valendo.

O diagnóstico da revisão estava correto nos 20 itens, e **confirmei cada um contra o código**
antes de corrigir (não reaproveitei a descrição): o vazamento da máscara de espaços
(`"PREFEITURA DE VILA VELHA SERRA"` → `serra` em confiança alta, e com `\x00` em baixa),
`_coberto("serra", {"serrana"}) is True`, `tokens_identidade("Prefeitura de Serra") == {"serra"}`,
os 37 achados sem `categoria` no arquivo versionado, a ausência de poda que alcance
`inscricoes.fim == null`, e `novos.append(achado)` para todo achado inédito sem registro casado.

As quatro HIGH se resolvem com **um único mecanismo novo**, e é a mudança estrutural deste
passe: uma função de normalização `normalizar_achado()` chamada por `main()` para **todo**
achado, de qualquer fonte, antes de qualquer decisão (§6.10). Era a peça que faltava — o
segundo passe especificou bem o coletor novo e o validador novo, e deixou implícito o contrato
entre eles.

Uma correção factual que nem o design nem a revisão tinham certa: os registros com
`esfera: "intermunicipal"` são **4 no total** (`ps-aries-es-analista-fiscalizacao-001-2026`,
`...-003-2026`, `ps-cim-polinorte-es-2026`, `ps-consorcio-caparao-es-2026`), e **2** deles são
ARIES — não "4 registros `ps-aries-es-*`", como os dois documentos afirmavam. Isso muda o caso
de §7.4: o registro que de fato credita um município por via indevida é
`ps-consorcio-caparao-es-2026`, com `municipio: "Divino de São Lourenço"` (município real),
enquanto `ps-cim-polinorte-es-2026` usa `"Diversos (ES) - Linhares e região"`, que §9.3 aceita
sem resolver.

---

## 1. Visão geral

O repositório monitora oportunidades do ES a partir de 38 fontes catalogadas
(`fontes/fontes.json`) e de dois coletores (`selecao-es`, `concursosnobrasil-es`). Dos 78
municípios do estado, **7** têm fonte própria catalogada (8 fontes municipais, sendo duas de
Aracruz: `prefeitura-aracruz` e `camara-aracruz`) e **nenhum lugar do repositório declara que
os 78 existem**. A consequência é estrutural: o coletor não tem como saber que Sooretama ou
Laranja da Terra deveriam ser monitorados, e a ausência de notícia sobre eles é
indistinguível de ausência de certame.

O design resolve isso com quatro peças, nesta ordem de dependência:

1. **Cadastro canônico** `fontes/municipios-es.json` — os 78 municípios com código IBGE, nome
   oficial, slug, aliases, microrregião e URLs *verificadas* ou declaradas pendentes. É a
   fonte da verdade sobre "quem deveria estar coberto".
2. **Coletor agregador** — duas fontes novas (`ioes-busca-dio`, `ioes-busca-dom`) que leem o
   buscador do IOES por **assunto**, não por município, e fazem o casamento município↔texto
   localmente. Troca 78 scrapers frágeis por um parser e ~80 requisições.
3. **Reconhecimento e sinalização de município** — cada achado carrega `municipio_slug` /
   `municipio_escopo` / `municipio_confianca`; nome de município capixaba que não resolve
   contra o cadastro entra em `municipios_nao_mapeados` e abre issue.
4. **Reforço do validador e do workflow** — correção do campo `esfera` nas 12 fontes, novas
   checagens sobre cadastro e catálogo, e inclusão de `fontes/**` nos gatilhos (hoje uma
   mudança em `fontes/` **não** dispara validação em PR).

A palavra-chave é **degradação graciosa**. O comportamento atual já é "uma fonte fora do ar
não derruba a coleta" (laço de `FONTES` em `coletar.py` com `try/except` por fonte). Tudo que
se acrescenta se encaixa nesse laço em vez de contorná-lo, e nada passa a escrever em
`dados/` — `descobertas/` continua sendo quarentena.

### 1.1 Fatos medidos que sustentam as decisões

| Fato | Medição |
| ---- | ------- |
| Municípios do ES | 78 (IBGE UF 32). `/projects/sandbox/ibge_es.json` tem os mesmos 78 `id` e `nome` da API |
| API do IBGE | responde **200 com `Content-Encoding: gzip`** mesmo sem `Accept-Encoding`; `urllib` não descomprime |
| Registros em `dados/` | **53**, dos quais **24** com `municipio: "Âmbito estadual (ES)"`; 18 valores distintos de `municipio`, e só 2 não são nome oficial (`"Âmbito estadual (ES)"`, `"Diversos (ES) - Linhares e região"`) |
| Catálogo | 38 fontes; **12 sem `esfera`** = `banca`(7) + `portal_concursos`(3) + `imprensa`(2); as 26 com `esfera` = `oficial`(23) + `diario_oficial`(3) |
| Fontes municipais | 8 fontes / **7 municípios**; `prefeitura-castelo` aponta para `educacao.castelo.es.gov.br` (portal de secretaria, não institucional) |
| Volume na janela de 7 dias | DIO `"concurso publico"` 16, DIO `"processo seletivo"` 8, DOM `"concurso publico"` 63, DOM `"processo seletivo"` **131** |
| Latência | ~1,0 s por requisição ao buscador |
| `descobertas.json` versionado | **37 achados**, nenhum com `categoria` nem campo `municipio_*`; 8 chaves de topo |

---

## 2. Stack e restrições (travadas após aprovação)

| Item | Decisão |
| ---- | ------- |
| Linguagem | Python compatível com **3.9** (sandbox é 3.9.25) e 3.11 (CI). Proibido `match`, `X \| Y` em anotação avaliada em runtime, `dict \| dict`. Manter `from __future__ import annotations` nos módulos novos. |
| Dependências | **Somente biblioteca padrão**: `urllib.request`, `urllib.parse`, `urllib.error`, `json`, `re`, `unicodedata`, `html.parser`, `datetime`, `argparse`, `os`, `sys`, `http.cookiejar`, **`gzip`**, **`time`**, **`socket`**, **`functools`**, **`collections`**, **`unittest`**. Sem `requests`, `bs4`, `pyyaml`. |
| Formato de dados | JSON UTF-8, `ensure_ascii=False`, `indent=2`, newline final — igual ao que `coletar.py` já grava. |
| Idioma | pt-BR em nomes de arquivo, chaves JSON, logs, comentários e docs. **Convenção de acento por arquivo**: `.md` com acentos (como `ESQUEMA.md`); `.py` sem acentos em comentários e docstrings (como `comum.py`); valores de dados JSON com acentos (`"Vitória"`); chaves JSON sem acentos (`microrregiao`, `codigo_ibge`). |
| Comentários | Comentário longo em português explicando **o porquê** é a convenção forte deste código. Todo bloco não óbvio (máscara de boilerplate, ordem de casamento, poda de captura, tetos de paginação) precisa de um. |

`gzip` porque o IBGE responde comprimido (§7.3), `time` para a pausa de cortesia entre
requisições, `socket` para `socket.timeout` no retry, `functools` para `lru_cache` no índice do
cadastro, e **`collections` para o `namedtuple` do índice** (§5.1) — este último é acréscimo
deste passe, porque o segundo passe usava `namedtuple` nos snippets sem declarar o módulo, o
que tornava os próprios exemplos inválidos sob esta restrição.

---

## 3. Decisão 1 — onde vive o cadastro

**Alternativas.** (a) `dados/municipios-es.json`; (b) `fontes/municipios-es.json`.

**Escolha: `fontes/municipios-es.json`.** Razões lidas do código:

- `dados/` é governado por `dados/ESQUEMA.md`, que define "uma oportunidade = um arquivo JSON"
  nomeado `<id>.json`. Um cadastro de municípios não é uma oportunidade.
- `comum.carregar_registros()` varre apenas os seis subdiretórios de `comum.DIRETORIOS`, então
  um arquivo na raiz de `dados/` não seria lido por acidente — mas `validar.valida_diretorio()`
  reprova com "diretorio desconhecido" qualquer registro fora daqueles seis, e pôr arquivo de
  outra natureza na mesma árvore convida exatamente esse erro em varreduras futuras.
- `fontes/` já é o lugar do "onde e quem observar": `fontes.json` tem `descricao`, `escopo`,
  `ultima_atualizacao` e uma lista. O cadastro é da mesma natureza — universo monitorado.
- Ganho operacional: a correção do gatilho (`fontes/**`, §10.1) passa a cobrir cadastro e
  catálogo com uma única mudança.

### 3.1 Esquema de `fontes/municipios-es.json`

**O eixo do cadastro é o canal de publicação, não a entidade administrativa.** Esta é a
clarificação do usuário incorporada neste passe, verbatim: *"São as plataformas que cada município
usa pra mandar informações a respeito de emprego."* A pergunta que cada entrada responde é
**"por onde este município publica vaga, edital, concurso e processo seletivo?"** — e há mais de
uma resposta por município, com ordem de prevalência. Por isso o par
`url_prefeitura` + `url_diario_oficial` + `diario_oficial_em` do passe anterior **não serve**: são
três campos escalares para uma relação 1→N, e não tinham onde guardar a seção "trabalhe conosco",
a plataforma de inscrição nem a banca historicamente usada. A forma correta é uma lista `canais`.

```jsonc
{
  "descricao": "Cadastro canonico dos municipios do ES e dos canais por onde cada um publica informacao de emprego.",
  "fonte_da_verdade": "IBGE - Localidades, UF 32 (https://servicodados.ibge.gov.br/api/v1/localidades/estados/32/municipios)",
  "ibge_consultado_em": "2026-10-01",
  "total_esperado": 78,
  "ultima_atualizacao": "2026-10-01",
  "municipios": [
    {
      "codigo_ibge": 3204906,
      "nome": "Sooretama",
      "slug": "sooretama",
      "aliases": [],
      "microrregiao": "Linhares",
      "canais": [
        {
          "tipo": "diario_oficial_agregador",
          "precedencia": 1,
          "url": "https://ioes.dio.es.gov.br/dom",
          "fonte_id": "amunes-dom",
          "estado": "confirmado",
          "evidencia": "ato do municipio observado no DOM/AMUNES na janela medida (2026-09-24..10-01)",
          "verificado_em": "2026-10-01"
        }
      ],
      "pendencias_verificacao": ["canais:conferir_manual"],
      "verificado_em": "2026-10-01"
    },
    {
      "codigo_ibge": 3201209,
      "nome": "Cachoeiro de Itapemirim",
      "slug": "cachoeiro-de-itapemirim",
      "aliases": ["Cachoeiro do Itapemirim", "Cachoeiro"],
      "microrregiao": "Cachoeiro de Itapemirim",
      "canais": [
        {
          "tipo": "diario_oficial_agregador",
          "precedencia": 1,
          "url": "https://ioes.dio.es.gov.br/dom",
          "fonte_id": "amunes-dom",
          "estado": "confirmado",
          "evidencia": "ato do municipio observado no DOM/AMUNES na janela medida",
          "verificado_em": "2026-10-01"
        },
        {
          "tipo": "secao_concursos",
          "precedencia": 2,
          "url": "https://www.cachoeiro.es.gov.br/editais/",
          "fonte_id": "prefeitura-cachoeiro",
          "estado": "pendente",
          "evidencia": "url catalogada em fontes.json; host deu timeout na sondagem de 2026-10-01",
          "verificado_em": null
        }
      ],
      "pendencias_verificacao": ["canais:nao_responde"],
      "verificado_em": "2026-10-01"
    }
  ],
  "orgaos_vinculados": [ /* §4 */ ]
}
```

**Os dois exemplos são o caso comum e o caso difícil.** Sooretama é o **caso comum e esperado**:
publica exclusivamente via DOM/AMUNES, tem **um** canal, e esse canal é `confirmado` por evidência
forte (ato do próprio município observado na coleta). Ele **não** é um município "descoberto pela
metade" — ver a nota de cobertura no fim desta seção. Cachoeiro é o difícil: está ao mesmo tempo no
conjunto das URLs catalogadas reaproveitáveis **e** no dos hosts que falharam na sondagem, então o
canal catalogado é registrado com `estado: "pendente"` + pendência `canais:nao_responde`, enquanto
o canal de diário segue `confirmado`. Nenhuma URL é afirmada como verificada sem sondagem, e
nenhuma URL real é descartada por o robô ter sido bloqueado.

| Campo | Tipo | Obrigatório | Regra |
| ----- | ---- | ----------- | ----- |
| `codigo_ibge` | int | sim | 7 dígitos, começa com `32`. Chave primária real. |
| `nome` | string | sim | Nome oficial do IBGE, **com acentos**, exatamente como na API. |
| `slug` | string | sim | Derivado de `nome` por `comum.slug()`. Nunca escrito à mão (§9.2). |
| `aliases` | lista de strings | sim (pode ser `[]`) | Só variante **observada**, com evidência (§3.3). |
| `microrregiao` | string | sim | `microrregiao.nome` do IBGE. Recorte de agregação dos relatórios. |
| `canais` | lista de objetos | sim (pode ser `[]`) | Canais de publicação, forma na tabela abaixo. `[]` só com pendência declarada. |
| `pendencias_verificacao` | lista de strings | sim | Item na forma `campo` ou `campo:motivo`. Vocabulário e produtor de cada motivo na tabela adiante. |
| `verificado_em` | data ISO \| `null` | sim | Data da última curadoria da entrada (a data por canal fica no canal). |

#### 3.1.1 Forma do canal

| Campo do canal | Tipo | Obrigatório | Regra |
| -------------- | ---- | ----------- | ----- |
| `tipo` | string | sim | Vocabulário fechado de 6 valores, abaixo. |
| `precedencia` | int ≥ 1 | sim | Ordem de prevalência **dentro do município**; única por município (§9.2). `1` = canal onde o ato tem fé pública. |
| `url` | string \| `null` | sim | `https://...`. `null` **somente** para canal cuja identidade não é uma URL (`banca` sem portal próprio). **Nunca inventada** (§3.2). |
| `fonte_id` | string \| `null` | sim | `id` existente em `fontes/fontes.json`, quando o canal já está catalogado; `null` quando não há entrada de catálogo. |
| `estado` | `"confirmado"` \| `"pendente"` | sim | `confirmado` = sondagem 2xx/3xx **ou** ato do município observado naquele canal. `pendente` = URL real mas não confirmada (403/406/429) ou catalogada e não sondada. |
| `evidencia` | string | sim | Uma frase dizendo **de onde** o canal veio: registro de `dados/`, fonte catalogada, ato observado na coleta, ou sondagem com o resultado. É o campo que impede canal inventado — sem evidência, não se escreve o canal. |
| `verificado_em` | data ISO \| `null` | sim | Data da confirmação. `null` obriga `estado: "pendente"` (§9.2). |

**Vocabulário de `tipo`**, fechado em `comum.TIPOS_CANAL`, um por pergunta que a curadoria faz:

| `tipo` | O que é | Exemplo medido |
| ------ | ------- | -------------- |
| `diario_oficial_proprio` | diário oficial do próprio município | Serra (`/diariodaserra` no IOES, §18.2) |
| `diario_oficial_agregador` | agregador onde os atos do município saem | `amunes-dom` (DOM/AMUNES), `diario-oficial-es` (Caderno dos Municípios do DIO) |
| `portal_prefeitura` | site institucional da prefeitura | `https://www.vitoria.es.gov.br/` |
| `secao_concursos` | seção de concursos / editais / "trabalhe conosco" dentro do portal | `https://www.cachoeiro.es.gov.br/editais/`, `https://educacao.castelo.es.gov.br/processos-seletivos` |
| `plataforma_inscricao` | plataforma de terceiro usada para inscrição | portal de inscrição apontado por edital do município |
| `banca` | banca organizadora historicamente usada, **só com evidência** | banca citada em registro de `dados/` daquele município |

**Regra de precedência, decidida:** `precedencia: 1` é sempre um canal de diário
(`diario_oficial_proprio` ou `diario_oficial_agregador`) quando existir algum, porque é o canal com
fé pública — é o ato publicado ali que a coleta encontra e que a cobertura conta (§7.4). Os demais
canais (portal, seção, plataforma, banca) recebem `2, 3, ...` na ordem de utilidade para a
curadoria humana. Quando um município tem **os dois** tipos de diário, o próprio recebe `1` e o
agregador `2`, e a razão está escrita no `evidencia` de cada um; a coleta continua lendo os dois
escopos do IOES de qualquer modo (§6.3), logo a precedência orienta o humano e **não** muda o
comportamento do coletor.

**Vocabulário de `motivo` de pendência, cada um com produtor declarado.** Motivo sem produtor é
vocabulário morto — fica no validador dando impressão de cobertura e nunca aparece no dado:

| Motivo | Quem produz | Significado |
| ------ | ----------- | ----------- |
| `conferir_manual` | sondagem de §3.2 com 403/406/429 | o host existe e responde, mas bloqueia robô; o canal **é** registrado, com `estado: "pendente"` |
| `nao_responde` | sondagem de §3.2 com 404 / NXDOMAIN / timeout / erro TLS | a URL sondada **não** entra como canal `confirmado`: ou fica `pendente` (quando é URL catalogada, caso de Cachoeiro) ou não entra |
| `nao_encontrado` | curadoria, em três campos: `canais` quando nenhum canal de diário foi identificado; `municipios_slugs` de órgão intermunicipal sem composição apurada (§4); e `url` de órgão vinculado sem endereço institucional localizado (§4.1) | foi procurado e nada foi achado — distinto de "não foi procurado" |

As formas que aparecem no dado são exatamente `canais:conferir_manual`, `canais:nao_responde`,
`canais:nao_encontrado`, `municipios_slugs:nao_encontrado` e `url:nao_encontrado`. O validador
(§9.2) exige que o `campo` do item exista no esquema da entrada e que o motivo esteja nesta tabela
— é esse par de exigências que mantém vocabulário e validador falando a mesma língua, e foi a
incoerência que a revisão do terceiro passe apontou (`url_diario_oficial:*` era exigido pelo
validador e nenhum produtor o escrevia).

**Publicar só pelo agregador não é lacuna, e a auditoria não deve contá-lo como tal.** A maior
parte dos 78 municípios não tem diário próprio: o DOM/AMUNES **é** o canal correto deles, e um
município com um único canal `diario_oficial_agregador` em `estado: "confirmado"` está
**completamente mapeado** para o propósito deste repositório. Lacuna de cadastro é outra coisa, e
tem nome: município **sem nenhum canal confirmado** (§9.2 avisa) ou com
`canais:nao_encontrado`. Por isso o README não tem coluna "Fonte própria" sugerindo falta, e sim
"Canal principal" dizendo qual é (§11.1).

### 3.2 Regra de dados: URL não sondada não entra, mas HTTP 403 não é ausência

O padrão de domínio é **candidato a verificar**, nunca resposta: medi que
`https://www.cachoeiro.es.gov.br/` é o domínio real de Cachoeiro de Itapemirim, isto é, o slug
não prevê o domínio; e `www.atiliovivacqua.es.gov.br` nem resolve em DNS.

Sondei 14 candidatos com o `User-Agent` do projeto
(`Mozilla/5.0 (X11; Linux x86_64) Python-urllib monitoramento-concursos-es`), sem seguir
redirecionamento, timeout 12 s:

| Resposta | Domínios |
| -------- | -------- |
| 200 | `laranjadaterra`, `serra`, `colatina`, `novavenecia` |
| 301 / 302 | `iuna` (301), `linhares` (302), `guacui` (302) |
| **403** | `sooretama`, `marataizes`, `vilapavao`, `saoroquedocanaa`, `joaoneiva` |
| NXDOMAIN | `atiliovivacqua` |
| timeout | `cachoeiro` |

A regra "aceitar apenas 200" do passe anterior jogaria para pendência **cinco domínios que
existem e respondem** — incluindo três dos seis nomes difíceis que este trabalho precisa
cobrir (Marataízes, São Roque do Canaã, Vila Pavão). Isso não é "dado ausente melhor que
inventado": é dado real descartado por WAF bloqueando robô. Critério corrigido:

```
2xx ou 3xx                        -> canal com estado "confirmado"; verificado_em = data da sondagem
403 / 406 / 429                   -> canal REGISTRADO com estado "pendente", verificado_em null,
                                     + pendencia "canais:conferir_manual"
                                     (o dominio existe e responde; bloqueio de robo nao e ausencia)
404 / NXDOMAIN / timeout / erro TLS -> candidato DERIVADO nao entra como canal;
                                     candidato CATALOGADO entra com estado "pendente"
                                     (a url existe no catalogo, so nao foi confirmada);
                                     nos dois casos + pendencia "canais:nao_responde"
```

A assimetria da última linha é deliberada e é o caso de Cachoeiro: um host que eu **derivei** e que
não responde é palpite não confirmado, e palpite não vira dado; uma URL que **alguém catalogou** e
que não responde hoje é dado de procedência conhecida, e apagá-la perderia informação real — ela
fica no cadastro marcada `pendente`, com a sondagem registrada em `evidencia`.

O `User-Agent` usado fica registrado em `fontes/README.md`, porque o resultado depende dele.

**Reaproveitamento das URLs já catalogadas — escolhe o candidato, não dispensa a sondagem.**
Esta é a regra que o passe anterior deixou ambígua, e a ambiguidade produziu um exemplo
impossível (§3.1). Decidido, em três partes:

1. **O catálogo fornece o candidato.** Entra na lista de candidatos a canal a fonte
   com `tipo == "oficial"`, `esfera == "municipal"`, `id` começando com `prefeitura-` **e host
   institucional do município**. Isso dá **6**: Vitória, Anchieta, Santa Maria de Jetibá
   (`pmsmj.es.gov.br`), Aracruz, Cachoeiro, Vila Velha.
2. **O `tipo` do canal vem da forma da URL catalogada, e nada é descartado.** URL de raiz
   (`scheme://host/`) → `portal_prefeitura`; URL com caminho → `secao_concursos`, com o caminho
   **preservado** (`https://www.cachoeiro.es.gov.br/editais/` é exatamente a seção de editais que a
   curadoria quer abrir). Esta é a diferença em relação ao passe anterior, que normalizava a URL
   para `scheme://host/` e jogava o caminho fora porque só havia um campo escalar para guardá-lo.
   Com `canais` os dois cabem: quem tiver as duas informações cadastra os dois canais, com
   precedências distintas.
3. **Todo canal de URL passa pela sondagem da tabela acima, inclusive essas 6.** São 6
   requisições a mais, uma única vez, no povoamento — e **nenhuma** no CI. Dispensar a sondagem
   por a URL "já estar catalogada" obrigaria a escrever `verificado_em` sem verificação, que é
   exatamente o que §3.2 proíbe, ou a deixar `verificado_em: null` com `estado: "confirmado"`, que
   §9.2 torna erro. A tabela de sondagem é a **única** regra de preenchimento de `estado`.

Consequência medida: Cachoeiro é candidato pelo catálogo **e** deu timeout na sondagem; a
sondagem vence quanto ao `estado`, e o resultado é o canal `secao_concursos` com
`estado: "pendente"` + `canais:nao_responde` (§3.1). Os dois casos que o passe anterior tratava
como exceção deixam de ser exceção, porque agora têm `tipo` próprio:

- `camara-aracruz` → **não** é canal de município: vai para `orgaos_vinculados[].url` (§4);
- `prefeitura-castelo` (`https://educacao.castelo.es.gov.br/processos-seletivos`) → canal
  `secao_concursos` de Castelo, com `fonte_id: "prefeitura-castelo"`. Era o caso que não caberia em
  `url_prefeitura` (não é o portal institucional) e que agora cabe exatamente, sem perder o
  caminho e sem afirmar que é o site da prefeitura.

**A tabela de 14 sondagens acima não é dado de implementação.** Ela justifica a *regra* (403 não
é ausência), e os números dependem de WAF, data e `User-Agent`. A implementação **re-sonda os 78
candidatos** e grava o que medir; copiar esta tabela para o cadastro seria afirmar como verificado
um resultado de outro dia.

**De onde sai o candidato de cada um dos 78, e quem roda a sondagem.** A regra acima diz como
*aceitar* um resultado e não dizia como *obter* o candidato dos 72 municípios sem fonte catalogada —
dois implementadores produziriam cadastros diferentes. Três decisões fecham isso:

1. **Candidato derivado, um só por município:** `https://www.<slug sem hifens>.es.gov.br/`. Os
   hosts da tabela de 14 foram construídos exatamente assim (`laranjadaterra`, `saoroquedocanaa`,
   `vilapavao`, `atiliovivacqua`), e é a fórmula que o estado usa de fato. Ela **não** é previsão:
   é palpite de candidato, e a sondagem é quem decide — Cachoeiro (`cachoeiro` e não
   `cachoeirodeitapemirim`) é o contraexemplo que prova que o slug não prevê o domínio, e ele cai
   no item 2.
2. **Fonte catalogada elegível substitui o derivado.** Havendo fonte do catálogo elegível pelo
   critério de três partes acima (os **6**: Vitória, Anchieta, Santa Maria de Jetibá, Aracruz,
   Cachoeiro, Vila Velha), o candidato é a URL catalogada **normalizada para `scheme://host/`**, e
   o derivado é descartado. Só `https://`; nenhuma tentativa de HTTP→HTTPS, e falha de TLS cai em
   `nao_responde` pela tabela acima.
3. **A sondagem tem dono: `ferramentas/sondar_prefeituras.py`** (novo, declarado em §17). Script de
   **uso único** na curadoria: lê o cadastro (ou a lista de 78 slugs), deriva o candidato pelas
   regras 1–2, sonda com o `User-Agent` do projeto e **imprime** uma linha TSV por candidato —
   `slug → (tipo_de_canal, status_http, url, estado, pendência)` — para a curadoria colar no
   cadastro. Ele **não** é chamado pelo workflow e **não** escreve no cadastro: 78 requisições não
   cabem no cron diário (§6.4 orça 80 requisições para a coleta, que é a única rede do caminho
   agendado), e escrita automática no cadastro violaria a decisão de §10.4 (`git add` sem
   `fontes/`).

**O canal de diário não sai da sondagem, sai da coleta.** Para `diario_oficial_agregador` a
evidência forte está de graça no pipeline: se um ato do município apareceu no DOM/AMUNES, o canal
está confirmado por observação, e é isso que vai em `evidencia`. Na janela medida, **41 dos 78**
municípios tiveram ato em confiança alta (§5.3), isto é, 41 canais de agregador confirmados por
observação sem uma única requisição extra. Para os demais, a curadoria escreve o canal com
`estado: "pendente"` (o DOM/AMUNES **é** o canal esperado do município, só não houve ato na janela)
ou `canais:nao_encontrado` quando nem isso se sustenta.

**Expectativa honesta:** ao final do primeiro povoamento, parte dos 78 fica com canal de portal
pendente ou ausente. É resultado correto. A cobertura de coleta **não depende** dessas URLs (§6):
elas servem à curadoria humana, e o canal que sustenta a coleta — o agregador — é confirmado pelo
próprio pipeline.

### 3.3 Política de aliases

Alias só é útil se **sobreviver à normalização**. `comum.normalizar()` remove acento e cedilha,
então variante puramente ortográfica é gratuita — verifiquei com a função real que
`Guaçuí→guacui`, `Iúna→iuna`, `Marataízes→marataizes`, `São Roque do Canaã→sao-roque-do-canaa`,
`Vila Pavão→vila-pavao`, `Atílio Vivácqua→atilio-vivacqua`. **Essas não entram como alias**:
seriam ruído dando falsa sensação de cobertura.

Precisa de alias só o que muda a cadeia **já normalizada**: troca de preposição,
encurtamento usual, abreviação de título, grafia consonantal divergente.

**Regra de admissão (decidida, não enumerada por palpite):** entra como alias somente a
variante **observada** em (a) registro de `dados/`, (b) `fontes/fontes.json`, (c) texto real de
diário coletado, ou (d) campo do próprio IBGE. Procurei evidência para os candidatos que o
passe anterior listou:

| Candidato | Evidência | Decisão |
| --------- | --------- | ------- |
| `Cachoeiro do Itapemirim` | **sim** — `regiao-imediata.regiao-intermediaria.nome` do IBGE é `"Cachoeiro do Itapemirim"` (com "do"), para os 24 municípios daquela região | **cadastrar** |
| `Cachoeiro` | **sim** — `id` da fonte `prefeitura-cachoeiro` e host `www.cachoeiro.es.gov.br` | **cadastrar** |
| `Santa Maria do Jetibá` | não encontrada: `dados/` usa `"Santa Maria de Jetibá"` (4×) e a fonte é `prefeitura-santa-maria-jetiba` | **não cadastrar** |
| `Atilio Vivaqua` (um `c`) | não encontrada em `dados/` nem em `fontes.json` nem nas 144 páginas | **não cadastrar** |
| `S. Mateus`, `Sta Teresa`, `Gov. Lindenberg`, `Pres. Kennedy`, `Divino de S. Lourenço`, `Venda Nova`, `Jetibá` | nenhuma evidência | **não cadastrar** |

Portanto o primeiro passe nasce com **2 aliases**, ambos em Cachoeiro de Itapemirim. A lista
cresce pelo mecanismo de `municipios_nao_mapeados` (§7), que entrega o nome observado **com
URL e trecho de exemplo** — ou seja, a evidência vem junto com a sugestão, e é esse o
mecanismo de aprendizagem do sistema. O validador não consegue conferir evidência; a regra é
imposta na revisão do PR, e está escrita em `fontes/README.md`. Limitação aceita e declarada.

**Pontuação.** `comum.normalizar()` **não** remove pontuação — conferi que
`normalizar("S. Mateus") == "s. mateus"`. Como o casamento usa `re.escape`, um alias com ponto
só casaria com o ponto presente. Para que isso nunca seja uma pegadinha, o cadastro e o
casamento usam uma chave canônica única:

```python
def chave_nome(texto):
    """Normaliza E colapsa pontuacao: 'S. Mateus', 'S.Mateus' e 'S Mateus' viram
    a mesma chave. normalizar() sozinho nao faz isso, e sem este colapso um alias
    abreviado casaria apenas com a grafia exata que alguem digitou no cadastro.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalizar(texto))).strip()
```

Medido: `chave_nome("S. Mateus") == chave_nome("S.Mateus") == "s mateus"`.

---

## 4. Decisão 2 — regra de alcance (ambiguidade resolvida explicitamente)

Além das 78 prefeituras, o ES tem câmaras municipais, autarquias municipais e consórcios
intermunicipais, e **o repositório já tem registros desses**:
`concurso-camara-aracruz-es-2026`, `concurso-camara-cachoeiro-itapemirim-es-2026`,
`concurso-codeg-guarapari-es-2026`, `ps-cim-polinorte-es-2026`,
`ps-consorcio-caparao-es-2026`, `ps-aries-es-analista-fiscalizacao-001-2026` e `-003-2026`,
`ps-cariacica-es-ipc-previdenciario-2026`. Na coleta real do DOM encontrei, na janela de 7
dias, atos do **Serviço Autônomo de Água e Esgoto de Aracruz** nomeando candidato de concurso:
autarquia municipal é caso frequente, não exceção.

Varredura dos 53 registros: **4** têm `esfera: "intermunicipal"` — os **2** da ARIES
(`municipio: "Vitória"`), `ps-cim-polinorte-es-2026` (`"Diversos (ES) - Linhares e região"`) e
`ps-consorcio-caparao-es-2026` (`"Divino de São Lourenço"`). Os dois passes anteriores deste
documento e a revisão diziam "4 registros `ps-aries-es-*`"; são 2, e a correção importa para
§7.4, porque o registro que de fato creditaria um município real por via indevida é o do
Consórcio Caparaó, não os da ARIES.

**Decisão: o cadastro cobre os órgãos vinculados, em uma lista irmã no mesmo arquivo — e essa
lista existe para o casamento de texto, não como unidade de cadastro.** A clarificação do usuário
(§3.1) fixa o eixo: `municipios` é um cadastro de **canais de publicação**, um por unidade
territorial. Câmara, autarquia e consórcio **não** são entradas de primeira classe desse cadastro e
**não** têm `canais`; eles existem em `orgaos_vinculados` por dois usos concretos e verificáveis:

1. alimentar `indice.padroes_orgaos`, isto é, o reconhecimento do órgão no texto do diário (§5.2.1);
2. atribuir o ato ao(s) município(s) do órgão, quando a aridade permite (`municipios_slugs`).

- `municipios` — exatamente **78** entradas, uma por unidade territorial, cada uma com seus
  `canais`. É a chave de contagem de cobertura. Nenhum órgão vinculado entra aqui.
- `orgaos_vinculados` — lista aberta, uma entrada por órgão com personalidade própria, **sem**
  `canais`: o órgão publica no mesmo diário do município (ou no DOM/AMUNES), e inventar uma lista
  de canais para ele duplicaria a informação do município sem ninguém para consumi-la. O órgão tem
  **um** `url` institucional, que serve ao rastreamento humano do ato.

Os **4 registros intermunicipais já versionados continuam válidos** e nada neles muda: eles
seguem monitorados, seguem sem creditar cobertura (regra desta seção) e seguem rastreáveis ao órgão
pela lista acima.

```jsonc
{
  "id": "camara-aracruz",
  "nome": "Camara Municipal de Aracruz",
  "sigla": null,
  "natureza": "camara_municipal",
  "esfera": "municipal",
  "municipios_slugs": ["aracruz"],
  "url": "https://www.aracruz.es.leg.br/transparencia/concurso-publico",
  "fontes": ["camara-aracruz"],
  "pendencias_verificacao": [],
  "verificado_em": "2026-10-01"
}
```

`natureza` tem vocabulário fechado: `camara_municipal`, `autarquia_municipal`,
`fundacao_municipal`, `empresa_municipal`, `consorcio_intermunicipal`, `agencia_reguladora`.

### 4.1 As 8 entradas iniciais de `orgaos_vinculados`, enumeradas

O passe anterior descrevia a forma de `orgaos_vinculados` e não dizia quais entradas criar, o que
deixava o implementador sem lista. Todas as 8 abaixo derivam de **evidência no repositório** (um
registro em `dados/`, uma fonte em `fontes.json`) ou de **ato observado na coleta** — nenhuma foi
imaginada. `sigla` é usada no casamento de texto livre (§5.2) e por isso é preenchida quando
existe de fato:

| `id` | `nome` | `sigla` | `natureza` | `esfera` | `municipios_slugs` | Evidência | Pendências |
| ---- | ------ | ------- | ---------- | -------- | ------------------ | --------- | ---------- |
| `camara-aracruz` | Camara Municipal de Aracruz | — | `camara_municipal` | `municipal` | `["aracruz"]` | fonte `camara-aracruz` + `concurso-camara-aracruz-es-2026` | `[]` |
| `camara-cachoeiro-itapemirim` | Camara Municipal de Cachoeiro de Itapemirim | — | `camara_municipal` | `municipal` | `["cachoeiro-de-itapemirim"]` | `concurso-camara-cachoeiro-itapemirim-es-2026` | `url:nao_encontrado` |
| `saae-aracruz` | Servico Autonomo de Agua e Esgoto de Aracruz | `SAAE` | `autarquia_municipal` | `municipal` | `["aracruz"]` | ato de nomeação observado no DOM na janela medida | `url:nao_encontrado` |
| `codeg-guarapari` | Companhia de Desenvolvimento de Guarapari | `CODEG` | `empresa_municipal` | `municipal` | `["guarapari"]` | `concurso-codeg-guarapari-es-2026` | `url:nao_encontrado` |
| `ipc-cariacica` | Instituto de Previdencia dos Servidores de Cariacica | `IPC` | `autarquia_municipal` | `municipal` | `["cariacica"]` | `ps-cariacica-es-ipc-previdenciario-2026` | `url:nao_encontrado` |
| `cim-polinorte` | Consorcio Publico da Regiao Polinorte | `CIM Polinorte` | `consorcio_intermunicipal` | `intermunicipal` | `[]` | `ps-cim-polinorte-es-2026` | `municipios_slugs:nao_encontrado` |
| `consorcio-caparao` | Consorcio Publico da Regiao do Caparao | — | `consorcio_intermunicipal` | `intermunicipal` | `[]` | `ps-consorcio-caparao-es-2026` | `municipios_slugs:nao_encontrado` |
| `aries` | Agencia Reguladora Intermunicipal de Saneamento Basico do ES | `ARIES` | `agencia_reguladora` | `intermunicipal` | `[]` | `ps-aries-es-analista-fiscalizacao-001-2026`, `-003-2026` | `municipios_slugs:nao_encontrado` |

`IPC` é a sigla que §15.11 cita como o caso difícil — órgão cujo nome não contém o nome da
cidade. Ele só se resolve porque está nesta lista: é literalmente a razão de `orgaos_vinculados`
existir. Os três últimos nascem com `municipios_slugs: []` e pendência, pelo motivo já dado
(composição de consórcio depende de ratificação documental); eles **são monitorados** e **não
creditam** cobertura a município nenhum.

**Por que duas listas e não uma.** A pergunta de negócio é "quantos dos 78 municípios estão
cobertos?". Se a Câmara de Aracruz fosse uma 79ª entrada de `municipios`, a contagem
`len(municipios) == total_esperado` deixaria de ser invariante verificável e a cobertura
somaria maçãs com laranjas. Ao mesmo tempo, um ato da Câmara de Aracruz **é** sinal de
atividade em Aracruz — daí `municipios_slugs`, que resolve o órgão para o(s) município(s).

**Órgãos de jurisdição multimunicipal.** `consorcio_intermunicipal` e `agencia_reguladora`
exigem `esfera: "intermunicipal"` (valor já em `comum.ESFERAS_VALIDAS` e em `ESQUEMA.md`) e
aceitam **0..N** slugs. Composição de consórcio muda por ratificação de protocolo de intenções
e é difícil de confirmar: se os membros não forem verificáveis, grava-se
`municipios_slugs: []` + `"municipios_slugs"` em `pendencias_verificacao`. O órgão **continua
monitorado** (os atos dele são capturados), mas não credita cobertura a município nenhum até os
membros serem apurados. Isso é deliberado: atribuir cobertura a município adivinhado inflaria
a métrica com dado inventado.

O caso que obrigou essa forma é real: `ps-aries-es-*` (Agência Reguladora Intermunicipal de
Saneamento Básico do ES) tem `municipio: "Vitória"` nos registros, mas Vitória é **sede**, não
jurisdição. Exigir exatamente 1 slug forçaria creditar Vitória por um órgão intermunicipal —
o rateio por palpite que esta seção proíbe. Por isso a regra de aridade do validador (§9.2) é
por natureza, e não uma regra única.

Consequência explícita para a cobertura (§7.4): um município fica "com atividade detectada" se
houver ato atribuído a ele **ou** a órgão vinculado cujo `municipios_slugs` o contenha. Órgão
com `municipios_slugs: []` aparece em linha própria de "não atribuível a município", nunca
distribuído por rateio.

**A proibição vale também para o dado curado de `dados/`, e não só para o coletor.** O passe
anterior deixou essa brecha: §7.4 definia `com_registro_curado` como "resolver o campo
`municipio` dos registros pelo cadastro", e os registros intermunicipais **têm** município de
sede preenchido — medido: `ps-consorcio-caparao-es-2026` com `"Divino de São Lourenço"` e os dois
da ARIES com `"Vitória"`. Pela regra ingênua, o Consórcio Caparaó creditaria Divino de São
Lourenço e a ARIES creditaria Vitória duas vezes, exatamente pelos órgãos que esta seção decidiu
não creditar ninguém.

Decisão: **registro com `esfera == "intermunicipal"` não credita cobertura a município algum**,
venha de `dados/` ou da coleta. Ele é contado em linha própria
(`registros_intermunicipais_sem_atribuicao`, §7.4) e o validador avisa quando o `municipio` de um
registro intermunicipal resolve para um slug (§9.3), apontando para `orgaos_vinculados` como o
lugar correto de declarar jurisdição. A alternativa — tratar o dado curado como autoritativo,
porque um humano escreveu "Vitória" ali — foi rejeitada: o campo `municipio` desses registros
responde "onde fica a sede", que é pergunta diferente de "qual município tem jurisdição", e
misturar as duas é o rateio por palpite que esta seção proíbe. Enquanto a composição não for
apurada, o certame aparece como monitorado e não atribuído, que é a verdade.

**Fora do cadastro, por decisão:** órgãos estaduais e federais (SEDU, SESA, PM-ES, SEGER,
UFES, IFES, conselhos profissionais). Continuam exclusivamente em `fontes/fontes.json`, porque
não pertencem a município algum — 24 dos 53 registros já têm
`municipio: "Âmbito estadual (ES)"`, e tratá-los como cobertura municipal distorceria a
métrica. No achado, o escopo deles é dito positivamente por `municipio_escopo: "estadual"`
(§6.6), não por ausência de dado.

---

## 5. Decisão 3 — normalização e casamento de nome de município

`_sem_acento()`, `normalizar()` e `slug()` existem hoje **dentro de `coletar.py`**, mas o
cadastro precisa ser lido também por `validar.py`, `gerar_readme.py`, `gerar_relatorio.py` e
`gerar_email.py`.

**Decisão: mover os três para `comum.py` sem alterar a implementação**, acrescentar
`chave_nome()` (§3.3), e em `coletar.py` substituir as definições por delegações
(`normalizar = comum.normalizar`, etc.) para que nenhum call site existente mude. A
implementação atual é correta para o problema (conferi nos 78 nomes) e reescrevê-la só criaria
risco.

### 5.1 Acesso ao cadastro, em `comum.py`

```python
CAMINHO_MUNICIPIOS = os.path.join(RAIZ, "fontes", "municipios-es.json")

# O indice e um namedtuple, e nao um dict, por causa do lru_cache: um dict
# memoizado e devolvido POR REFERENCIA, e um chamador que escrevesse nele
# corromperia o indice de todos os outros pelo resto do processo. namedtuple e
# imutavel, stdlib e 3.9-compativel. Acesso e SEMPRE por atributo
# (indice.por_slug), nunca por chave (indice["por_slug"]).
IndiceMunicipios = collections.namedtuple(
    "IndiceMunicipios",
    "por_slug por_chave_nome padroes_ordenados padroes_orgaos orgaos_por_id "
    "total_esperado max_tokens_nome",
)

def carregar_municipios():
    """Dict completo do cadastro. Levanta ValueError com o caminho quando o JSON
    e invalido, no mesmo estilo de carregar_registros()."""

@functools.lru_cache(maxsize=1)
def indice_municipios():
    """IndiceMunicipios memoizado. A memoizacao nao e otimizacao prematura:
    valida_escopo() chama resolver_municipio() uma vez por registro (53 hoje) e
    o coletor chama por pagina (ate 1000), e sem cache cada chamada releria e
    reindexaria o arquivo inteiro."""
```

**Uma única forma de chave, e um construtor de padrão tolerante a pontuação.** O passe anterior
misturava duas formas incompatíveis: `padroes_ordenados` guardava `normalizar(nome)` e
`padroes_orgaos` guardava `chave_nome(nome)`, ambas casadas contra texto `normalizar()`-ado.
Medi com as funções reais que isso não funciona: `chave_nome("CIM Polinorte") == "cim polinorte"`,
mas o diário escreve `cim-polinorte`, e `re.search(r"\bcim polinorte\b", "ato do cim-polinorte")`
é **False** — `normalizar()` não colapsa pontuação. Todo nome ou sigla que apareça com hífen, ponto
ou barra ficava fora do casamento, **inclusive os três órgãos intermunicipais de §4.1**.

Inverter o lado (aplicar `chave_nome()` ao texto) **não** é opção: `PADROES_BOILERPLATE`,
`MARCA_DEPOIS` (`[/-] es`) e `PADROES_MENCAO` (`[/,-]`) dependem da pontuação que `chave_nome()`
apagaria. Decisão: **o texto de trabalho fica em `normalizar()`** e os padrões são compilados a
partir de `chave_nome()` por um construtor único:

```python
def _padrao_de_chave(texto):
    """Compila a chave canonica em padrao tolerante a pontuacao: 'cim-polinorte',
    'cim/polinorte', 'cim.polinorte' e 'cim polinorte' casam o mesmo padrao
    (medido com as quatro formas). O texto de trabalho fica em normalizar(), e
    nao em chave_nome(), porque boilerplate (§5.3), MARCA_DEPOIS e
    PADROES_MENCAO (§7.2) dependem da pontuacao que chave_nome() apagaria.

    O separador exclui \\x00 DE PROPOSITO. Com [^a-z0-9]+ a mascara de §5.2
    passaria a valer como separador e um nome ja consumido viraria ponte entre
    dois tokens distantes: medido em
    'secretaria de vila, conceicao do castelo, pavao e outros', depois de
    mascarar 'conceicao do castelo', o padrao de 'Vila Pavao' CASA com
    [^a-z0-9]+ e NAO casa com [^a-z0-9\\x00]+. E a mesma razao pela qual a
    mascara e \\x00 e nao espaco (§5.2), vista do lado do padrao.
    """
    toks = [re.escape(t) for t in chave_nome(texto).split()]
    return re.compile(r"\b" + r"[^a-z0-9\x00]+".join(toks) + r"\b")
```

Duas operações distintas de resolução, com assinaturas separadas porque os textos de entrada são
de naturezas diferentes e uma não serve para o outro:

```python
def resolver_municipio(texto, indice=None):
    """Consulta EXATA por chave_nome(), para texto CURTO e ja curado: o campo
    'municipio' de um registro de dados/ (§9.3). Devolve (slug, origem) com
    origem em {'nome', 'alias', 'orgao_vinculado'}, ou (None, None).

    'orgao_vinculado' e o caso em que a chave casada e o nome de um orgao de
    §4.1 que resolve para exatamente 1 slug (esses nomes estao em
    por_chave_nome): o validador usa a origem para avisar, em vez de tratar
    'Camara Municipal de Aracruz' como se fosse o municipio Aracruz.
    """

def resolver_municipio_em_texto(texto, indice=None):
    """Passada longest-first de §5.2 sobre TEXTO LIVRE (titulo, nome de orgao,
    conteudo de pagina). Devolve (slug, origem) quando o texto resolve para UM
    unico municipio; (None, None) quando resolve zero OU mais de um.

    Ambiguidade nunca e desempatada por palpite: 'Prefeitura de Serra e de Vila
    Velha' devolve (None, None), nao a primeira ocorrencia. Esta e a funcao que
    §6.10 usa para achado de 'oportunidade' — a consulta exata devolveria None
    em praticamente todos, porque ali o texto e 'Prefeitura de Anchieta',
    'ARIES', 'SEDU'.
    """
```

Campos do `IndiceMunicipios`, todos lidos por atributo:

| Campo | Conteúdo |
| ----- | -------- |
| `por_slug` | `{slug: entrada}` |
| `por_chave_nome` | `{chave_nome(nome\|alias): slug}`, incluindo os nomes dos `orgaos_vinculados` que resolvem para **exatamente 1** slug |
| `padroes_ordenados` | lista `(padrao, slug, origem)`, `origem ∈ {"nome", "alias"}`, **uma entrada por nome e uma por alias**, `padrao = _padrao_de_chave(nome\|alias)`, ordenada por **comprimento decrescente de `chave_nome(nome\|alias)`** (§5.2) |
| `padroes_orgaos` | lista `(padrao, orgao_id, origem)`, `origem ∈ {"nome", "sigla"}`, uma entrada por `nome` e uma por `sigla` (quando existe e tem ≥3 caracteres), mesmo construtor e mesma ordenação |
| `orgaos_por_id` | `{orgao_id: entrada}`, para ler `municipios_slugs`, `esfera` e `natureza` ao casar |
| `total_esperado` | `total_esperado` do cadastro — **nunca** o literal 78 no código |
| `max_tokens_nome` | `max(len(k.split()) for k in por_chave_nome)` — **calculado, não literal**. Medido hoje: **8**, de `servico autonomo de agua e esgoto de aracruz`; o maior nome de **município** tem 4 tokens (12 nomes empatados). O teto existe para a poda por prefixo da **captura** do diário (§7.2), e calculá-lo sobre `por_chave_nome` é o que torna alcançáveis as chaves de órgão de 5 a 8 tokens — com o literal 4, `instituto de previdencia dos servidores de cariacica` nunca seria resolvido pela poda |

**`padroes_ordenados` inclui os aliases, e isso é o que faz §3.3 valer.** Os 2 aliases cadastrados
com evidência (`Cachoeiro do Itapemirim`, `Cachoeiro`) existem precisamente porque aparecem no
mundo real — e o diário é onde eles aparecem. Sem entrada própria na lista de padrões, eles
creditariam `resolver_municipio()` e **nada** no casamento de texto livre, que é o oposto do que
§3.3 afirma ("o cadastro **e o casamento** usam uma chave canônica única"). Alias casado em texto
livre segue a **mesma** regra de confiança de §5.3 (adjacência), sem desconto e sem bônus: a
evidência de pertencimento é o contexto, não a forma do nome.

Quem precisar recarregar em teste chama `indice_municipios.cache_clear()` — declarado aqui porque
é o tipo de detalhe que, omitido, produz teste que contamina o seguinte.

### 5.2 Casamento em texto livre: longest-first com mascaramento

Computei os conflitos reais entre os 78 nomes:

- **Subconjunto de tokens** — exatamente 2 casos: `Castelo` ⊂ `Conceição do Castelo`;
  `Itapemirim` ⊂ `Cachoeiro de Itapemirim`.
- **Prefixo de slug** — **nenhum** slug dos 78 é prefixo de outro.
- **Tokens compartilhados** — `sao` (7), `rio` (4), `santa` (3), `norte` (3), `vila` (3).

Algoritmo, em duas passadas — **órgãos vinculados primeiro, municípios depois**:

0. **Entrada:** um **bloco de ato** (`t`), já normalizado por `comum.normalizar()` e já com o
   boilerplate limpo **na página inteira**. Normalização e limpeza são os estágios 2 e 3 de §6.5 e
   acontecem **uma vez por página**, antes da segmentação; esta passada é o estágio 6 e roda por
   bloco. Nenhuma das duas é refeita aqui — refazê-las por bloco quebraria assinaturas que
   atravessam a fronteira `protocolo \d+` e mudaria os números medidos em §5.3 e §7.2.
1. **Passada de órgãos.** Percorrer `indice.padroes_orgaos` (mais longo primeiro). Ao casar,
   avaliar, mascarar e registrar `orgao_vinculado_id` (§5.2.1).
2. **Passada de municípios.** Percorrer `indice.padroes_ordenados` (chave mais longa primeiro).
   Cada item é `(padrao, slug, origem)`, com `padrao` compilado por `_padrao_de_chave()` (§5.1) a
   partir de `chave_nome(nome)` **ou** de `chave_nome(alias)` — por isso alias casa em texto livre,
   e por isso `cim-polinorte` casa a chave `cim polinorte`.
3. Para cada padrão: coletar **todas** as ocorrências com `finditer`, avaliar a confiança de cada
   uma (§5.3) e só **depois** mascarar o padrão inteiro, substituindo cada trecho casado por
   `"\x00"` do mesmo comprimento. A ordem "avaliar tudo, depois mascarar" é decisão, não detalhe:
   ver o laço abaixo.

O mascaramento resolve os dois subconjuntos sem heurística: "conceicao do castelo" é testado
antes de "castelo" e consome o trecho, de modo que Castelo não é creditado por engano.

**A máscara é `"\x00"`, não espaço — e isso não é detalhe de estilo.** O passe anterior mandava
mascarar com espaços do mesmo comprimento, para preservar os offsets que a regra de contexto usa.
Preserva os offsets e **quebra a adjacência**, que é a defesa central de §5.3: como `MARCAS_ANTES`
termina em `\s*$`, a marca do primeiro município atravessa a máscara de espaços e é creditada ao
segundo. Reproduzi com as regras exatamente como escritas:

```
texto: "PREFEITURA DE VILA VELHA SERRA edital de convocacao"
  mascara = " "     -> [('vila-velha', 'alta'), ('serra', 'alta')]    <- serra INDEVIDO
  mascara = "\x00"  -> [('vila-velha', 'alta'), ('serra', 'baixa')]   <- correto

texto: "MUNICIPIO DE SANTA MARIA DE JETIBA LINHARES"
  mascara = " "     -> [('santa-maria-de-jetiba', 'alta'), ('linhares', 'alta')]  <- indevido
  mascara = "\x00"  -> [('santa-maria-de-jetiba', 'alta'), ('linhares', 'baixa')] <- correto
```

```python
# A mascara e "\x00" e nao espaco por um motivo que custou uma rodada de revisao
# para aparecer: MARCAS_ANTES termina em \s*$, entao mascarar com espaco faz a
# marca do municipio ja casado "vazar" para o municipio seguinte
# ("PREFEITURA DE VILA VELHA SERRA" creditava SERRA em confianca alta). O \x00
# preserva os offsets igual ao espaco, mas nao casa com \s nem com \b, de modo
# que adjacencia volta a significar adjacencia. Listas de lotacao e cabecalhos
# de caderno poem nomes de municipio em sequencia com frequencia: nao e caso
# teorico.
for padrao, slug, origem in indice.padroes_ordenados:   # chave mais longa primeiro
    # finditer, e nao sub: a regra de confianca de §5.3 precisa dos OFFSETS de
    # cada ocorrencia para ler a janela de 45/6 caracteres, e re.sub nao os expoe.
    for m in list(padrao.finditer(t)):
        antes = t[max(0, m.start() - 45):m.start()]
        depois = t[m.end():m.end() + 6]
        conf = "alta" if (MARCAS_ANTES.search(antes) or MARCA_DEPOIS.match(depois)) else "baixa"
        registrar(slug, conf, origem)
    # Mascara DEPOIS de avaliar TODAS as ocorrencias deste padrao, nunca
    # intercalado: avaliar e mascarar de uma em uma faria a 2a ocorrencia do
    # mesmo nome ler a 1a ja mascarada, e o resultado medido depende disso.
    # Reproduzi as duas medicoes de §5.2 com esta ordem exata.
    t = padrao.sub(lambda m: "\x00" * len(m.group(0)), t)
```

`MARCA_DEPOIS.match` e não `search` — `match` ancora no início da fatia de 6 caracteres, que é o
que materializa a adjacência decidida em §5.3; com `search`, `"serra xx/es"` passaria a contar.

Não há risco de o `\x00` chegar ao dado gravado: ele existe só na variável de trabalho do
casamento. `titulo` vem de `highlight` (§6.7) e os campos de município vêm do cadastro (§6.7),
nunca do texto mascarado.

#### 5.2.1 Casamento de órgão vinculado em texto livre

Sem esta passada, `orgao_vinculado_id` nunca seria preenchido e `orgaos_vinculados` seria uma
lista que o validador confere e o coletor nunca usa — o caso "IPC (Cariacica)", que é a razão de
ser da lista, continuaria indeterminado. Regras:

- `padroes_orgaos` casa `nome` **e** `sigla` (quando existe), ambos compilados por
  `_padrao_de_chave()` a partir de `chave_nome()` (§5.1), ordenados por comprimento decrescente da
  chave, igual aos municípios. Sigla com menos de 3 caracteres é ignorada, porque casaria com
  qualquer sopa de letras do diário. É o construtor tolerante a pontuação que faz os três órgãos
  intermunicipais funcionarem: medido, `chave_nome("CIM Polinorte") == "cim polinorte"`, o diário
  escreve `cim-polinorte`, e `re.search(r"\bcim polinorte\b", texto)` é **False** — com
  `_padrao_de_chave` as quatro formas (`cim polinorte`, `cim-polinorte`, `cim/polinorte`,
  `cim.polinorte`) casam.
- Município herdado de órgão recebe `municipio_origem: "orgao_vinculado"` no achado (§6.7), para que
  a cobertura seja auditável: "Aracruz contou por quê?" tem resposta no dado, e não só no código.
- A passada de órgãos vem **antes** da de municípios e mascara igual. Assim "Servico Autonomo de
  Agua e Esgoto de Aracruz" é consumido como órgão, e a palavra "aracruz" dentro dele não é
  contada de novo como menção solta de município.
- **Nome de órgão casado é marca de contexto própria, e vale confiança `alta`** — o nome do órgão
  *é* a evidência de pertencimento, mais forte que qualquer heurística de adjacência.
- Herança de município, pela aridade de `municipios_slugs` do órgão:

| `len(municipios_slugs)` | `municipio_slug` | `municipio_escopo` |
| ----------------------: | ---------------- | ------------------ |
| 1 | o slug, confiança `alta` | `municipal` |
| 0 | `null` | `intermunicipal` se a `esfera` do órgão for `intermunicipal`, senão `indeterminado` |
| N > 1 | `null` | `intermunicipal` |

Em todos os casos `orgao_vinculado_id` é gravado, de modo que o ato fica rastreável ao órgão
mesmo quando não credita município — que é precisamente o comportamento que §4 decidiu.

**Proibido usar `coletar._coberto()` para município.** Essa função aceita casamento por prefixo
a partir de 4 caracteres — conferi que `_coberto("serra", {"serrana"})` é `True`. Para
identidade de órgão isso é deliberado (cobre `cref`/`cref22`); para município produziria falso
positivo. Município usa **igualdade de cadeia com fronteira de palavra**, e nada mais.
`casar()` e `tokens_identidade()` **não são alterados** — mexer neles reabriria o risco que os
comentários atuais do arquivo descrevem. Em vez disso, o achado de diário é desviado para
`casar_estrito()`, que omite o ramo fraco (§6.7): o problema não é o comportamento de `casar()` para
o caso em que ela foi escrita, é aplicá-la a um tipo de achado que não existia.

### 5.3 A armadilha "Vitória" — medida, e a correção é outra

Esta é a parte mais importante do trabalho e a que o passe anterior errou. Medições sobre as
144 páginas reais:

| Variante | Páginas com `vitoria` |
| -------- | --------------------: |
| texto bruto normalizado | **30 / 144 (21%)** |
| após os 5 padrões de limpeza do passe anterior | 20 |
| após os padrões propostos pela revisão | 12 |
| após a limpeza desta revisão (abaixo) | **8 ocorrências**, em nenhuma com marca municipal |

O passe anterior afirmou "100% das páginas" e deu o caso como resolvido; a revisão mediu 42%/27%
e concluiu que **Vitória lideraria a cobertura em confiança alta**. Reproduzi o pipeline
completo e **as duas descrições estão erradas**, por motivos diferentes. O que de fato
acontece:

**(1) O resíduo é a linha de assinatura de ato estadual, e tem mais formas do que qualquer dos
dois documentos previu.** O padrão do passe anterior exigia dia da semana; a revisão
acrescentou data por extenso. Os resíduos reais incluem **data numérica** e **"de setembro
2026" sem o segundo "de"**:

```
... a contar de 25/09/2026. vitoria-es, 28/09/2026. riodo lo...
... cargo do responsavel: gerente geral geafi. vitoria/es, 24/09/2026. geaco/co...
... divulgados no site www.selecao.es.gov.br, nota de convocacao. vitoria/es, 24 de setembro 2026.
... esta portaria entra em vigor na data de sua publicacao. vitoria-es, 25 de setembro de 2026.
```

Padrão único que cobre as três formas (e o separador `-`, que nenhum dos dois previa):

```python
MES = (r"(?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro"
       r"|outubro|novembro|dezembro)")

# Linha de local-data de assinatura. Medida em 144 paginas: aparece como
# "vitoria (es), quinta-feira, 1 de outubro de 2026.", "vitoria-es, 28/09/2026.",
# "vitoria/es, 24 de setembro 2026." (sem o segundo "de") e "vitoria, es, cep:".
# O dia da semana e OPCIONAL e o separador pode ser "(es)", "/es", "-es" ou ", es":
# exigir qualquer um deles foi o erro das duas versoes anteriores deste padrao.
PADROES_BOILERPLATE = (
    r"diario oficial dos municipios capixabas\s*\d*",
    r"assinado digitalmente pelo dio.*?codigo de autenticacao:\s*\w+",
    r"dom/es - edicao n[º°o]?\s*[\d\.]+\s*\d*",
    r"vitoria\s*(?:\(es\)|[/-]\s*es|,\s*es)?\s*,?\s*"
    r"(?:(?:segunda|terca|quarta|quinta|sexta|sabado|domingo)-feira,?\s*)?"
    r"(?:\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}|\d{1,2}\s+de\s+" + MES + r"\s+(?:de\s+)?\d{4})",
    r"vitoria,?\s*es,?\s*cep:?\s*[\d\.\-]+",
)
```

As 8 ocorrências de `vitoria` que sobrevivem são, verbatim: sobrenome de pessoa
(`... gustavo saloum simon vitoria zolli gualandi ...`, `alana simora da vitoria`), nome de
empresa (`a maternidade unimed vitoria atraves da unimed vitoria cooperativa de trabalho`) e
órgão estadual (`superintendencia regional de saude de vitoria - srsv/cre metropolitana`).
Nenhuma é removível por regex de boilerplate sem apagar texto legítimo, e **nenhuma precisa
ser**: a camada 2 as classifica como confiança baixa.

**(2) A camada que de fato carrega o peso é a exigência de contexto ADJACENTE, não o raio de
80 caracteres.** O passe anterior exigia marca de pertencimento "num raio de ~80 caracteres" e
incluía `/es`, `- es` e `estado do espirito santo` na lista de marcas — marcas quase universais
em ato estadual. A revisão propôs remover as três. Medi as duas variantes:

| Política de contexto | Municípios distintos com confiança alta | Vitória alta / baixa |
| -------------------- | --------------------------------------: | -------------------- |
| marca de órgão imediatamente antes **ou** `[/-] es` imediatamente depois | **41** | **0 / 6** |
| só marca de órgão imediatamente antes (proposta da revisão) | 35 | 0 / 6 |

Ou seja: com a limpeza corrigida, **Vitória sai da confiança alta nas duas políticas**, e
aceitar o sufixo de UF **adjacente** recupera 6 municípios de cobertura que a proposta da
revisão descartaria. A preocupação da revisão estava certa quanto à causa (`/es` em raio de
80 caracteres casa com qualquer ato estadual) e errada quanto ao remédio (remover a marca):
o que torna a marca precisa é a **adjacência**, não a sua ausência.

**Decisão.** Marca de pertencimento municipal é:

```python
# Ancorado em $: a marca tem de terminar IMEDIATAMENTE antes do nome casado.
# "prefeitura municipal de serra" conta; "prefeitura ... 300 caracteres ... serra"
# nao conta. Foi a troca de "raio de 80 caracteres" por adjacencia que tirou
# Vitoria da lideranca da cobertura (medido: 0 ocorrencias em confianca alta).
MARCAS_ANTES = re.compile(
    r"(municipio de|municipio da|prefeitura municipal de|prefeitura de"
    r"|camara municipal de|gabinete do prefeito de|prefeito municipal de"
    r"|saae de|servico autonomo de agua e esgoto de)\s*$"
)
# Sufixo de UF colado ao nome: "serra/es", "serra - es". Vale como marca porque
# e adjacente; "estado do espirito santo" em algum lugar da pagina NAO vale.
MARCA_DEPOIS = re.compile(r"\s*[/-]\s*es\b")
```

Confiança = `"alta"` quando `MARCAS_ANTES` casa nos 45 caracteres imediatamente anteriores
**ou** `MARCA_DEPOIS` casa nos 6 caracteres imediatamente seguintes; `"baixa"` caso contrário.
Quando o mesmo município aparece nas duas situações na mesma página, **alta prevalece**.

**A janela de contexto (45 antes / 6 depois) é lida no texto MASCARADO**, isto é, no mesmo `t` que
a passada de §5.2 vai modificando, e não no texto normalizado original. As duas leituras dão
resultados diferentes e a diferença é exatamente o vazamento de marca medido em §5.2: ler a janela
no original faria `MARCAS_ANTES` enxergar a marca de um município que já foi consumido. É por isso
que a máscara precisa ser `"\x00"` e não espaço — os dois pontos são a mesma decisão vista de dois
lados, e o passe anterior não declarava nenhum dos dois.

**E o momento exato da leitura é "todas as ocorrências do padrão corrente, antes de mascarar o
padrão corrente"** — o laço de §5.2 com `finditer`. Fica assim definido o que o passe anterior
deixou indefinido: a confiança de uma ocorrência **nunca** é afetada por outra ocorrência do
**mesmo** padrão, e **é** afetada pelos padrões mais longos já consumidos. Reproduzi os dois
resultados de §5.2 com esta ordem (`vila-velha` alta + `serra` **baixa**;
`santa-maria-de-jetiba` alta + `linhares` **baixa**); com avaliação intercalada à máscara, o
resultado muda. **Alias casado em texto livre segue exatamente esta regra**, sem exceção: quem
credita confiança alta é a marca adjacente, não a forma do nome (§5.1).

Achado com `municipio_confianca: "baixa"` entra em `descobertas/` normalmente, mas **não conta
para a cobertura** e **não vai para o e-mail**. Mantém o dado rastreável sem contaminar
métrica.

Resultado medido com o pipeline completo (os 10 primeiros, 144 páginas, janela de 7 dias):
`joao-neiva` 19, `nova-venecia` 14, `santa-teresa` 11, `aracruz` 10, `fundao` 10,
`aguia-branca` 9, `santa-leopoldina` 8, `ibiracu` 7, `linhares` 6, `santa-maria-de-jetiba` 6.
Isto é o perfil correto: são os municípios cujos cadernos saíram na janela. **41 dos 78
municípios** aparecem com confiança alta em uma única janela de 7 dias — o que mostra que a
arquitetura de agregador entrega cobertura real, e não uma lista de 78 zeros.

### 5.4 Quando não há município identificável

Há páginas de continuação em que o ato prossegue sem repetir o nome do município. Nesses casos:
`municipio_slug: null`, `municipio_confianca: null`, `municipio_escopo: "indeterminado"`.
**Nunca herdar o município do bloco ou da página anterior**: a ordem das páginas no índice não
garante contiguidade e a herança inventaria atribuição.

---

## 6. Decisão 4 — como o coletor cobre 78 municípios

### 6.1 Alternativas consideradas

| Abordagem | Requisições/dia | Fragilidade | Acha município novo? | Veredito |
| --------- | --------------: | ----------- | -------------------- | -------- |
| (a) Um scraper por prefeitura | ~78+ | 78 layouts; 5 dos 14 domínios sondados respondem 403 a robô (§3.2) | Não | **Rejeitada** |
| (b) Uma consulta por município no buscador | ~312 (78 × 2 escopos × 2 frases) | Baixa, mas ~5 min só nisso a 1,0 s/req | Não (só acha o que já está no cadastro) | **Rejeitada** |
| (c) Poucas consultas por assunto + casamento local | **80** | Baixa; um único parser | **Sim, de graça** | **ESCOLHIDA** |

A opção (c) inverte o problema: em vez de perguntar "há concurso em Sooretama?" 78 vezes,
pergunta "quais atos de concurso saíram esta semana?" e descobre os municípios **a partir da
resposta**. É isso que torna a detecção de município não mapeado possível — em (a) e (b) o
pipeline só vê o que já foi cadastrado, que é exatamente o bug estrutural de hoje.

### 6.2 API real do buscador do IOES (verificada nesta revisão)

Não é documentada; o contrato foi levantado do bundle Angular
`/buscanova/assets/javascripts/application.*.js` e exercitando o endpoint.

```
GET {BASE}/busca/busca/buscar/query/{pagina}[/di:AAAA-MM-DD][/df:AAAA-MM-DD]/?1=1&q={termo}
```

- `BASE` define o **escopo**, e são dois índices distintos:
  - `https://ioes.dio.es.gov.br` → Diário Oficial do Estado, que inclui o "Caderno dos
    Municípios Capixabas" (`tipo_edicao: 1`, `diario: "DIO"`);
  - `https://ioes.dio.es.gov.br/dom` → **DOM - AMUNES** (`tipo_edicao: 13`,
    `diario: "DOM - AMUNES"`).
  Consultar os dois é obrigatório: na janela de 7 dias, `"concurso publico"` deu 16 no DIO e
  **63** no DOM; `"processo seletivo"` deu 8 no DIO e **131** no DOM.
- `pagina` é **0-based**, 10 resultados por página.
- `di:`/`df:` filtram por data e **são indispensáveis**: sem janela, `q=Sooretama` devolve
  14.415 hits com documentos de 2019 e 2022.
- Aspas duplas fazem busca de frase exata. O termo vai **URL-encoded**.
- Resposta: envelope Elasticsearch. `hits.total` é **int** (medido: `131`). `hits.hits[]` com
  `_id` = `"{diario_id}_{pagina}"` (ex.: `11517_322`), `_source` = `conteudo, data, day, month,
  year, pagina, paginas, diario_id, pdf_id, tipo_edicao`, e no nível do hit `diario`,
  `suplemento`, `highlight`, `sort`, `_score`.
- **`suplemento` é o rótulo da edição**, não indicador de suplemento: medido `"Edição 3099"`,
  `"Edição 26821"`. Guardamos o número extraído por `re.search(r"(\d[\d\.]*)$", suplemento)` em
  `edicao`, e nada mais é inferido dele.
- `highlight.conteudo` é lista de trechos com `<strong>`. **Usar `highlight` para o título** do
  achado (é o trecho relevante) e `_source.conteudo` para o casamento de município (é o texto
  completo da página).
- URLs de citação, verificadas respondendo 200: PDF da página
  `{BASE}/portal/edicoes/download/{diario_id}/{pagina}` (`application/pdf`); visualizador
  `{BASE}/ver/{diario_id}/{pagina}/""` (`text/html`). **Usar o PDF da página** como `url` do
  achado: é estável, citável e aponta para o ato, não para a edição inteira.
- `hits.total` pode mudar de forma em versão futura do Elasticsearch (`{"value": n,
  "relation": ...}`). Tolerar os dois com um helper de uma linha
  (`total = t["value"] if isinstance(t, dict) else t`), porque custa nada e evita quebra silenciosa.

### 6.3 Duas fontes, uma por escopo — e por que isso é melhor que uma

O passe anterior definia **uma** fonte `ioes-busca` que internamente varria os dois escopos,
com `try/except` por escopo e um campo `escopos_com_falha`. A revisão apontou corretamente que
(i) declarar essa fonte como `esfera: "municipal"` descreve mal o DIO, que traz ato estadual, e
(ii) o canal de retorno dos metadados não estava especificado.

**Decisão: registrar duas fontes**, cada uma com um escopo:

```python
# functools.partial em vez de duas funcoes: o corpo e identico e o escopo e o
# unico parametro que muda. Registrar as duas em FONTES faz o laco existente de
# main() dar a degradacao graciosa DE GRACA e por escopo — se o DOM cair, o DIO
# aparece como 'ok' em fontes_consultadas e o DOM como 'erro', sem precisar de
# try/except interno nem do campo escopos_com_falha que a versao anterior inventava.
FONTES = {
    "selecao-es": coletar_selecao_es,
    "concursosnobrasil-es": coletar_concursosnobrasil_es,
    "ioes-busca-dio": functools.partial(coletar_ioes, escopo="dio"),
    "ioes-busca-dom": functools.partial(coletar_ioes, escopo="dom"),
}
```

Ganhos concretos, todos consequência de reutilizar o laço em vez de duplicá-lo:
`suspeita_extracao_vazia` passa a valer por escopo; `--fonte ioes-busca-dom` torna-se possível;
cada fonte declara a `esfera` verdadeira (`ioes-busca-dio` → `estadual` com `observacao`
dizendo que o índice inclui o caderno dos municípios; `ioes-busca-dom` → `municipal`); e
`escopos_com_falha` deixa de existir.

Entradas novas em `fontes/fontes.json`, ambas `tipo: "diario_oficial"`, `prioridade: 1`,
`coletada_automaticamente: true`. A fonte `amunes-dom` existente permanece como referência
humana ao portal.

**Assinatura e canal de metadados.** O contrato atual é `FONTES[id]() -> lista`, e `main()`
monta `registro_fonte` com chaves fixas. Devolver tupla quebraria o laço compartilhado. Então:

```python
def coletar_ioes(escopo="dom", diagnostico=None, janela_dias=7, max_paginas=20,
                 max_achados=1000, indice=None):
    """Devolve LISTA de achados, como as outras fontes.

    Quando 'diagnostico' e um dict, escreve nele 'truncado',
    'limite_achados_atingido', 'total_relatado' e 'nao_mapeados'. E o canal de
    retorno dos metadados sem mudar o contrato (lista) que as outras duas fontes
    ja cumprem — mudar o contrato quebraria a degradacao graciosa do laco.
    """
```

e em `main()`, dentro do `try` do laço existente:

```python
# Conjunto explicito em vez de fonte_id.startswith("ioes-busca"): o modo de
# chamada e contrato da funcao, nao propriedade do nome dela. Com o prefixo,
# acrescentar um terceiro escopo (ou renomear um id) mudaria silenciosamente a
# forma como main() chama o coletor.
FONTES_COM_DIAGNOSTICO = {"ioes-busca-dio", "ioes-busca-dom"}

diag = {}
chamavel = FONTES[fonte_id]
if fonte_id in FONTES_COM_DIAGNOSTICO:
    brutos = chamavel(diagnostico=diag, janela_dias=args.janela_ioes_dias,
                      max_paginas=args.max_paginas_ioes,
                      max_achados=args.max_achados_ioes,
                      indice=indice_mun)
else:
    brutos = chamavel()
...
registro_fonte.update({k: v for k, v in diag.items() if k != "nao_mapeados"})
nao_mapeados_brutos.extend(diag.get("nao_mapeados", []))
```

`cobertura_municipios` **não** é calculado dentro de fonte nenhuma. É uma função pura chamada
por `main()` depois do laço, para que `--fonte selecao-es` isolado também produza o bloco:

```python
def cobertura(indice, registros, achados, slugs_com_sinal_historico_antes, referencia):
    """Bloco cobertura_municipios. Funcao pura: recebe o indice do cadastro, os
    registros de dados/, a lista final de achados, o conjunto HISTORICO de slugs
    que ja tiveram sinal em QUALQUER execucao anterior, e a data de referencia.
    Devolve dict.

    O quarto parametro e historico, e nao o retrato da janela anterior, porque
    'vistos_pela_primeira_vez' precisa significar "primeira vez em todas as
    execucoes": com o retrato, um municipio que publica hoje, fica uma semana
    sem publicar e volta seria anunciado DE NOVO como primeiro ato, e §10.2
    abriria issue (§7.4). Vem de descobertas.json anterior ->
    cobertura_municipios.slugs_com_sinal_historico, via o 'bruto' que
    carregar_anterior() passa a devolver (§7.2); set() quando a chave nao
    existe, isto e, na primeira execucao com cadastro.

    'referencia' entra porque com_achado_na_janela conta apenas achados vistos
    NESTA execucao (§7.4), e a lista final inclui preservados de execucoes
    anteriores.

    Pura para ser testavel sem rede e sem disco.
    """
```

**Por que não usar o `cobertura_vistos` do e-mail** (`email/.estado-envios.json`, §11.3): aquele é
estado *do envio*. Derivar a cobertura dele tornaria a métrica dependente de ter havido e-mail, e
`--fonte` isolado (§15.25) ou `--forcar` mudariam o resultado. O estado da cobertura vive em
`descobertas.json`, junto do dado que ele descreve.

### 6.4 Política de consulta, tetos e orçamento

- **Frases de assunto** (`FRASES_IOES`, 2 itens): `"concurso publico"` e `"processo seletivo"`.
  Parar em duas é decisão medida: `q=edital` na mesma janela dá 161 hits no DIO com queda
  enorme de precisão — pega licitação, chamamento público e credenciamento, que não são objeto
  deste repositório. As duas frases mapeiam o vocabulário de `comum.TIPOS_VALIDOS`.
- **Janela**: `--janela-ioes-dias`, padrão **7**. `di: = comum.hoje() - janela`, sem `df:`.
  Sete dias cobrem o cron diário e absorvem alguns dias de falha consecutiva. É parâmetro
  **separado** de `--janela-dias` (que trata de descarte por prazo de inscrição encerrado):
  são conceitos distintos e misturá-los faria o operador mudar um e quebrar o outro.
- **Tetos.** Os padrões do passe anterior (10 páginas, 200 achados) cortariam o volume
  **ordinário** medido: DOM/`"processo seletivo"` tem 131 hits, isto é, 14 páginas, e a soma dos
  quatro pares escopo×frase é 218 hits. Truncar o DOM significa perder exatamente os municípios
  pequenos que este trabalho existe para enxergar. Padrões corrigidos:

| Argumento | Padrão | Teto | Justificativa |
| --------- | -----: | ---: | ------------- |
| `--max-paginas-ioes` | **20** | 100 | 200 resultados por escopo×frase cobre os 131 medidos com ~50% de folga |
| `--max-achados-ioes` | **1000** | 5000 | por fonte; **218 hits na janela de 7 dias** (≈ 31 por dia), folga para edição extra |

**Unidade dos 218, porque o passe anterior escreveu "por dia" e isso dimensionava três decisões.**
Os quatro pares escopo×frase de §6.2 (DIO 16/8, DOM 63/131) foram medidos **na janela de 7 dias**,
com `di: = hoje - 7`. Logo: **218 hits por janela**, ≈ **31 por dia** de fluxo inédito. Os tetos
desta tabela são **por execução e por fonte**, e por isso continuam dimensionados pelos 218 (uma
execução varre a janela inteira, não o dia) — o que muda é o raciocínio de crescimento do arquivo
em §6.9.1, que é por dia e estava errado por um fator de 7.

- **Orçamento de tempo**: por fonte, 2 frases × ≤20 páginas = ≤40 requisições; as duas fontes
  somam **≤80 requisições ≈ 80 s** a 1,0 s/req medido, mais `time.sleep(0.2)` entre páginas por
  cortesia ≈ **~96 s** no pior caso. Confortável num job de Actions, e o pior caso só ocorre
  quando há volume para isso.
- Para de paginar quando `hits.hits` vem vazio **ou** quando o acumulado atinge `total`. Se o
  teto for atingido com `total` ainda maior: `::warning::` com quantos ficaram de fora,
  `truncado: true` no diagnóstico **e linha no corpo da issue** (§7.5) — truncamento recorrente
  é lacuna de cobertura e precisa de olho humano, não só de uma linha de log que ninguém lê.
- **Leitor próprio, sem cookiejar.** O buscador não exige sessão (verificado), ao contrário do
  Seleção ES. Reaproveitar `_abridor()` arrastaria `CookieJar` sem motivo:

```python
def _ler_bytes(url, cabecalhos=None):
    """Leitura crua para os endpoints que nao exigem sessao (IOES, IBGE).

    'Accept-Encoding: identity' pede texto puro, mas o servicodados.ibge.gov.br
    devolve gzip MESMO ASSIM (verificado: 200 com Content-Encoding: gzip) e o
    urllib nao descomprime sozinho — sem este tratamento, json.loads quebraria
    em 100% das execucoes e a reconciliacao com o IBGE nunca funcionaria.
    """
    cab = {"User-Agent": NAVEGADOR, "Accept-Encoding": "identity"}
    cab.update(cabecalhos or {})
    req = urllib.request.Request(url, headers=cab)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        bruto = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            bruto = gzip.decompress(bruto)
        codificacao = resp.headers.get_content_charset() or "utf-8"
    return bruto.decode(codificacao, "replace")
```

- **Timeout e retry**: reaproveitar `TIMEOUT = 30`. `_ler_com_retry()` faz **1 retentativa**
  após 2 s, apenas para `URLError`, `socket.timeout` e `HTTPError` com `code >= 500`.
  `HTTPError` 4xx **não** é retentado (é contrato errado, não indisponibilidade). O cron é
  diário e a janela de 7 dias já tolera um dia perdido; retry agressivo só aumentaria o risco
  de o job estourar tempo.

### 6.5 Segmentação em blocos de ato — a correção do produto cartesiano

O passe anterior mandava emitir "um achado por par (município, número de edital)" sem dizer
como um número se associa a um município. Medi o efeito nas 144 páginas: **30 páginas têm >1
município e >1 número de edital**, e o par cartesiano produziria **1.419 achados**, dos quais a
esmagadora maioria não existe. Pior, `numeros_de_edital()` (função existente) captura
`273/0001` e `318/0001` — fragmento de CNPJ: o "ano" `0001` aparece **55 vezes** na amostra.

**Decisão: segmentar a página em blocos de ato antes de parear.**

```python
# O diario separa atos por "Protocolo <n>". Medido em 144 paginas: 94 tem o
# delimitador (de 1 a 7 blocos por pagina) e 50 nao tem — TODAS as 50 no escopo
# DOM. Nessas 50, nenhuma tem simultaneamente >1 municipio e >1 numero de edital,
# ou seja, tratar a pagina sem "protocolo" como UM bloco nao reintroduz o
# cartesiano. Por isso nao ha segundo delimitador: inventar um por cabecalho de
# orgao seria especulacao sobre um caso que a medicao mostra inexistente.
DELIMITADOR_BLOCO = re.compile(r"protocolo \d+")

def _blocos_de_ato(texto_normalizado):
    partes = [p for p in DELIMITADOR_BLOCO.split(texto_normalizado) if len(p.strip()) >= 40]
    return partes or [texto_normalizado]
```

**Ordem das operações sobre `_source.conteudo`, fixada aqui porque três seções a tocam.** São
**seis estágios numerados**, quatro por página e dois por bloco; esta lista é a única ordem válida
do pipeline de texto, e §5.2, §5.3 e §7.2 são consumidoras dela, não definidoras:

```
--- por PAGINA ---
1. truncar _source.conteudo em 20.000 caracteres (§13.1)  -> conteudo_truncado: true se cortou
2. t = comum.normalizar(conteudo_truncado)
3. t = _limpar_boilerplate(t)                 # PAGINA inteira, UMA vez (§5.3)
4. PADROES_MENCAO + classificar_mencao sobre t # PAGINA (§7.2)
--- por BLOCO ---
5. blocos = _blocos_de_ato(t)                 # 'protocolo \d+' sobrevive a (3)
6. para cada bloco: passada de orgaos -> passada de municipios (§5.2)
                    -> pareamento de edital (regras abaixo)
```

**Por que a limpeza vem antes da segmentação, e por que isso é seguro.** O passe anterior fixava
`normalizar → segmentar → limpar por bloco` e, duas seções depois, §7.2 exigia um estágio de
"página limpa" que essa ordem não produzia — as duas seções eram inexequíveis juntas. Os números
medidos dos dois lados (as 8 ocorrências residuais de `vitoria` de §5.3; as 50 capturas em 64
páginas de §7.2) **só** se reproduzem com a limpeza aplicada **à página**. Limpar por bloco, além de
divergir dos números, quebra padrões de assinatura que atravessam a fronteira `protocolo \d+`. E
limpar antes de segmentar é seguro por uma razão específica e verificável: **`protocolo \d+` não
está em `PADROES_BOILERPLATE`** (§5.3) — ele saiu daquela lista exatamente para poder ser
delimitador, e no passe anterior estava nos dois papéis ao mesmo tempo, o que se autodestruía.
Nenhum dos cinco padrões de boilerplate de §5.3 consome a palavra `protocolo` seguida de número.

O truncamento vem **primeiro**, antes da segmentação. A alternativa (segmentar e truncar cada
bloco) manteria mais sinal, mas custa normalizar a página inteira antes de saber se ela interessa,
e o ganho é marginal: 20.000 caracteres cobrem com folga o cabeçalho e o corpo de qualquer ato,
e o que excede isso em página longa é quadro de classificação, não ato novo. O que **não** é
aceitável é a perda silenciosa: em página longa o corte pode levar blocos inteiros e municípios
reais desapareceriam sem sinal. Por isso o achado ganha `conteudo_truncado: true` quando houve
corte, e o diagnóstico da fonte agrega `paginas_truncadas: <int>` — se esse número crescer, a
decisão do teto é revista com dado, não com palpite.

Regras de pareamento, explícitas:

- município e número de edital só formam par **dentro do mesmo bloco**;
- bloco sem município → `municipio_escopo: "indeterminado"`, sem herdar do bloco anterior (§5.4);
- **no máximo 1 achado por (bloco, município)**. Havendo vários números no bloco, vale o
  primeiro que apareça a ≤200 caracteres de `edital`, `concurso publico` ou `processo seletivo`;
  os demais vão para `editais_citados` (lista) em vez de multiplicar achados;
- descartar número cujo ano não esteja em **`[ano_corrente - 4, ano_corrente + 1]`**. Medido na
  amostra: isso mata `0001` (55 ocorrências), `17/2007`, `x/1958`..`x/2021` (números de lei) e
  `x/2031`. A faixa é 4 anos para trás porque há ato de 2026 nomeando candidato de
  `concurso publico 01/2022`, caso real na amostra.

O filtro de ano é seguro porque **não descarta o achado, só o número**: um bloco cujos números
foram todos rejeitados cai na chave por página (§6.6) e o município continua contando para a
cobertura. Sem essa propriedade o filtro perderia sinal, e seria errado.

### 6.6 Chave estável e deduplicação determinística

`chave` precisa ser estável entre execuções (é o que preserva `primeira_deteccao`) e não deve
duplicar o mesmo certame em páginas diferentes:

- com número de edital válido:
  `"ioes-%s:%s:edital-%s" % (escopo, municipio_slug or "indeterminado", numero.replace("/", "-"))`
  — une as várias páginas e edições **do mesmo escopo** que tratam do mesmo edital;
- sem número: `"ioes-%s:%s:%s-%s" % (escopo, municipio_slug or "indeterminado", diario_id, pagina)`.
  Granularidade de página é o melhor disponível sem inventar identidade.

**`escopo` faz parte da chave, e a duplicação entre escopos é aceita — decisão, não descuido.**
Um edital municipal publicado tanto no Caderno dos Municípios do DIO quanto no DOM/AMUNES gera
**dois** achados, com títulos e URLs diferentes. A alternativa (remover `escopo` da chave quando
há número de edital) uniria os dois e perderia a propriedade que mais importa na curadoria: cada
achado aponta para **o PDF que de fato contém o ato**, e esse PDF é por escopo. Unificar obrigaria
a escolher uma das duas URLs e descartar a outra, ou a inventar um campo de lista de URLs que
nenhum consumidor lê. Como os dois achados contam para o **mesmo** `municipio_slug`, a cobertura
não é inflada — `com_achado_na_janela` conta municípios distintos, não achados (§7.4). O custo é
uma linha extra na quarentena, com rastreabilidade correta; o benefício é não perder a citação.

**Determinismo da deduplicação.** O conjunto `vistos` de `main()` mantém a primeira ocorrência,
mas a ordem da API **não é determinística dentro de um dia**: medi que o campo `sort` é o
timestamp do **dia** (`[1790812800000]` para todos os itens de 2026-10-01), logo o desempate
intradiário é interno do Elasticsearch e pode variar. Sem ordenação explícita, o achado retido
— e portanto `titulo`, `url`, `edicao` — mudaria entre execuções sem nada mudar na fonte,
gerando ruído diário em `descobertas.json` e risco no `gerar_readme.py --check`.

Decisão: antes de devolver, `coletar_ioes()` ordena os candidatos por chave explícita e o
**primeiro após a ordenação** ganha:

```python
# Ordem: data mais RECENTE primeiro; dentro da data, menor diario_id e menor
# pagina. A API ordena por DIA, nao por item (campo sort = timestamp do dia),
# entao sem este desempate qual pagina "ganha" a chave varia entre execucoes.
candidatos.sort(key=lambda a: (a["data_publicacao_ato"] or "", -int(a["_diario_id"]),
                               -int(a["_pagina"])), reverse=True)
```

**A deduplicação acontece dentro de `coletar_ioes()`, antes do `return`, e não no `vistos` de
`main()`.** Dois blocos da mesma página que citem o mesmo município produzem, pela chave sem número,
`ioes-<escopo>:<slug>:<diario_id>-<pagina>` **idêntica** — §6.5 permite 1 achado por
(bloco, município), e a chave só tem granularidade de página. Se o descarte ficasse para o `vistos`
de `main()`, quem sobrevive dependeria da ordem de iteração de um conjunto construído fora do
coletor, isto é, de código que não conhece a ordenação de §6.6. Decisão: `coletar_ioes()` ordena os
candidatos pela chave explícita acima e **colapsa por `chave`** antes de devolver, mantendo o
primeiro. `main()` continua com seu `vistos` (ele protege contra colisão **entre** fontes), mas não
é mais ele que decide este caso.

Os campos auxiliares `_diario_id` e `_pagina` são removidos do achado antes da gravação
(prefixo `_` marca "interno ao coletor", e gravá-los ampliaria `CAMPOS_DESCOBERTA` sem razão).

### 6.7 Forma do achado de diário

Campos obrigatórios de `validar.CAMPOS_DESCOBERTA` (`chave`, `fonte_id`, `orgao`, `titulo`,
`url`, `primeira_deteccao`, `ultima_deteccao`, `no_repositorio`) são todos preenchidos:

| Campo | Valor |
| ----- | ----- |
| `orgao` | `"Prefeitura de <Nome>"` quando a marca de contexto foi `prefeitura`/`municipio`; o nome do órgão vinculado quando o casamento veio de `orgaos_vinculados`; `comum.AUSENTE` quando indeterminado |
| `titulo` | primeiro trecho de `highlight.conteudo`, tags removidas, colapsado por `re.sub(r"\s+", " ", ...)`, truncado em 200 caracteres |
| `esfera` | `"municipal"` quando resolveu município ou órgão vinculado municipal; `"intermunicipal"` para consórcio/agência; `None` quando indeterminado |
| `tipo` | `"concurso_publico"` para a frase `"concurso publico"`; `"processo_seletivo_simplificado"` para `"processo seletivo"` |
| `inscricoes` | `{"inicio": null, "fim": null}` — a página do diário não informa prazo de forma confiável e **extrair data por regex de PDF seria inventar dado** |
| `vagas_informadas` | `null`, pelo mesmo motivo |
| `categoria` | `"ato_diario"` (§6.8) |
| `data_publicacao_ato` | `_source.data` (já vem `AAAA-MM-DD`) |
| `edicao` | número extraído de `suplemento` (§6.2), ou `null` |
| `editais_citados` | demais números do bloco (§6.5), ou `[]` |
| `conteudo_truncado` | `true` quando `_source.conteudo` foi cortado em 20.000 caracteres (§6.5), senão `false` |
| `municipio` | **`nome` oficial do cadastro** (com acentos, `indice.por_slug[slug]["nome"]`) quando `municipio_slug` resolve; `comum.AUSENTE` quando não resolve. **Nunca o trecho casado no texto**, que está normalizado e sem acento |
| `municipio_codigo_ibge` | `codigo_ibge` do cadastro quando `municipio_slug` resolve; `null` caso contrário |
| `municipio_slug` | slug do cadastro, ou `null` (§5.2, §5.4) |
| `municipio_confianca` | `"alta"` / `"baixa"` / `null` (§5.3) |
| `municipio_escopo` | vocabulário fechado de §6.7, sempre presente |
| `municipio_origem` | **como** o município foi resolvido: `"nome"`, `"alias"`, `"orgao_vinculado"` ou `null` quando não resolveu. É a `origem` que `padroes_ordenados` carrega (§5.1) |
| `orgao_vinculado_id` | `id` do órgão quando a passada de §5.2.1 casou; `null` caso contrário |

**`municipio_origem` existe para que a cobertura seja auditável e para que o aprendizado de alias
feche o ciclo.** Com ele, "quantos municípios contaram por alias e não pelo nome oficial?" é uma
consulta ao arquivo, e um alias que se revele errado tem como ser rastreado até os achados que
creditou. O campo é **gravado sempre** por `normalizar_achado()` (§6.10) e o validador confere
**apenas o vocabulário** quando presente (§9.4) — deliberadamente **não** entra na lista de campos
de presença obrigatória, para não criar um quinto item de tolerância de legado (§6.9) em troca de
nada: achado antigo simplesmente não tem a informação.

As duas primeiras linhas fecham um furo do passe anterior, que listava `municipio` e
`municipio_codigo_ibge` remetendo a "§5.3, §5.4" — seções que definem apenas os campos
`municipio_slug`/`_confianca`/`_escopo`. Ficava sem valor definido um campo que
`gerar_relatorio.py` e `gerar_email.py` **exibem**, e um campo que §9.4 exige coerente. Gravar o
nome oficial (e não o trecho normalizado) é o que mantém `"Vitória"` legível no relatório em vez
de `"vitoria"`, e é a mesma grafia que os registros de `dados/` usam.

`status_estimado` continua vindo de `status_estimado()`; sem datas e sem `situacao_portal`
resulta `None`, que `valida_descobertas()` já aceita.

**Casamento com `dados/`: achado de diário usa `casar_estrito()`, não `casar()`.** `main()` chama
`casar()` para todo achado, e o passe anterior mantinha `casar()` intacto afirmando que ela "exige
coincidência de tokens de órgão além do número". Conferi no código e a afirmação é falsa para o
ramo sem número de edital: `tokens_identidade("Prefeitura de Serra")` devolve `{"serra"}` (medido —
`prefeitura` e `de` estão em `TOKENS_GENERICOS`), e o laço final de `casar()` aceita o primeiro
registro cujo `nome_tokens | local_tokens` cubra `{"serra"}` — qualquer certame daquele município.
Pior, `_coberto()` casa por prefixo: `_coberto("serra", {"serrana"})` é `True` (medido). Um ato de
nomeação em Serra sairia com `no_repositorio: true` apontando para um concurso não relacionado,
corrompendo `ja_no_repositorio`/`pendentes_de_curadoria` e **desaparecendo da curadoria**, que é o
pior desfecho possível para a quarentena.

```python
# Ato de diario casa com registro curado SOMENTE por evidencia forte: url igual
# ou numero de edital coincidente. O ramo final de casar() (por tokens de orgao)
# casaria qualquer ato de Serra com qualquer certame de Serra, porque
# 'prefeitura' e 'de' sao genericos e sobra so o nome do municipio — e um ato de
# nomeacao marcado como 'ja no repositorio' sai da fila de curadoria sem ter
# sido conferido. Para achado de oportunidade o ramo fraco continua valendo: ali
# o orgao e o titulo vem de um portal de concursos, nao de texto corrido.
registro = (casar(achado, indice) if achado["categoria"] == "oportunidade"
            else casar_estrito(achado, indice))
```

`casar_estrito()` reusa as **duas primeiras** regras de `casar()` (URL normalizada igual; número de
edital coincidente **mais** cobertura de tokens) e omite o ramo final. `casar()` e
`tokens_identidade()` seguem **sem alteração** — mexer nelas reabriria o risco que os comentários
do arquivo descrevem, e o problema não é o comportamento delas para o caso em que foram escritas.

**`municipio_escopo` em vez de `municipio_indeterminado`.** O passe anterior usava um booleano
`municipio_indeterminado`, e a revisão mostrou que a regra derivada ("slug nulo exige
indeterminado") obrigaria o coletor a **afirmar algo falso** para SEDU/SESA/PM-ES, onde o
certame é estadual e o slug é legitimamente nulo. Em vez de uma exceção na regra, trocamos por
um campo positivo de vocabulário fechado:

```
municipio_escopo ∈ {"municipal", "intermunicipal", "estadual", "federal", "indeterminado"}
```

Um só campo, sempre presente, nunca ambíguo: `null` deixa de significar duas coisas
diferentes. `municipio_indeterminado` não existe neste design.

### 6.8 `categoria`: por que achado de diário não é "vaga nova"

Um ato de diário pode ser nomeação, convocação, homologação ou retificação — não
necessariamente abertura de inscrição. Se esses achados entrassem nas listas que hoje alimentam
o e-mail e o README, o efeito seria ruim de um jeito específico e verificável:
`gerar_email.classificar_descobertas()` só descarta por prazo quando `inscricoes.fim` existe
(`if fim is not None and fim < referencia: continue`), e achado de diário **não tem** prazo —
logo passariam todos, e o resumo diário viraria despejo do diário oficial.

Decisão: todo achado ganha `categoria`, com vocabulário fechado de dois valores:

- `"oportunidade"` — `selecao-es`, `concursosnobrasil-es` (comportamento atual, inalterado);
- `"ato_diario"` — `ioes-busca-dio`, `ioes-busca-dom`.

O campo é escrito em **um** lugar, `normalizar_achado()` (§6.10), e não em cada coletor. Nenhuma
fonte precisa conhecer o vocabulário novo.

**São quatro consumidores, não três.** O passe anterior listou `gerar_readme`, `gerar_email` e
`gerar_relatorio`, e esqueceu o mais importante: `coletar.main()` ele mesmo.

| Consumidor | Mudança |
| ---------- | ------- |
| `coletar.main()` | **`novos` passa a aceitar só `categoria == "oportunidade"`** (§6.10) |
| `gerar_readme.carregar_descobertas()` | filtra `a.get("categoria") != "ato_diario"`, mantendo a tabela "Detectado automaticamente" com o significado de hoje |
| `gerar_email.classificar_descobertas()` | ignora `"ato_diario"` na lista de novidades |
| `gerar_relatorio.bloco_coleta()` | conta os dois separadamente |

Sem a primeira linha, o resto não serve para nada. No código atual, `novos.append(achado)` ocorre
para **todo** achado inédito sem registro casado:

```python
else:
    achado["primeira_deteccao"] = referencia.isoformat()
    if registro is None:
        novos.append(achado)
```

Com os 218 hits medidos na janela de 7 dias (DIO 16/8, DOM 63/131) e ≥1 achado por hit, `novos`
passaria de dezenas para **centenas por dia**; a tabela da issue (`| Órgão | Oportunidade |
Inscrições | Fonte |`) viraria despejo do diário oficial com `Inscrições = não informado` em todas
as linhas; e o título `"<novos> nova(s) oportunidade(s) do ES"` passaria a mentir — exatamente o
estrago que esta seção descreve para o e-mail e evita lá.

### 6.9 Migração do `descobertas.json` já commitado

O arquivo versionado tem **37 achados sem `categoria`** e sem nenhum campo `municipio_*`, e não
tem os blocos novos. Sem migração explícita o repositório ficaria **reprovado antes de qualquer
coleta** (o job `validar` roda `validar.py` em todo PR e push), e pior: `coletar.main()`
reanexa achados antigos **verbatim** (`finais.append(previo)` nos dois ramos de preservação),
então mesmo depois de uma coleta nova os herdados continuariam sem `categoria` e o passo
"Revalidar depois das alteracoes" travaria o commit automático todos os dias.

Duas medidas, uma em cada lado:

1. **No coletor**, backfill explícito ao reaproveitar `previo`, nos **dois** ramos:

```python
# Achado herdado de execucao anterior ao cadastro de municipios. O default e
# 'oportunidade' porque so as duas fontes de oportunidade existiam quando esses
# achados foram gravados. Sem este backfill o validador reprovaria o proprio
# commit automatico, todos os dias, por falta de um campo que a execucao antiga
# nao tinha como gravar.
previo.setdefault("categoria", "oportunidade")
previo.setdefault("municipio_slug", None)
previo.setdefault("municipio_escopo", "indeterminado")
previo.setdefault("municipio_confianca", None)
```

2. **No validador**, as checagens dos blocos novos (`cobertura_municipios`,
   `municipios_nao_mapeados`, `reconciliacao_ibge`) valem **somente se a chave existir**. Chave
   ausente = arquivo de versão anterior = **aviso** ("descobertas.json anterior ao cadastro de
   municipios; rode a coleta"), não erro.

**As duas medidas acima não bastam, e o passe anterior enunciou o risco sem fechá-lo.** Elas
cobrem as chaves de **topo** e o backfill de `previo`, mas a exigência de `categoria` e
`municipio_escopo` é **por achado**, e o arquivo versionado tem 37 achados sem nenhum dos dois
(medido: 8 chaves de topo, 37 achados, 0 com `categoria`, sendo 19 de `selecao-es` e 18 de
`concursosnobrasil-es`). O backfill da medida 1 vive em `coletar.py`, que **não roda** no job
`validar` (`if: pull_request || push`). Resultado: o PR que implementa este design é reprovado pelo
próprio validador que ele acrescenta, em 37 achados × 2 campos, antes de qualquer coleta.

Adotadas **as duas** correções, porque resolvem problemas diferentes:

3. **Tolerância versionada** — `categoria` e `municipio_escopo` **ausentes** em achado cuja
   `primeira_deteccao` seja anterior ao `ibge_consultado_em` do cadastro geram **aviso**, não erro.
   Presentes e fora do vocabulário continuam **erro**. Isto protege a execução agendada contra
   qualquer arquivo antigo que apareça depois (checkout de branch velha, revert), não só contra o
   arquivo de hoje. A data do cadastro é a fronteira natural: tudo gravado antes dela é
   necessariamente de uma versão do coletor que não tinha os campos.

```python
# Achado gravado antes do cadastro existir nao tinha como ter 'categoria': a
# fronteira e ibge_consultado_em do cadastro, que e a data em que este
# vocabulario passou a existir. Aviso e nao erro, senao um checkout de branch
# antiga reprova o CI por divida que ja foi paga no main.
#
# '<=', e nao '<': o cadastro e commitado no MESMO dia em que a coleta anterior
# rodou. Medi o arquivo versionado: das 37 entradas, 2 tem
# primeira_deteccao == '2026-10-01' == ibge_consultado_em (as outras 35 sao de
# 09-23 a 09-30). Com '<' essas duas viram ERRO e nao aviso, que e o oposto da
# tolerancia que esta linha existe para dar — e a protecao prometida contra
# "checkout de branch velha, revert" falharia exatamente na fronteira.
legado = (achado.get("primeira_deteccao") or "") <= cadastro["ibge_consultado_em"]
```

4. **Migração no PR** — `coletar.py` ganha `--migrar-descobertas`, definido como **"aplica
   `normalizar_achado(achado, indice)` a cada achado e regrava"**, e não como uma lista própria de
   campos. Esta é a definição que importa: enquanto §6.9 listava quatro campos e §6.10 definia
   sete, as duas listas divergiriam na primeira mudança de esquema. Com a definição por função
   existe **um** lugar com a lista de campos — `normalizar_achado()` (§6.10) —, e os campos que o
   backfill de `previo` no item 1 aplica são, por construção, os mesmos. **Sem rede, sem coleta,
   idempotente** (`setdefault`). O arquivo migrado é commitado junto com a mudança do validador
   (declarado na tabela de §17), de modo que o repositório fica limpo imediatamente em vez de
   depender da próxima execução agendada.

A tolerância sozinha deixaria dívida silenciosa no arquivo versionado por tempo indeterminado; a
migração sozinha não protegeria contra arquivo antigo reaparecendo. Juntas, a dívida desaparece
agora e não volta.

### 6.9.1 Retenção: `ato_diario` não tem prazo, logo a poda existente nunca o alcança

A única poda de `descobertas.json` hoje depende de prazo de inscrição, nos **dois** lugares em que
aparece:

```python
fim = comum.data_ou_none((previo.get("inscricoes") or {}).get("fim"))
if fim and fim < limite_antiguidade:
    continue  # saiu da janela de relevancia
...
previo["ausente_na_fonte"] = True
finais.append(previo)
```

Por decisão explícita de §6.7, o achado de diário tem `inscricoes = {"inicio": null, "fim": null}`.
Então `fim` é sempre `None`, a condição nunca dispara, e o laço de preservação **reanexa o achado
para sempre** com `ausente_na_fonte: true`. Como a janela do IOES anda um dia por vez, cada
execução acrescenta os atos do dia e mantém todos os anteriores. **Na ordem de grandeza medida —
218 hits na janela de 7 dias, ≈ 31 achados inéditos por dia (§6.4)** — o arquivo, que o bot
**commita diariamente**, cresce em **algumas dezenas de entradas por dia**, e com ele o diff
diário, o tempo de `validar.py`, de `gerar_readme.py` e de `gerar_email.py`. Nenhuma seção do passe
anterior tratava disso: §7.2 poda apenas `municipios_nao_mapeados`.

**A conta que dimensiona a retenção, explícita, porque o passe anterior a fez com a unidade
errada.** Com 90 dias de retenção e ~31 achados inéditos/dia, o regime permanente é
**90 × 31 ≈ 2,8 mil achados** — contra o aviso de `len(achados) > 5000` de §9.4, que fica com
**~45% de folga**. Com o número errado ("218/dia") o regime seria ~19,6 mil, o aviso dispararia para
sempre e a conclusão seria que 90 dias é inviável: a unidade não era detalhe de redação, ela
mudava a decisão.

**Decisão: regra de retenção própria por categoria, no laço de preservação.**

```python
# Ato de diario nao tem prazo de inscricao, logo a poda por 'inscricoes.fim'
# nunca o alcanca e o laco de preservacao o reanexaria para sempre. 90 dias e o
# horizonte em que um ato ainda e util para curadoria (um edital publicado ha
# tres meses ja foi promovido para dados/ ou ja foi descartado); o teto de 365
# existe para que um erro de digitacao no argumento nao transforme a quarentena
# em arquivo historico.
RETENCAO_ATO_DIARIO_DIAS = 90   # argumento --retencao-atos-dias, teto 365
```

Descartar `previo` com `categoria == "ato_diario"` cuja `data_publicacao_ato` — ou, na falta dela,
`ultima_deteccao` — seja anterior a `referencia - RETENCAO_ATO_DIARIO_DIAS`, contabilizando em
`descartados_por_retencao`, exposto no resumo impresso, no `--json` do validador e em
`bloco_coleta()` (§11.2). A retenção **não** se aplica a `categoria == "oportunidade"`: lá a poda
por `inscricoes.fim` já funciona e é a regra semanticamente correta.

Como rede de segurança contra a regressão dessa poda, §9.4 ganha um **aviso** quando
`len(achados) > 5000`: se a retenção quebrar, o sintoma aparece como aviso num arquivo que cresce,
em vez de como lentidão inexplicada meses depois.

### 6.10 Normalização de todo achado, em um ponto único

Esta é a peça que faltava no passe anterior e a causa comum das quatro findings bloqueantes. §6.7
especificava os campos `municipio_*` **apenas** para o achado de diário, e §6.9 fazia backfill
apenas em `previo`. Não havia regra para os achados **novos** das duas fontes existentes (19 de
`selecao-es` + 18 de `concursosnobrasil-es` no arquivo atual) — e §9.4 torna `municipio_escopo`
ausente um **erro**, sem restringir por categoria. Na primeira coleta real o validador reprovaria,
e o passo "Revalidar depois das alteracoes" bloquearia o commit automático: CI vermelho, não
defeito sutil.

**Decisão: `main()` normaliza todo achado, de qualquer fonte, antes de `finais.append`.**

```python
def normalizar_achado(achado, indice):
    """Garante os campos de categoria/municipio em TODO achado, de qualquer fonte.

    Ponto unico de proposito: nenhuma fonte precisa conhecer o vocabulario novo,
    e o validador nunca ve achado sem os campos obrigatorios. Sem este ponto,
    cada coletor novo teria de lembrar de preencher os campos de categoria e de
    municipio (slug, codigo_ibge, confianca, escopo, origem), e esquecer um deles
    so apareceria como CI vermelho depois do merge. E a mesma funcao que
    --migrar-descobertas aplica (§6.9), para que exista UMA lista de campos.

    Usa setdefault e nao atribuicao: o coletor de diario JA resolveu municipio
    com evidencia de texto (§5.2) e essa resolucao e mais forte que a daqui.
    """
    achado.setdefault("categoria", "oportunidade")

    if achado["categoria"] == "oportunidade":
        # Portal de terceiro nao e evidencia de ato: o nome do municipio vem de
        # um campo de formulario, nao de um diario oficial. Por isso confianca
        # 'baixa' por construcao, e por isso achado de oportunidade NUNCA entra
        # na cobertura (§7.4) — a metrica mede atividade observada em ato.
        #
        # resolver_municipio_em_texto e nao resolver_municipio: nos achados reais
        # destas duas fontes o campo e 'ARIES', 'SEDU', 'Prefeitura de Anchieta',
        # 'Camara Municipal de ...'. A consulta EXATA por chave devolveria None em
        # praticamente todos e municipio_slug nasceria sempre nulo — a linha
        # 'oportunidade ... resolve' da tabela abaixo nunca ocorreria. Os dois
        # campos vao CONCATENADOS porque o nome do municipio pode estar em
        # qualquer um dos dois, e a passada longest-first lida com texto livre.
        alvo = " ".join(x for x in (achado.get("municipio"), achado.get("orgao")) if x)
        slug, origem = comum.resolver_municipio_em_texto(alvo, indice)
        achado.setdefault("municipio_slug", slug)
        achado.setdefault(
            "municipio_codigo_ibge",
            indice.por_slug[slug]["codigo_ibge"] if slug else None)
        achado.setdefault("municipio_confianca", "baixa" if slug else None)
        achado.setdefault("municipio_origem", origem)
        achado.setdefault("municipio_escopo",
                          "municipal" if slug else
                          ("estadual" if achado.get("esfera") == "estadual"
                           else "indeterminado"))
    achado.setdefault("municipio_origem", None)
    achado.setdefault("orgao_vinculado_id", None)
    achado.setdefault("conteudo_truncado", False)
    return achado
```

A tabela de regras, para que não reste interpretação:

| Situação | `municipio_slug` | `municipio_confianca` | `municipio_escopo` | `municipio_origem` |
| -------- | ---------------- | --------------------- | ------------------ | ------------------ |
| `oportunidade`, `municipio` + `orgao` resolve para **um** município | slug | `"baixa"` | `"municipal"` | `"nome"` / `"alias"` / `"orgao_vinculado"` |
| `oportunidade`, resolve para **dois ou mais** (ambiguidade) | `null` | `null` | `"indeterminado"` | `null` |
| `oportunidade`, não resolve, `esfera == "estadual"` | `null` | `null` | `"estadual"` | `null` |
| `oportunidade`, não resolve, demais casos | `null` | `null` | `"indeterminado"` | `null` |
| `ato_diario` | já resolvido pelo coletor (§5.2–§5.4) | `"alta"`/`"baixa"`/`null` | §5.2.1, §5.4 | §5.1, §5.2.1 |

A linha da ambiguidade é consequência de `resolver_municipio_em_texto()` devolver `(None, None)`
quando o texto casa mais de um município (§5.1): `"Prefeitura de Serra e de Vila Velha"` **não**
credita nenhum dos dois. Preferir o primeiro seria desempate por palpite, e §4 proíbe isso para o
dado curado pela mesma razão.

**Achado de `oportunidade` nunca conta para a cobertura**, por construção: a confiança é sempre
`baixa`, e §7.4 conta só `alta`. A métrica continua significando "município com ato observado em
diário oficial", que é o que §5.3 definiu — e não "município que apareceu em algum portal".

**E o filtro de novidade, no mesmo laço:**

```python
# So oportunidade e 'novidade'. Ato de diario pode ser nomeacao, convocacao ou
# homologacao: contar isso como vaga nova poe centenas de linhas por dia na
# tabela da issue, todas com 'Inscricoes: nao informado', e faz o titulo mentir.
if registro is None and achado.get("categoria") == "oportunidade":
    novos.append(achado)
elif registro is None:
    atos_novos.append(achado)
```

Os atos de diário inéditos são contados em `atos_novos` e publicados como
`atos_diario_novos=<int>` em `--saida-github`, exibidos na issue em **linha de resumo**, nunca na
tabela de oportunidades (§7.5).

**A terceira novidade possível: primeiro ato num município.** Depois de corrigir `novos`, um dia
cuja única notícia seja "primeiro ato detectado em Sooretama" não abriria issue nenhuma — §7.1
promete essa notificação e a condição de §10.2 não tinha saída para ela. Por isso `--saida-github`
ganha também `primeira_vez=<len(cobertura_municipios.vistos_pela_primeira_vez)>`, que entra na
condição da issue (§10.2) e como quarta parte do título (§7.5).

---

## 7. Decisão 5 — detecção de município novo / não mapeado

São **três** situações distintas com tratamentos distintos. Confundi-las seria o erro fácil.

### 7.1 (A) Município do cadastro com atividade inédita

Sooretama nunca teve registro nem achado, e hoje apareceu. Não é anomalia: é a notícia que o
repositório existe para dar. Entra na cobertura e na novidade do e-mail/issue como "primeiro
ato detectado em \<município\>", registrado em
`descobertas.json → cobertura_municipios.vistos_pela_primeira_vez`.

### 7.2 (B) Nome de município citado que não resolve contra o cadastro

Pode ser variante ortográfica sem alias, erro de OCR do PDF, ou município efetivamente novo.

**Os padrões têm de rodar sobre o texto normalizado.** O passe anterior misturou literal
minúsculo (`munic[ií]pio de`) com classe de captura maiúscula (`[A-ZÁ-Ú]`) e literal `ES`: no
texto normalizado a captura nunca casa, e no texto bruto o diário escreve `MUNICÍPIO DE` em
caixa alta. Medi nas 144 páginas: **o padrão do passe anterior produz 1 captura**; a versão
minúscula sobre o texto normalizado produz **137**. O requisito nascia silenciosamente morto.

```python
# Capturas sobre o texto JA normalizado (minusculas, sem acento). O diario
# escreve "MUNICIPIO DE X/ES" em caixa alta; normalizar antes evita precisar de
# re.I e de classes acentuadas, que foi o erro da primeira versao destes padroes.
PADROES_MENCAO = (
    re.compile(r"municipio de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]\s*es\b"),
    re.compile(r"prefeitura (?:municipal )?de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]"),
    re.compile(r"camara municipal de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]"),
)
```

**Poda da captura — defeito que nem o design nem a revisão tinham visto.** Com os padrões
acima funcionando, apliquei-os às 144 páginas e classifiquei as capturas contra o cadastro: das
capturas que **não** resolvem, **7 em 7 eram falso positivo**, todas por excesso de captura
(o terminador `[/,-]` está longe, e a captura engole a frase seguinte):

```
3x 'joao neiva por falta disciplinar e'      2x 'santa teresa far'
1x 'santa leopoldina no 001'                 1x 'ibiracu espirito santo 27 165 208'
1x 'fundao e publicado no diario oficial dos municipios'
1x 'santa maria ate a data indicada no anexo i'
1x 'que trata esta lei constitui'
```

Seis das sete contêm um município **real** como prefixo. Reportá-las abriria issue pedindo que
alguém cadastrasse "joao neiva por falta disciplinar e" como alias. A regra que resolve é poda
por prefixo de tokens, contra o próprio cadastro:

```python
# Teto do NOME CANDIDATO gravado em municipios_nao_mapeados. E o maior nome
# oficial de municipio do ES (medido: 4 tokens, em 12 nomes), porque o candidato
# e um suposto nome de municipio e passar disso e so a frase que a captura
# engoliu. Nao confundir com indice.max_tokens_nome, que e o teto da BUSCA por
# prefixo e vale 8 (medido: 'servico autonomo de agua e esgoto de aracruz', uma
# chave de orgao de §4.1): com o teto da busca em 4, as chaves de orgao de 5 a 8
# tokens nunca seriam alcancadas pela poda e 'instituto de previdencia dos
# servidores de cariacica' viraria candidato eternamente.
MAX_TOKENS_CANDIDATO = 4

def classificar_mencao(captura, indice):
    """Resolve a captura por PREFIXO de tokens, do mais longo para o mais curto.

    A captura do diario engole texto depois do nome ("joao neiva por falta
    disciplinar e"): medido, 6 de 7 capturas nao resolvidas eram municipio REAL
    seguido de frase. Testar prefixos do mais longo para o mais curto resolve
    'venda nova do imigrante' antes de tentar 'venda nova', e so chama de
    candidato o que nao resolve em NENHUM tamanho.
    """
    toks = comum.chave_nome(captura).split()
    for n in range(min(len(toks), indice.max_tokens_nome), 0, -1):
        prefixo = " ".join(toks[:n])
        slug = indice.por_chave_nome.get(prefixo)
        if slug:
            return "mapeado", slug
    return "candidato", " ".join(toks[:MAX_TOKENS_CANDIDATO])
```

**Dois tetos, com papéis diferentes e por isso números diferentes.** O da **busca** é
`indice.max_tokens_nome`, calculado como `max(len(k.split()) for k in por_chave_nome)` (§5.1) e hoje
igual a **8**; subir o teto da busca só pode **resolver mais** capturas, nunca menos, então os
números medidos adiante (7 falso positivos → 2) continuam valendo. O do **candidato gravado** é
`MAX_TOKENS_CANDIDATO = 4`, e é ele que mantém as cadeias exibidas na issue como as medidas neste
documento (`'que trata esta lei'`, `'santa maria ate a'`) em vez de parágrafos inteiros.

Efeito medido: as capturas resolvem para **29 municípios distintos** (137 ocorrências) e os
falso positivos caem de 7 para **2** (`'que trata esta lei'` e `'santa maria ate a'`), cada um
com **1** ocorrência — e portanto eliminados pelo filtro de ≥2 ocorrências abaixo.

**O mecanismo foi testado por injeção, não só por ausência de ruído.** Removi João Neiva e
Sooretama do cadastro e rodei de novo: o pipeline passou a reportar `joao neiva` com 18
ocorrências (mais 3 da variante com excesso) e `sooretama` com 1. Ou seja, **a detecção de
município não mapeado funciona de verdade** — e esse experimento é o teste de regressão
descrito em §16, porque "não aparece ruído" é indistinguível de "não aparece nada".

**Filtros obrigatórios antes de reportar**, para não transformar isto em gerador de ruído:

- descartar captura com menos de 3 caracteres, ou só dígitos;
- descartar captura cujos tokens sejam todos genéricos (`coletar.TOKENS_GENERICOS`);
- descartar captura que seja nome de UF ou de capital de outro estado (lista curta explícita),
  porque diário do ES cita convênio com outros entes;
- exigir `paginas_distintas >= 2` **OU** `com_marca_uf` (captura vinda do primeiro de
  `PADROES_MENCAO`, o que exige `/ES`). Ocorrência única sem `/ES` é quase sempre OCR ruim — mas a
  disjunção importa: na injeção acima, `sooretama` apareceu em **1** página, e só é reportado
  porque veio com a marca de UF;
- **consolidar variantes por prefixo**: se o candidato A é prefixo de tokens do candidato B,
  somar as ocorrências em A (o mais curto) e descartar B. Sem isso, `joao neiva` (18) e
  `joao neiva por falta` (3) virariam duas linhas da mesma issue.

**Dois contadores, e o filtro usa o segundo.** O passe anterior gravava um campo `ocorrencias` e
filtrava por "≥2 ocorrências em páginas distintas" — duas grandezas diferentes com um só nome. A
diferença é observável, porque o validador exige o campo e a issue o exibe em tabela: uma página
pode citar o mesmo município 5×, o que é 5 ocorrências e 1 página. Decidido:

| Campo | Conta | Papel |
| ----- | ----- | ----- |
| `ocorrencias` | casamentos da captura podada, somando todas as páginas | informativo; dimensiona a relevância na issue |
| `paginas_distintas` | páginas distintas em que a captura apareceu | **é o que o filtro usa** |
| `com_marca_uf` | `true` se alguma ocorrência veio do padrão com `/ES` | segundo termo da disjunção do filtro |

**Estágio em que os `PADROES_MENCAO` rodam, fixado** (o passe anterior não dizia, e medi que
importa): é o **estágio 4 de §6.5** — **por página**, sobre o texto normalizado e **depois** da
limpeza de boilerplate. Por página e não por bloco porque o objetivo aqui é descobrir *que nomes de
município o diário cita*, não associá-los a um ato; rodar por bloco daria contagens e `exemplos`
diferentes dos que este documento declara, sem ganho. Depois da limpeza porque a assinatura de ato
estadual é ruído para esta medida também. Que isto aconteça antes da segmentação é **consequência
da ordem de §6.5**, e não uma regra à parte desta seção — era essa duplicação que fazia as duas
seções se contradizerem. Na amostra, esse estágio dá 50 capturas em 64 páginas, com excessos reais
como `'santa leopoldina no 001'` — que é o insumo da poda por prefixo acima.

`exemplos` guarda **no máximo 3** trechos, de páginas distintas, para a issue ser legível e o
arquivo não crescer com texto de diário.

Cada candidato é gravado com **evidência**, não só com o nome:

```jsonc
{
  "nome_detectado": "sao roque do canaa",
  "ocorrencias": 7,
  "paginas_distintas": 3,
  "com_marca_uf": true,
  "fontes": ["ioes-busca-dom"],
  "exemplos": [
    {"url": "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11517/42",
     "data": "2026-10-01",
     "trecho": "...prefeitura municipal de sao roque do canaa, estado do..."}
  ],
  "primeira_deteccao": "2026-10-01",
  "ultima_deteccao": "2026-10-01",
  "provavel_alias_de": "sao-roque-do-canaa",
  "sugestao": "alias"
}
```

`provavel_alias_de` é preenchido **só** quando há candidato único por similaridade forte, e a
regra é conservadora e explícita: comparar o conjunto de tokens não genéricos da captura com o
de cada município e aceitar quando houver **igualdade de conjuntos** ou diferença de exatamente
um token de ligação (`de`, `do`, `da`). **Nada de distância de edição difusa** — sugestão errada
faria alguém cadastrar alias indevido. Sem candidato: `provavel_alias_de: null` e
`sugestao: "verificar"`.

**Preservação de estado.** `primeira_deteccao`/`ultima_deteccao` dos candidatos têm de
sobreviver entre execuções, e `carregar_anterior()` hoje devolve `{chave: achado}` e **descarta
o resto do arquivo** — não há como ler a lista anterior sem mudar a função. Mudança declarada:

```python
def carregar_anterior():
    """Devolve (achados_por_chave, bruto). 'bruto' e o dict inteiro do arquivo,
    necessario para preservar municipios_nao_mapeados entre execucoes — a versao
    anterior devolvia so os achados e jogava fora o resto.
    """
    ...
    return {a["chave"]: a for a in dados.get("achados", []) if a.get("chave")}, dados
```

O único call site em `main()` é atualizado; `bruto.get("municipios_nao_mapeados", [])` tolera
arquivo antigo (é o caso do arquivo commitado hoje).

**Regra de fusão entre execuções, escrita por inteiro** — o passe anterior dizia apenas que as
datas "têm de sobreviver", e cada escolha omitida muda o que a issue mostra:

```
chave de fusao      = nome_detectado  (captura JA podada por prefixo e JA
                      consolidada por prefixo entre si — §7.2 acima)
ocorrencias         = ACUMULADO: anterior + desta execucao
paginas_distintas   = ACUMULADO: anterior + desta execucao
com_marca_uf        = OR do anterior com o desta execucao
fontes              = uniao ordenada
primeira_deteccao   = do anterior quando existir; senao, a referencia de hoje
ultima_deteccao     = referencia desta execucao, quando apareceu agora;
                      senao preserva a anterior
exemplos            = ate 3, de paginas DISTINTAS, preferindo os mais recentes
filtro de reporte   = aplicado aos ACUMULADOS: paginas_distintas >= 2 OR com_marca_uf
remocao             = ultima_deteccao < referencia - (--janela-ioes-dias * 4)
```

**Por que acumulado e não por execução, com o caso que decide.** Um candidato real que apareça
**1× por dia em página distinta** e sem `/ES` tem, na semana, 7 páginas distintas — mas, com
contadores por execução, nunca passa de `paginas_distintas == 1` e **nunca** é reportado. O
mecanismo de aprendizagem de alias de §3.3 depende exatamente desse candidato: é assim que
`Cachoeiro do Itapemirim` apareceria se não estivesse cadastrado. Como a janela do IOES é de 7 dias
e as execuções se sobrepõem, o acumulado conta a mesma ocorrência mais de uma vez — isso é
**aceito**: `ocorrencias` e `paginas_distintas` são medidas de **insistência** do candidato, não
inventário de páginas, e o campo que faz juízo de grandeza na issue é o primeiro. A remoção por
`ultima_deteccao` é o que impede o acumulado de crescer para sempre: candidato que parou de aparecer
sai inteiro da lista, zerando os contadores junto.

### 7.3 (C) Divergência contra o IBGE — município de fato novo

Criação de município é lei estadual e o IBGE é quem publica a lista. Reconciliação em
`coletar.py`, com flag explícita:

```python
# Duas flags para o mesmo destino precisam de dest e default escritos, senao o
# padrao depende da ordem de declaracao. Ligada por padrao: conferir a lista
# oficial custa 1 requisicao por execucao.
parser.add_argument("--conferir-ibge", dest="conferir_ibge", action="store_true", default=True)
parser.add_argument("--sem-conferir-ibge", dest="conferir_ibge", action="store_false")
```

- `GET https://servicodados.ibge.gov.br/api/v1/localidades/estados/32/municipios` via
  `_ler_bytes()` (§6.4) — **o tratamento de gzip não é opcional aqui**: medi que o endpoint
  responde 200 com `Content-Encoding: gzip` mesmo sem o cliente pedir, e sem
  `gzip.decompress()` o `decode` falha com `UnicodeDecodeError` em 100% das execuções. Sem isso
  este caminho de detecção nasceria morto, igual ao (B).
- Comparar o conjunto de `codigo_ibge` da resposta com o do cadastro.
- Gravar em `descobertas.json → reconciliacao_ibge`:
  `{"status": "ok"|"erro"|"nao_conferido", "consultado_em", "total_ibge", "total_cadastro",
  "ausentes_no_cadastro": [{"codigo_ibge","nome"}], "excedentes_no_cadastro": [...],
  "nomes_divergentes": [{"codigo_ibge","nome_ibge","nome_cadastro"}], "erro": null}`.
- **Falha é não fatal**: `status: "erro"` + `::warning::`, e a coleta segue. O IBGE fora do ar
  não pode derrubar o monitoramento.
- Divergência **não altera o cadastro automaticamente**. Ela abre issue. Escrever 78→79
  municípios sem revisão humana violaria a curadoria do repositório, e um endpoint que responda
  errado uma vez corromperia a fonte da verdade.

Isto responde diretamente a "o GitHub Actions consegue achar municípios novos?": **sim, por
dois caminhos independentes** — (B) pelo texto dos diários e (C) pela lista oficial — e em
ambos o resultado é uma issue, não uma escrita silenciosa.

### 7.4 Novas chaves em `descobertas/descobertas.json`

Acrescentadas ao dict `saida` de `coletar.main()`, **preservando todas as atuais**
(`descricao`, `gerado_em`, `janela_dias`, `total_achados`, `ja_no_repositorio`,
`pendentes_de_curadoria`, `fontes_consultadas`, `achados`) — nenhuma é renomeada ou removida,
porque `gerar_relatorio.bloco_coleta()`, `gerar_email.carregar_descobertas()`,
`gerar_readme.carregar_descobertas()` e `validar.valida_descobertas()` leem essas chaves:

```jsonc
{
  "janela_ioes_dias": 7,
  "retencao_atos_dias": 90,
  "descartados_por_retencao": 0,
  "atos_diario_novos": 0,
  "cobertura_municipios": {
    "total_municipios": 78,
    "com_registro_curado": 15,
    "com_achado_na_janela": 41,
    "com_achado_acumulado": 41,
    "sem_sinal_algum": 30,
    "slugs_com_achado_acumulado": ["aracruz", "fundao", "..."],
    "slugs_com_sinal": ["aracruz", "fundao", "..."],
    "slugs_com_sinal_historico": ["aracruz", "fundao", "serra", "..."],
    "vistos_pela_primeira_vez": ["sooretama"],
    "sem_sinal_slugs": ["agua-doce-do-norte", "..."],
    "orgaos_vinculados_sem_municipio": ["cim-polinorte", "consorcio-caparao", "aries"],
    "registros_intermunicipais_sem_atribuicao": 4
  },
  "municipios_nao_mapeados": [ /* §7.2 */ ],
  "reconciliacao_ibge": { /* §7.3 */ }
}
```

Definição exata de cada contador, porque três deles estavam ambíguos ou errados no passe anterior:

| Campo | Definição |
| ----- | --------- |
| `total_municipios` | `total_esperado` do cadastro, **nunca** literal no código (§9.2) |
| `com_registro_curado` | municípios cujo campo `municipio` de **algum registro de `dados/`** resolve pelo cadastro, **excluídos os registros com `esfera == "intermunicipal"`** (§4). Medido nos 53 registros: **16** nomes oficiais distintos no total, **15** após excluir os intermunicipais — e **15 é o valor do campo** |
| `com_achado_na_janela` | municípios com achado de `municipio_confianca == "alta"` **e** `ultima_deteccao == gerado_em` — isto é, **revistos nesta execução** |
| `com_achado_acumulado` | o mesmo sem a condição de data: inclui achados preservados de execuções anteriores |
| `slugs_com_achado_acumulado` | lista **ordenada** dos slugs que compõem `com_achado_acumulado`. Existe porque a coluna "Ato detectado" do README é por município e `com_achado_acumulado` é um inteiro (§11.1) |
| `slugs_com_sinal` | lista ordenada dos slugs que compõem `com_achado_na_janela ∪ com_registro_curado`. **Retrato de hoje** |
| `slugs_com_sinal_historico` | `ordenado(slugs_com_sinal_historico_antes ∪ slugs_com_sinal)` — conjunto **monotônico**. **É o estado que a próxima execução lê** para calcular o delta (§6.3) |
| `vistos_pela_primeira_vez` | `ordenado(slugs_com_sinal − slugs_com_sinal_historico_antes)` — o que nunca teve sinal em **nenhuma** execução anterior |
| `registros_intermunicipais_sem_atribuicao` | registros de `dados/` com `esfera == "intermunicipal"` (medido: **4**), que por §4 não creditam município nenhum |

**O exemplo do bloco acima traz `15`, e não `16`, e essa diferença é um município concreto.** Medi
nos 53 registros: `Divino de São Lourenço` aparece **somente** em `ps-consorcio-caparao-es-2026`,
que tem `esfera: "intermunicipal"` — exatamente o registro que §4 decidiu **não** creditar. Os 16
nomes oficiais distintos existem; `com_registro_curado` não é esse número. O passe anterior
escrevia a definição certa e o exemplo errado, e um teste derivado do exemplo fixaria o bug: por
isso §16 passa a assertar as **duas** metades do caso (não entra em `com_registro_curado` **e** soma
1 em `registros_intermunicipais_sem_atribuicao`).

**O estado persistido é histórico e monotônico, não o retrato da janela.** `com_achado_na_janela` é,
por definição, da janela desta execução: um município com ato hoje e nenhum na semana seguinte
**sai** de `slugs_com_sinal`. Se o delta fosse contra o retrato anterior, ao voltar a publicar ele
entraria de novo em `vistos_pela_primeira_vez` e a issue anunciaria "primeiro ato detectado em X"
pela segunda vez — contradizendo §7.1 ("nunca teve registro nem achado, e hoje apareceu"). O e-mail
estava protegido por `cobertura_vistos` (§11.3); a issue (§10.2) e o título (§7.5) **não**. Com
`slugs_com_sinal_historico`, "primeira vez" passa a significar primeira vez de verdade, e o retrato
da janela continua disponível para quem fala do dia.

`cobertura()` recebe, portanto, `slugs_com_sinal_historico_antes` (e **não** o retrato anterior),
lido de `descobertas.json → cobertura_municipios.slugs_com_sinal_historico`; quando a chave não
existe — arquivo anterior à primeira coleta com cadastro — vale `set()`, e aí todos os slugs com
sinal entram no delta (§15.34, controlado no anúncio por §11.3). Para tolerar o arquivo gravado por
uma versão intermediária que tenha só `slugs_com_sinal`, a leitura é
`bruto["cobertura_municipios"].get("slugs_com_sinal_historico") or bruto["cobertura_municipios"].get("slugs_com_sinal") or []`
— degradação graciosa, no mesmo espírito do resto do arquivo.

**`com_achado_na_janela` exige `ultima_deteccao == gerado_em`**, e essa condição é o conserto de um
erro do passe anterior. A "lista final de achados" que `cobertura()` recebe é `finais`, que contém
também **todos os preservados** das execuções anteriores, inclusive os marcados
`ausente_na_fonte`. Contar confiança alta sobre ela produzia número **cumulativo e crescente** —
contradizendo o nome do campo, a frase "o valor 41 é o que medi na janela de 7 dias" e a linha da
issue "N/78 municípios com sinal na janela". O número cumulativo continua disponível, com o nome
que o descreve, em `com_achado_acumulado`, e a **lista** correspondente em
`slugs_com_achado_acumulado`; é essa lista que o README usa para a coluna "Ato detectado" (§11.1),
onde o histórico é desejável, enquanto a issue e o e-mail usam o da janela.

**A lista acumulada é publicada e não derivada no README, por uma razão medida.**
`gerar_readme.carregar_descobertas()` filtra `no_repositorio` e `ausente_na_fonte` (linha 186,
conferido) — e é justamente o ato **antigo** (portanto `ausente_na_fonte: true`) que carrega o
histórico. Derivar a coluna dos `achados` dentro do gerador daria uma coluna que esquece o passado
no dia seguinte. Quem calcula é `cobertura()`, sobre a lista final inteira e sem condição de data,
com `municipio_confianca == "alta"` — a mesma regra de `com_achado_acumulado`, e §9.4 passa a exigir
`com_achado_acumulado == len(slugs_com_achado_acumulado)` para que as duas não possam divergir.

**`slugs_com_sinal_historico` existe porque `vistos_pela_primeira_vez` é um delta.** Sem persistir o
conjunto histórico, não há como calcular "nunca teve sinal e hoje apareceu": `cobertura()` é pura e
recebe esse conjunto como parâmetro (§6.3), lido do `descobertas.json` anterior pelo `bruto` que
`carregar_anterior()` passa a devolver (§7.2). Chave ausente → `set()`, e nesse caso **todos** os
slugs com sinal aparecem como vistos pela primeira vez; isso é correto na primeira execução com
cadastro, e §7.5/§11.3 controlam o anúncio para que não vire um e-mail com 41 "primeiras vezes" —
`gerar_email` só anuncia o que ainda não está em `cobertura_vistos`.

### 7.5 Issue automática e saídas do workflow

`coletar.py` passa a escrever em `--saida-github`, além de `novos=`, `pendentes=`, `total=`:

```
nao_mapeados=<len(municipios_nao_mapeados)>
divergencia_ibge=<0|1>
municipios_com_sinal=<int>
primeira_vez=<len(cobertura_municipios.vistos_pela_primeira_vez)>
atos_diario_novos=<len(atos_novos)>
truncado=<0|1>
```

`novos=` continua significando **oportunidades** novas, e é por isso que ele volta a ser um número
pequeno (§6.10). `atos_diario_novos=` é a contagem dos atos de diário inéditos e aparece **só em
linha de resumo** do corpo da issue ("Atos de diário oficial novos nesta coleta: 37 — ver
`descobertas/descobertas.json`"), nunca na tabela de oportunidades: a tabela tem colunas
`Inscrições` e `Oportunidade` que um ato de nomeação não preenche.

**`truncado` é agregado, porque há duas fontes IOES e uma só saída.** Cada fonte escreve o seu
diagnóstico (§6.3), e `--saida-github` publica um valor:

```
truncado = 1 se QUALQUER diagnostico de fonte tiver truncado OU
             limite_achados_atingido; 0 caso contrario
```

Assim o DOM truncado não é escondido por o DIO ter caído dentro do teto, que é o caso provável (o
volume está no DOM: 131 de 218 hits na janela).

**Assinatura nova de `monta_relatorio_md()`, porque a atual não recebe nada disso.** Hoje é
`monta_relatorio_md(novos, relatorio_fontes, referencia)`. Passa a ser:

```python
def monta_relatorio_md(novos, relatorio_fontes, referencia, contexto):
    """'contexto' e um dict com as chaves: 'cobertura' (bloco de §7.4),
    'nao_mapeados' (lista de §7.2), 'reconciliacao' (bloco de §7.3),
    'atos_novos' (lista) e 'truncado' (bool agregado acima).

    Um dict e nao cinco parametros posicionais: a funcao ja tem tres, e a cada
    secao condicional nova a assinatura cresceria de novo. Chave ausente no dict
    e tratada como secao ausente (a secao e condicional de qualquer modo), de
    modo que um chamador de teste pode passar {}.
    """
```

`monta_relatorio_md()` ganha, após a tabela de achados novos e antes de "Fontes consultadas",
seções **condicionais**: "Municípios citados sem mapeamento" (tabela `Nome detectado |
Ocorrências | Provável alias de | Exemplo`, com a instrução de acrescentar alias em
`fontes/municipios-es.json` ou abrir entrada nova se for município real); "Divergência com a
lista do IBGE" (códigos e nomes, com a instrução de atualizar o cadastro **manualmente**);
"Coleta truncada" quando `truncado`; e uma linha de cobertura
("Cobertura: N/78 municípios com sinal na janela; M sem sinal algum"); uma linha "Primeiro ato
detectado em: Sooretama" quando `vistos_pela_primeira_vez` não é vazio; e a linha de resumo de
`atos_diario_novos`.

**A primeira linha do corpo e o título da issue passam a dizer o motivo certo.** Hoje
`monta_relatorio_md()` abre com "encontrou **0** oportunidade(s)" e o título é montado no YAML
como `"Coleta automatica: <novos> nova(s) oportunidade(s) do ES"`. Como a issue passa a abrir
também quando `novos == 0` (§10.2), sem isto ela chegaria negando o próprio motivo de existir:

```bash
# if/then/fi, e nao '[ cond ] && atribuicao': a forma com && sai com codigo 1
# quando o teste falha, e o dia em que alguem acrescentar 'set -euo pipefail'
# neste passo (outros passos do mesmo workflow ja tem) o titulo deixaria de ser
# montado e o passo abortaria. Aqui o custo de escrever por extenso e zero.
partes=""
if [ "${{ steps.coleta.outputs.novos }}" != "0" ]; then
  partes="${{ steps.coleta.outputs.novos }} nova(s) oportunidade(s)"
fi
if [ "${{ steps.coleta.outputs.primeira_vez }}" != "0" ]; then
  partes="${partes:+$partes, }${{ steps.coleta.outputs.primeira_vez }} municipio(s) com 1o ato"
fi
if [ "${{ steps.coleta.outputs.nao_mapeados }}" != "0" ]; then
  partes="${partes:+$partes, }${{ steps.coleta.outputs.nao_mapeados }} municipio(s) sem mapeamento"
fi
if [ "${{ steps.coleta.outputs.divergencia_ibge }}" = "1" ]; then
  partes="${partes:+$partes, }divergencia com o IBGE"
fi
titulo="Coleta automatica: ${partes:-sem novidade} — $(date -u +%Y-%m-%d)"
```

São **quatro** partes, e `primeira_vez` é a que o passe anterior esquecia: depois de `novos` passar
a contar só oportunidades, um dia cuja única notícia seja "primeiro ato em Sooretama" não teria
nem título nem gatilho de issue (§10.2).

e a primeira linha de `monta_relatorio_md()` vira frase condicional que cita os três motivos
(novos / não mapeados / divergência), **preservando** o aviso "estes itens são pistas não
conferidas".

---

## 8. Decisão 6 — correção do campo `esfera` nas 12 fontes

### 8.1 Diagnóstico

Das 38 fontes, 12 não têm `esfera`, e **não é aleatório**: as 26 que têm são exatamente as de
`tipo` `oficial` (23) e `diario_oficial` (3); as 12 sem são exatamente `banca` (7: idcap,
consulplan, ibade, ibest, idecan, access, fundatec), `portal_concursos` (3: pciconcursos-es,
concursosnobrasil-es, qconcursos) e `imprensa` (2: agazeta-concursos,
tribunaonline-concursos). Confirmei a distribuição item a item.

O campo falta justamente onde ele **não tem significado**. Fundatec não é federal, estadual nem
municipal — é uma fundação privada que organiza certames de qualquer esfera. O vocabulário de
`comum.ESFERAS_VALIDAS` descreve nível de governo, e nenhum dos quatro valores é verdadeiro
para uma banca.

### 8.2 Alternativas e escolha

| Opção | Problema |
| ----- | -------- |
| Exigir `esfera` de todas com o vocabulário atual | Obriga atribuir nível de governo a entidade privada — dado falso |
| Deixar `esfera` opcional conforme o tipo | Resolve, mas mantém forma variável e regra condicional sem marca positiva no dado |
| Preencher as 12 com `"nao_se_aplica"` | Forma uniforme, afirmação verdadeira, validável sem ambiguidade |

**Escolha: preencher as 12 com `"esfera": "nao_se_aplica"`.** Isto **não** é inventar dado: não
se afirma um fato desconhecido sobre o mundo, classifica-se corretamente a entidade. Também não
serve `comum.AUSENTE` (`"não informado"`), que significa "a fonte não informa" — aqui o campo
não se aplica, informação diferente e mais forte. O estilo (sem acento, snake_case) segue o
`nao_informado` já presente em `comum.REGIMES_VALIDOS`.

```python
# Vocabulario de esfera do CATALOGO DE FONTES, que e mais largo que o dos
# registros de dados/. Uma banca ou um portal de concursos nao pertence a
# nenhuma esfera de governo: 'nao_se_aplica' diz isso de forma verificavel, em
# vez de forcar um nivel de governo falso ou de usar "nao informado", que
# significaria "nao sabemos" — e nos sabemos.
ESFERAS_FONTE_VALIDAS = ESFERAS_VALIDAS | {"nao_se_aplica"}

# Tipos de fonte que SAO orgao publico e portanto devem declarar esfera de
# governo real; os demais devem declarar 'nao_se_aplica'.
TIPOS_FONTE_COM_ESFERA = {"oficial", "diario_oficial"}
```

(`ESFERAS_VALIDAS | {...}` é união de `set`, válida em 3.9 — não é o operador de dicionário do
3.9+/3.10.) `ESQUEMA.md` ganha um parágrafo distinguindo a `esfera` do registro (vocabulário de
quatro valores, **inalterado** — nada em `dados/` muda) da `esfera` da fonte.

---

## 9. Decisão 7 — novas checagens do validador

`validar.py` ganha duas funções de nível de arquivo e reforços nas existentes. **Erro** reprova
(exit 1); **aviso** não.

**Decisão de assinatura, para que o validador seja testável:** as funções novas recebem o dado
**já carregado**, e a leitura de disco fica num wrapper fino —
`valida_cadastro_municipios(rel, cadastro, catalogo)` e `valida_catalogo_fontes(rel, catalogo)`.
Sem isso cada caso de teste precisaria escrever um arquivo temporário, o que por si só
justificaria repensar o design.

### 9.1 `valida_catalogo_fontes()` — novo

Arquivo obrigatório. JSON inválido ou ausente → **erro** (hoje
`coletar.carregar_catalogo_fontes()` engole a falha devolvendo `{}`, degradando a coleta em
silêncio).

| Checagem | Nível |
| -------- | ----- |
| `id` presente, único, casando `^[a-z0-9][a-z0-9-]*$` | erro |
| `nome`, `url`, `tipo`, `esfera`, `prioridade` presentes em **toda** fonte | erro |
| `tipo` ∈ `comum.TIPOS_FONTE_VALIDOS` | erro |
| `esfera` ∈ `comum.ESFERAS_FONTE_VALIDAS` | erro |
| `tipo` ∈ `TIPOS_FONTE_COM_ESFERA` **e** `esfera == "nao_se_aplica"` | erro (é o bug inverso) |
| `tipo` ∉ `TIPOS_FONTE_COM_ESFERA` **e** `esfera != "nao_se_aplica"` | erro |
| `prioridade` int em 1..4 | erro |
| `url` começa com `https://` | aviso |
| Chave desconhecida no objeto (fora de `id,nome,url,tipo,esfera,prioridade,observacao,coletada_automaticamente`) | erro |
| `coletada_automaticamente: true` sem coletor em `coletar.FONTES` | aviso |
| `ultima_atualizacao` ISO e não futura | erro |

A checagem de **chave desconhecida** é o reforço que impede o bug do `esfera` de voltar: hoje
nada no pipeline olha para a forma de `fontes.json`, e foi assim que 12 fontes ficaram sem o
campo sem ninguém notar. Ela também pega `esferra:` digitado errado, que hoje passaria.

**A checagem de `coletada_automaticamente` cria uma dependência nova, declarada.** Hoje
`validar.py` importa só `comum`; conferir se existe coletor exige conhecer `coletar.FONTES`, o que
arrasta para o validador as constantes de rede e o `sys.path.insert` do coletor. Duas saídas
viáveis: mover o conjunto de ids para `comum.FONTES_COLETAVEIS`, ou importar `coletar` tardiamente.
**Escolha: import tardio**, dentro de `valida_catalogo_fontes()`:

```python
def valida_catalogo_fontes(rel, catalogo):
    # Import tardio e deliberado: 'coletar' e o unico dono legitimo do mapa
    # FONTES (e so ele sabe quais ids tem coletor), mas importa-lo no topo
    # arrastaria TIMEOUT, NAVEGADOR e o sys.path.insert do coletor para dentro
    # do validador, que hoje depende apenas de comum. Duplicar a lista em
    # comum.FONTES_COLETAVEIS seria a alternativa, e criaria duas fontes da
    # verdade que divergem no dia em que alguem acrescentar uma fonte.
    import coletar
```

A dependência `validar → coletar` consta da tabela de §17.

### 9.2 `valida_cadastro_municipios()` — novo

| Checagem | Nível |
| -------- | ----- |
| Arquivo existe e é JSON válido | erro |
| `len(municipios) != total_esperado` | erro |
| `total_esperado < 78` | erro ("o ES nunca teve menos de 78") |
| `total_esperado != 78` | **aviso** ("confira contra o IBGE e atualize o README") |
| `codigo_ibge` int de 7 dígitos começando com `32`, **único** | erro |
| `nome` não vazio, sem espaço duplo nem espaço nas bordas | erro |
| **`slug == comum.slug(nome)`** | erro |
| `slug` único | erro |
| `microrregiao` não vazia | erro |
| `aliases` é lista de strings não vazias | erro |
| Alias cujo `chave_nome()` colide com nome/alias de **outro** município | erro |
| Alias cujo `chave_nome()` é igual ao do próprio `nome` (redundante) | aviso |
| Chave desconhecida em entrada de `municipios` (fora de `codigo_ibge,nome,slug,aliases,microrregiao,canais,pendencias_verificacao,verificado_em`) | erro |
| **Canais** — chave desconhecida em canal (fora de `tipo,precedencia,url,fonte_id,estado,evidencia,verificado_em`) | erro |
| `canais[].tipo` ∈ `comum.TIPOS_CANAL` (§3.1.1) | erro |
| `canais[].url`: `null` ou `https://...` | erro |
| `canais[].url == null` com `tipo != "banca"` | erro — só canal de banca pode não ter URL (§3.1.1) |
| `canais[].estado` ∈ {`confirmado`,`pendente`} | erro |
| `canais[].estado == "confirmado"` e `verificado_em` ausente, nulo ou futura | erro — confirmado sem data é afirmação não verificada |
| `canais[].evidencia` ausente ou vazia | erro — é o campo que impede canal inventado (§3.1) |
| `canais[].fonte_id` não nulo e inexistente em `fontes.json` | erro |
| `canais[].precedencia` int ≥ 1, **única dentro do município** | erro |
| Existe canal de diário (`diario_oficial_proprio`/`diario_oficial_agregador`) e `precedencia == 1` **não** é de diário | erro (§3.1.1) |
| Nenhum canal com `tipo` ∈ {`diario_oficial_proprio`,`diario_oficial_agregador`} **e** nenhum item de `pendencias_verificacao` com campo `canais` | **erro** |
| Algum canal `pendente` e nenhuma pendência de `canais` declarada | erro — pendência no canal e na entrada têm de concordar |
| Município sem **nenhum** canal `confirmado` | aviso — é lacuna real de cobertura |
| Item de `pendencias_verificacao` fora da forma `campo[:motivo]`, com `campo` ∈ chaves da entrada e `motivo` ∈ `comum.MOTIVOS_PENDENCIA` | erro |
| **`orgaos_vinculados`** — chave obrigatória ausente ou desconhecida (conjunto permitido, por extenso: `id,nome,sigla,natureza,esfera,municipios_slugs,url,fontes,pendencias_verificacao,verificado_em`) | erro |
| `orgaos_vinculados[].id` único e não colidindo com slug de município | erro |
| `orgaos_vinculados[].natureza` no vocabulário fechado | erro |
| `orgaos_vinculados[].url == null` sem pendência `url:nao_encontrado` | erro — forma usada em 5 das 8 entradas de §4.1 |
| `orgaos_vinculados[].fontes[]` referenciando `id` inexistente em `fontes.json` | erro |
| `orgaos_vinculados[].verificado_em` ausente, nulo ou futura | erro |
| `natureza` ∈ {`camara_municipal`,`autarquia_municipal`,`fundacao_municipal`,`empresa_municipal`} e `len(municipios_slugs) != 1` | erro |
| `natureza` ∈ {`consorcio_intermunicipal`,`agencia_reguladora`} e `esfera != "intermunicipal"` | erro |
| `natureza` ∈ {`consorcio_intermunicipal`,`agencia_reguladora`} e `municipios_slugs == []` sem pendência declarada | erro |
| `municipios_slugs` referenciando slug inexistente | erro |

**A linha de canal de diário é a correção de uma incoerência que reprovava o dado correto.** A
versão anterior exigia "pendência de `url_diario_oficial`" — motivo que o vocabulário de §3.1
**nunca produz**: o produtor declarado de `nao_encontrado` é o campo do diário, e as formas válidas
no dado nunca foram `url_diario_oficial:*`. Um município curado exatamente como §3.1 manda era
reprovado, e para passar o curador teria de inventar um item de pendência sem produtor — o
"vocabulário morto" que §3.1 diz evitar. Com `canais`, a exigência passa a ser verificável e
escrita no vocabulário real: **ou** existe canal de diário, **ou** existe
`canais:nao_encontrado`. Município que publica só pelo DOM/AMUNES passa com um único canal, e é o
caso comum (§3.1).

As entradas de `orgaos_vinculados` passam a ser validadas com a **mesma severidade** das de
`municipios` (chaves, `url` nula exigindo pendência, `fontes[]` existente, `verificado_em`). Antes
havia checagem de `id`, `natureza`, aridade e slugs, e nada de forma — a assimetria era a mesma que
deixou 12 fontes sem `esfera` passar durante meses (§8.1).

Três regras merecem justificativa:

- **`slug == comum.slug(nome)`** trava a classe de bug mais provável deste trabalho: slug
  escrito à mão para `Guaçuí`, `Iúna`, `Marataízes`, `São Roque do Canaã`, `Vila Pavão`,
  `Atílio Vivácqua`, `Águia Branca`. Recalcular e comparar elimina a possibilidade por
  construção, em vez de confiar em revisão visual de 78 linhas.
- **O literal `78` vive só no cadastro.** `validar.py` compara `len(municipios)` com
  `total_esperado` do arquivo, e trata `total_esperado != 78` como **aviso**. Se o `78` fosse
  literal no código, o dia em que um 79º município fosse criado por lei — exatamente o caso que
  §7.3 existe para detectar — deixaria o repositório reprovado até que alguém editasse
  `validar.py`, edição que ninguém lembraria de fazer. O piso (`< 78` → erro) protege contra
  alguém "resolver" uma falha apagando entradas.
- **Aridade de `municipios_slugs` por natureza**, e não uma regra única, pelo motivo de §4:
  `agencia_reguladora` com jurisdição multimunicipal não pode ser forçada a creditar a sede.

### 9.3 Reforço em `valida_escopo()` (registros de `dados/`)

Hoje só confere `uf == "ES"` e avisa se `municipio` está ausente. Passa a resolver `municipio`
contra o cadastro:

- `"Âmbito estadual (ES)"` ou valor começando com `"Diversos (ES)"` → aceito sem resolução. São
  os dois padrões já em uso (medido: 24 registros no primeiro, 1 no segundo — o sufixo livre de
  `"Diversos (ES) - Linhares e região"` é descritivo e não deve ser normalizado).
- Caso contrário, **`comum.resolver_municipio(valor, indice)`** — a consulta **exata** por
  `chave_nome()` (§5.1), e não a passada de texto livre: aqui o valor é um campo curado e curto, e
  casamento parcial esconderia erro de digitação em vez de apontá-lo. Se não devolver slug →
  **erro**: `"municipio 'X' nao consta de fontes/municipios-es.json (verifique a grafia ou
  acrescente alias)"`. É este check que pega `"Cachoeiro do Itapemirim"` digitado num registro
  novo.
- Resolveu por **alias** (`origem == "alias"`) e não pelo nome oficial → **aviso** sugerindo o nome
  oficial, para os dados tenderem à grafia do IBGE sem reprovar trabalho em curso.
- Resolveu por **nome de órgão vinculado** (`origem == "orgao_vinculado"`) → **aviso**:
  `"'X' e nome de orgao vinculado, nao de municipio; use o nome oficial do municipio no campo
  'municipio'"`. É o terceiro valor de `origem` e existe porque §5.1 injeta esses nomes em
  `por_chave_nome`; sem a distinção, `"Camara Municipal de Aracruz"` passaria como se fosse o
  município Aracruz, silenciosamente.
- Registro com `esfera == "intermunicipal"` cujo `municipio` **resolve** para um slug → **aviso**:
  `"registro intermunicipal: o municipio de sede nao credita cobertura; declare a jurisdicao em
  orgaos_vinculados[].municipios_slugs"`. Medido, isto dispara hoje em 3 dos 4 registros
  intermunicipais (`ps-consorcio-caparao-es-2026` → `divino-de-sao-lourenco`, e os dois da ARIES →
  `vitoria`); `ps-cim-polinorte-es-2026` usa `"Diversos (ES) - Linhares e região"` e passa pelo
  ramo aceito acima. Aviso e não erro porque o dado **não está errado** — a sede é aquela mesmo; o
  que está errado é usá-lo como jurisdição, e §7.4 já impede isso no cálculo.

Conferi que este reforço **não reprova nenhum registro existente**: os 53 registros têm 18
valores distintos de `municipio`, e os únicos dois que não são nome oficial do IBGE são
exatamente os dois padrões aceitos acima.

Erro (e não aviso) é a escolha certa aqui porque o nome de município é chave de agregação da
cobertura: um registro com grafia divergente não desaparece, ele **conta errado** — e contar
errado é pior que falhar alto.

### 9.4 Reforço em `valida_descobertas()`

| Checagem | Nível |
| -------- | ----- |
| `categoria` presente e ∈ {`oportunidade`, `ato_diario`} | erro — **salvo achado legado**, ver abaixo |
| `municipio_escopo` presente e ∈ {`municipal`,`intermunicipal`,`estadual`,`federal`,`indeterminado`} | erro — **salvo achado legado** |
| `categoria`/`municipio_escopo` **ausentes** em achado com `primeira_deteccao <= cadastro.ibge_consultado_em` | **aviso** ("achado anterior ao cadastro; rode `--migrar-descobertas`") — §6.9, e o `<=` é medido: 2 dos 37 achados versionados têm data **igual** à fronteira |
| `categoria`/`municipio_escopo` **presentes** e fora do vocabulário | erro, sempre (inclusive em legado) |
| `municipio_slug` não nulo inexistente no cadastro | erro |
| `municipio_confianca` fora de {`alta`, `baixa`, `null`} | erro |
| `municipio_origem` **presente** e fora de {`nome`,`alias`,`orgao_vinculado`,`null`} | erro |
| `municipio_origem` **ausente** | **ok** — o campo não entra na exigência de presença, para não criar um quinto item de tolerância de legado (§6.7) |
| `municipio_origem` não nulo com `municipio_slug` nulo | erro — origem sem município resolvido é contradição |
| `categoria == "ato_diario"` e `municipio_slug` nulo e `municipio_escopo` ∉ {`indeterminado`,`intermunicipal`} | erro |
| `categoria == "oportunidade"`: `municipio_slug` nulo com `municipio_escopo` ∈ {`estadual`,`federal`} | **ok** |
| `categoria == "oportunidade"` com `municipio_confianca == "alta"` | erro — portal de terceiro não é evidência de ato (§6.10) |
| `municipio_codigo_ibge` incoerente com `municipio_slug` | erro |
| `orgao_vinculado_id` inexistente no cadastro | erro |
| `categoria == "ato_diario"` com `inscricoes.fim` preenchido | erro — sinal de que alguém passou a extrair data de PDF por regex |
| `municipios_nao_mapeados[]` com `nome_detectado`, `ocorrencias`, `paginas_distintas`, `com_marca_uf`, `exemplos`, datas válidas | erro |
| `paginas_distintas > ocorrencias` | erro — contadores trocados (§7.2) |
| `len(exemplos) > 3` | erro (§7.2) |
| `provavel_alias_de` apontando para slug inexistente | erro |
| `municipios_nao_mapeados` não vazio | **aviso** (pendência de curadoria, não defeito de dado) |
| `reconciliacao_ibge.status == "erro"` | aviso |
| `reconciliacao_ibge` com `ausentes_no_cadastro`/`excedentes_no_cadastro` não vazios | aviso |
| `cobertura_municipios.total_municipios != total_esperado` do cadastro | erro |
| `cobertura_municipios.com_achado_na_janela > total_municipios` | erro |
| `com_achado_na_janela > com_achado_acumulado` | erro — a janela é subconjunto do acumulado (§7.4) |
| `com_achado_acumulado != len(slugs_com_achado_acumulado)` | erro — contagem e lista não podem divergir (§7.4) |
| `set(vistos_pela_primeira_vez) ⊄ set(slugs_com_sinal)` | erro — o delta tem de ser subconjunto do retrato de hoje (§7.4) |
| `set(slugs_com_sinal) ⊄ set(slugs_com_sinal_historico)` | erro — o histórico é monotônico e contém o retrato (§7.4) |
| `slugs_com_sinal` / `slugs_com_sinal_historico` / `slugs_com_achado_acumulado` com slug inexistente no cadastro, ou não ordenados | erro |
| `len(achados) > 5000` | **aviso** ("quarentena grande; confira a retenção de `ato_diario`") — §6.9.1 |
| Chave `cobertura_municipios` / `municipios_nao_mapeados` / `reconciliacao_ibge` **ausente** | **aviso** ("descobertas.json anterior ao cadastro; rode a coleta") — §6.9 |

**A regra de legado é por achado, e é o que permite o PR existir.** O arquivo versionado tem 37
achados sem `categoria` (medido), e o job `validar` roda em todo PR e push **sem** passar por
`coletar.py` — logo o backfill do coletor não o alcança. Sem a linha de tolerância, o PR que
acrescenta estas checagens é reprovado pelas próprias checagens que acrescenta. A fronteira é
`cadastro.ibge_consultado_em`, a data em que este vocabulário passou a existir (§6.9), e a
comparação é **`<=`**: medi que 2 dos 37 achados versionados têm `primeira_deteccao` exatamente
igual a `"2026-10-01"` (as outras 35 são de 09-23 a 09-30), porque o cadastro é commitado no mesmo
dia em que a coleta anterior rodou. Com `<`, esses dois achados da fronteira viram **erro** em vez
de aviso — exatamente o oposto da tolerância que a linha existe para dar, e sem caminho de
recuperação automático no CI.

O aviso de `len(achados) > 5000` é rede de segurança para a retenção de §6.9.1: se ela quebrar, o
sintoma aparece como aviso num arquivo que cresce, em vez de como lentidão inexplicada.

A regra de `municipio_slug` nulo é **por categoria**, não universal: para SEDU, SESA e PM-ES o
slug é legitimamente nulo porque o certame é estadual, e exigir "indeterminado" obrigaria o
coletor a afirmar algo falso. `municipio_escopo` resolve isso dizendo o escopo de forma
positiva.

### 9.5 Saída `--json`

O dict de `--json` ganha `fontes`, `municipios`, `orgaos_vinculados`,
`municipios_sem_cobertura`, `atos_diario` e `descartados_por_retencao` (contagens), ao lado de
`registros` e `descobertas`. Chaves existentes preservadas. As duas últimas existem para que a
auditoria do pipeline possa ver, sem abrir o JSON de 5.000 achados, se a retenção de §6.9.1 está
funcionando.

---

## 10. Decisão 8 — correções no workflow

### 10.1 O bug dos gatilhos

Conferido no YAML: `pull_request.paths` = `dados/**`, `ferramentas/**`, `README.md`;
`push.paths` = `dados/**`, `ferramentas/**`. **`fontes/**` não está em nenhum dos dois.** Hoje
isso já é bug — editar `fontes/fontes.json` não roda `validar.py` no PR — e com o cadastro em
`fontes/` passaria a ser grave: a maior parte deste trabalho ficaria sem porta de validação.

```yaml
  pull_request:
    paths:
      - "dados/**"
      - "fontes/**"
      - "ferramentas/**"
      - ".github/workflows/monitoramento.yml"
      - "README.md"
  push:
    branches: [main]
    paths:
      - "dados/**"
      - "fontes/**"
      - "ferramentas/**"
      - ".github/workflows/monitoramento.yml"
```

O arquivo do workflow entra nos dois para que uma edição de YAML passe pela validação que ela
mesma define.

**`descobertas/**` e `README.md` ficam fora do `push`, deliberadamente.** A razão é uma só:
**o conteúdo de `descobertas/` e de `README.md` é gerado pelo bot e já foi revalidado pelo passo
"Revalidar depois das alteracoes", que roda imediatamente antes do commit — não há revisão humana a
proteger neles.** Um PR humano que edite `README.md` à mão continua validado, porque `README.md`
permanece no `pull_request`.

A justificativa do passe anterior ("evita execução redundante a cada commit automático") estava
**errada**, e vale registrar para que ninguém a reintroduza: o commit do bot é único e inclui
`dados/` (`git add -A README.md email/ relatorios/ dados/ historico/ descobertas/`), e `dados/`
**permanece** em `push.paths`. Logo a execução disparada pelo commit automático acontece de
qualquer modo nos dias em que `atualizar_prazos.py` mexe em `dados/`; excluir `descobertas/**` não
elimina execução nenhuma. A decisão continua correta, pela razão certa.

### 10.2 Condição da issue

Hoje: `if: steps.coleta.outputs.novos != '0' && steps.coleta.outputs.novos != ''`. Município não
mapeado e divergência do IBGE não abririam issue nenhuma — a detecção existiria sem notificação.

```yaml
        if: >-
          (steps.coleta.outputs.novos != '0' && steps.coleta.outputs.novos != '') ||
          (steps.coleta.outputs.primeira_vez != '0' && steps.coleta.outputs.primeira_vez != '') ||
          (steps.coleta.outputs.nao_mapeados != '0' && steps.coleta.outputs.nao_mapeados != '') ||
          steps.coleta.outputs.divergencia_ibge == '1'
```

A cláusula `primeira_vez` é obrigatória e não decorativa: §6.10 restringe `novos` a oportunidades, e
sem ela o "primeiro ato detectado em Sooretama" que §7.1 promete seria calculado, gravado em
`descobertas.json` e **nunca notificado**. `atos_diario_novos` **não** entra na condição — ato de
diário é rotina diária, e abrir issue por isso geraria uma issue por dia para sempre, que é o
oposto de notificação.

O título e a primeira linha do corpo passam a dizer o motivo (§7.5). `monta_relatorio_md()` já é
escrito incondicionalmente, então nenhuma mudança de ordem de passos é necessária.

### 10.3 Testes no workflow

`ferramentas/testes.py` (§16) roda em **dois** lugares:

1. passo novo no job `validar`, antes de `validar.py`;
2. passo novo no job `atualizar`, **antes** de "Revalidar depois das alteracoes".

Só o (1) não bastaria: o job `validar` tem `if: pull_request || push`, logo **não roda na
execução agendada** — que é precisamente a que escreve no repositório.

### 10.4 Resto do workflow

Sem mudança estrutural. A ausência de `needs: validar` no job `atualizar` é deliberada e já
documentada no arquivo (prazo vencido deixa o registro momentaneamente incoerente). `git add`
**continua sem `fontes/`**: o cadastro é editado por humano, e deixar `fontes/` fora do `git
add` é a garantia mecânica dessa decisão, não apenas documental.

---

## 11. Decisão 9 — README, relatório e e-mail

### 11.1 README (`gerar_readme.py`)

O bloco entre `<!-- INICIO:TABELAS -->` e `<!-- FIM:TABELAS -->` ganha:

1. Três linhas no **Panorama**, após "Descobertas automáticas pendentes de conferência":
   `| Municípios do ES monitorados | total_esperado |`,
   `| Municípios com registro curado | com_registro_curado |` (hoje **15**, §7.4),
   `| Municípios com ato detectado na janela da coleta | com_achado_na_janela |`. Os três números
   vêm do cadastro e de `cobertura_municipios`, nunca de literal.
2. Seção **"Cobertura por município"** ao final, com os 78 num `<details>` recolhido (o README
   já tem 29 KB; 78 linhas visíveis dominariam a página):

```markdown
## Cobertura por município

<details>
<summary>Situação dos 78 municípios do Espírito Santo</summary>

| Município | Registros curados | Ato detectado | Canal principal |
| --------- | ----------------: | ------------- | --------------- |
...
</details>
```

`Ato detectado` usa ✓/— a partir de **`slugs_com_achado_acumulado`** (§7.4), isto é, pertinência à
lista publicada, e não da janela: no README o histórico é a informação útil ("este município já
apareceu alguma vez"), enquanto a issue e o e-mail falam do dia. Usar a **lista** e não o inteiro
`com_achado_acumulado` é o que torna a coluna possível — ela é por município, e o inteiro não diz
quais; derivar dos `achados` dentro do gerador não serve, porque `carregar_descobertas()` filtra
`no_repositorio` e `ausente_na_fonte` (linha 186, conferido), que é justamente o ato antigo.

`Canal principal` é o canal de `precedencia: 1` do cadastro (§3.1.1), exibido pelo `tipo` em texto
legível: `DOM/AMUNES`, `Diário próprio`, `Portal da prefeitura`, `Seção de concursos`. A coluna
**não** se chama "Fonte própria": a maioria dos municípios publica pelo agregador e isso é o canal
correto deles, não uma falta (§3.1). Município **sem canal nenhum** aparece com `—`, e aí sim é
lacuna — a mesma que §9.2 avisa. Os municípios sem registro e sem ato aparecem com `0 | — | <canal>`,
e **isso é o ponto**: o que falta fica visível sem acusar falta onde não há.

**Estado do PR que implementa este design: `cobertura_municipios` ainda não existe.**
`--migrar-descobertas` faz backfill **por achado** e preserva as chaves de topo (§6.9), logo o
`descobertas.json` commitado no PR **não** terá o bloco; e o job `validar` roda
`gerar_readme.py --check` em todo PR. A regra, portanto, é escrita e não deixada à implementação:
quando `cobertura_municipios` está **ausente**, as três linhas de Panorama saem com `0` e a coluna
`Ato detectado` sai `—` nas 78 linhas. `Registros curados` e `Canal principal` continuam corretos,
porque vêm de `dados/` e do cadastro — que existem no PR. O bloco permanece determinístico, e é esse
o README que o PR commita; na primeira coleta agendada ele se preenche sozinho.

Compatibilidade com `--check`: o bloco continua determinístico, porque deriva de arquivos em
disco (`dados/`, cadastro, `descobertas.json`) e da data de referência já extraída do próprio
README por `referencia_registrada()`; nenhuma chamada de rede entra aqui, e a ordenação dos
achados do coletor é determinística por §6.6. `carregar_municipios()` falhando aqui é **fatal**
(§12), diferente de `carregar_descobertas()`, que é tolerante por design porque a coleta é
opcional — o cadastro não é.

### 11.2 Relatório (`gerar_relatorio.py`)

`bloco_coleta()` ganha, depois da tabela de indicadores: separação de `total_achados` em
oportunidades e atos de diário, com `atos_diario_novos` e `descartados_por_retencao` (§6.9.1);
sub-bloco "Cobertura municipal" (N/78 na janela e M acumulado, lista de
`vistos_pela_primeira_vez`, contagem de `municipios_nao_mapeados`,
`registros_intermunicipais_sem_atribuicao`); e agregação por
**microrregião** — único recorte geográfico que o cadastro oferece, e que evita uma tabela de 78
linhas no relatório diário.

### 11.3 E-mail (`gerar_email.py`)

- `classificar_descobertas()` ignora `categoria == "ato_diario"` (§6.8).
- Bloco novo curto, só quando houver conteúdo: "Cobertura — primeiro ato detectado em:
  Sooretama, Laranja da Terra" e "Municípios citados sem mapeamento: 2 (ver issue)".
- O estado `email/.estado-envios.json` ganha `cobertura_vistos`, para que "primeiro ato em
  Sooretama" não seja anunciado todo dia. Assinaturas novas, explícitas (hoje
  `carregar_estado()` devolve tupla de **2** e `gravar_estado()` recebe 3 argumentos):

```python
def carregar_estado():
    """Devolve (impressoes, descobertas, cobertura_vistos). Estado antigo sem a
    chave nova e lido como {}, para que um arquivo de versao anterior continue
    legivel em vez de virar primeira execucao."""
    return (estado.get("impressoes", {}), estado.get("descobertas", {}),
            estado.get("cobertura_vistos", {}))

def gravar_estado(impressoes, descobertas, cobertura_vistos, referencia):
    ...
```

O valor de `cobertura_vistos` é `{slug: data_do_primeiro_anuncio}` (**não** lista), para
permitir expiração por data. Os dois call sites em `gerar_email.main()` (linhas 410 e 436) são
atualizados; o ramo de estado corrompido devolve `{}, {}, {}`.

---

## 12. Tratamento de erros, operação por operação

| Operação | Falha possível | Fatal? | O que o chamador recebe | Log |
| -------- | -------------- | ------ | ----------------------- | --- |
| Ler cadastro em `coletar.py` | ausente / JSON inválido | **Fatal** (exit 1) | — | `stderr` + `::error::cadastro de municipios ilegivel` |
| Ler cadastro em `validar.py` | ausente / inválido | **Fatal** (exit 1) | — | erro no relatório |
| Ler cadastro em `gerar_readme.py` / `gerar_relatorio.py` / `gerar_email.py` | ausente / inválido | **Fatal** (exit 1) | — | `stderr` |
| Ler `fontes/fontes.json` | ausente / inválido | **Fatal** em `validar.py`; **recuperável** em `coletar.py` (comportamento atual: `{}`), agora com aviso explícito | `{}` | `::warning::catalogo de fontes ilegivel; metadados de fonte ficarao ausentes` |
| `GET` busca IOES (escopo×frase×página) | `URLError`, `socket.timeout`, 5xx | Recuperável: 1 retentativa após 2 s | resultados já acumulados | `::warning::` com fonte, frase e página |
| `GET` busca IOES | `HTTPError` 4xx | Recuperável, **sem** retentativa | resultados acumulados | `::warning::` (4xx = contrato mudado → revisar o coletor) |
| `GET` busca IOES | corpo não-JSON ou sem `hits` | Recuperável | para a paginação daquele par | `::warning::resposta inesperada do IOES` |
| Fonte `ioes-busca-*` inteira indisponível | qualquer das acima esgotada | Recuperável — **o laço de `FONTES` já trata** | `achados == []`, `status: "erro"` naquela fonte; a outra continua | `::warning::fonte %s indisponivel nesta execucao` |
| Todas as fontes falham | — | **Já tratado**: exit 1 só com `--exigir-fonte`; senão segue | — | `::error::nenhuma fonte respondeu nesta coleta` |
| `GET` IBGE (`--conferir-ibge`) | qualquer, incluindo gzip malformado | Recuperável | `reconciliacao_ibge.status = "erro"`, `erro` preenchido | `::warning::` |
| Extração de município devolve 0 em todas as páginas | regex de boilerplate comendo o texto, ou mudança de layout | Recuperável | `com_achado_na_janela = 0` + `suspeita_extracao_vazia` (mecanismo **já existente**, agora por escopo) | `::warning::` |
| Teto de páginas/achados atingido | volume acima do previsto | Recuperável | `truncado` / `limite_achados_atingido` no relatório da fonte **e na issue** | `::warning::` com quantos ficaram de fora |
| Gravar `descobertas.json` | `OSError` | **Fatal** (exit 1) | — | `stderr` |
| Achado sem `chave` | bug de parser | Recuperável — descartado com contagem | `descartados_invalidos` | `::warning::` (comportamento atual preservado) |
| Achado de `ato_diario` fora da retenção de 90 dias | nenhuma — é o caminho normal | Não é falha | descartado do arquivo, contado em `descartados_por_retencao` | nenhum (vai ao resumo e ao relatório, §6.9.1) |
| `--migrar-descobertas` sobre arquivo ausente | arquivo nunca gerado | Recuperável — nada a migrar | exit 0 com mensagem | `stdout` |
| `--migrar-descobertas` sobre JSON inválido | arquivo corrompido | **Fatal** (exit 1) | — | `stderr` — regravar em cima de JSON inválido perderia o original |
| Truncamento de `_source.conteudo` | página muito longa | Recuperável | `conteudo_truncado: true` no achado, `paginas_truncadas` no diagnóstico (§6.5) | `::warning::` agregado por fonte |
| Ler `email/.estado-envios.json` | corrompido | Recuperável | `({}, {}, {})` = primeira execução | nenhum (comportamento atual) |

**`_achados_de_resposta()` não propaga `KeyError` nem `TypeError`.** O laço de `FONTES` captura
`(urllib.error.URLError, OSError, ValueError, RuntimeError)` — um envelope malformado que produzisse
`KeyError`/`TypeError` derrubaria a coleta **inteira**, contra a degradação graciosa que esta seção
promete. O contrato é, portanto: **todo** acesso a campo de terceiro dentro de
`_achados_de_resposta()` usa `.get()` com a validação por item de §13.1, e item inválido é ignorado
com aviso. Isso é contrato da função e não "cuidado na implementação": se a função o violar, o
sintoma é a coleta do dia inteiro perdida, e o teste de §16 passa um envelope com `_source: null`,
`hits: {"hits": [{}]}` e `hits.hits: "texto"` exigindo lista vazia e **nenhuma** exceção.

Princípio por trás da coluna "Fatal?": **configuração ilegível é fatal, rede indisponível não
é.** O cadastro é config versionada — se está quebrado, qualquer número produzido adiante é
falso e falhar alto é a única resposta honesta. Fonte externa fora do ar é condição esperada do
mundo, e o repositório já escolheu seguir com o resto.

---

## 13. Validação de entrada externa

### 13.1 Resposta da busca IOES

| Campo | Regra | Falha |
| ----- | ----- | ----- |
| corpo | `json.loads` bem-sucedido | descarta a página, `::warning::` |
| `hits` | dict presente; `total` int ≥ 0 **ou** dict com `value` (§6.2) | descarta a página |
| `hits.hits` | lista; cada item dict com `_id` str | item sem `_id` é ignorado |
| `_id` | `^\d+_\d+$` | formato inesperado → item ignorado com aviso |
| `_source.diario_id` | int ou dígitos | obrigatório para montar a URL; sem ele o item é ignorado |
| `_source.pagina` | int em 1..`paginas` | obrigatório; idem |
| `_source.data` | `^\d{4}-\d{2}-\d{2}$` | inválido → `data_publicacao_ato: null` (não derruba o item) |
| `_source.conteudo` | str; **truncar em 20.000 caracteres** antes de normalizar e segmentar (§6.5); gravar `conteudo_truncado: true` quando houve corte | ausente → só `highlight` é usado e `municipio_escopo: "indeterminado"` |
| `highlight.conteudo` | lista de str | ausente → `titulo` vem dos 200 primeiros caracteres de `conteudo` |
| `suplemento` | str; número extraído por `re.search(r"(\d[\d\.]*)$", ...)` | ausente/sem número → `edicao: null` |

O truncamento de `conteudo` é deliberado: uma página de diário pode trazer tabela de
classificação com dezenas de milhares de caracteres, e o custo é regex sobre todo o texto ×
78 padrões × até 1000 itens. 20.000 caracteres cobrem com folga o cabeçalho e o corpo do ato,
que é onde o município aparece.

### 13.2 Resposta da API do IBGE

Lista não vazia; cada item com `id` int de 7 dígitos iniciando em `32` e `nome` string não
vazia; `microrregiao.nome` opcional. **`len != 78` não é erro** — é exatamente o sinal que se
quer detectar. Corpo gzipado é o caso normal (§6.4), não exceção. Resposta malformada →
`status: "erro"`, sem tocar o cadastro.

### 13.3 Argumentos de linha de comando de `coletar.py`

| Argumento | Regra | Falha |
| --------- | ----- | ----- |
| `--janela-ioes-dias` | int ≥ 1, ≤ 365; padrão 7 | `parser.error` (exit 2) |
| `--max-paginas-ioes` | int ≥ 1, ≤ 100; padrão **20** | `parser.error` |
| `--max-achados-ioes` | int ≥ 1, ≤ 5000; padrão **1000** | `parser.error` |
| `--conferir-ibge` | `dest="conferir_ibge"`, `action="store_true"`, `default=True` | — |
| `--sem-conferir-ibge` | `dest="conferir_ibge"`, `action="store_false"` | — |
| `--retencao-atos-dias` | int ≥ 1, ≤ 365; padrão **90** (§6.9.1) | `parser.error` |
| `--migrar-descobertas` | `action="store_true"`; aplica `normalizar_achado()` a cada achado, regrava e sai, sem rede (§6.9) | — |
| `--autoteste-ioes` | `action="store_true"`; §16 | — |
| `--fonte` | `choices=sorted(FONTES)` (já existe; passa a incluir as duas `ioes-busca-*`) | `argparse` |

Os tetos superiores existem para que um erro de digitação (`--max-paginas-ioes 1000`) não
transforme o cron diário em varredura de acervo.

### 13.4 O próprio cadastro

É entrada externa para as ferramentas de leitura, mesmo sendo versionado. Elas **não**
revalidam tudo (isso é papel de `validar.py`); assumem a forma e falham alto com
`ValueError`/`KeyError` convertidos em mensagem acionável **com o caminho do arquivo** — o mesmo
contrato que `comum.carregar_registros()` já usa para JSON inválido.

---

## 14. Invariantes e camada responsável

| Invariante | Camada que impõe | Por quê ali |
| ---------- | ---------------- | ----------- |
| `len(municipios) == total_esperado`, e `total_esperado >= 78` | `validar.py` | Único ponto rodado em PR, push e antes do commit automático. O literal `78` fica no dado, não no código, para que um 79º município não reprove o repositório (§9.2) |
| `slug == comum.slug(nome)` | `validar.py` (recalculando) | Comparação mecânica elimina a classe de erro; revisão humana de 78 slugs acentuados não |
| Nenhum alias colide entre municípios | `validar.py` | Propriedade global do arquivo; nenhuma leitura isolada a veria |
| Todo canal é confirmado com data e evidência, ou é `pendente` com pendência declarada | `validar.py` (§9.2: `estado`⇄`verificado_em`⇄`pendencias_verificacao`) | Garante "não invente canal" sem depender de rede no CI; a sondagem vive fora do CI (§3.2) |
| Todo município tem canal de diário, ou declara `canais:nao_encontrado` | `validar.py` (§9.2) | É o canal de que a coleta depende; ausência silenciosa seria lacuna invisível |
| `esfera` coerente com `tipo` da fonte | `validar.py` | Reforço que impede a regressão das 12 fontes |
| `municipio` de registro resolve pelo cadastro | `validar.py` (`valida_escopo`) | Chave de agregação da cobertura; erro silencioso aqui corrompe a métrica |
| Município de achado nunca é adivinhado | `coletar.py` (`municipio_escopo`, confiança alta/baixa) | Só o coletor tem o texto da página; é a única camada que sabe se houve evidência |
| Todo achado tem `categoria` e os campos `municipio_*` (slug, codigo_ibge, confianca, escopo, origem) | `coletar.normalizar_achado()`, chamada por `main()` para toda fonte (§6.10) e por `--migrar-descobertas` (§6.9) | Ponto único: uma fonte nova não pode esquecer de preencher, o validador nunca vê achado incompleto, e a migração não tem lista própria de campos para divergir |
| Cobertura conta só confiança **alta** e detectado **nesta execução** | `coletar.cobertura()` (função pura) | Precisa ser a mesma regra para README, relatório e e-mail; calcular em três lugares divergiria. A condição de data existe porque a lista final inclui preservados (§7.4) |
| "Primeira vez" é contra o **histórico**, não contra a janela anterior | `coletar.cobertura()` (`slugs_com_sinal_historico`, §7.4) | Só quem calcula o bloco vê os dois conjuntos; com o retrato da janela, a issue reanunciaria o mesmo município a cada intermitência |
| Uma ordem única do pipeline de texto (§6.5, seis estágios) | `coletar_ioes()` / `_achados_de_resposta()` | Três seções consomem essa ordem (§5.2, §5.3, §7.2); duplicá-la foi o que as fez divergir |
| Só `oportunidade` é novidade | `coletar.main()` (filtro de `novos`, §6.10) | É `main()` que monta `novos`, a issue e o `--saida-github`; filtrar só nos geradores deixaria o título e a tabela da issue errados |
| Achado de diário só casa com `dados/` por evidência forte | `coletar.casar_estrito()` (§6.7) | `casar()` tem um ramo por tokens de órgão que, para "Prefeitura de Serra", casa qualquer certame de Serra |
| Quarentena não cresce sem limite | `coletar.main()` (retenção por categoria, §6.9.1) | Só `main()` vê o arquivo anterior inteiro e a data de referência |
| Registro intermunicipal não credita município | `coletar.cobertura()` (exclui `esfera == "intermunicipal"`) + aviso em `validar.valida_escopo()` | A métrica é calculada num lugar; o validador só sinaliza a tentação |
| Achado nunca vira registro de `dados/` | `coletar.py` (escreve só em `descobertas/`) | Decisão de curadoria vigente, preservada |
| Cadastro só muda por mão humana | workflow (`git add` não inclui `fontes/`) | Garantia mecânica, não documental |
| Uma fonte fora do ar não derruba a coleta | `coletar.py` (`try/except` por fonte, e uma fonte por escopo) | Comportamento existente; o novo coletor se encaixa nele em vez de contorná-lo |
| Dedup é determinística | `coletar_ioes()` (ordenação explícita antes de devolver) | A API empata dentro do dia; só o coletor vê `diario_id`/`pagina` |

---

## 15. Casos de borda

1. **"Vitória" no boilerplate do diário** — medido em **30 das 144 páginas (21%)** antes da
   limpeza. Resolvido pela limpeza corrigida (assinatura com data numérica, por extenso com e
   sem o segundo "de", e separadores `(es)`/`/es`/`-es`/`, es`) **mais** a exigência de contexto
   **adjacente**. Resultado medido: Vitória com **0** ocorrências em confiança alta. É o caso de
   borda mais importante do trabalho e o que as duas versões anteriores descreveram errado (§5.3).
2. **Resíduo de "vitoria" que não é boilerplate** — sobrenome de pessoa (`vitoria zolli`,
   `alana simora da vitoria`), empresa (`unimed vitoria`) e órgão estadual
   (`superintendencia regional de saude de vitoria`). Não são removíveis por regex sem apagar
   texto legítimo, e não precisam ser: caem em confiança baixa e não contam para cobertura.
3. **`Castelo` ⊂ `Conceição do Castelo`; `Itapemirim` ⊂ `Cachoeiro de Itapemirim`** — os dois
   únicos casos de subconjunto entre os 78. Resolvidos por longest-first com mascaramento (§5.2).
4. **`Cachoeiro de Itapemirim` vs `Cachoeiro do Itapemirim`** — a própria API do IBGE usa a
   segunda forma em `regiao-imediata.regiao-intermediaria.nome`. Alias obrigatório, com evidência.
5. **Captura de menção que engole a frase seguinte** — `"joao neiva por falta disciplinar e"`.
   Medido: 6 de 7 capturas não resolvidas eram município real seguido de texto. Resolvido por
   poda por prefixo de tokens, com teto de 4 tokens (§7.2).
6. **Duas capturas que são a mesma** — `joao neiva` (18) e `joao neiva por falta` (3).
   Consolidadas por prefixo antes de reportar (§7.2).
7. **Página de continuação sem nome de município** — `municipio_escopo: "indeterminado"`, sem
   herança do bloco ou da página anterior (§5.4).
8. **Página sem `Protocolo`** — medido em **50 das 144 (34%)**, todas no escopo DOM. Tratada como
   bloco único; nenhuma dessas 50 tem simultaneamente >1 município e >1 edital, logo o
   cartesiano não volta por essa porta (§6.5).
9. **Produto cartesiano município × edital** — 30 páginas com >1 de cada; 1.419 achados se
   pareado cegamente. Resolvido por bloco + no máximo 1 achado por (bloco, município) +
   `editais_citados` (§6.5).
10. **Número que não é edital** — `273/0001`, `318/0001` (CNPJ fragmentado), `17/2007` (lei).
    O "ano" `0001` aparece 55 vezes na amostra. Resolvido por adjacência a palavra-chave e faixa
    de ano `[ano-4, ano+1]`; o achado **não** é perdido, só perde o número na chave (§6.5).
11. **Autarquia municipal cujo nome não cita a cidade** — "Serviço Autônomo de Água e Esgoto de
    Aracruz" cita (e `saae de` é marca de contexto); "IPC" (Cariacica) não. Resolve-se por
    `orgaos_vinculados`; o que não estiver lá cai em indeterminado ou em não mapeado — **nunca
    atribuído por palpite** (§4).
12. **Consórcio sem lista de membros** — `municipios_slugs: []` + pendência; não credita
    cobertura a ninguém e aparece em `orgaos_vinculados_sem_municipio` (§4).
13. **Agência reguladora intermunicipal com sede em Vitória** — `ps-aries-es-*`. Não credita
    Vitória; aridade 0..N por natureza (§4, §9.2).
14. **Mesmo número de edital em municípios diferentes** (`001/2026` é frequentíssimo) — a chave
    inclui o slug, então não colide. Para o **casamento com `dados/`**, achado de diário usa
    `casar_estrito()`: medi que `tokens_identidade("Prefeitura de Serra") == {"serra"}` e que
    `_coberto("serra", {"serrana"})` é `True`, de modo que o ramo final de `casar()` marcaria um ato
    de nomeação como `no_repositorio: true` apontando para qualquer certame de Serra (§6.7).
15. **Edital citado em várias páginas e edições** — unificado pela chave por (escopo, município,
    número) (§6.6).
16. **Empate de ordenação dentro do mesmo dia** — `sort` é o timestamp do dia (medido
    `[1790812800000]` para todos os itens de 2026-10-01). Resolvido por ordenação explícita
    (data desc, menor `diario_id`, menor `pagina`) (§6.6).
17. **`suplemento` não é suplemento** — é o rótulo da edição (`"Edição 3099"`). Guardado como
    `edicao`, sem inferência (§6.2).
18. **Volume ordinário acima do teto** — DOM/`"processo seletivo"` tem 131 hits = 14 páginas.
    Tetos novos (20 páginas, 1000 achados) e truncamento visível na issue (§6.4, §7.5).
19. **IBGE respondendo gzip** — caso normal, não exceção. Sem `gzip.decompress()` a reconciliação
    falharia em 100% das execuções (§6.4, §7.3).
20. **Domínio de prefeitura devolvendo 403** — 5 dos 14 sondados. Canal **registrado** com
    `estado: "pendente"`, `verificado_em: null` e pendência `canais:conferir_manual`; não
    descartado (§3.2).
21. **`descobertas.json` de versão anterior** — 37 achados sem `categoria`. Quatro medidas, cada uma
    cobrindo um caminho distinto: backfill no coletor (achado herdado), chaves de topo ausentes =
    aviso, tolerância por achado legado no validador (fronteira em `ibge_consultado_em`) e
    `--migrar-descobertas` commitado no PR (§6.9).
22. **Primeira execução sem `descobertas.json`** — `carregar_anterior()` devolve `({}, {})`;
    `municipios_nao_mapeados` anterior é tratado como `[]`.
23. **Município novo criado por lei** — detectado por (B) e/ou (C); nunca escrito
    automaticamente. `total_esperado != 78` é aviso, não erro (§9.2).
24. **Fuso horário** — `comum.hoje()` respeita `DATA_REFERENCIA`; `di:` deriva dele, logo
    execução reproduzível continua reproduzível. O workflow usa `date -u`, e a janela de 7 dias
    absorve UTC vs Brasília sem caso especial.
25. **`--fonte ioes-busca-dom` isolado** — `cobertura_municipios` é recalculada só com o que foi
    coletado; os contadores ficam menores, o que é correto e **não** deve ser "corrigido"
    mesclando com a execução anterior.
26. **Alias redundante** — alias que normaliza igual ao próprio nome gera **aviso**, para o
    arquivo não acumular ruído que dá falsa sensação de cobertura (§9.2).
27. **Dois municípios adjacentes no texto** — `"PREFEITURA DE VILA VELHA SERRA"`,
    `"MUNICIPIO DE SANTA MARIA DE JETIBA LINHARES"`. Medido: com máscara de espaço o segundo herda a
    marca do primeiro e sai em confiança **alta** indevida; com máscara `"\x00"` sai em `baixa`.
    Listas de lotação e cabeçalhos de caderno produzem essa sequência com frequência (§5.2).
28. **Ato de órgão vinculado cujo nome não cita a cidade** — `IPC`, Cariacica. Resolvido pela
    passada de órgãos de §5.2.1, que casa `nome` **e** `sigla` antes da passada de municípios; sem
    ela, `orgao_vinculado_id` nunca seria preenchido e a lista de §4.1 seria decorativa.
29. **Quarentena crescendo para sempre** — `ato_diario` tem `inscricoes.fim == null`, então a poda
    existente nunca o alcança e o laço de preservação o reanexa indefinidamente, a ~218 achados/dia
    num arquivo commitado diariamente. Resolvido pela retenção de 90 dias por categoria (§6.9.1),
    com `descartados_por_retencao` visível e aviso de `len(achados) > 5000` (§9.4).
30. **O PR que implementa este design reprovando no próprio validador novo** — 37 achados
    versionados sem `categoria`, e o job `validar` não passa por `coletar.py`. Resolvido pela
    tolerância por achado legado **mais** `--migrar-descobertas` commitado junto (§6.9).
31. **Achado de `selecao-es` sem os campos `municipio_*`** — as duas fontes antigas não os
    conheciam, e §9.4 os exige. Resolvido por `normalizar_achado()` em `main()`, aplicado a toda
    fonte (§6.10); sem isso a primeira coleta real travaria o commit automático.
32. **Mesmo edital publicado no DIO e no DOM** — gera dois achados, por decisão: a chave inclui o
    escopo porque cada achado aponta para o PDF que contém o ato, e esse PDF é por escopo. A
    cobertura não infla, porque conta municípios distintos e não achados (§6.6).
33. **Página longa truncada em 20.000 caracteres** — pode cortar blocos de ato inteiros. O
    truncamento vem antes da segmentação, e a perda é observável por `conteudo_truncado: true` no
    achado e `paginas_truncadas` no diagnóstico, em vez de silenciosa (§6.5).
34. **Primeira execução com cadastro** — `slugs_com_sinal_historico` anterior não existe, então
    todos os municípios com sinal entram em `vistos_pela_primeira_vez` de uma vez. Correto no dado;
    `gerar_email` não anuncia os 41 porque só anuncia o que ainda não está em `cobertura_vistos`
    (§7.4, §11.3).
35. **Município intermitente: ato hoje, silêncio na semana seguinte, ato de novo** — sai de
    `slugs_com_sinal` (que é retrato da janela) e **não** volta a `vistos_pela_primeira_vez`, porque
    o delta é contra `slugs_com_sinal_historico`, que é monotônico. Sem isso a issue anunciaria
    "primeiro ato detectado em X" a cada intermitência (§7.4).
36. **Nome ou sigla com pontuação no diário** — `cim-polinorte`, `cim/polinorte`, `s.mateus`.
    Medido: `re.search(r"\bcim polinorte\b", "ato do cim-polinorte")` é **False**, porque
    `normalizar()` não colapsa pontuação. Resolvido por `_padrao_de_chave()`, que compila a chave de
    `chave_nome()` com separador tolerante (§5.1). O separador **exclui `\x00`** porque, medido, com
    `[^a-z0-9]+` a máscara de §5.2 viraria ponte: em
    `"secretaria de vila, conceicao do castelo, pavao e outros"`, depois de consumir
    `conceicao do castelo`, o padrão de `Vila Pavão` **casa** — e não casa com `[^a-z0-9\x00]+`.
37. **Município que publica exclusivamente pelo DOM/AMUNES** — caso comum, **não** lacuna: um canal
    `diario_oficial_agregador` com `estado: "confirmado"` por ato observado é mapeamento completo. A
    auditoria e o README dizem qual é o canal, em vez de marcar falta de "fonte própria" (§3.1,
    §11.1).
38. **Candidato de menção que aparece 1× por dia em páginas distintas e sem `/ES`** — com contadores
    por execução nunca passaria de `paginas_distintas == 1` e **nunca** seria reportado, embora tenha
    7 páginas na semana. Resolvido pela fusão acumulada de §7.2; é desse candidato que o aprendizado
    de alias depende.
39. **PR que implementa o design, antes da primeira coleta** — `descobertas.json` sem
    `cobertura_municipios`, e `gerar_readme.py --check` rodando no PR. Panorama com `0`, coluna
    `Ato detectado` com `—` nas 78 linhas, `Registros curados` e `Canal principal` corretos; README
    determinístico (§11.1).

---

## 16. Testabilidade

Não existe suíte hoje (`ferramentas/` tem só executáveis). O design **não** introduz framework
externo: acrescenta `ferramentas/testes.py`, executável por `python3 ferramentas/testes.py`, com
`unittest` da biblioteca padrão (3.9 ok), e dois passos no workflow (§10.3).

**Unitário, sem rede — onde está o risco de verdade:**

| Alvo | Asserção |
| ---- | -------- |
| `comum.slug()` sobre os 78 nomes | compara com uma **lista literal escrita no arquivo de teste**, não com o cadastro. Dupla contabilidade deliberada e comentada: comparar o cadastro consigo mesmo seria circular e passaria mesmo com a função quebrada |
| `comum.chave_nome()` | `"S. Mateus"`, `"S.Mateus"`, `"S Mateus"` → mesma chave |
| **`comum._padrao_de_chave()`** | `"CIM Polinorte"` casa `cim polinorte`, `cim-polinorte`, `cim/polinorte` e `cim.polinorte`; **não** casa através da máscara (`"vila, " + "\x00"*20 + ", pavao"` → `Vila Pavão` **não** casa). As duas asserções juntas travam o separador `[^a-z0-9\x00]+` (§5.1) |
| **Alias em texto livre** | `"MUNICIPIO DE CACHOEIRO DO ITAPEMIRIM/ES"` → `cachoeiro-de-itapemirim` com `municipio_origem == "alias"` e confiança **alta** (marca adjacente); `"... cachoeiro ..."` sem marca → mesma resolução com confiança **baixa** (§5.1, §5.3) |
| `resolver_municipio()` vs `resolver_municipio_em_texto()` | exata: `"Anchieta"` → `("anchieta", "nome")`, `"Prefeitura de Anchieta"` → `(None, None)`, `"Camara Municipal de Aracruz"` → `("aracruz", "orgao_vinculado")`. Em texto livre: `"Prefeitura de Anchieta"` → `("anchieta", "nome")`; `"Prefeitura de Serra e de Vila Velha"` → `(None, None)` por ambiguidade (§5.1) |
| `_limpar_boilerplate()` | sobre as 4 formas reais de assinatura (dia da semana, data numérica, "de setembro 2026" sem o segundo "de", `cep:`): `"vitoria"` desaparece e o corpo do ato permanece |
| Casamento longest-first | `"Conceição do Castelo"` **não** credita Castelo; `"Cachoeiro de Itapemirim"` não credita Itapemirim; texto com os dois nomes credita os dois |
| `municipio_confianca` | marca adjacente → alta; mesma marca a 300 caracteres → baixa; `serra/es` → alta; `estado do espirito santo` em outro trecho → baixa |
| **Não vazamento de marca entre municípios adjacentes** | `"prefeitura de vila velha serra"` → `vila-velha` **alta** e `serra` **baixa**; `"municipio de santa maria de jetiba linhares"` → `linhares` **baixa**. É o teste que trava a máscara `"\x00"`: com espaço, as duas asserções falham (§5.2) |
| Casamento de órgão vinculado | `"instituto de previdencia dos servidores de cariacica"` e `"IPC"` → `orgao_vinculado_id == "ipc-cariacica"`, `municipio_slug == "cariacica"`, confiança alta; `"ARIES"` → `orgao_vinculado_id == "aries"`, `municipio_slug is None`, escopo `intermunicipal` |
| `casar_estrito()` | ato de diário de Serra **sem** número de edital **não** casa com `concurso-...-serra-2026`; com `001/2026` coincidente **casa**; URL idêntica **casa**. E o mesmo achado passado a `casar()` **casaria** — a asserção negativa prova que a distinção importa |
| `normalizar_achado()` | achado real de `concursosnobrasil-es` com `orgao: "Prefeitura de Anchieta"` e `municipio` ausente sai com `municipio_slug == "anchieta"`, `municipio_escopo == "municipal"`, `municipio_confianca == "baixa"`, `municipio_origem == "nome"` — **é** a linha da tabela de §6.10 que a consulta exata nunca produziria, e o teste falharia se alguém trocasse de volta para `resolver_municipio()`; achado com `orgao: "SEDU"` e `esfera: "estadual"` sai `null`/`estadual`; achado de `ato_diario` com `municipio_confianca: "alta"` **não** é sobrescrito (`setdefault`) |
| Filtro de `novos` | lista com 2 oportunidades e 5 atos de diário inéditos → `len(novos) == 2` e `len(atos_novos) == 5` |
| Retenção de `ato_diario` | ato com `data_publicacao_ato` de 100 dias atrás é descartado e contado; de 80 dias é preservado; `oportunidade` sem `inscricoes.fim` e com 100 dias **não** é descartada pela retenção |
| Tolerância de legado em `valida_descobertas()` | achado sem `categoria` e `primeira_deteccao` anterior a `ibge_consultado_em` → **aviso**; `primeira_deteccao` **igual** a `ibge_consultado_em` → **aviso** (é o caso dos 2 achados medidos; com `<` seria erro); posterior → **erro**; com `categoria: "lixo"` → **erro** nos três casos |
| `--migrar-descobertas` | idempotente: aplicar duas vezes dá o mesmo arquivo; preserva `primeira_deteccao` e todas as chaves de topo existentes; e o conjunto de campos escritos é **exatamente** o de `normalizar_achado()` — o teste compara as chaves do achado migrado com as de um achado novo normalizado, de modo que acrescentar campo em um só lugar falha |
| Fusão de `municipios_nao_mapeados` | candidato com `ocorrencias: 1, paginas_distintas: 1, com_marca_uf: false` no arquivo anterior, visto 1× numa página nova → acumulado `2/2` e **passa** a ser reportado; `primeira_deteccao` preservada, `ultima_deteccao` de hoje, ≤3 exemplos de páginas distintas; candidato com `ultima_deteccao` de 29 dias atrás (`--janela-ioes-dias 7` × 4) é **removido** (§7.2) |
| Degradação de envelope malformado | `_achados_de_resposta()` com `{"hits": {"hits": [{}]}}`, `_source: null` e `hits.hits: "texto"` devolve `[]` e **não** levanta `KeyError`/`TypeError` (§12) |
| **Regressão da armadilha Vitória** | trecho real em caixa alta do cabeçalho do caderno + assinatura estadual: assere `("vitoria", "alta")` **ausente** e o município do ato presente. Sem este teste o bug volta sem aviso |
| **Regressão dos padrões de menção** | trecho real em caixa alta (`PREFEITURA MUNICIPAL DE ...`): assere **≥1** captura. É o teste que o passe anterior não tinha e que deixou o requisito nascer morto |
| `classificar_mencao()` | `"joao neiva por falta disciplinar e"` → `("mapeado", "joao-neiva")`; `"que trata esta lei"` → candidato; `"venda nova do imigrante ..."` resolve no prefixo de 4 tokens |
| **Detecção por injeção** | com um índice de cadastro **sem** `sooretama`, um trecho citando `"MUNICÍPIO DE SOORETAMA/ES"` produz candidato; com o cadastro completo, não produz nenhum. "Não aparece ruído" é indistinguível de "não aparece nada", então o caminho positivo tem de ser exercitado |
| Filtros de candidato | 1 ocorrência sem `/ES` é descartada; 1 ocorrência **com** `/ES` passa; 2 ocorrências sem `/ES` passam; consolidação de `joao neiva` + `joao neiva por falta` em uma linha |
| `_blocos_de_ato()` | texto com 3 `"protocolo N"` → 3 blocos; texto sem → 1 bloco; bloco com <40 caracteres descartado |
| Pareamento | bloco com 1 município e 3 números → 1 achado + 2 em `editais_citados`; número com ano fora da faixa descartado; bloco cujos números foram todos descartados cai na chave por página |
| `chave` | estável entre duas execuções com a mesma entrada; mesma chave para o mesmo edital em páginas diferentes |
| Ordenação determinística | dois envelopes com itens embaralhados e mesmo `sort` produzem a mesma lista final |
| `valida_cadastro_municipios()` / `valida_catalogo_fontes()` | um dict em memória por defeito de §9.1/§9.2, conferindo que cada um produz **exatamente** o erro esperado — incluindo os casos "ok" que **não** devem gerar erro: município com **um único** canal `diario_oficial_agregador` confirmado (caso comum, §3.1); canal `pendente` com `verificado_em: null` e `canais:conferir_manual`; `agencia_reguladora` com 0 slugs e pendência. E os casos de erro novos: município sem canal de diário e sem `canais:nao_encontrado`; canal `confirmado` sem `verificado_em`; duas `precedencia` iguais no mesmo município; `precedencia: 1` não sendo de diário havendo canal de diário; órgão com `url: null` sem `url:nao_encontrado`; chave desconhecida em canal e em órgão |
| **Tabela de cobertura do README sem `cobertura_municipios`** | `descobertas.json` sem o bloco (o estado do PR) → Panorama com `0`, 78 linhas com `Ato detectado` `—`, `Registros curados` e `Canal principal` preenchidos, e `--check` estável entre duas gerações (§11.1) |
| `cobertura()` | função pura: índice + registros + achados + `slugs_com_sinal_historico_antes` + referência → contagens esperadas; achado de confiança baixa **não** conta; órgão vinculado com `municipios_slugs` credita o município |
| `cobertura()` — janela vs acumulado | achado `alta` com `ultima_deteccao != gerado_em` conta em `com_achado_acumulado` e **não** em `com_achado_na_janela` (§7.4) |
| `cobertura()` — delta | `slugs_com_sinal_historico_antes = {"serra"}` e sinal agora em `{"serra", "sooretama"}` → `vistos_pela_primeira_vez == ["sooretama"]`; `= set()` → todos |
| `cobertura()` — **histórico monotônico** | histórico `{"serra", "sooretama"}` e sinal agora só em `{"serra"}` → `slugs_com_sinal == ["serra"]`, `slugs_com_sinal_historico == ["serra", "sooretama"]` e `vistos_pela_primeira_vez == []`; na execução seguinte, com sinal em `{"serra", "sooretama"}`, `vistos_pela_primeira_vez` continua `[]` — é o teste que trava o reanúncio (§7.4) |
| `cobertura()` — lista acumulada | achado `alta` com `ultima_deteccao` antiga entra em `slugs_com_achado_acumulado` e não em `slugs_com_sinal`; `len(slugs_com_achado_acumulado) == com_achado_acumulado` |
| `cobertura()` — intermunicipal | os 53 registros reais (ou um recorte com `ps-consorcio-caparao-es-2026`) dão `com_registro_curado == 15` e **não** 16: `Divino de São Lourenço` **não** entra em `com_registro_curado` **e** soma 1 em `registros_intermunicipais_sem_atribuicao` (§4, §7.4). As duas metades são asseridas; o passe anterior só tinha a segunda |
| Imutabilidade do índice | `indice_municipios()` devolve `IndiceMunicipios` (namedtuple), e tentar atribuir a um campo levanta `AttributeError` — trava a regressão para dict memoizado mutável (§5.1) |
| `carregar_estado()` | estado sem `cobertura_vistos` devolve `{}` na terceira posição; estado corrompido devolve `({}, {}, {})` |

**Ponto de parsing isolado.** A extração de achados a partir de um envelope **já
desserializado** vive em `_achados_de_resposta(envelope, escopo, frase, indice)`, função pura.
É ela que os testes exercitam, com envelopes fixos salvos como literais no arquivo de teste. A
camada de rede (`_ler_bytes`, `_ler_com_retry`) **não** é testada unitariamente — é fina de
propósito justamente para que isso seja aceitável.

**Integração, com rede, fora do CI:** `--autoteste-ioes` em `coletar.py` faz uma consulta real
por escopo e imprime total, nº de itens, municípios resolvidos e não mapeados. Serve à auditoria
manual e a diagnosticar mudança de layout. **Não** roda no workflow: teste que depende de
terceiro não pode reprovar PR.

---

## 17. Arquivos criados e modificados

| Arquivo | Ação | Resumo |
| ------- | ---- | ------ |
| `fontes/municipios-es.json` | **criar** | 78 municípios, cada um com sua lista `canais` (§3.1, §3.1.1), + `orgaos_vinculados` (§4) |
| `ferramentas/sondar_prefeituras.py` | **criar** | sondagem de **uso único** dos candidatos de canal (§3.2): deriva `https://www.<slug sem hifens>.es.gov.br/`, substitui pelo catalogado quando houver, sonda com o `User-Agent` do projeto e imprime TSV `slug / tipo / status / url / estado / pendência`. **Não** é chamado pelo workflow e **não** escreve no cadastro |
| `fontes/fontes.json` | modificar | `esfera: "nao_se_aplica"` nas 12 fontes; duas fontes novas `ioes-busca-dio` / `ioes-busca-dom`; `ultima_atualizacao` |
| `fontes/README.md` | **criar** | documenta os dois arquivos de `fontes/`, o **vocabulário de `tipo` de canal e a regra de precedência** (§3.1.1), a regra de pendência de verificação, o `User-Agent` de sondagem e a regra de admissão de alias |
| `ferramentas/comum.py` | modificar | mover `_sem_acento`/`normalizar`/`slug`; acrescentar `chave_nome()`, **`_padrao_de_chave()`** (§5.1), `CAMINHO_MUNICIPIOS`, `IndiceMunicipios` (namedtuple, §5.1), `carregar_municipios()`, `indice_municipios()` (com `lru_cache`), **`resolver_municipio()` e `resolver_municipio_em_texto()`** (§5.1), `ESFERAS_FONTE_VALIDAS`, `TIPOS_FONTE_COM_ESFERA`, **`TIPOS_CANAL`**, `NATUREZAS_ORGAO_VINCULADO`, `CATEGORIAS_ACHADO`, `ESCOPOS_MUNICIPIO`, **`ORIGENS_MUNICIPIO`**, `MOTIVOS_PENDENCIA` |
| `ferramentas/coletar.py` | modificar | `coletar_ioes()` (com os seis estágios de §6.5 e deduplicação por chave antes do `return`, §6.6) + duas entradas em `FONTES` via `functools.partial` + `FONTES_COM_DIAGNOSTICO`; `_ler_bytes()` (gzip), `_ler_com_retry()`, `_limpar_boilerplate()`, `_blocos_de_ato()`, `_achados_de_resposta()`, `classificar_mencao()` + `MAX_TOKENS_CANDIDATO` (§7.2), fusão de `municipios_nao_mapeados` (§7.2), **`normalizar_achado()`** (§6.10), **`casar_estrito()`** (§6.7), `cobertura()` com 5 parâmetros (o quarto é `slugs_com_sinal_historico_antes`, §7.4), reconciliação IBGE, backfill de `previo`, **retenção de `ato_diario`** (§6.9.1), filtro de `novos` + `atos_novos`, `carregar_anterior()` devolvendo `(dict, bruto)`, `--retencao-atos-dias`, `--migrar-descobertas` (= `normalizar_achado()` em cada achado), novas saídas GitHub com `truncado` agregado (§7.5), **`monta_relatorio_md(novos, relatorio_fontes, referencia, contexto)`** (§7.5); delegação dos utilitários de texto para `comum` |
| `descobertas/descobertas.json` | **migrar e commitar** | rodar `coletar.py --migrar-descobertas` e commitar junto com a mudança do validador: backfill de `categoria`/`municipio_slug`/`municipio_escopo`/`municipio_confianca` nos 37 achados, sem rede (§6.9). Sem isto o PR é reprovado pelo validador que ele mesmo acrescenta |
| `ferramentas/validar.py` | modificar | `valida_catalogo_fontes()` (com **import tardio de `coletar`**, §9.1), `valida_cadastro_municipios()`, reforço de `valida_escopo()` e `valida_descobertas()` (tolerância de legado, contadores de menção, teto de 5000), `--json` estendido. **Dependência nova declarada: `validar → coletar`**, tardia e isolada numa função |
| `ferramentas/gerar_readme.py` | modificar | 3 linhas de Panorama + seção "Cobertura por município" (coluna `Ato detectado` por `slugs_com_achado_acumulado`, coluna `Canal principal` pelo canal de `precedencia: 1`, e a regra do bloco ausente, §11.1); filtro de `ato_diario` em `carregar_descobertas()` |
| `ferramentas/gerar_relatorio.py` | modificar | `bloco_coleta()` com cobertura e agregação por microrregião |
| `ferramentas/gerar_email.py` | modificar | filtro de `ato_diario`; bloco de cobertura; `carregar_estado()`/`gravar_estado()` com `cobertura_vistos` e os dois call sites |
| `ferramentas/testes.py` | **criar** | `unittest` stdlib (§16) |
| `.github/workflows/monitoramento.yml` | modificar | `fontes/**` e o próprio YAML nos gatilhos; `descobertas/**` e `README.md` fora do `push`; condição e título da issue; passo de testes nos dois jobs |
| `dados/ESQUEMA.md` | modificar | parágrafo distinguindo `esfera` de registro vs de fonte; referência ao cadastro como vocabulário de `municipio` |

**Não modificados, deliberadamente:** `ferramentas/atualizar_prazos.py` (transições mecânicas de
prazo, nada a ver com município), `ferramentas/enviar_email.py` (só transporte SMTP),
`ferramentas/consultar_selecao_es.py` (curadoria pontual),
`comum.ESFERAS_VALIDAS`/`comum.DIRETORIOS`/`comum.STATUS_VALIDOS`, e **todos os 53 registros de
`dados/`** — nenhum dado curado muda neste trabalho; só se acrescenta a infraestrutura que
permite medir o que falta. Conferi que o reforço de §9.3 não reprova nenhum dos 53.

---

## 18. Pendências de verificação reconhecidas

Itens que a implementação deve **declarar** em vez de preencher por suposição:

1. Canais de `portal_prefeitura`/`secao_concursos` dos municípios cujo candidato de domínio não
   responder, ou responder 403 (neste caso o canal é registrado com `estado: "pendente"` +
   `canais:conferir_manual`, §3.2). Na amostra de 14, 4 responderam 200, 3 responderam 3xx, 5
   responderam 403, 1 não resolveu em DNS e 1 deu timeout. **Esses números justificam a regra e não
   são dado de implementação**: dependem de WAF, data e `User-Agent`, e `sondar_prefeituras.py`
   re-sonda os 78 candidatos e grava o que medir (§3.2).
2. Canal `diario_oficial_proprio`: só a Serra tem diário próprio aparentemente confirmado dentro
   do IOES (opção `/diariodaserra` do seletor "Outros Diários Oficiais", ao lado de
   `/caderno_municipios` e `/dom`). **Não conferi o seletor inteiro**, então os demais nascem só com
   o canal `diario_oficial_agregador` (`fonte_id: "amunes-dom"`), `confirmado` quando houver ato
   observado no DOM e `pendente` quando não houver observação. Isso **não** é lacuna de cadastro
   (§3.1): é o canal correto da maioria.
3. `plataforma_inscricao` e `banca` por município: nascem **ausentes** em quase todos, porque a
   evidência existe por certame (um edital aponta a banca) e não por município. Entram quando um
   registro de `dados/` daquele município já traz a banca — e a regra de "só com evidência" vale
   aqui como vale para alias (§3.3). Não há pendência declarada para eles: canal que nunca foi
   afirmado não é dívida, e inventar `banca:nao_encontrado` para 78 municípios seria vocabulário
   morto em escala.
3. Composição dos consórcios intermunicipais (CIM Polinorte, Consórcio Caparaó, ARIES) —
   `municipios_slugs: []` + pendência até apuração documental.
4. `aliases` além dos 2 com evidência (§3.3) — a lista nasce curta de propósito e cresce pelas
   issues de `municipios_nao_mapeados`, que entregam a evidência junto. Preenchê-la por
   antecipação com variantes imaginadas esvaziaria o mecanismo.
5. Estabilidade do endpoint `/busca/busca/buscar/` e do bundle Angular que documenta o contrato —
   não documentados publicamente. Mitigado por `suspeita_extracao_vazia` (agora por escopo),
   `truncado` e `--autoteste-ioes`; se mudar, a coleta degrada com aviso e não quebra o pipeline.
6. Forma de `hits.total` a longo prazo (int hoje; Elasticsearch ≥7 devolveria dict) — tolerada
   nos dois formatos por §6.2, mas é suposição sobre versão de terceiro.
7. Os números de volume e de cobertura deste documento valem para a janela medida
   (`di:2026-09-24`, 144 páginas amostradas em até 6 páginas por escopo×frase). São ordem de
   grandeza para dimensionar tetos, **não** garantia de que 41 municípios aparecerão todo dia.

---

## Anexo A — os 78 municípios do Espírito Santo

Fonte: IBGE, Localidades, UF 32 (`/projects/sandbox/ibge_es.json`, conferido nesta revisão
contra `https://servicodados.ibge.gov.br/api/v1/localidades/estados/32/municipios` — **os 78
`id` e os 78 `nome` são idênticos**). `slug` calculado por `comum.slug()`; **nenhum** destes
slugs é prefixo de outro, e os únicos conflitos de nome entre eles são
`Castelo`/`Conceição do Castelo` e `Itapemirim`/`Cachoeiro de Itapemirim`.

| # | Código IBGE | Nome oficial | `slug` | Microrregião |
| -: | ----------- | ------------ | ------ | ------------ |
| 1 | 3200102 | Afonso Cláudio | `afonso-claudio` | Afonso Cláudio |
| 2 | 3200169 | Água Doce do Norte | `agua-doce-do-norte` | Barra de São Francisco |
| 3 | 3200136 | Águia Branca | `aguia-branca` | Nova Venécia |
| 4 | 3200201 | Alegre | `alegre` | Alegre |
| 5 | 3200300 | Alfredo Chaves | `alfredo-chaves` | Guarapari |
| 6 | 3200359 | Alto Rio Novo | `alto-rio-novo` | Colatina |
| 7 | 3200409 | Anchieta | `anchieta` | Guarapari |
| 8 | 3200508 | Apiacá | `apiaca` | Cachoeiro de Itapemirim |
| 9 | 3200607 | Aracruz | `aracruz` | Linhares |
| 10 | 3200706 | Atílio Vivácqua | `atilio-vivacqua` | Cachoeiro de Itapemirim |
| 11 | 3200805 | Baixo Guandu | `baixo-guandu` | Colatina |
| 12 | 3200904 | Barra de São Francisco | `barra-de-sao-francisco` | Barra de São Francisco |
| 13 | 3201001 | Boa Esperança | `boa-esperanca` | Nova Venécia |
| 14 | 3201100 | Bom Jesus do Norte | `bom-jesus-do-norte` | Cachoeiro de Itapemirim |
| 15 | 3201159 | Brejetuba | `brejetuba` | Afonso Cláudio |
| 16 | 3201209 | Cachoeiro de Itapemirim | `cachoeiro-de-itapemirim` | Cachoeiro de Itapemirim |
| 17 | 3201308 | Cariacica | `cariacica` | Vitória |
| 18 | 3201407 | Castelo | `castelo` | Cachoeiro de Itapemirim |
| 19 | 3201506 | Colatina | `colatina` | Colatina |
| 20 | 3201605 | Conceição da Barra | `conceicao-da-barra` | São Mateus |
| 21 | 3201704 | Conceição do Castelo | `conceicao-do-castelo` | Afonso Cláudio |
| 22 | 3201803 | Divino de São Lourenço | `divino-de-sao-lourenco` | Alegre |
| 23 | 3201902 | Domingos Martins | `domingos-martins` | Afonso Cláudio |
| 24 | 3202009 | Dores do Rio Preto | `dores-do-rio-preto` | Alegre |
| 25 | 3202108 | Ecoporanga | `ecoporanga` | Barra de São Francisco |
| 26 | 3202207 | Fundão | `fundao` | Linhares |
| 27 | 3202256 | Governador Lindenberg | `governador-lindenberg` | Colatina |
| 28 | 3202306 | Guaçuí | `guacui` | Alegre |
| 29 | 3202405 | Guarapari | `guarapari` | Guarapari |
| 30 | 3202454 | Ibatiba | `ibatiba` | Alegre |
| 31 | 3202504 | Ibiraçu | `ibiracu` | Linhares |
| 32 | 3202553 | Ibitirama | `ibitirama` | Alegre |
| 33 | 3202603 | Iconha | `iconha` | Guarapari |
| 34 | 3202652 | Irupi | `irupi` | Alegre |
| 35 | 3202702 | Itaguaçu | `itaguacu` | Santa Teresa |
| 36 | 3202801 | Itapemirim | `itapemirim` | Itapemirim |
| 37 | 3202900 | Itarana | `itarana` | Santa Teresa |
| 38 | 3203007 | Iúna | `iuna` | Alegre |
| 39 | 3203056 | Jaguaré | `jaguare` | São Mateus |
| 40 | 3203106 | Jerônimo Monteiro | `jeronimo-monteiro` | Cachoeiro de Itapemirim |
| 41 | 3203130 | João Neiva | `joao-neiva` | Linhares |
| 42 | 3203163 | Laranja da Terra | `laranja-da-terra` | Afonso Cláudio |
| 43 | 3203205 | Linhares | `linhares` | Linhares |
| 44 | 3203304 | Mantenópolis | `mantenopolis` | Barra de São Francisco |
| 45 | 3203320 | Marataízes | `marataizes` | Itapemirim |
| 46 | 3203346 | Marechal Floriano | `marechal-floriano` | Afonso Cláudio |
| 47 | 3203353 | Marilândia | `marilandia` | Colatina |
| 48 | 3203403 | Mimoso do Sul | `mimoso-do-sul` | Cachoeiro de Itapemirim |
| 49 | 3203502 | Montanha | `montanha` | Montanha |
| 50 | 3203601 | Mucurici | `mucurici` | Montanha |
| 51 | 3203700 | Muniz Freire | `muniz-freire` | Alegre |
| 52 | 3203809 | Muqui | `muqui` | Cachoeiro de Itapemirim |
| 53 | 3203908 | Nova Venécia | `nova-venecia` | Nova Venécia |
| 54 | 3204005 | Pancas | `pancas` | Colatina |
| 55 | 3204054 | Pedro Canário | `pedro-canario` | São Mateus |
| 56 | 3204104 | Pinheiros | `pinheiros` | Montanha |
| 57 | 3204203 | Piúma | `piuma` | Guarapari |
| 58 | 3204252 | Ponto Belo | `ponto-belo` | Montanha |
| 59 | 3204302 | Presidente Kennedy | `presidente-kennedy` | Itapemirim |
| 60 | 3204351 | Rio Bananal | `rio-bananal` | Linhares |
| 61 | 3204401 | Rio Novo do Sul | `rio-novo-do-sul` | Guarapari |
| 62 | 3204500 | Santa Leopoldina | `santa-leopoldina` | Santa Teresa |
| 63 | 3204559 | Santa Maria de Jetibá | `santa-maria-de-jetiba` | Santa Teresa |
| 64 | 3204609 | Santa Teresa | `santa-teresa` | Santa Teresa |
| 65 | 3204658 | São Domingos do Norte | `sao-domingos-do-norte` | Colatina |
| 66 | 3204708 | São Gabriel da Palha | `sao-gabriel-da-palha` | Nova Venécia |
| 67 | 3204807 | São José do Calçado | `sao-jose-do-calcado` | Cachoeiro de Itapemirim |
| 68 | 3204906 | São Mateus | `sao-mateus` | São Mateus |
| 69 | 3204955 | São Roque do Canaã | `sao-roque-do-canaa` | Santa Teresa |
| 70 | 3205002 | Serra | `serra` | Vitória |
| 71 | 3205010 | Sooretama | `sooretama` | Linhares |
| 72 | 3205036 | Vargem Alta | `vargem-alta` | Cachoeiro de Itapemirim |
| 73 | 3205069 | Venda Nova do Imigrante | `venda-nova-do-imigrante` | Afonso Cláudio |
| 74 | 3205101 | Viana | `viana` | Vitória |
| 75 | 3205150 | Vila Pavão | `vila-pavao` | Nova Venécia |
| 76 | 3205176 | Vila Valério | `vila-valerio` | Nova Venécia |
| 77 | 3205200 | Vila Velha | `vila-velha` | Vitória |
| 78 | 3205309 | Vitória | `vitoria` | Vitória |

---

## Anexo B — respostas às 26 findings do primeiro passe

*Mantido porque as decisões que ele justifica continuam valendo. As findings do segundo passe estão
no Anexo C.*

Todas as findings foram **endereçadas**. Nenhuma foi ignorada; nenhuma foi mandada para
backlog. Em quatro casos (2, 3, 16, 21) a correção adotada **difere** da proposta da revisão, e a
diferença está justificada com medição própria — como a revisão pediu que fosse feito com o
design original.

### HIGH

**1 — Os regex de detecção não casam nada. ATENDIDA, e ampliada.**
Reproduzi: o padrão original dá **1 captura em 144 páginas** (a revisão mediu 0 em 36; a ordem de
grandeza é a mesma: morto). Adotei os padrões minúsculos sobre o texto **normalizado**, conforme
proposto, e declarei isso explicitamente em §7.2 — 137 capturas na mesma amostra. Adotei também o
teste de regressão exigido (§16, "Regressão dos padrões de menção").
**Além do pedido:** com os padrões funcionando, descobri que **7 de 7** capturas não resolvidas
eram falso positivo por excesso de captura (`"joao neiva por falta disciplinar e"`), isto é, a
correção da revisão, isolada, trocaria "requisito morto" por "gerador de ruído". Acrescentei a
poda por prefixo de tokens e a consolidação de variantes (§7.2), medidas: falso positivos caem
de 7 para 2, ambos eliminados pelo filtro de ≥2 ocorrências; e um teste **por injeção** (§16),
porque ausência de ruído é indistinguível de ausência de detecção.

**2 — A mitigação "Vitória" não funciona e exclui o município real. ATENDIDA; correção diferente
em um dos três pontos, com medição.**
- Ponto (1) — padrão de assinatura: **adotado e estendido**. A versão da revisão deixava 12
  páginas com resíduo, porque os resíduos reais incluem **data numérica** (`vitoria-es,
  28/09/2026.`), **"de setembro 2026" sem o segundo "de"** e o separador `-es`, nenhum previsto
  nas duas versões. O padrão de §5.3 cobre as três formas; sobram 8 ocorrências, nenhuma com
  marca municipal adjacente.
- Ponto (2) — remover `/es`, `- es` e `estado do espirito santo` das marcas de contexto:
  **parcialmente adotado, e aqui discordo com dado.** `estado do espirito santo` e marca em raio
  de 80 caracteres: removidos, a revisão está certa. Mas medi as duas políticas no pipeline
  completo: aceitar `[/-] es` **imediatamente adjacente** (≤6 caracteres) dá **41** municípios em
  confiança alta contra **35** sem aceitar, e **Vitória fica com 0 em confiança alta nas duas**.
  Ou seja, o que torna a marca precisa é a adjacência, não a sua ausência; remover a marca
  custaria 6 municípios de cobertura sem nenhum ganho de precisão. Adotei a adjacência (§5.3).
- Ponto (3) — tratar título de seção do caderno como marca própria: **não necessário, e por isso
  não adotado.** Com a limpeza corrigida e a adjacência, Nova Venécia aparece em confiança
  **alta** (14 ocorrências, 2º lugar) e o perfil geral é o correto (João Neiva 19, Santa Teresa
  11, Aracruz 10...). O sintoma que motivava o ponto (3) — "o DIO inteiro degrada para baixa" —
  não se reproduz. Acrescentar um marcador posicional baseado em cabeçalho removido seria
  mecanismo extra sem defeito a corrigir.
- Número `100%` corrigido para **21% antes da limpeza** (30/144), medido (§5.3, §15.1).

**3 — Pareamento município × edital explode. ATENDIDA.**
Reproduzi: **30 páginas** com >1 município e >1 número, **1.419** achados se cartesiano. Adotei a
segmentação por `protocolo \d+` antes da limpeza, o pareamento só dentro do bloco, no máximo 1
achado por (bloco, município), `editais_citados` para os demais, e o filtro de ano.
Dois ajustes com medição própria: **(i)** a faixa de ano é `[ano-4, ano+1]` e não `[ano-3,
ano+1]`, porque há ato de 2026 nomeando candidato de `concurso publico 01/2022`, caso real na
amostra; e explicitei que o filtro **não descarta o achado, só o número** — sem essa propriedade
o filtro perderia sinal de cobertura. **(ii)** O fallback por "cabeçalho de órgão" que a revisão
sugeriu foi **descartado deliberadamente**: medi que 50 das 144 páginas não têm `protocolo`
(todas DOM) e que **nenhuma delas** tem simultaneamente >1 município e >1 edital, logo tratá-las
como bloco único não reintroduz o cartesiano. Inventar um segundo delimitador para um caso que a
medição mostra inexistente seria especulação. Registrei também que `protocolo \d+` **saiu** da
lista de boilerplate, porque no passe anterior estava nos dois papéis e se autodestruía.

**4 — Tetos padrão cortam o volume ordinário. ATENDIDA integralmente.**
Confirmei os quatro números (DIO 16/8, DOM 63/**131**) e o teto estourando em dia normal. Novos
padrões: `--max-paginas-ioes=20` (teto 100), `--max-achados-ioes=1000` (teto 5000). Orçamento
recalculado em §6.4: ≤80 requisições ≈ 80 s a 1,0 s/req medido, ~96 s com a pausa de cortesia.
`truncado` passa a aparecer **no corpo da issue** (§7.5) e em `--saida-github`, não só no log.

**5 — `Content-Encoding: gzip` não tratado e `gzip` fora da lista. ATENDIDA integralmente.**
Reproduzi exatamente: o endpoint do IBGE responde **200 com `Content-Encoding: gzip`** sem o
cliente pedir, e `json.loads` falha com `UnicodeDecodeError` — a reconciliação seria `"erro"` em
100% das execuções. `gzip`, `time`, `socket` e `functools` acrescentados à §2, e `_ler_bytes()`
especificado em §6.4 com `Accept-Encoding: identity` + `gzip.decompress()` condicional.

**6 — Não há migração do `descobertas.json` commitado. ATENDIDA integralmente.**
Confirmei: 37 achados, nenhum com `categoria`, 8 chaves de topo. Adotados os dois lados do fix:
backfill explícito ao reaproveitar `previo` nos **dois** ramos de preservação, e checagens dos
blocos novos valendo só se a chave existir (ausência = aviso). §6.9 documenta o mecanismo e o
motivo (o commit automático travaria todo dia).

### MEDIUM

**7 — Contradição sobre `url_diario_oficial` nulo. ATENDIDA integralmente.** A regra única virou
três linhas em §9.2: `url_prefeitura` nula sem pendência → erro; `url_diario_oficial` nula **e**
`diario_oficial_em` nulo sem pendência → erro; `url_diario_oficial` nula **com**
`diario_oficial_em` preenchido → **ok**. O caso de §18.2 deixa de ser reprovado por §9.2.

**8 — `len(municipios_slugs) == 1` quebra `agencia_reguladora`. ATENDIDA integralmente.** Regra
de aridade por natureza (§9.2): 1 slug só para `camara_municipal`, `autarquia_municipal`,
`fundacao_municipal`, `empresa_municipal`; `consorcio_intermunicipal` e `agencia_reguladora`
exigem `esfera: "intermunicipal"` e aceitam 0..N, com `[]` exigindo pendência. §4 explica com o
caso ARIES por que creditar a sede seria o rateio por palpite que a própria seção proíbe.

**9 — Literal `78` em `validar.py` conflita com a detecção. ATENDIDA integralmente.** O literal
vive só no cadastro (`total_esperado`). Regras de §9.2: `len != total_esperado` → erro;
`total_esperado < 78` → erro; `total_esperado != 78` → **aviso**;
`cobertura_municipios.total_municipios != total_esperado` → erro. §14 reescrito para dizer o
invariante nesses termos.

**10 — Canal de retorno dos metadados. ATENDIDA, com solução melhor que a proposta.** Adotei o
dict `diagnostico` mesclado em `registro_fonte` e a função pura `cobertura(indice, registros,
achados)` chamada por `main()` depois do laço, como a revisão pediu. **Além disso**, dividi a
fonte em `ioes-busca-dio` e `ioes-busca-dom` via `functools.partial` (§6.3): o laço existente
passa a dar degradação graciosa **por escopo** de graça, `suspeita_extracao_vazia` passa a valer
por escopo, `--fonte ioes-busca-dom` torna-se possível, e o campo `escopos_com_falha` — que a
revisão ainda listava como metadado a transportar — **deixa de ser necessário**. Resolve também a
finding 21 pela raiz.

**11 — `carregar_anterior()` não dá acesso a `municipios_nao_mapeados`. ATENDIDA integralmente.**
Passa a devolver `(achados_por_chave, bruto)`; único call site atualizado;
`bruto.get("municipios_nao_mapeados", [])` tolera arquivo antigo. Registrado em §7.2 e na tabela
de §17.

**12 — Assinaturas de `carregar_estado()`/`gravar_estado()`. ATENDIDA integralmente.** §11.3 define
`carregar_estado() -> (impressoes, descobertas, cobertura_vistos)` com
`estado.get("cobertura_vistos", {})`, `gravar_estado(impressoes, descobertas, cobertura_vistos,
referencia)`, valor `{slug: data_do_primeiro_anuncio}` para permitir expiração, os dois call
sites (linhas 410 e 436) e o ramo de estado corrompido devolvendo `({}, {}, {})`.

**13 — Números factuais errados. ATENDIDA; medi todos de novo.**

| Afirmação anterior | Valor correto (medido nesta revisão) | Onde foi corrigido |
| ------------------ | ------------------------------------ | ------------------ |
| "14 dos 54 registros com Âmbito estadual" | **24 de 53** | §1.1, §4, §9.3 |
| "54 registros" | **53** | §1.1, §17 |
| "8 municípios com fonte própria" | **7** (8 fontes municipais, 2 de Aracruz) | §1, §1.1, §3.2 |
| "Vitória em 100% das páginas" | **21%** antes da limpeza (30/144) | §5.3, §15.1 |
| "`q=Sooretama` com `di:` cai para 29" | número não reproduzido; **removido** do documento e substituído pelos volumes por escopo×frase, que são os que dimensionam os tetos | §6.2, §6.4 |

Nenhum desses números é usado como expectativa em teste: a lista esperada de slugs em §16 é um
literal no arquivo de teste, e as contagens de §11.1/§11.2 são lidas do cadastro e de
`cobertura_municipios` em tempo de execução.

**14 — "Só 200" descarta domínios que existem. ATENDIDA integralmente.** Sondei 14 candidatos com
o `User-Agent` do projeto e reproduzi os 403 (sooretama, marataizes, vilapavao, saoroquedocanaa —
e também joaoneiva) e os 3xx (linhares, guacui, iuna). Critério de §3.2: 2xx/3xx → confirmada;
403/406/429 → URL registrada **com** pendência `conferir_manual`; 404/NXDOMAIN/timeout/TLS →
`null` + pendência `nao_responde`. O `User-Agent` fica documentado em `fontes/README.md`.
A regra de §9.2 foi ajustada para não reprovar URL preenchida com pendência `conferir_manual`.

**15 — Dedup não determinística. ATENDIDA integralmente.** Confirmei que `sort` é o timestamp do
**dia** (`[1790812800000]` para todos os itens de 2026-10-01). §6.6 especifica a ordenação
explícita antes do dedup (data desc, menor `diario_id`, menor `pagina`), diz qual item ganha a
chave, e declara que `_diario_id`/`_pagina` são campos internos removidos antes da gravação.

**16 — Política de aliases se contradiz e ignora pontuação. ATENDIDA; fui além na parte (a).**
Parte (b) — `chave_nome()` com colapso de pontuação — **adotada integralmente** (§3.3), inclusive
usada no cadastro e no casamento, e testada (§16). Parte (a): procurei evidência para cada
candidato em vez de aceitar a lista sugerida. `Cachoeiro do Itapemirim` tem evidência (confirmei
`regiao-imediata.regiao-intermediaria.nome` no IBGE) e `Cachoeiro` também (id e host da fonte
`prefeitura-cachoeiro`). **`Santa Maria do Jetibá` e `Atilio Vivaqua`, que a revisão listava como
evidenciados, não têm evidência** — `dados/` usa `"Santa Maria de Jetibá"` (4×) e nenhuma das 144
páginas traz `Atilio Vivaqua`. Portanto o cadastro nasce com **2** aliases, não 4, e a tabela de
§3.3 registra candidato por candidato o que foi procurado e o que foi achado.

**17 — `municipio_slug` nulo exigindo `municipio_indeterminado`. ATENDIDA pela via positiva que a
revisão sugeriu como opcional.** Em vez de restringir a regra por categoria e manter o booleano,
**eliminei** `municipio_indeterminado` e adotei `municipio_escopo` ∈ {`municipal`,
`intermunicipal`, `estadual`, `federal`, `indeterminado`}, sempre presente (§6.7). Um campo só,
positivo, e `null` deixa de significar duas coisas. As checagens de §9.4 são por categoria, como
pedido: `ato_diario` com slug nulo exige `municipio_escopo == "indeterminado"`; `oportunidade`
estadual grava `estadual` e passa; `municipio_confianca` fora de {alta, baixa, null} → erro.

**18 — As "8 URLs verificadas" incluem câmara e URL de secretaria. ATENDIDA integralmente.**
Conferi as 9 fontes com `esfera: "municipal"`. §3.2 passa a reaproveitar como `url_prefeitura`
apenas `tipo == "oficial"` + `esfera == "municipal"` + `id` começando com `prefeitura-` + host
institucional: **6** municípios. `camara-aracruz` vai para `orgaos_vinculados[].url`;
`prefeitura-castelo` (host `educacao.castelo.es.gov.br`) entra em `fontes[]` com `url_prefeitura`
sondada à parte ou `null` + pendência.

**19 — `descobertas/**` no push contradiz a justificativa do `README.md`. ATENDIDA, opção (a).**
§10.1 adota `push.paths = dados/**, fontes/**, ferramentas/**, .github/workflows/monitoramento.yml`,
**sem** `descobertas/**` nem `README.md`, com a razão escrita: ambos são escritos pelo bot no
mesmo commit único (`git add -A README.md email/ relatorios/ dados/ historico/ descobertas/`) e
ambos já passaram pelo passo "Revalidar depois das alteracoes" antes do commit; revalidá-los no
push disparado por esse commit duplica execução sem acrescentar cobertura. `README.md` permanece
no `pull_request`, para o caso de edição humana.

**20 — Título e corpo da issue não especificados. ATENDIDA integralmente.** §7.5 traz a
composição do título no shell (concatenando as três partes, com `${partes:-sem novidade}` para o
caso degenerado) e manda trocar a primeira linha de `monta_relatorio_md()` por frase condicional
que cite os três motivos, **preservando** o aviso "pistas não conferidas".

### NIT

**21 — `ioes-busca` com `esfera: "municipal"`. ATENDIDA pela primeira opção da revisão.** Duas
fontes: `ioes-busca-dio` (`esfera: "estadual"`, com `observacao` dizendo que o índice inclui o
caderno dos municípios) e `ioes-busca-dom` (`esfera: "municipal"`), ambas em `FONTES` (§6.3). A
escolha não é só cosmética: ela resolve a finding 10 pela raiz e elimina `escopos_com_falha`.

**22 — `resolver_municipio()` sem índice nem memoização. ATENDIDA integralmente.** §5.1:
`resolver_municipio(texto, indice=None)` e `indice_municipios()` com
`functools.lru_cache(maxsize=1)`, com comentário explicando o porquê (53 chamadas no validador,
até 1000 no coletor) e menção explícita a `cache_clear()` para os testes.

**23 — Testes só no job `validar`; lista esperada circular. ATENDIDA integralmente.** §10.3 põe o
passo de testes **nos dois** jobs (em `validar`, e em `atualizar` antes da revalidação), com a
razão (`validar` não roda no agendado, que é o que escreve). §16 declara que a lista esperada de
slugs é um **literal no arquivo de teste** — dupla contabilidade deliberada e comentada.

**24 — `suplemento` não é indicador de suplemento. ATENDIDA integralmente.** Confirmei:
`"Edição 3099"`, `"Edição 26821"`. §6.2 corrige a descrição e grava `edicao` extraída por
`re.search(r"(\d[\d\.]*)$", suplemento)`; §15.17 registra o caso.

**25 — Cabeçalhos, cookies e cortesia não especificados. ATENDIDA integralmente.** §6.4 declara
`_ler_bytes()` próprio, **sem** cookiejar (o buscador não exige sessão), com o `User-Agent` do
projeto, `Accept-Encoding: identity` + `gzip.decompress()` condicional, e `time.sleep(0.2)` entre
páginas por cortesia; `time` consta de §2 e o orçamento de §6.4 inclui a pausa.

**26 — `--conferir-ibge`/`--sem-conferir-ibge` sem `dest`/default. ATENDIDA integralmente.** §7.3
traz as duas linhas com `dest="conferir_ibge"` e `default=True`, e as duas aparecem na tabela de
argumentos de §13.3, junto com `--autoteste-ioes`.

### Resumo das divergências deliberadas

| Finding | Proposta da revisão | O que este design faz | Evidência |
| ------- | ------------------- | --------------------- | --------- |
| 2 (ponto 2) | remover `/es` e `- es` das marcas de contexto | aceita `[/-] es` **adjacente** (≤6 caracteres); remove só o raio de 80 e `estado do espirito santo` | 41 vs 35 municípios em confiança alta; Vitória com 0 nas duas políticas |
| 2 (ponto 3) | marcar título de seção do caderno como alta confiança | não implementa | Nova Venécia já fica em alta (14, 2º lugar) com a limpeza + adjacência |
| 3 | fallback de bloco por cabeçalho de órgão | não implementa; página sem `protocolo` é bloco único | 50/144 páginas sem `protocolo`, nenhuma com >1 município **e** >1 edital |
| 3 | faixa de ano `[ano-3, ano+1]` | `[ano-4, ano+1]` | ato de 2026 nomeando candidato de `concurso publico 01/2022` |
| 16 (a) | cadastrar 4 aliases evidenciados | cadastra **2** | `Santa Maria do Jetibá` e `Atilio Vivaqua` não aparecem em `dados/`, `fontes.json` nem nas 144 páginas |
| 17 | restringir a regra por categoria, mantendo o booleano | elimina `municipio_indeterminado`, adota `municipio_escopo` | evita que `null` signifique duas coisas; vocabulário positivo fechado |
| 10 / 21 | uma fonte com `diagnostico`, mais `escopos_com_falha` | duas fontes por escopo via `functools.partial`; `escopos_com_falha` deixa de existir | degradação graciosa e `suspeita_extracao_vazia` por escopo, de graça, pelo laço existente |

E uma correção que **nem o design nem a revisão** tinham visto: sem a poda por prefixo de tokens,
os padrões de menção corrigidos pela finding 1 produzem **7 de 7 capturas falso positivas**
(§7.2). O requisito "detectar município não mapeado" só funciona com as duas peças juntas.

---

## Anexo C — respostas às 20 findings do segundo passe

Veredito recebido: `CHANGES_REQUESTED` (4 HIGH, 10 MEDIUM, 6 NIT). **Todas as 20 foram
endereçadas.** Nenhuma foi mandada para backlog e nenhuma foi ignorada. Confirmei cada diagnóstico
contra o código antes de corrigir; em dois casos (10 e 14) a correção adotada é mais ampla que a
proposta, e em um (10) a revisão oferecia duas alternativas e este documento escolhe uma
explicitamente.

### HIGH

**1 — Achado de diário entra em `novos`, e por isso na issue e no `novos=`. ATENDIDA
integralmente.** Confirmei no código o `novos.append(achado)` para todo achado inédito sem registro
casado. Adotados os três itens do fix: filtro `registro is None and categoria == "oportunidade"`
(§6.10); `atos_novos` contado à parte e publicado como `atos_diario_novos=`, exibido em **linha de
resumo** da issue e nunca na tabela de oportunidades (§6.10, §7.5); e `primeira_vez=` como quarta
parte do título (§7.5) e quarta cláusula da condição da issue (§10.2). Registrei explicitamente que
`atos_diario_novos` **não** entra na condição da issue — ato de diário é rotina diária, e abrir
issue por isso daria uma issue por dia para sempre. O furo que a revisão apontou de passagem — "um
dia cuja única novidade seja Sooretama não abriria issue" — está fechado pela cláusula
`primeira_vez`.

**2 — Campos `municipio_*` não especificados para as fontes antigas, mas obrigatórios no validador.
ATENDIDA integralmente, e virou a mudança estrutural do passe.** Adotei o ponto único de
normalização em `main()` com a tabela de regras completa (§6.10, `normalizar_achado()`), incluindo a
declaração de que **achado de `oportunidade` nunca conta para a cobertura** (confiança `baixa` por
construção, porque portal de terceiro não é evidência de ato). Dois acréscimos além do fix: (i)
`setdefault` em vez de atribuição, com comentário dizendo por quê — a resolução do coletor de
diário vem de evidência de texto e é mais forte que a daqui; (ii) §9.4 ganha `categoria ==
"oportunidade"` com `municipio_confianca == "alta"` → **erro**, para que a invariante "oportunidade
não vira cobertura" seja imposta por verificação e não só por convenção. §6.8 passou a listar
`coletar.main()` como o **quarto** consumidor, que era a omissão de origem.

**3 — A migração de §6.9 não resolve o erro por achado no arquivo já commitado. ATENDIDA
integralmente, com as duas medidas.** Reconfirmei o arquivo versionado (8 chaves de topo, 37
achados, 0 com `categoria`, 19 de `selecao-es` + 18 de `concursosnobrasil-es`) e que o job `validar`
não passa por `coletar.py`. Adotadas **(a)** tolerância versionada por achado, com fronteira em
`cadastro.ibge_consultado_em` — ausente → aviso, presente e fora do vocabulário → erro sempre; e
**(b)** `--migrar-descobertas` em `coletar.py`, sem rede e idempotente, com o arquivo migrado
commitado junto e declarado na tabela de §17 como linha própria. As duas, pela razão que a revisão
deu: (a) protege contra arquivo antigo reaparecendo depois, (b) deixa o repositório limpo agora.
Acrescentei o comportamento de erro de `--migrar-descobertas` sobre JSON inválido (§12): **fatal**,
porque regravar em cima de JSON corrompido perderia o original.

**4 — `descobertas.json` cresce sem limite. ATENDIDA integralmente.** Confirmei que a única poda
depende de `inscricoes.fim` e que `ato_diario` o tem `null` por decisão de §6.7, de modo que o laço
de preservação reanexaria para sempre. Adotados `RETENCAO_ATO_DIARIO_DIAS = 90`,
`--retencao-atos-dias` com teto 365, descarte por `data_publicacao_ato` com queda para
`ultima_deteccao`, `descartados_por_retencao` exposto no resumo, no `--json` e em `bloco_coleta()`,
e o aviso de `len(achados) > 5000` em §9.4 (§6.9.1). Declarei explicitamente que a retenção **não**
se aplica a `oportunidade`, onde a poda por prazo já é a regra semanticamente correta, e inclui o
caso na matriz de erros de §12 marcado como "não é falha" — para que ninguém o trate como anomalia.

### MEDIUM

**5 — Tipo do índice inconsistente; `collections` fora da lista. ATENDIDA integralmente.** §5.1 fixa
`IndiceMunicipios = collections.namedtuple(...)`, com o comentário explicando que a imutabilidade
existe por causa do `lru_cache` (dict memoizado é devolvido por referência e um chamador
corromperia o índice de todos). Acesso por atributo em todo o documento. `collections` acrescentado
a §2, com nota de que o snippet do passe anterior era inválido sob a própria restrição. Acrescentei
dois campos que as findings 14 e 5 juntas exigem (`padroes_orgaos`, `orgaos_por_id`) e um teste que
assere `AttributeError` na tentativa de escrita (§16).

**6 — `vistos_pela_primeira_vez` não tem fonte de estado. ATENDIDA integralmente.** Assinatura
corrigida para `cobertura(indice, registros, achados, slugs_com_sinal_antes, referencia)` — o
quinto parâmetro é consequência da finding 7 e está justificado no docstring. `slugs_com_sinal`
(lista ordenada) acrescentado ao bloco de §7.4 e lido do `bruto` de `carregar_anterior()`, com
`set()` quando a chave não existe. §9.4 ganha a checagem de subconjunto como **erro**, mais
`slugs_com_sinal` ordenado e com slugs existentes. Registrei por que **não** usar o
`cobertura_vistos` do e-mail (é estado do envio; tornaria a métrica dependente de ter havido
e-mail) e o que acontece na primeira execução (todos entram; o anúncio é controlado por
`gerar_email`, §7.4, §15.34).

**7 — `com_achado_na_janela` calculado sobre a lista final. ATENDIDA integralmente.** Definido em
§7.4 como `municipio_confianca == "alta"` **e** `ultima_deteccao == gerado_em`, com
`com_achado_acumulado` para o número cumulativo. A linha de §14 passou a dizer "confiança alta **e**
detectado nesta execução". Decidi também **qual consumidor usa qual**, que o fix não cobria: o
README usa o acumulado (histórico é a informação útil em "Ato detectado", §11.1) e a issue/e-mail
usam a janela. §9.4 ganha `com_achado_na_janela > com_achado_acumulado` → erro.

**8 — Mascarar com espaços faz a marca vazar para o município seguinte. ATENDIDA integralmente.**
Reproduzi as duas medições da revisão antes de corrigir (`vila-velha`/`serra` e `santa-maria-de-
jetiba`/`linhares`, alta indevida com espaço e baixa correta com `\x00`) e os números estão no
documento. Adotados: máscara `"\x00" * len(m.group(0))` com comentário longo explicando o papel do
caractere (§5.2); declaração explícita de que a janela de 45/6 caracteres é lida **no texto
mascarado** (§5.3), que era a segunda metade da ambiguidade; e o caso de teste em §16 como asserção
dupla (`vila-velha` alta **e** `serra` baixa), mais o caso de borda §15.27. Acrescentei a nota de
que o `\x00` não vaza para o dado gravado, porque é a pergunta imediata que o leitor faz.

**9 — O exemplo canônico de §3.1 contradiz §3.2 e §9.2. ATENDIDA integralmente.** As três regras
foram escritas: URL reaproveitada é **normalizada para `scheme://host/`** (o caminho fica em
`fontes[]`); **toda** `url_prefeitura` passa pela sondagem, e reaproveitamento só **escolhe o
candidato** — são 6 requisições na curadoria, nenhuma no CI; e o exemplo de §3.1 foi reescrito.
Em vez de escolher entre as duas opções que a revisão ofereceu, mantive **os dois** exemplos:
Cachoeiro com `url_prefeitura: null` + `nao_responde` (o caso que está nos dois conjuntos, onde a
sondagem vence) e Vitória com URL preenchida e `pendencias_verificacao: []` (o caso simples). O
exemplo errado existia porque faltava um caso de contraste.

**10 — §4 proíbe creditar o município-sede, §7.4 credita por via de `dados/`. ATENDIDA; escolhi a
primeira alternativa e corrigi um fato errado nos dois documentos.** A revisão oferecia duas saídas;
adotei a que preserva a decisão de §4: registro com `esfera == "intermunicipal"` **não credita
cobertura**, excluído de `com_registro_curado` e contado em
`registros_intermunicipais_sem_atribuicao` (§7.4), com aviso em `valida_escopo()` apontando para
`orgaos_vinculados` (§9.3). §4 ganhou um parágrafo dizendo isso explicitamente, inclusive por que a
alternativa ("o dado curado é autoritativo") foi rejeitada: o campo `municipio` desses registros
responde "onde fica a sede", pergunta diferente de "qual município tem jurisdição".
**Correção factual:** a revisão diz "os quatro registros `ps-aries-es-*` têm `municipio: 'Vitória'`"
e o design dizia o mesmo. Medi: há **4 registros intermunicipais no total**, dos quais **2** são
ARIES (`municipio: "Vitória"`); os outros são `ps-cim-polinorte-es-2026` (`"Diversos (ES) - Linhares
e região"`, que §9.3 aceita sem resolver) e `ps-consorcio-caparao-es-2026` (`"Divino de São
Lourenço"`). O caso que de fato creditava um município real por via indevida é o do Consórcio
Caparaó, não os da ARIES — e a correção o cobre.

**11 — `casar()` aplicado a achado de diário produz `no_repositorio` falso. ATENDIDA
integralmente.** Confirmei no código: `tokens_identidade("Prefeitura de Serra") == {"serra"}` e
`_coberto("serra", {"serrana"}) is True`. Adotado `casar_estrito()` (URL igual; número de edital
coincidente + tokens) com despacho por categoria em `main()`, documentado em §6.7 com o comentário
longo explicando a consequência real — ato de nomeação marcado como "já no repositório" sai da fila
de curadoria sem ter sido conferido, que é o pior desfecho possível para uma quarentena. §15.14 foi
reescrito (afirmava o contrário), §14 ganhou a linha do invariante, e §16 traz a asserção **dupla**
que a revisão pediu, mais uma que ela não pediu: o mesmo achado passado a `casar()` **casaria** — sem
isso, o teste passaria mesmo se alguém apagasse a distinção.

**12 — O campo `municipio` do achado de diário não tem valor definido. ATENDIDA integralmente.**
§6.7 ganhou as duas linhas: `municipio` = `nome` oficial do cadastro quando o slug resolve (nunca o
trecho normalizado), `comum.AUSENTE` quando não resolve; `municipio_codigo_ibge` = `codigo_ibge` do
cadastro ou `null`. Expandi a tabela para listar **todos** os seis campos de município de uma vez,
em vez de remeter a outras seções, e registrei a razão de usar o nome oficial: é o que mantém
`"Vitória"` legível em `gerar_relatorio`/`gerar_email` e é a mesma grafia de `dados/`.

**13 — `ocorrencias` é ambíguo e o estágio dos `PADROES_MENCAO` não está fixado. ATENDIDA
integralmente.** Gravados os três campos com papéis distintos numa tabela (`ocorrencias` =
casamentos, informativo; `paginas_distintas` = **o que o filtro usa**; `com_marca_uf` = segundo termo
da disjunção), filtro reescrito como `paginas_distintas >= 2 or com_marca_uf`, e o estágio declarado:
**por página**, após a limpeza de boilerplate e antes da segmentação em blocos, com a justificativa
(o objetivo é descobrir que nomes o diário cita, não associá-los a um ato). `exemplos` limitado a 3
trechos de páginas distintas. §9.4 ganhou `paginas_distintas > ocorrencias` → erro e
`len(exemplos) > 3` → erro, para que a troca de contadores seja detectada e não apenas documentada.

**14 — Não existe mecanismo de casamento de órgão vinculado, e a lista inicial não é enumerada.
ATENDIDA integralmente, nas duas partes.** (1) §5.2 passou a ter **duas passadas**, com a de órgãos
**antes** da de municípios e mascarando igual, e a nova §5.2.1 especifica `padroes_orgaos` (nome e
sigla por `chave_nome()`, longest-first, sigla < 3 caracteres ignorada), a herança de
`municipios_slugs` por aridade numa tabela (1 → slug com alta; 0 → `intermunicipal` ou
`indeterminado` conforme a esfera; N → `intermunicipal`), e a declaração de que **nome de órgão
casado vale confiança alta** porque o nome do órgão *é* a evidência. Acrescentei um detalhe que o
fix não mencionava e que a ordem das passadas resolve: consumir "SAAE de Aracruz" como órgão evita
contar "aracruz" de novo como menção solta. (2) §4.1 enumera as **8** entradas (as 7 da revisão mais
`camara-cachoeiro-itapemirim`, que tem registro em `dados/`) com `id`, `nome`, `sigla`, `natureza`,
`esfera`, `municipios_slugs`, **evidência** e pendências — todas derivadas de registro, fonte ou ato
observado, nenhuma imaginada. §15.28 registra o caso IPC.

### NIT

**15 — `validar.py` importaria `coletar.py` sem que isso esteja declarado. ATENDIDA.** Escolhi o
**import tardio** dentro de `valida_catalogo_fontes()`, com comentário explicando a escolha, e
descartei `comum.FONTES_COLETAVEIS` pela razão escrita: duplicar a lista criaria duas fontes da
verdade que divergem no dia em que alguém acrescentar uma fonte. A dependência `validar → coletar`
está declarada na linha de `validar.py` em §17.

**16 — Despacho por prefixo de string em `main()`. ATENDIDA integralmente.**
`FONTES_COM_DIAGNOSTICO = {"ioes-busca-dio", "ioes-busca-dom"}` com teste de pertencimento, e o
`if/else` escrito por extenso em §6.3 (a expressão condicional de uma linha ficava ilegível com
cinco argumentos). Comentário diz por quê: o modo de chamada é contrato da função, não propriedade
do nome dela.

**17 — A justificativa para deixar `descobertas/**` fora do `push` é parcialmente falsa. ATENDIDA
integralmente.** §10.1 adota a razão correta ("conteúdo gerado e já revalidado no passo anterior ao
commit; não há revisão humana a proteger") e **registra o erro anterior** com a verificação que o
desmonta (o commit é único e inclui `dados/`, que permanece em `push.paths`, logo a execução
duplicada acontece de qualquer modo). Mantive o registro de propósito: razão errada que some do
documento volta na próxima revisão.

**18 — A chave inclui o escopo, logo o mesmo edital em DIO e DOM gera dois achados. ATENDIDA pela
primeira opção.** §6.6 declara que a duplicação entre escopos é **aceita**, com a razão: cada achado
aponta para o PDF que contém o ato e esse PDF é por escopo; unificar obrigaria a descartar uma das
URLs ou a inventar um campo de lista que nenhum consumidor lê. Acrescentei o argumento que fecha a
preocupação implícita — a cobertura **não** infla, porque `com_achado_na_janela` conta municípios
distintos e não achados. §15.32 registra o caso.

**19 — Motivo `nao_encontrado` nunca é produzido. ATENDIDA pela segunda opção.** Em vez de remover o
motivo, dei-lhe produtor e documentei os três numa tabela "motivo → quem produz → significado"
(§3.1): `conferir_manual` pela sondagem 403/406/429, `nao_responde` pela sondagem
404/NXDOMAIN/timeout/TLS, e `nao_encontrado` pela curadoria em `diario_oficial_em` sem agregador
identificado e em `municipios_slugs` de órgão intermunicipal sem composição apurada. Mantê-lo foi a
escolha certa porque §4.1 **precisa** dele: as três entradas de consórcio/agência nascem com
`municipios_slugs:nao_encontrado`. A tabela existe porque motivo sem produtor é vocabulário morto —
fica no validador dando impressão de cobertura.

**20 — Interação entre o truncamento e a segmentação não está dita. ATENDIDA integralmente.** §6.5
abre com a ordem das cinco operações numerada (truncar → normalizar → segmentar → limpar → casar),
declara que o truncamento vem **antes** da segmentação e **por que** (a alternativa custa normalizar
a página inteira por ganho marginal), e torna a perda observável: `conteudo_truncado: true` no
achado (§6.7) e `paginas_truncadas` agregado no diagnóstico da fonte, com linha em §12 e caso de
borda §15.33.

### Resumo das divergências e dos acréscimos

| Finding | Proposta da revisão | O que este design faz | Por quê |
| ------- | ------------------- | --------------------- | ------- |
| 2 | ponto único de normalização | adota, **mais** `categoria == "oportunidade"` com confiança `alta` → erro em §9.4 | a invariante "oportunidade não vira cobertura" passa a ser verificada, não só convencionada |
| 7 | definir a regra da janela | adota, **mais** a decisão de qual consumidor usa janela e qual usa acumulado | o fix deixava os três geradores sem regra |
| 10 | duas alternativas | escolhe a primeira (intermunicipal não credita) e **corrige o fato** de "4 registros ARIES" para "4 intermunicipais, 2 ARIES" | preserva a decisão de §4; o registro problemático é o do Consórcio Caparaó |
| 11 | asserção de que não casa | adota, **mais** a asserção de que `casar()` **casaria** | sem o contraste, o teste passa mesmo se a distinção for apagada |
| 14 | 7 entradas de `orgaos_vinculados` | enumera **8** (acrescenta `camara-cachoeiro-itapemirim`) | tem registro em `dados/`, mesma evidência das outras |
| 15 | `comum.FONTES_COLETAVEIS` **ou** import tardio | import tardio | `comum.FONTES_COLETAVEIS` duplicaria a lista e divergiria |
| 19 | remover `nao_encontrado` **ou** dar produtor | dá produtor, com tabela dos três motivos | §4.1 precisa dele para os três órgãos intermunicipais |

---

## Anexo D — respostas às 21 findings do terceiro passe, e à clarificação do usuário

Veredito recebido: `CHANGES_REQUESTED` (2 HIGH, 11 MEDIUM, 8 NIT), com a arquitetura **aprovada**.
**Todas as 13 HIGH+MEDIUM e todas as 8 NIT foram endereçadas**; nenhuma foi mandada para backlog e
nenhuma foi ignorada. Confirmei contra o código, os dados e as funções reais os diagnósticos que
dependiam de medição — e em dois pontos a prescrição foi seguida **com um ajuste medido**, marcado
abaixo e no resumo de divergências.

**Aviso de leitura sobre os Anexos B e C.** Eles registram as respostas aos dois passes anteriores e
ficaram desatualizados em **dois** pontos, de propósito (são histórico, não especificação):

- citam os campos `url_prefeitura` / `url_diario_oficial` / `diario_oficial_em`, que **deixaram de
  existir** neste passe — a clarificação do usuário os substituiu pela lista `canais` (§3.1);
- o Anexo C (finding 20) descreve a ordem do pipeline de texto em **cinco** operações, com a
  segmentação antes da limpeza. Essa ordem foi **substituída** pelos seis estágios de §6.5 (limpeza
  na página, antes da segmentação), que é a única válida.

Os anexos foram mantidos porque documentam *decisões* que continuam valendo (reaproveitar o catálogo
escolhe o candidato e não dispensa a sondagem; 403 não é ausência; motivo de pendência precisa de
produtor declarado; truncamento antes de tudo, com perda observável). Onde citarem nome de campo ou
ordem de estágio, valem §3.1 e §6.5.

### HIGH

**1 — §6.5 e §7.2 especificavam ordens incompatíveis do pipeline, e §6.5 era internamente
incoerente. ATENDIDA integralmente, pela prescrição.** §6.5 passa a ter **seis estágios numerados**,
quatro por página (truncar → `normalizar` → `_limpar_boilerplate` na página → `PADROES_MENCAO` +
`classificar_mencao` na página) e dois por bloco (`_blocos_de_ato` → órgãos → municípios →
pareamento). Removi de §7.2 a frase "antes da segmentação", que passou a ser **consequência** da
ordem e não regra à parte — era a duplicação que fazia as duas seções divergirem. Mantive e
explicitei o argumento que torna (3) antes de (5) seguro: `protocolo \d+` **não** está em
`PADROES_BOILERPLATE`, e nenhum dos cinco padrões de §5.3 consome a palavra seguida de número.
Acréscimos de coerência que a prescrição não pedia: §5.2 ganhou um **estágio 0** dizendo que recebe
o bloco já normalizado e já limpo (e que não refaz nenhuma das duas), e §14 ganhou a linha de
invariante "uma ordem única do pipeline de texto", para que a próxima mudança tenha um dono em vez
de três seções.

**2 — O casamento de texto livre excluía aliases e misturava `normalizar()` com `chave_nome()`.
ATENDIDA integralmente, com um ajuste medido no construtor.** Reproduzi a medição da revisão com as
funções reais: `chave_nome("CIM Polinorte") == "cim polinorte"`, o texto normalizado traz
`cim-polinorte`, e `re.search(r"\bcim polinorte\b", texto)` é **False**. Adotado o desenho prescrito:
`t` fica em `normalizar()`; `_padrao_de_chave()` compila a chave de `chave_nome()`;
`padroes_ordenados` passa a ser `(padrao, slug, origem)` com **uma entrada por nome e uma por
alias**, ordenada por comprimento decrescente de `chave_nome`; `padroes_orgaos` idem, com `origem ∈
{nome, sigla}`. As duas decisões que a revisão mandava tomar aqui estão tomadas: **(a)** alias
casado em texto livre segue a **mesma** regra de confiança de §5.3 (adjacência), sem desconto —
quem credita alta é a marca, não a forma do nome; **(b)** a origem **é gravada no achado**, no campo
novo `municipio_origem` (§6.7), com o vocabulário `{nome, alias, orgao_vinculado, null}` conferido
por §9.4. Deliberadamente **não** acrescentei `municipio_origem` à lista de campos de presença
obrigatória, para não criar um quinto item de tolerância de legado em troca de nada.

*Divergência medida, no separador:* a prescrição dava
`r"[^a-z0-9]+".join(...)`; adotei **`r"[^a-z0-9\x00]+"`**. Razão medida: com `[^a-z0-9]+` a máscara
de §5.2 passa a valer como separador e um nome já consumido vira **ponte** entre dois tokens
distantes. Em `"secretaria de vila, conceicao do castelo, pavao e outros"`, depois de mascarar
`conceicao do castelo`, o padrão de `Vila Pavão` **casa** com `[^a-z0-9]+` e **não** casa com
`[^a-z0-9\x00]+`. Conferi que a tolerância a pontuação não se perde: `cim polinorte`,
`cim-polinorte`, `cim/polinorte` e `cim.polinorte` continuam casando. É a mesma decisão que fez a
máscara ser `\x00` e não espaço, vista do lado do padrão — e está registrada em §5.1, §15.36 e no
teste de §16.

### MEDIUM

**3 — `com_registro_curado = 16` contradizia a definição. ATENDIDA integralmente.** Medi nos 53
registros com as funções reais: **16** nomes oficiais distintos no total, **15** excluindo os
`esfera: "intermunicipal"`; o nome que sai é `Divino de São Lourenço`, presente **somente** em
`ps-consorcio-caparao-es-2026`. O exemplo de §7.4 passa a `15`, a definição ganhou a anotação dos
dois números, §11.1 declara que a linha de Panorama usa `com_registro_curado` (hoje 15), e §16
assere as **duas** metades do caso (fora de `com_registro_curado` **e** +1 em
`registros_intermunicipais_sem_atribuicao`), que era a metade que faltava.

**4 — §9.2 exigia pendência de `url_diario_oficial`, motivo sem produtor. ATENDIDA, e a correção foi
reformulada sobre o esquema novo de canais.** A incoerência diagnosticada é real e a causa também:
validador e vocabulário falavam línguas diferentes. Como a clarificação do usuário substituiu os
três campos escalares pela lista `canais`, a linha prescrita não tinha mais onde existir; a
exigência equivalente, e agora verificável no vocabulário real, é: **nenhum canal de diário
(`diario_oficial_proprio`/`diario_oficial_agregador`) e nenhum item de `pendencias_verificacao` com
campo `canais` → erro**. §3.1 continua como manda a prescrição — quem escreve o motivo é a
curadoria, e a forma existe no dado (`canais:nao_encontrado`). O município curado como §3.1 manda
passa; o caso de §18.2 (sem diário próprio, publicando pelo DOM) passa com **um** canal.

**5 — A sondagem dos 78 não tinha regra de derivação nem dono. ATENDIDA integralmente, nas três
partes.** (1) candidato derivado único `https://www.<slug sem hifens>.es.gov.br/`, com a observação
de que ele é palpite e a sondagem decide (Cachoeiro é o contraexemplo); (2) fonte catalogada
elegível **substitui** o derivado — e, com `canais`, o caminho da URL **deixa de ser descartado**:
URL de raiz vira `portal_prefeitura`, URL com caminho vira `secao_concursos`, de modo que
`https://www.cachoeiro.es.gov.br/editais/` e `https://educacao.castelo.es.gov.br/processos-seletivos`
entram inteiras, cada uma no seu `tipo`; (3) `ferramentas/sondar_prefeituras.py`, novo, uso único,
declarado em §17, **não** chamado pelo workflow e **não** escrevendo no cadastro, imprimindo TSV para
a curadoria. Só `https://`; falha de TLS cai em `nao_responde`. Acrescentei o que a prescrição não
cobria e o esquema novo tornou visível: o canal de **diário** não sai de sondagem nenhuma, sai da
coleta — 41 dos 78 ficam `confirmado` por ato observado, sem uma requisição extra.

**6 — A semântica de `resolver_municipio()` não estava definida, e §6.10 a usava num texto para o
qual ela não funciona. ATENDIDA integralmente.** Duas assinaturas escritas em §5.1:
`resolver_municipio()` = consulta **exata** por `chave_nome()`, devolvendo `(slug, origem)` com
`origem ∈ {nome, alias, orgao_vinculado}` — o terceiro valor é o caso, antes indefinido, em que a
chave casada é nome de órgão injetado em `por_chave_nome`; e `resolver_municipio_em_texto()` =
passada longest-first de §5.2, devolvendo `(slug, origem)` só quando resolve para **um** município e
`(None, None)` quando resolve zero **ou mais de um** (ambiguidade nunca desempatada por palpite).
§6.10 passa a usar a segunda, com `municipio` e `orgao` **concatenados**, e ganhou a linha de tabela
da ambiguidade; §9.3 usa a primeira, explicitando por quê (campo curado e curto: casamento parcial
esconderia erro de digitação) e ganhou o aviso de `origem == "orgao_vinculado"`. §16 troca o teste
que passava trivialmente por um que usa achado real (`orgao: "Prefeitura de Anchieta"`) e falha se
alguém voltar à consulta exata.

**7 — `vistos_pela_primeira_vez` reanunciava o mesmo município. ATENDIDA integralmente.** Estado
monotônico, exatamente como prescrito: `slugs_com_sinal` (retrato de hoje),
`slugs_com_sinal_historico = ordenado(historico_antes ∪ slugs_com_sinal)`, e
`vistos_pela_primeira_vez = ordenado(slugs_com_sinal − historico_antes)`. `cobertura()` passa a
receber `slugs_com_sinal_historico_antes` (docstring de §6.3 reescrita), §9.4 troca a checagem única
por **duas** (`vistos ⊆ slugs_com_sinal` e `slugs_com_sinal ⊆ slugs_com_sinal_historico`), §15.35
registra o caso do município intermitente e §16 traz o teste de duas execuções que trava o
reanúncio. Acréscimo de robustez: a leitura tolera arquivo de versão intermediária caindo para
`slugs_com_sinal` quando o histórico não existe.

**8 — A coluna "Ato detectado" exigia lista que o bloco não publicava. ATENDIDA integralmente.**
`slugs_com_achado_acumulado` (ordenada, `municipio_confianca == "alta"`, **sem** condição de data)
acrescentada ao bloco de §7.4; §11.1 passa a usá-la; §9.4 ganha
`com_achado_acumulado == len(slugs_com_achado_acumulado)` → erro. Registrei no documento a razão de
não derivar no gerador, com a linha conferida: `carregar_descobertas()` filtra `no_repositorio` e
`ausente_na_fonte` (linha 186), que é exatamente o ato antigo que carrega o histórico.

**9 — A fronteira de legado com `<` deixava de fora os 2 achados mais novos. ATENDIDA
integralmente.** Medi o arquivo versionado: 37 achados, `primeira_deteccao` em 09-23 (18), 09-25 (3),
09-28 (9), 09-29 (2), 09-30 (3) e **10-01 (2)** — e `ibge_consultado_em` do exemplo é `2026-10-01`.
Trocado para `<=` em §6.9 e em §9.4, com o comentário explicando a medição e o motivo (o cadastro é
commitado no mesmo dia da coleta anterior). §16 passa a cobrir os **três** casos: anterior → aviso,
igual → aviso, posterior → erro.

**10 — "218 hits/dia" era erro de unidade. ATENDIDA integralmente.** §6.4 passa a dizer
"**218 hits na janela de 7 dias** (≈ 31 por dia)" e explica que os tetos são por execução e por
fonte, logo continuam dimensionados pelos 218. §6.9.1 refaz a conta por extenso: ~31 inéditos/dia ×
90 dias ≈ **2,8 mil achados** em regime, contra o aviso de 5.000 de §9.4 — **~45% de folga** —, e
registra que, com o número errado, o aviso dispararia para sempre e a conclusão seria que 90 dias é
inviável. O texto de "centenas de entradas por dia" virou "algumas dezenas".

**11 — A fusão de `municipios_nao_mapeados` não estava especificada. ATENDIDA integralmente, pela
prescrição.** §7.2 ganhou o bloco com as sete regras: chave = `nome_detectado` (já podado e
consolidado); `ocorrencias` e `paginas_distintas` **acumulados**; `com_marca_uf` por OR;
`primeira_deteccao` do anterior; `ultima_deteccao` desta execução; `exemplos` até 3 de páginas
distintas preferindo os recentes; filtro aplicado aos **acumulados**; remoção por
`ultima_deteccao < referencia - (--janela-ioes-dias * 4)`. Acrescentei o caso que justifica o
acumulado (candidato 1×/dia sem `/ES` nunca seria reportado, §15.38) e a consequência aceita
explicitamente: como as janelas se sobrepõem, o acumulado é medida de **insistência** e não
inventário de páginas.

**12 — A janela de contexto não tinha momento de leitura definido, e `re.sub` não permitia lê-la.
ATENDIDA integralmente.** O snippet de §5.2 passa a ser o laço com `finditer`: coletar todas as
ocorrências do padrão, avaliar `antes`/`depois` e a confiança de cada uma, e **só então** mascarar o
padrão inteiro — com o comentário dizendo por que não intercalar. `MARCA_DEPOIS.match` (e não
`search`) está escrito e justificado como o que materializa a adjacência. §5.3 ganhou o parágrafo
que fixa o momento ("todas as ocorrências do padrão corrente, antes de mascarar o padrão corrente")
e registra que foi assim que os dois resultados medidos se reproduzem.

**13 — Faltava a regra do README quando `cobertura_municipios` não existe. ATENDIDA integralmente.**
§11.1 ganhou o parágrafo do estado do PR: Panorama com `0`, `Ato detectado` `—` nas 78 linhas,
`Registros curados` e `Canal principal` corretos porque vêm de `dados/` e do cadastro, bloco
determinístico, e é esse o README que o PR commita. §15.39 registra o caso e §16 traz o teste com
`--check` estável entre duas gerações.

### NIT — todas as 8 aplicadas

**14 — `max_tokens_nome` medido só nos nomes de município. APLICADA, com dois tetos em vez de um.**
Passa a ser `max(len(k.split()) for k in por_chave_nome)`; medi o valor real e é **8**
(`servico autonomo de agua e esgoto de aracruz`), não 7 — o 7 da revisão é a chave do IPC, que é a
segunda mais longa. Com isso as chaves de órgão de 5 a 8 tokens tornam-se alcançáveis pela poda.
*Acréscimo:* o teto do **candidato gravado** ficou separado, `MAX_TOKENS_CANDIDATO = 4` (maior nome
oficial de município), porque é ele que mantém as cadeias exibidas na issue iguais às medidas neste
documento (`'que trata esta lei'`, `'santa maria ate a'`); usar 8 nos dois papéis mudaria os
exemplos medidos sem ganho. Os dois números estão comentados com o papel de cada um.

**15 — `orgaos_vinculados` validado com menos severidade que `municipios`. APLICADA integralmente.**
§9.2 ganhou as quatro linhas, com o conjunto de chaves permitidas escrito por extenso
(`id,nome,sigla,natureza,esfera,municipios_slugs,url,fontes,pendencias_verificacao,verificado_em`),
`url == null` exigindo `url:nao_encontrado`, `fontes[]` referenciando `id` existente e
`verificado_em` presente e não futura — mais a nota de por que a assimetria importa (é a mesma que
deixou 12 fontes sem `esfera` passar).

**16 — `monta_relatorio_md()` estendida sem assinatura nova. APLICADA, pela opção do dict.**
`monta_relatorio_md(novos, relatorio_fontes, referencia, contexto)`, com `contexto` contendo
`cobertura`, `nao_mapeados`, `reconciliacao`, `atos_novos` e `truncado`, chave ausente = seção
ausente. Escolhi o dict e não os cinco parâmetros posicionais porque a função já tem três e cada
seção condicional futura faria a assinatura crescer de novo. Declarada em §7.5 e na linha de
`coletar.py` em §17.

**17 — O `[ cond ] && partes=...` aborta sob `set -e`. APLICADA.** As quatro partes do título viraram
`if ... then ... fi`, com comentário dizendo por que (outros passos do mesmo workflow usam
`set -euo pipefail`, e o padrão é copiado com facilidade).

**18 — `truncado` sem regra de agregação. APLICADA.** §7.5: `truncado = 1` se **qualquer**
diagnóstico de fonte tiver `truncado` ou `limite_achados_atingido`; 0 caso contrário — com a nota de
que o volume está no DOM, logo esconder o DOM atrás do DIO seria o caso provável.

**19 — Duas listas de campos para a mesma invariante. APLICADA.** `--migrar-descobertas` passa a ser
definido como "aplica `normalizar_achado(achado, indice)` a cada achado e regrava", em §6.9 e na
tabela de §13.3; §14 registra que o ponto único serve ao coletor **e** à migração, e §16 compara as
chaves do achado migrado com as de um achado novo normalizado, de modo que acrescentar campo em um
só lugar falha o teste.

**20 — O `except` de `main()` não cobre `KeyError`/`TypeError`. APLICADA pela primeira opção.** §12
ganhou o parágrafo de contrato: `_achados_de_resposta()` **não propaga** `KeyError`/`TypeError`, todo
acesso a campo de terceiro usa `.get()` com a validação de §13.1, e o teste de §16 passa envelopes
malformados (`_source: null`, `hits.hits: "texto"`) exigindo `[]` e nenhuma exceção. Preferi o
contrato à ampliação da tupla do `except` porque ampliar a tupla esconderia bug de parser do
**nosso** código como se fosse indisponibilidade de terceiro.

**21 — Dois blocos da mesma página colidem na chave e o descarte depende de `main()`. APLICADA.**
§6.6 declara que `coletar_ioes()` **deduplica por chave antes de devolver**, aplicando a ordenação
explícita da própria seção, e que o `vistos` de `main()` segue existindo para colisão **entre**
fontes — mas não decide mais este caso.

### Clarificação do usuário — o eixo do cadastro é o canal de publicação

Resposta do usuário à ambiguidade sobre o alcance do cadastro, verbatim: *"São as plataformas que
cada município usa pra mandar informações a respeito de emprego."* Mudanças aplicadas, todas de
especificação de dado — o pipeline de texto (§5, §6) **não** foi reaberto:

1. **§3.1 reescrita.** A entrada de município passa a ter uma lista **`canais`** (N por município),
   substituindo `url_prefeitura` + `url_diario_oficial` + `diario_oficial_em` + `fontes[]`. §3.1.1
   fixa a forma do canal (`tipo`, `precedencia`, `url`, `fonte_id`, `estado`, `evidencia`,
   `verificado_em`), o vocabulário fechado de `tipo` (`diario_oficial_proprio`,
   `diario_oficial_agregador`, `portal_prefeitura`, `secao_concursos`, `plataforma_inscricao`,
   `banca`) e a **regra de prevalência**: `precedencia: 1` é o canal de diário quando existir, porque
   é o que tem fé pública; os demais recebem 2, 3, … na ordem de utilidade para a curadoria.
2. **§4 reorientada.** Câmara, autarquia e consórcio **não** são entradas de primeira classe nem têm
   `canais`: `orgaos_vinculados` existe para (i) alimentar `padroes_orgaos` no casamento de texto e
   (ii) atribuir o ato ao município pela aridade de `municipios_slugs`. Está escrito que os **4
   registros intermunicipais versionados continuam válidos** e que nada neles muda.
3. **"Nunca inventar URL" ficou mais forte, não mais fraco.** Todo canal carrega `evidencia`
   obrigatória (de onde veio) e `estado`; `confirmado` sem `verificado_em` é **erro** (§9.2). A
   assimetria do resultado de sondagem está escrita: candidato **derivado** que não responde não
   entra; candidato **catalogado** que não responde entra como `pendente` — apagar dado de
   procedência conhecida perderia informação real, inventar host não.
4. **Publicar só pelo DOM/AMUNES é o caso correto e comum**, dito em §3.1, §11.1 (coluna
   `Canal principal` em vez de "Fonte própria"), §15.37 e §18.2. Lacuna passa a ter definição
   própria e verificável: município **sem nenhum canal confirmado** (aviso de §9.2) ou com
   `canais:nao_encontrado`.
5. **Findings 4 e 5 foram resolvidas dentro desse esquema**, e não isoladamente: o vocabulário de
   pendência de §3.1 (`canais:conferir_manual`, `canais:nao_responde`, `canais:nao_encontrado`,
   `municipios_slugs:nao_encontrado`, `url:nao_encontrado`) é **exatamente** o que §9.2 exige, cada
   motivo com produtor declarado; e a derivação de candidato + `sondar_prefeituras.py` passaram a
   produzir canais tipados, com o caminho da URL preservado.

### Resumo das divergências e dos acréscimos deste passe

| Finding | Prescrição | O que este design faz | Por quê (medido) |
| ------- | ---------- | --------------------- | ---------------- |
| 2 | separador `[^a-z0-9]+` no `_padrao_de_chave` | **`[^a-z0-9\x00]+`** | com `[^a-z0-9]+`, a máscara vira separador: em `"secretaria de vila, conceicao do castelo, pavao e outros"`, `Vila Pavão` **casa** depois de consumir `conceicao do castelo`; com `\x00` excluído, não casa — e as quatro formas de `cim polinorte` continuam casando |
| 2 | gravar `origem` **ou** ignorá-la explicitamente | grava `municipio_origem`, **sem** entrar na exigência de presença | torna a cobertura auditável e o alias rastreável; ficar fora da presença obrigatória evita um quinto item de tolerância de legado |
| 4 | reescrever a linha de §9.2 sobre `url_diario_oficial` | exigência equivalente sobre `canais` + `canais:nao_encontrado` | o campo deixou de existir com a clarificação do usuário; a incoerência diagnosticada (validador exigindo motivo sem produtor) está fechada do mesmo jeito |
| 5 | normalizar a URL catalogada para `scheme://host/` | mantém o **caminho**, tipando o canal (`portal_prefeitura` vs `secao_concursos`) | com `canais` não é mais preciso escolher: `/editais/` e `/processos-seletivos` são a informação útil, e eram descartadas por falta de campo |
| 14 | um único `max_tokens_nome` | `max_tokens_nome` calculado (**8**, não 7) para a busca **+** `MAX_TOKENS_CANDIDATO = 4` para o nome gravado | medi 8 em `servico autonomo de agua e esgoto de aracruz`; usar 8 também no candidato mudaria as cadeias medidas exibidas na issue, sem ganho |
| 20 | contrato em §12 **ou** ampliar o `except` | contrato em §12, com teste | ampliar a tupla esconderia bug de parser nosso como indisponibilidade de terceiro |
