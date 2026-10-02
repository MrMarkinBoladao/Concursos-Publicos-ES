# Review do design — Cobertura dos 78 municípios do ES (terceiro passe)

Documento revisado: `.agents/design-cobertura-municipios.md` (2.884 linhas).
Revisão feita **sem o contexto que produziu o design**: tudo que o documento afirma sobre o
código, sobre os dados e sobre as APIs foi conferido na fonte. O sandbox tem rede, então os
contratos do IOES e do IBGE foram exercitados de verdade, e não aceitos pela descrição.

**Veredito: CHANGES_REQUESTED — 2 HIGH, 11 MEDIUM, 8 NIT.**

O documento é, na maior parte, implementável e honesto: 100% das afirmações factuais que
testei sobre o repositório e sobre as duas APIs se reproduziram (ver *Suposições verificadas*),
incluindo as medições delicadas (máscara `\x00`, boilerplate de assinatura, padrões de menção,
volumes por escopo×frase). Os bloqueios estão concentrados em **dois pontos onde duas seções se
contradizem** (ordem do pipeline de texto; forma das chaves de casamento) e num conjunto de
**contadores/semânticas que o próprio documento define de um jeito e exemplifica de outro**.

Checagem das sete perguntas do pedido:

| Item | Situação |
| ---- | -------- |
| (a) cadastro canônico justificado | **OK.** §3 compara `dados/` vs `fontes/` com razões lidas do código (`comum.DIRETORIOS`, `validar.valida_diretorio`) — conferi as duas. |
| (b) slug/alias cobre os nomes difíceis | **Parcial.** Os 6 nomes normalizam corretamente (verificado com a função real); mas §5.2 não inclui aliases no casamento de texto livre → finding 2 (HIGH). |
| (c) coletor realista para 78 | **OK.** Agregador + 80 requisições, degradação graciosa reaproveitando o laço existente. Volumes confirmados contra a API. |
| (d) detecção de não mapeado concreta | **Parcial.** Padrões, poda e issue estão concretos e reproduzíveis; falta a regra de **fusão entre execuções** → finding 11. |
| (e) REGRA DE ALCANCE explícita | **OK.** §4/§4.1 decidem duas listas, aridade por natureza e "intermunicipal não credita", com as 8 entradas enumeradas e evidenciadas. |
| (f) `esfera` + checagens do validador | **Quase OK.** Decisão sólida e verificável; uma checagem de §9.2 contradiz o vocabulário de §3.1 → finding 4. |
| (g) Python 3.9 + stdlib-only | **OK.** Nenhum snippet usa `match`, `X \| Y` em anotação avaliada, `dict \| dict` ou dependência externa; `collections`/`gzip`/`socket`/`time`/`functools` estão declarados em §2. |

---

## Findings

### HIGH

**1. §6.5 e §7.2 especificam ordens incompatíveis do pipeline de texto, e §6.5 é internamente incoerente.**

§6.5 fixa a ordem como `truncar → normalizar → segmentar em blocos → (por bloco) limpar
boilerplate → (por bloco) casar`, e reforça: *"A segmentação roda sobre o texto normalizado e
**antes** da limpeza de boilerplate"*. §7.2 fixa o contrário para a mesma página: os
`PADROES_MENCAO` rodam *"**depois** da limpeza de boilerplate e **antes** da segmentação em
blocos"*. Nessa ordem de §6.5 **não existe** um estágio "página limpa", logo §7.2 é
inexequível. Pior, o passo 5 de §6.5 é "por bloco: casar ..., **rodando `PADROES_MENCAO` por
página**" — um estágio por página dentro de um laço por bloco. Os números medidos dos dois lados
(8 ocorrências residuais de `vitoria` em §5.3; 50 capturas em 64 páginas em §7.2) só são
reproduzíveis com a limpeza aplicada **à página**, não a cada bloco; e limpar por bloco quebra
padrões de assinatura que atravessam a fronteira `protocolo \d+`.

*Correção concreta* — substituir a lista de §6.5 por seis estágios numerados, e remover de §7.2
a frase "antes da segmentação" (ela passa a ser consequência da ordem, não uma regra à parte):

```
1. truncar _source.conteudo em 20.000 caracteres   -> conteudo_truncado
2. t = comum.normalizar(conteudo)
3. t = _limpar_boilerplate(t)                      # PAGINA inteira, uma vez
4. PADROES_MENCAO + classificar_mencao sobre t     # PAGINA (§7.2)
5. blocos = _blocos_de_ato(t)                      # 'protocolo \d+' sobrevive a (3)
6. por bloco: passada de orgaos -> passada de municipios -> pareamento de edital
```

Declarar explicitamente que `protocolo \d+` não está em `PADROES_BOILERPLATE` **é** o que torna
(3) antes de (5) seguro — o documento já diz isso em §6.5, e é esse argumento que a ordem nova
usa.

---

**2. O casamento de texto livre não inclui aliases e usa duas formas de chave incompatíveis entre si (`normalizar()` vs `chave_nome()`).**

Três afirmações do documento não fecham:

- §5.1: `padroes_ordenados` = *"lista `(nome_normalizado, slug)`"*; §5.2 passo 3 casa com
  `r"\b" + re.escape(nome_normalizado) + r"\b"`. Nada diz que **aliases** entram nessa lista —
  só `por_chave_nome` (usado por `resolver_municipio()` e por `classificar_mencao()`) os contém.
  Consequência: os **2 aliases** que §3.3 cadastra com evidência (`Cachoeiro do Itapemirim`,
  `Cachoeiro`) **não** creditariam nada no diário, que é justamente onde eles aparecem. A §3.3
  afirma o oposto ("o cadastro **e o casamento** usam uma chave canônica única").
- §5.1: `padroes_orgaos` = `(chave_nome(nome|sigla), orgao_id)`, casado contra o texto
  `normalizar()`-ado. `chave_nome()` colapsa pontuação e `normalizar()` **não** — medido com as
  funções reais: `chave_nome("CIM Polinorte") == "cim polinorte"`, mas o texto normalizado traz
  `"cim-polinorte"`, e `re.search(r"\bcim polinorte\b", texto)` é **False**. Todo nome/sigla com
  hífen, ponto ou barra no diário fica fora do casamento, inclusive os três órgãos
  intermunicipais de §4.1 e qualquer alias abreviado que §3.3 admita no futuro.
- O texto **não pode** ser `chave_nome()`-ado para compensar: `PADROES_BOILERPLATE`,
  `MARCA_DEPOIS` (`[/-] es`) e `PADROES_MENCAO` (`[/,-]`) dependem da pontuação.

*Correção concreta* — manter `t` em `normalizar()` e construir os dois conjuntos de padrões a
partir de `chave_nome()` com um compilador tolerante a pontuação; e declarar que
`padroes_ordenados` inclui **nome e aliases**:

```python
def _padrao_de_chave(texto):
    """Casa a chave canonica mesmo quando o diario separa os tokens por pontuacao:
    'cim-polinorte', 'cim/polinorte' e 'cim polinorte' casam o mesmo padrao. O texto
    de trabalho fica em normalizar() porque boilerplate, MARCA_DEPOIS e PADROES_MENCAO
    dependem da pontuacao que chave_nome() apagaria."""
    toks = [re.escape(t) for t in comum.chave_nome(texto).split()]
    return re.compile(r"\b" + r"[^a-z0-9]+".join(toks) + r"\b")
```

- `padroes_ordenados`: lista `(padrao, slug, origem)` com `origem ∈ {"nome", "alias"}`, uma
  entrada por nome **e** por alias, ordenada por comprimento decrescente de
  `chave_nome(nome|alias)`;
- `padroes_orgaos`: idem, com `_padrao_de_chave`;
- regra de confiança: alias casado em texto livre segue a **mesma** regra de §5.3 (adjacência),
  e `origem == "alias"` é gravado no achado (campo novo `municipio_origem`) ou, no mínimo,
  ignorado explicitamente — decidir uma das duas aqui, não deixar para a implementação.

---

### MEDIUM

**3. `com_registro_curado = 16` contradiz a própria definição que exclui registros intermunicipais (o valor correto é 15).**

§7.4 define `com_registro_curado` como "municípios cujo campo `municipio` de algum registro de
`dados/` resolve pelo cadastro, **excluídos os registros com `esfera == "intermunicipal"`**" e
em seguida anota "Medido: 16 nomes oficiais distintos nos 53 registros". Os dois números não
podem ser o mesmo campo. Medi nos 53 registros: **16** nomes oficiais distintos no total, e
**15** quando se excluem os intermunicipais — `Divino de São Lourenço` aparece **somente** em
`ps-consorcio-caparao-es-2026` (`esfera: "intermunicipal"`), que é precisamente o registro que
§4 decidiu não creditar. O bloco de exemplo de §7.4 (`"com_registro_curado": 16`) e as três
linhas de Panorama de §11.1 nascem com o número errado, e um teste escrito a partir do exemplo
fixaria o bug.

*Correção concreta*: trocar o exemplo para `"com_registro_curado": 15`, anotar
"16 nomes oficiais distintos, **15** após excluir os intermunicipais" e acrescentar a §16 a
asserção `Divino de São Lourenço` → não entra em `com_registro_curado` **e** soma 1 em
`registros_intermunicipais_sem_atribuicao` (hoje §16 só tem a segunda metade).

---

**4. §9.2 exige pendência de `url_diario_oficial`, motivo que §3.1 nunca produz — o município corretamente curado é reprovado.**

§9.2: "`url_diario_oficial == null` **e** `diario_oficial_em == null` sem pendência de
**`url_diario_oficial`** → erro". Mas o vocabulário de §3.1 declara o produtor de
`nao_encontrado` como "`diario_oficial_em` quando não há agregador identificado nem diário
próprio", e lista as formas válidas no dado: `url_prefeitura:conferir_manual`,
`url_prefeitura:nao_responde`, `diario_oficial_em:nao_encontrado`,
`municipios_slugs:nao_encontrado`. Nenhuma forma `url_diario_oficial:*` existe. Um município sem
diário próprio e sem agregador, curado exatamente como §3.1 manda
(`diario_oficial_em:nao_encontrado`), é **reprovado** por §9.2; para passar, o curador teria de
inventar um item de pendência cujo motivo não tem produtor declarado — o "vocabulário morto" que
§3.1 diz querer evitar.

*Correção concreta*: reescrever a linha de §9.2 como

```
url_diario_oficial == null E diario_oficial_em == null E
nenhum item de pendencias_verificacao com campo em {"diario_oficial_em", "url_diario_oficial"}
   -> erro
```

e manter §3.1 como está (o curador escreve `diario_oficial_em:nao_encontrado`).

---

**5. A sondagem dos 78 candidatos a `url_prefeitura` não tem regra de derivação do candidato nem dono.**

§3.2 decide bem o **critério de aceitação** (2xx/3xx, 403/406/429, 404/NXDOMAIN/timeout) e
fecha o reaproveitamento dos 6 do catálogo, mas manda "a implementação **re-sonda os 78
candidatos**" sem dizer **de onde sai o candidato dos outros 72**. A tabela de 14 sondagens usa
hosts do tipo `www.laranjadaterra.es.gov.br` / `www.saoroquedocanaa.es.gov.br` (slug sem
hífens), e a própria §3.2 abre dizendo que "o padrão de domínio é candidato a verificar" e que
"o slug **não** prevê o domínio" (Cachoeiro). Sem a fórmula escrita, dois implementadores
produzem cadastros diferentes. Além disso, **nenhuma linha de §17 hospeda a sondagem**: não há
script, e `coletar.py` não deve fazer 78 requisições no cron.

*Correção concreta*, três linhas de decisão:

1. candidato único derivado: `https://www.<slug sem hifens>.es.gov.br/` (ex.:
   `saoroquedocanaa`, `vilapavao`, `laranjadaterra`);
2. quando houver fonte catalogada elegível (os 6 de §3.2), o candidato é a URL catalogada
   normalizada para `scheme://host/`, e **substitui** o derivado;
3. a sondagem vive em `ferramentas/sondar_prefeituras.py` (novo, uso único, declarado em §17,
   **não** chamado pelo workflow), que imprime o par `slug → (status, url, pendência)` para a
   curadoria colar no cadastro. Sem HTTP→HTTPS: só `https://`, e falha de TLS cai em
   `nao_responde`, como §3.2 já diz.

---

**6. A semântica de `resolver_municipio()` não está definida, e §6.10 a usa num tipo de texto para o qual ela não funciona.**

§5.1 descreve `resolver_municipio(texto, indice=None)` como "(slug, origem) para um texto
**curto** tipo o campo `municipio` de um registro" — isto é, consulta em `por_chave_nome`. §6.10
a chama com `alvo = achado.get("municipio") or achado.get("orgao")`. Nos achados reais de
`concursosnobrasil-es`/`selecao-es` esse campo é `"ARIES"`, `"SEDU"`, `"Prefeitura de
Anchieta"`, `"Câmara Municipal de ..."` — uma consulta por chave exata devolve `None` em
praticamente todos, e `municipio_slug` de `oportunidade` nasce sempre nulo. A tabela de §6.10
("`oportunidade`, `municipio`/`orgao` resolve → slug/baixa/municipal") descreve uma linha que
nunca ocorre, e o teste de §16 ("sai com os cinco campos preenchidos") passaria trivialmente
sem exercitar nada. Também não está dito o que `origem` vale quando a chave casada é o nome de
um **órgão vinculado** (§5.1 injeta esses nomes em `por_chave_nome`), nem o que acontece com
texto que casa dois municípios.

*Correção concreta*: separar as duas operações e escrever as duas assinaturas:

```python
def resolver_municipio(texto, indice=None):
    """Consulta EXATA por chave_nome(). Para campo 'municipio' de registro curado.
    Devolve (slug, origem) com origem em {'nome','alias','orgao_vinculado'}, ou (None, None)."""

def resolver_municipio_em_texto(texto, indice=None):
    """Passada longest-first de §5.2 sobre texto livre. Devolve (slug, origem) quando
    resolve para UM unico municipio; (None, None) quando resolve zero OU mais de um —
    ambiguidade nunca e desempatada por palpite."""
```

e mandar §6.10 usar a segunda (`municipio` + `orgao` concatenados), §9.3 a primeira.

---

**7. `vistos_pela_primeira_vez` reanuncia o mesmo município, porque o estado persistido é da janela e não histórico.**

§7.4: `slugs_com_sinal` = "`com_achado_na_janela ∪ com_registro_curado`" e
`vistos_pela_primeira_vez` = "`slugs_com_sinal` de agora **menos** `slugs_com_sinal_antes`".
Como `com_achado_na_janela` é da janela desta execução, um município que tem ato hoje e nenhum
na semana seguinte **sai** de `slugs_com_sinal`; quando voltar a publicar, entra de novo no
delta e é anunciado outra vez como "primeiro ato detectado em X" — e, por §10.2, **abre issue**.
O e-mail está protegido (`cobertura_vistos`, §11.3), a issue e o título (§7.5) não. Isso
contradiz §7.1 ("Sooretama nunca teve registro nem achado, e hoje apareceu").

*Correção concreta*: tornar o estado monotônico e separar os dois conceitos:

```
slugs_com_sinal           = ordenado(com_achado_na_janela ∪ com_registro_curado)   # retrato de hoje
slugs_com_sinal_historico = ordenado(slugs_com_sinal_antes_historico ∪ slugs_com_sinal)
vistos_pela_primeira_vez  = ordenado(slugs_com_sinal − slugs_com_sinal_antes_historico)
```

`cobertura()` passa a receber `slugs_com_sinal_historico_antes` (e não o retrato), e §9.4 troca a
checagem de subconjunto por `vistos ⊆ slugs_com_sinal` **e**
`slugs_com_sinal ⊆ slugs_com_sinal_historico`.

---

**8. §11.1 manda a coluna "Ato detectado" do README usar `com_achado_acumulado`, que é um inteiro: falta a lista por município.**

`cobertura_municipios` (§7.4) publica `com_achado_acumulado` (contagem) e
`slugs_com_sinal`/`sem_sinal_slugs` (listas da **janela**). A tabela de 78 linhas precisa de um
✓/— **por município acumulado**, que não existe em lugar nenhum. Derivar de `achados` em
`gerar_readme.py` não serve: `carregar_descobertas()` (linha 186, conferido) filtra
`no_repositorio` e `ausente_na_fonte`, e é exatamente o ato antigo que carrega o histórico.

*Correção concreta*: acrescentar ao bloco `cobertura_municipios` a lista
`"slugs_com_achado_acumulado": [...]` (ordenada, derivada dos achados `municipio_confianca ==
"alta"` **sem** condição de data), usá-la em §11.1, e acrescentar a §9.4
`com_achado_acumulado == len(slugs_com_achado_acumulado)` → erro.

---

**9. A fronteira de legado (`primeira_deteccao < ibge_consultado_em`) deixa de fora os 2 achados mais novos do arquivo versionado.**

§6.9/§9.4 definem legado por `(achado.get("primeira_deteccao") or "") < cadastro["ibge_consultado_em"]`,
com `ibge_consultado_em: "2026-10-01"` no exemplo de §3.1. Medi o arquivo versionado: das 37
entradas, **2 têm `primeira_deteccao == "2026-10-01"`** (as outras 35 são de 09-23 a 09-30).
Para essas duas a comparação é falsa → **erro**, não aviso. Com `--migrar-descobertas` rodado e
commitado o arquivo de hoje fica limpo, mas a proteção que §6.9 promete ("protege a execução
agendada contra qualquer arquivo antigo que apareça depois — checkout de branch velha, revert")
falha justamente nos achados da fronteira, e o CI reprova sem caminho de recuperação
automático.

*Correção concreta*: usar `<=`, e dizer por quê no comentário:

```python
# <=, e nao <: o cadastro e commitado no mesmo dia em que a coleta anterior rodou,
# e medimos 2 achados com primeira_deteccao == ibge_consultado_em. Com '<' eles
# viram erro e nao aviso, que e o oposto da tolerancia que esta linha existe para dar.
legado = (achado.get("primeira_deteccao") or "") <= cadastro["ibge_consultado_em"]
```

---

**10. "218 hits/dia" é erro de unidade: 218 é o total da janela de 7 dias — e é esse número que dimensiona a retenção e o aviso de 5.000.**

§6.2 mede os quatro pares escopo×frase **na janela de 7 dias** (DIO 16/8, DOM 63/131 — eu
reproduzi os quatro contra a API, idênticos). §6.4 então escreve "218 hits/dia medidos no
total" e §6.9.1 raciocina "na ordem de grandeza medida (218 hits/dia) ... o arquivo cresce em
**centenas de entradas por dia**". O número correto de **entradas novas por dia** é ~218/7 ≈
**31**, e o regime permanente com retenção de 90 dias é ~2.800 achados — abaixo do aviso de
5.000 de §9.4. Com o número errado (19.600) o aviso dispararia para sempre e a conclusão de
§6.9.1 seria que 90 dias é inviável. Como os dois valores sustentam decisões (retenção, teto do
aviso, `--max-achados-ioes`), o documento tem de dizer qual é qual.

*Correção concreta*: em §6.4 e §6.9.1, trocar por "**218 hits na janela de 7 dias** (≈ 31
achados inéditos/dia)"; recalcular explicitamente "90 dias × ~31 ≈ 2,8 mil achados em regime,
contra o aviso de 5.000 de §9.4, que fica com ~45% de folga"; manter os tetos (eles são por
execução e por fonte, e cobrem os 131 da janela).

---

**11. A fusão de `municipios_nao_mapeados` entre execuções não está especificada.**

§7.2 diz que `primeira_deteccao`/`ultima_deteccao` "têm de sobreviver entre execuções" e que
"candidato que não aparece há mais de `--janela-ioes-dias * 4` dias é removido". Falta tudo o
resto, e cada escolha muda o que a issue mostra: (i) a chave de fusão é `nome_detectado` após a
poda? (ii) `ocorrencias`/`paginas_distintas` são **da execução** ou acumuladas? (iii) o filtro
`paginas_distintas >= 2 or com_marca_uf` é aplicado aos contadores da execução ou aos
acumulados? (iv) `exemplos` antigos são preservados ou substituídos? Com (ii)/(iii) por
execução, um candidato real que apareça 1×/dia em páginas distintas e sem `/ES` **nunca** é
reportado, embora tenha 10 páginas distintas na semana — e o mecanismo de aprendizagem de alias
de §3.3 depende dele.

*Correção concreta*, escrever a regra:

```
chave de fusao = nome_detectado (captura ja podada e consolidada por prefixo)
ocorrencias, paginas_distintas: ACUMULADOS (soma do anterior + o desta execucao)
com_marca_uf: OR do anterior com o desta execucao
primeira_deteccao: do anterior, se existir;  ultima_deteccao: desta execucao
exemplos: ate 3, de paginas distintas, preferindo os mais recentes
filtro de reporte: aplicado aos ACUMULADOS (paginas_distintas >= 2 OR com_marca_uf)
remocao: ultima_deteccao < referencia - (--janela-ioes-dias * 4)
```

---

**12. A regra de confiança não diz em que momento a janela de contexto é lida, e o único snippet (`re.sub`) não dá como lê-la.**

§5.3 decide que a janela (45 antes / 6 depois) é lida "no texto **mascarado**, isto é, no mesmo
`t` que a passada de §5.2 vai modificando", mas o código de §5.2 é
`t = re.sub(padrao, lambda m: "\x00" * len(m.group(0)), t)` — `re.sub` não expõe offsets, e as
ocorrências do padrão corrente são mascaradas **todas de uma vez**. Fica indefinido se a
confiança de uma ocorrência é avaliada antes ou depois de mascarar as ocorrências do **mesmo**
padrão, e o resultado medido depende disso.

Reproduzi o mecanismo com a interpretação "avaliar todas as ocorrências do padrão, depois
mascarar o padrão inteiro" e os dois resultados de §5.2 saem exatamente como o documento diz
(`vila-velha` alta + `serra` **baixa**; `santa-maria-de-jetiba` alta + `linhares` **baixa**; com
máscara de espaço as duas saem alta). Então a decisão está certa — só não está escrita.

*Correção concreta*, substituir o snippet por:

```python
for padrao, slug, origem in indice.padroes_ordenados:   # mais longo primeiro
    achados_pad = list(padrao.finditer(t))              # finditer, nao sub: precisamos dos offsets
    for m in achados_pad:
        antes = t[max(0, m.start() - 45):m.start()]
        depois = t[m.end():m.end() + 6]
        conf = "alta" if (MARCAS_ANTES.search(antes) or MARCA_DEPOIS.match(depois)) else "baixa"
        registrar(slug, conf, origem)
    # mascara DEPOIS de avaliar todas as ocorrencias deste padrao, nunca antes:
    # avaliar e mascarar intercalado faria a 2a ocorrencia do mesmo nome ler a 1a.
    t = padrao.sub(lambda m: "\x00" * len(m.group(0)), t)
```

(`MARCA_DEPOIS.match`, e não `search`, é o que garante a adjacência que §5.3 decidiu.)

---

**13. Não há regra para o README quando `cobertura_municipios` ainda não existe — que é o estado do PR que implementa este design.**

§11.1 acrescenta três linhas de Panorama e a seção "Cobertura por município", e §12 declara que
ler o cadastro em `gerar_readme.py` é **fatal**. Mas `--migrar-descobertas` (§6.9) só faz
backfill **por achado** e "preserva todas as chaves de topo existentes": o `descobertas.json`
commitado no PR **não terá** `cobertura_municipios`. O job `validar` roda
`gerar_readme.py --check` em todo PR (conferido no YAML), então o PR precisa de um README
determinístico gerado desse estado. §9.4 trata a chave ausente como aviso, mas §11.1 não diz o
que a tabela mostra.

*Correção concreta*: acrescentar a §11.1 — "quando `cobertura_municipios` está ausente
(`descobertas.json` anterior à primeira coleta com cadastro), as três linhas de Panorama saem
com `0` e a coluna `Ato detectado` sai `—` em todas as 78 linhas; `Registros curados` e
`Fonte própria` continuam corretos porque vêm de `dados/` e do cadastro. O bloco permanece
determinístico, e é esse o estado que o PR commita."

---

### NIT

**14. `max_tokens_nome` é medido só nos nomes de município, mas `por_chave_nome` também contém nomes de órgão.**
§5.1 injeta em `por_chave_nome` os nomes de `orgaos_vinculados` que resolvem para exatamente 1
slug — `"instituto de previdencia dos servidores de cariacica"` tem 7 tokens — enquanto
`classificar_mencao()` (§7.2) só tenta prefixos até `indice.max_tokens_nome` (**4**, que eu
confirmei ser o máximo entre os 78 nomes). Essas chaves nunca são alcançáveis pela poda.
*Fix*: calcular `max_tokens_nome = max(len(k.split()) for k in por_chave_nome)` e manter o
comentário explicando que o limite existe para a captura, não para o cadastro.

**15. §9.2 não valida a forma das entradas de `orgaos_vinculados` com a mesma severidade das de `municipios`.**
Há checagens de `id`, `natureza`, aridade e slugs existentes, mas nenhuma de: chaves
obrigatórias/desconhecidas (como §9.1 faz para `fontes.json`), `url` `null` exigindo pendência
`url:nao_encontrado` (que §4.1 usa em 5 das 8 entradas), `fontes[]` referenciando `id`
existente, e `verificado_em` presente/não futura. *Fix*: replicar as quatro linhas na tabela de
§9.2, com o conjunto de chaves permitidas escrito por extenso
(`id,nome,sigla,natureza,esfera,municipios_slugs,url,fontes,pendencias_verificacao,verificado_em`).

**16. `monta_relatorio_md()` é estendida sem assinatura nova.**
§7.5 lhe dá quatro seções condicionais e uma linha de resumo; a assinatura atual é
`monta_relatorio_md(novos, relatorio_fontes, referencia)`. *Fix*: declarar
`monta_relatorio_md(novos, relatorio_fontes, referencia, cobertura, nao_mapeados, reconciliacao, atos_novos, truncado)`
— ou um único parâmetro `contexto` (dict) — em §7.5 e na linha de `coletar.py` em §17.

**17. O trecho de shell do título da issue aborta o passo sob `set -e`.**
§7.5 usa `[ "cond" ] && partes="..."`; quando o teste falha o comando sai com 1. O passo atual
não tem `set -e`, mas outros passos do mesmo workflow têm (`set -euo pipefail`), e é
copy-paste provável. *Fix*: usar `if [ ... ]; then ...; fi`, ou sufixar `|| true`.

**18. `truncado=<0|1>` não tem regra de agregação entre as duas fontes IOES.**
§6.3 dá a cada fonte seu `diag`, e §7.5 publica um único `truncado`. *Fix*: dizer
`truncado = 1 se qualquer diagnostico de fonte tiver truncado ou limite_achados_atingido`.

**19. `--migrar-descobertas` faz backfill de 4 campos; `normalizar_achado()` define 7.**
§6.9 lista `categoria`, `municipio_slug`, `municipio_escopo`, `municipio_confianca`; §6.10
acrescenta `municipio_codigo_ibge`, `orgao_vinculado_id`, `conteudo_truncado`. *Fix*: definir
`--migrar-descobertas` como "aplica `normalizar_achado()` a cada achado e regrava", para que
exista um só lugar com a lista de campos.

**20. O `except` de `main()` não cobre as exceções que um envelope malformado produz.**
O laço existente captura `(urllib.error.URLError, OSError, ValueError, RuntimeError)`; um
`KeyError`/`TypeError` vindo de `_achados_de_resposta()` derrubaria a coleta inteira, contra a
degradação graciosa que §12 promete. §13.1 especifica validação por item, o que basta **se** a
implementação a seguir à risca. *Fix*: uma linha em §12 — "`_achados_de_resposta()` não propaga
`KeyError`/`TypeError`: todo acesso a campo de terceiro usa `.get()` com validação de §13.1" —
ou incluir os dois tipos na tupla do `except`.

**21. Duas instâncias do mesmo município em blocos distintos da mesma página colidem na chave sem número.**
§6.5 permite "1 achado por (bloco, município)" e §6.6 monta a chave sem número como
`ioes-<escopo>:<slug>:<diario_id>-<pagina>` — dois blocos da mesma página geram a mesma chave, e
quem sobrevive depende do `vistos` de `main()`. *Fix*: dizer em §6.6 que `coletar_ioes()`
deduplica por chave **antes** de devolver, aplicando a ordenação de §6.6, para que o descarte
não dependa de `main()`.

---

## Suposições verificadas

Conferido no código, nos dados e nas APIs reais — todas se sustentaram.

**Repositório / código**

- `comum.py` não tem `normalizar`/`slug`/`_sem_acento` (estão em `coletar.py`), e `carregar_registros()`
  varre apenas os 6 subdiretórios de `comum.DIRETORIOS`; `validar.valida_diretorio()` reprova
  "diretorio desconhecido" fora deles. Base de §3.
- `_coberto("serra", {"serrana"})` é **True**; `tokens_identidade("Prefeitura de Serra")` é
  `{"serra"}` (`prefeitura`, `de` em `TOKENS_GENERICOS`); o ramo final de `casar()`
  (`for usar_local in (False, True)`) casaria qualquer certame de Serra. Justifica `casar_estrito()` (§6.7).
- `numeros_de_edital()` captura `273/0001` (regex `(\d{1,4})\s*/\s*(\d{4})`). §6.5.
- `novos.append(achado)` ocorre para todo achado inédito sem registro casado. §6.10.
- A única poda de preservação depende de `inscricoes.fim`, nos dois ramos; `ato_diario` com
  `fim: null` nunca é alcançado. §6.9.1.
- `carregar_anterior()` devolve só `{chave: achado}` e descarta o resto do arquivo. §7.2.
- `gerar_email.classificar_descobertas()` tem exatamente `if fim is not None and fim < referencia: continue`;
  `carregar_estado()` devolve 2 valores (linha 64), `gravar_estado()` recebe 3 (linha 77), call
  sites nas linhas **410** e **436**. §6.8, §11.3.
- `gerar_readme.carregar_descobertas()` filtra `no_repositorio` e `ausente_na_fonte` (linha 186). §11.1.
- `validar.CAMPOS_DESCOBERTA` é exatamente a lista de 8 campos citada; `status_estimado: None` é aceito. §6.7.
- Workflow: `pull_request.paths` = `dados/**`, `ferramentas/**`, `README.md`; `push.paths` =
  `dados/**`, `ferramentas/**` — **`fontes/**` não está em nenhum**; job `validar` com
  `if: pull_request || push`; `git add -A README.md email/ relatorios/ dados/ historico/ descobertas/`
  (sem `fontes/`); condição da issue `novos != '0' && novos != ''`; título
  `"Coleta automatica: <novos> nova(s) oportunidade(s) do ES — <data>"`. §10.1–§10.4.
- README com 29.082 bytes ("já tem 29 KB", §11.1); `dados/ESQUEMA.md` documenta `intermunicipal`.

**Dados**

- 53 registros; 18 valores distintos de `municipio`; 24 com `"Âmbito estadual (ES)"`; 1 com
  `"Diversos (ES) - Linhares e região"`; 16 nomes oficiais distintos.
- **4** registros `esfera: "intermunicipal"`: os **2** da ARIES (`"Vitória"`),
  `ps-cim-polinorte-es-2026` (`"Diversos (ES) - Linhares e região"`) e
  `ps-consorcio-caparao-es-2026` (`"Divino de São Lourenço"`) — exatamente a correção factual que
  o §0/§4 do design reivindica.
- `fontes.json`: 38 fontes, **12 sem `esfera`** = `banca`(7) + `portal_concursos`(3) +
  `imprensa`(2); as 26 com `esfera` são `oficial`(23) + `diario_oficial`(3); 8 fontes municipais
  cobrindo **7** municípios (2 de Aracruz); `prefeitura-castelo` aponta para
  `educacao.castelo.es.gov.br/processos-seletivos`; `prefeitura-cachoeiro` para
  `www.cachoeiro.es.gov.br/editais/`. §1.1, §3.2, §8.1.
- Chaves usadas em `fontes.json` são **exatamente**
  `id,nome,url,tipo,esfera,prioridade,observacao,coletada_automaticamente`, e `prioridade ∈ 1..4`
  — a checagem de "chave desconhecida" de §9.1 não reprova nada hoje.
- `descobertas.json` versionado: 8 chaves de topo, **37** achados, **0** com `categoria`, 0 com
  campo `municipio_*`, 19 de `selecao-es` + 18 de `concursosnobrasil-es`. §6.9.

**Cadastro / IBGE**

- `/projects/sandbox/ibge_es.json` tem 78 municípios, e a API
  `.../localidades/estados/32/municipios` devolveu **78** agora, com `id`/`nome` coincidentes.
- O **Anexo A inteiro confere**: os 78 pares (código IBGE, nome oficial, slug, microrregião)
  batem com o IBGE, com `slug` recalculado por `coletar.slug()`. Zero divergências.
- Os seis nomes difíceis caem por normalização, sem alias: `Guaçuí→guacui`, `Iúna→iuna`,
  `Marataízes→marataizes`, `São Roque do Canaã→sao-roque-do-canaa`, `Vila Pavão→vila-pavao`,
  `Cachoeiro de Itapemirim→cachoeiro-de-itapemirim` (+ `Atílio Vivácqua→atilio-vivacqua`).
- Nenhum slug é prefixo de outro; os únicos subconjuntos de tokens são `Castelo ⊂ Conceição do
  Castelo` e `Itapemirim ⊂ Cachoeiro de Itapemirim`; o máximo de tokens é **4**, em **12** nomes.
- `regiao-imediata.regiao-intermediaria.nome` é `"Cachoeiro do Itapemirim"` (com "do") para **24**
  municípios — a evidência do alias de §3.3.
- A API do IBGE responde **200 com `Content-Encoding: gzip` mesmo com `Accept-Encoding: identity`**,
  e `b.decode("utf-8")` levanta `UnicodeDecodeError`; após `gzip.decompress()` o JSON tem 78 itens.
  Exatamente o que §6.4/§7.3 afirmam.

**API do IOES (exercitada agora, `di:2026-09-24`)**

- Totais por escopo×frase, idênticos aos do design: DIO `"concurso publico"` **16**,
  DIO `"processo seletivo"` **8**, DOM `"concurso publico"` **63**, DOM `"processo seletivo"` **131**.
- `hits.total` é **int**; página 0-based com **10** itens; `_id` no formato `11515_69`;
  `_source` com `conteudo,data,day,diario_id,month,pagina,paginas,pdf_id,tipo_edicao,year`;
  nível do hit com `diario`, `suplemento`, `highlight`, `sort`, `_score`.
- `diario` = `"DIO"` com `tipo_edicao: 1` e `"DOM - AMUNES"` com `tipo_edicao: 13`;
  `suplemento` = `"Edição 26821"` / `"Edição 3099"` (rótulo de edição, não suplemento);
  `sort` = `[1790812800000]` para todos os itens do dia (empate intradiário real).
- `highlight.conteudo` é lista de trechos; o PDF por página
  `{BASE}/portal/edicoes/download/{diario_id}/{pagina}` responde **200 `application/pdf`** nos dois escopos.

**Mecanismos de texto (reimplementados e medidos)**

- Máscara: com `" "`, `"PREFEITURA DE VILA VELHA SERRA"` dá `serra` em **alta** (indevido) e
  `"MUNICIPIO DE SANTA MARIA DE JETIBA LINHARES"` dá `linhares` em **alta**; com `"\x00"` os dois
  caem para **baixa**, e `"prefeitura municipal de serra/es"` continua **alta** por `MARCA_DEPOIS`.
  A decisão central de §5.2/§5.3 se sustenta.
- `PADROES_BOILERPLATE` de §5.3 remove `vitoria` nas **seis** formas citadas (data numérica,
  por extenso com e sem o segundo "de", `(es)`/`/es`/`-es`/`, es`, e a linha de `cep:`).
- `PADROES_MENCAO` minúsculos sobre texto normalizado capturam
  `"MUNICÍPIO DE SOORETAMA/ES"` → `sooretama` (padrão 1, com marca de UF) e
  `"prefeitura municipal de sao roque do canaa, estado do"` → `sao roque do canaa` (padrão 2).
- `chave_nome()` colapsa `"S. Mateus"`, `"S.Mateus"`, `"S Mateus"` na mesma chave `"s mateus"`.
- Compatibilidade 3.9/stdlib dos snippets: nenhum uso de `match`, `X | Y` em anotação avaliada,
  `dict | dict`, `removeprefix` ou dependência externa; `ESFERAS_VALIDAS | {...}` é união de `set`.

## Suposições não verificadas / erradas

**Erradas (viraram finding)**

1. `com_registro_curado = 16` — pela definição do próprio §7.4 (exclui `intermunicipal`) o valor é
   **15**: `Divino de São Lourenço` só existe em `ps-consorcio-caparao-es-2026`. **Finding 3.**
2. "218 hits/dia" (§6.4, §6.9.1) — 218 é o total da **janela de 7 dias** (confirmado contra a API);
   o fluxo diário é ~31. **Finding 10.**
3. "a fronteira `ibge_consultado_em` protege todo achado legado" (§6.9) — 2 dos 37 achados
   versionados têm `primeira_deteccao` **igual** à fronteira e cairiam em erro. **Finding 9.**
4. "o cadastro e o casamento usam uma chave canônica única" (§3.3) — §5.1/§5.2 usam
   `nome_normalizado` no casamento de município e `chave_nome()` nos órgãos; medido que a segunda
   forma não casa texto com pontuação. **Finding 2.**
5. Ordem do pipeline de texto: §6.5 e §7.2 afirmam ordens mutuamente exclusivas. **Finding 1.**

**Não verificáveis aqui (riscos declarados, aceitos)**

6. As 14 sondagens de domínio de prefeitura (§3.2): não repeti (dependem de WAF, data e
   `User-Agent`, como o próprio documento diz). A **regra** derivada delas é razoável; o que falta
   é a derivação do candidato (finding 5).
7. As medições sobre as "144 páginas" amostradas (21% de `vitoria`, 94/144 com `protocolo`,
   30 páginas com cartesiano, 1.419 achados, 7 de 7 falso positivos, 41 municípios em confiança
   alta): amostra diferente, não reproduzível byte a byte. Amostrei 38 páginas da mesma janela e os
   indicadores ficam na mesma ordem de grandeza (`protocolo` em 33/38; `vitoria` em 21/38 — sendo
   que minha amostra concentra o dia 01/10, e `vitoria` cai para zero em confiança alta após a
   limpeza, que é a afirmação que importa). Nenhuma contradição observada; nenhum número desses é
   usado como expectativa de teste no design, o que é a mitigação correta.
8. `q=edital` com 161 hits e perda de precisão (§6.4) — não consultei; a decisão de ficar em duas
   frases é defensável de todo modo.
9. Estabilidade do endpoint `/busca/busca/buscar/` e do bundle Angular (§18.5) e a forma futura de
   `hits.total` (§18.6) — suposições sobre terceiro, mitigadas por `suspeita_extracao_vazia` por
   escopo, `truncado` e `--autoteste-ioes`.
10. `url_diario_oficial` próprio só confirmado para a Serra (§18.2) — o seletor "Outros Diários
    Oficiais" não foi varrido; o design declara a pendência em vez de preencher, o que é correto.
11. Composição dos consórcios (CIM Polinorte, Caparaó, ARIES) — `municipios_slugs: []` + pendência,
    declarado como pendência de curadoria (§18.3).
