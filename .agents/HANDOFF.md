# Handoff — cobertura dos 78 municípios do ES

Documento de passagem de bastão. Escrito para que outra pessoa (ou outro agente) retome o
trabalho sem precisar reconstruir o contexto. Estado em 2026-10-01, branch
`cobertura-78-municipios-es`.

## O que foi pedido

1. Listar todos os municípios do Espírito Santo.
2. Criar um plano para o repositório coletar concursos e processos seletivos de cada um deles.
3. Executar o plano e corrigir o que precisasse.
4. Auditar se o GitHub Actions consegue achar municípios novos e se há bugs.

Esclarecimento dado pelo usuário no meio do trabalho, que reorientou o eixo do cadastro:

> "São as plataformas que cada município usa pra mandar informações a respeito de emprego."

Ou seja: o cadastro por município é um cadastro de **canais de publicação** de informação de
emprego, não um cadastro de entidades administrativas. Câmaras, autarquias e consórcios continuam
existindo no casamento de texto e em `orgaos_vinculados`, mas não são entradas de primeira classe
dos 78.

## Estado: o trabalho está feito e verificado

Não há item do plano em aberto. As 5 FEATs estão `completed` em
`.agents/task-cobertura-municipios-es/`. Verificação independente, por execução real:

| Verificação | Comando | Resultado |
| --- | --- | --- |
| 78 municípios, sem faltante/sobrando/duplicata | conferência programática contra a API do IBGE (UF 32) | **78 exatos**, zero divergência |
| Suíte de testes | `python3 ferramentas/testes.py` | **183 testes, OK**, exit 0 (em 3.9 **e** 3.11) |
| Validador | `python3 ferramentas/validar.py` | **Validação aprovada**, exit 0 (0 erros, 57 avisos) |
| README sincronizado | `python3 ferramentas/gerar_readme.py --check` | **sincronizado**, exit 0 |
| Workflow | `actionlint -shellcheck -pyflakes` | **0 findings** (achou e corrigiu 3 × SC2086) |
| Pipeline agendado inteiro | execução local com rede real | **exit 0 em todos os passos** |

O job `validar` do CI roda exatamente `validar.py` e `gerar_readme.py --check`, então os dois
checks que governam o merge estão passando.

## O que mudou

16 arquivos, ~9.800 linhas adicionadas. Os pontos que importam:

- **`fontes/municipios-es.json`** (novo, 2.441 linhas) — cadastro canônico dos 78 municípios:
  `codigo_ibge`, `nome`, `slug`, `aliases`, `microrregiao`, lista de `canais` e
  `pendencias_verificacao`. Mais `orgaos_vinculados` com 8 órgãos (câmaras, autarquias, empresa
  municipal, consórcios).
  **Atenção:** ficou em `fontes/`, não em `dados/` como meu brief original pedia. Foi decisão
  consciente do design (decisão 1 do plano) — é catálogo de fontes, não registro de certame.
- **`ferramentas/coletar.py`** (+1.849) — casamento por município e por órgão sobre o texto do
  diário, com detecção de município não mapeado.
- **`ferramentas/validar.py`** (+1.095) — valida o catálogo de fontes (incluindo `esfera`, que
  faltava em 12 das 38 fontes), a integridade do cadastro e a referência de município nos registros.
- **`ferramentas/testes.py`** (novo, 2.866 linhas) — 175 testes. Não existia suíte antes.
- **`ferramentas/sondar_prefeituras.py`** (novo) — sondagem dos domínios candidatos das prefeituras.
- **`.github/workflows/monitoramento.yml`** — `fontes/**` e o próprio workflow entraram nos
  gatilhos de `pull_request` e `push`; a suíte de testes passou a rodar nos dois jobs.
- `comum.py`, `gerar_readme.py`, `gerar_relatorio.py`, `gerar_email.py`, `ESQUEMA.md`,
  `fontes/README.md`, `fontes/fontes.json`.

## Cobertura real hoje — leia antes de interpretar os números

O cadastro tem os 78, mas **cobertura confirmada por evidência é diferente de cadastro completo**:

| Métrica | Valor |
| --- | --- |
| Municípios cadastrados | 78 |
| Com ao menos um canal **confirmado** | **57** |
| Só com canais **pendentes** de verificação | **21** |
| Canais `diario_oficial_agregador` confirmados | 41 (de 78) |
| Canais `portal_prefeitura` confirmados | 35 (de 68) |

Os 21 sem canal confirmado são a lacuna real que sobrou. Ela cai quando atos forem observados
nesses municípios, **não** por mudança de regra.

Regra que foi seguida com rigor e que deve continuar valendo: **nunca inventar URL**. Domínio
candidato que respondeu 403/406 ou não respondeu entrou como `estado: "pendente"` com a evidência
do que aconteceu na sondagem, jamais como link afirmado. Há 55 municípios com
`canais:conferir_manual` e 2 com `canais:nao_responde`.

Um município que publica **apenas** via DOM/AMUNES não é lacuna — é o canal correto dele. Não
conte esses como cobertos pela metade.

## Auditoria: as duas perguntas do usuário

**"O GitHub Actions consegue achar municípios novos?"** Sim, e foi provado por execução, não por
leitura. `.agents/auditoria-cobertura-municipios.md` documenta dois caminhos independentes:
detecção pelo texto do diário (seção 2) e reconciliação contra a lista do IBGE (seção 3), além de
degradação graciosa (4) e integração ponta a ponta com coleta real (7).

**"Há bugs?"** Um defeito real foi encontrado e corrigido, e ele é o achado mais importante do
trabalho:

> `exemplos` de `municipios_nao_mapeados` sem checagem de forma **derrubava a coleta inteira**.
> Um `descobertas.json` com `"exemplos": ["url"]` (string em vez de objeto) passava no validador
> com 0 erros e depois estourava `AttributeError` em `coletar.main()`, fora do `try/except` por
> fonte — perdendo a coleta do dia. Corrigido em duas camadas: `coletar.py` descarta exemplo que
> não é `dict` na ingestão, e `validar.py` passou a tratar isso como erro. 3 testes novos.

Também corrigido: `fontes/**` não estava nos gatilhos do workflow, então alterar fontes não
disparava validação em PR nem no push.

**Falso alarme meu, registrado para ninguém repetir:** eu suspeitei que
`actions/checkout@v7` e `actions/setup-python@v7` não existissem e que o cron estivesse quebrado.
Verifiquei na API do GitHub: `checkout@v7.0.1` e `setup-python@v7.0.0`, ambos publicados em
2026-07-20. **As versões existem e o workflow está correto.**

## O que falta — ordenado por valor

Atualizado em 2026-10-02. Os itens 1, 4 e 5 do passe anterior foram **resolvidos** (detalhe na
seção seguinte); o que sobrou está abaixo, com o motivo de ainda estar aberto.

1. **Confirmar manualmente os canais dos 21 municípios sem evidência** (e os 55 com
   `canais:conferir_manual`). Trabalho de conferência humana, um município por vez.
   **Não automatize isso trocando o `User-Agent`.** A sondagem se identifica como robô de propósito
   (`coletar.NAVEGADOR`), e foi medido que os 403 **não** são artefato do cabeçalho mínimo:
   `consorciocaparao.es.gov.br` e `www.cariacica.es.gov.br` devolvem 403 também para `User-Agent` de
   navegador. Disfarçar o robô para furar o bloqueio seria contornar controle de acesso que o site
   escolheu aplicar, e trocaria uma lacuna honesta por dado obtido por evasão. O caminho correto já
   existe: o canal do agregador vira `confirmado` quando um ato daquele município for observado no
   DOM.
2. **Observar a primeira execução agendada no runner do GitHub.** O que **já foi** provado por
   execução local ponta a ponta, com rede real (2026-10-02): `atualizar_prazos` → `coletar`
   (4 fontes ok, 307 achados, 0 divergência com o IBGE, 0 não mapeados) → `gerar_readme` →
   `gerar_relatorio` → `gerar_email` (exit 0) → suíte (183 OK) → **revalidação (exit 0)** →
   `gerar_readme --check` (exit 0). Sobra só o que depende do runner: `actions/checkout@v7`,
   `actions/setup-python@v7`, o `git push` do bot e o `gh api` da issue.
3. **`plataforma_inscricao` e `banca` por município nascem ausentes** — a evidência existe por
   certame, não por município. Decidir se vale derivar do histórico.

## Resolvido em 2026-10-02

- **`actionlint` rodou** (item 1). Instalado da fonte (v1.7.12) e executado **com as integrações de
  `shellcheck` e `pyflakes` ligadas** — que é o que de fato encontra problema: sem elas o arquivo
  passa limpo e a conferência é falso-negativo. Achou **3 × SC2086** reais no passo "Gerar
  relatorios": `python3 ... --tipo diario $FORCAR` dependia de word splitting para o argumento
  desaparecer quando vazio, e **pôr aspas não resolveria** (`"$FORCAR"` vazio passa argumento vazio,
  que o `argparse` rejeita). Corrigido com array (`forcar=()` / `forcar=(--forcar)`), e
  `inputs.gerar_semanal`/`gerar_mensal` saíram da interpolação direta no corpo do script para `env`.
  O lint fecha agora em **0 findings**. Conferido também que a interpolação de
  `steps.coleta.outputs.*` no `bash` do passo da issue **não** é superfície de injeção: `coletar.py`
  grava todos esses outputs com `%d`, isto é, só inteiros.
- **O seletor "Outros Diários Oficiais" do IOES foi conferido inteiro** (item 4) — e o resultado
  **corrige uma afirmação errada deste handoff**: `diario_oficial_proprio` não existia "só para a
  Serra", existia para **ninguém** (zero canais desse tipo no cadastro). Agora existe para a Serra:
  `https://ioes.dio.es.gov.br/diariodaserra` responde 200 e titula "Diário Oficial Prefeitura
  Municipal da Serra". O 200 **não** é de rota curinga — `/doe`, `/diariodavilavelha`,
  `/diariodacariacica` e `/diariodexyzinexistente` devolvem 404 — e uma varredura de **390 caminhos
  candidatos (5 padrões × 78 municípios)** devolveu 200 só para a Serra. Os outros 77 ficam
  conferidos com **resultado negativo**, não por omissão.
- **Composição dos três intermunicipais apurada** (item 5): CIM Polinorte **13**, CIM Caparaó **13**,
  ARIES **18**. Os 44 nomes foram resolvidos contra o cadastro por script
  (`.agents/apurar-orgaos.py`, que **aborta** em vez de gravar parcialmente se um nome não resolver),
  e não transcritos à mão. Fontes: página institucional do próprio consórcio (Polinorte, conferida
  contra a AMUNES, que lista os mesmos 13), página de consórcios públicos da AMUNES (Caparaó) e a
  página "Municípios Consorciados" do próprio site da ARIES. Com isso
  `orgaos_vinculados_sem_municipio` ficou **vazio**.
- **Os 7 `url: null` foram a zero.** Localizados: câmara de Cachoeiro
  (`www.cachoeirodeitapemirim.es.leg.br`, 200 — e **sem** página de concurso, porque
  `/transparencia/concurso-publico`, `/transparencia/concursos-publicos` e `/transparencia/concurso`
  dão 404; a URL registrada é a raiz institucional, não uma seção inventada), SAAE de Aracruz
  (`www.saaeara.es.gov.br`, que tem página de concursos própria em 200), CODEG e IPC. Os 3 que
  responderam 403 ficaram com `url:conferir_manual` declarada, nunca como link afirmado sem ressalva.
- **Duas correções de nome contra a fonte oficial**, uma delas atendendo pendência escrita no próprio
  dado (`concurso-codeg-guarapari-es-2026` pedia "localizar a página oficial da CODEG"): a CODEG se
  identifica como **"Companhia de Melhoramentos e Desenvolvimento Urbano de Guarapari"**, e o IPC
  como **"Instituto de Previdência dos Servidores Públicos do Município de Cariacica"** — esta última
  já era a grafia do registro `ps-cariacica-es-ipc-previdenciario-2026`, então a correção também
  alinhou cadastro e registro.
- **Duas adições ao esquema de `orgaos_vinculados`**, ambas provocadas por problema real encontrado
  ao fazer o acima, não por gosto:
  - **`evidencia`** (obrigatória, não vazia): `municipios_slugs` de um consórcio credita jurisdição a
    13 ou 18 municípios de uma vez, e antes dela a única forma de auditar a procedência da lista era
    a descrição do PR, que não acompanha o arquivo.
  - **`aliases`**: ao corrigir o nome do IPC, a forma encurtada que o cadastro usava **deixou de
    casar no texto do diário**, e a suíte pegou. Sem `aliases`, corrigir um nome para a grafia
    oficial sempre custa recall silencioso sobre a forma antiga. Alias que colide com nome de
    município é **erro** (creditaria o ato ao município errado); alias igual à `sigla` não entra,
    porque a sigla já indexa sozinha.
  Ambas com teste: a suíte foi de **175 para 183**.

## Três decisões de produto que o código deixou explícitas e não resolveu por conta própria

Não são bugs. Alguém precisa decidir:

- **O relatório diário passará a listar ~319 bullets de ato de diário** a partir da primeira coleta
  agendada. Por desenho o relatório é o registro bruto da coleta; filtrar é decisão de produto.
- **Cobertura nova não dispara e-mail.** `novidades == 0 and not achados_novos` continua sendo o
  único critério de `exit 2`. Num dia cujo único fato seja "primeiro ato em Sooretama", quem
  notifica é a issue.
- **A primeira coleta publicará `primeira_vez` alto** (48 medido) porque o histórico nasce vazio.
  Correto por construção — **não "conserte" isso**.

## Avisos do validador que são permanentes por construção

`validar.py` termina com 57 avisos e exit 0. Três deles (`ps-aries-es-*` ×2,
`ps-consorcio-caparao-es-2026`) dizem que o município-sede de um registro intermunicipal não
credita cobertura. Isso é correto e **não deve ser silenciado**.

Atenção a uma leitura errada que é fácil de fazer: o texto desse aviso diz "declare a jurisdição em
`orgaos_vinculados[].municipios_slugs`", **e isso já foi feito** em 2026-10-02 (13 + 13 + 18). O
aviso continua aparecendo porque ele é disparado por `esfera == "intermunicipal"` no registro, sem
olhar se a composição do órgão está preenchida — ou seja, ele é informativo e permanente, não um
item de trabalho. Não "conserte" preenchendo coisa nenhuma: já está preenchido.

Os avisos de `descobertas.json` sobre as chaves `cobertura_municipios`,
`municipios_nao_mapeados` e `reconciliacao_ibge` ausentes desaparecem na primeira coleta — o
arquivo versionado é anterior ao cadastro. **Isso deixou de ser previsão e passou a ser medição:**
na execução local de 2026-10-02 os avisos caíram de 57 para 54 depois da coleta real, e os 3 que
saíram foram exatamente esses.

## Mapa dos documentos

| Arquivo | O que é |
| --- | --- |
| `.agents/design-cobertura-municipios.md` | Design, 3.688 linhas. Anexo A tem os 78 validados contra o IBGE; anexos B e C respondem às findings das reviews |
| `.agents/design-review-doc.md` / `.json` | Review do 3º passe: 2 HIGH, 11 MEDIUM, 8 NIT |
| `.agents/design-correcoes-aplicadas.md` | O que mudou em cada finding + a seção da clarificação do usuário |
| `.agents/plano-implementacao.md` | Plano em blocos A–E, 21 itens |
| `.agents/auditoria-cobertura-municipios.md` | Auditoria, 295 linhas, com saída real colada |
| `.agents/sondagem-2026-10-01.tsv` | Evidência bruta da sondagem dos domínios |
| `.agents/gerar_cadastro.py`, `promover-canais.py`, `transcrever_sondagem.py`, `apurar-orgaos.py` | Scripts auxiliares de uso único, versionados para auditabilidade. `apurar-orgaos.py` é o de 2026-10-02: resolve os 44 nomes de município dos três consórcios contra o cadastro e **aborta** se um não resolver |

Histórico honesto: o design levou 3 passes de review e **nunca recebeu `APPROVED`** — convergiu
6 HIGH → 4 HIGH → 2 HIGH e eu decidi encerrar o loop, porque as 13 findings restantes eram
coerência de especificação com correção já prescrita, não falha de arquitetura, e cada reescrita de
2.884 linhas dava ao revisor superfície nova. As 2 HIGH finais foram aplicadas no passe corretivo.
A segunda delas valeu o esforço todo: o casamento de texto era **cego a pontuação** —
`re.search(r'\bcim polinorte\b', 'ato do cim-polinorte...')` é `False` porque `normalizar()` não
colapsa pontuação — então todo nome ou sigla com hífen, ponto ou barra nunca casaria, e os aliases
ficavam de fora. Teria produzido cobertura aparentemente funcional com buraco invisível.

## Convenções do repositório

- **Só biblioteca padrão.** Sem `requests`, `beautifulsoup4`, `pyyaml`. Deliberado.
- **Python 3.9 e 3.11.** O sandbox tem 3.9, o CI usa 3.11. Evite `match` e `X | Y` em anotações
  avaliadas em runtime.
- **Português** em nomes, chaves, logs e comentários. O estilo local usa comentários longos
  explicando o *porquê* — é convenção forte deste código.
- **README nunca é editado à mão**: `python3 ferramentas/gerar_readme.py`.
- Não existe `CONTRIBUTING.md`.
