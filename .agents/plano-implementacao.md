# Plano de implementação — cobertura dos 78 municípios do ES

Plano derivado de `.agents/design-cobertura-municipios.md` (quarto passe, arquitetura aprovada) e
de `.agents/design-correcoes-aplicadas.md`. **Nada de arquitetura é redecidido aqui**; o que este
documento faz é sequenciar o trabalho em unidades implementáveis e verificáveis e registrar as
poucas decisões que o design deixou abertas (bloco "Decisões deste plano").

Todo caminho é absoluto a partir do worktree
`/projects/sandbox/Concursos-Publicos-ES/.worktrees/cobertura-municipios` (branch
`cobertura-78-municipios-es`). Caminho relativo cai no workspace pai — use sempre o absoluto.

## Baseline medido neste worktree (antes de qualquer mudança)

| Fato | Medição |
| ---- | ------- |
| `python3 ferramentas/validar.py` | exit 0, 0 erros, 24 avisos pré-existentes |
| `python3 ferramentas/gerar_readme.py --check` | exit 0 (README sincronizado, referência 01/10/2026) |
| Registros em `dados/` | **53** arquivos JSON (o brief fala em 54; o número real é 53 — 25 estaduais, 22 municipais, 4 intermunicipais, 2 federais) |
| `descobertas/descobertas.json` | 8 chaves de topo, 37 achados, 0 com `categoria`, `primeira_deteccao` 09-23(18)…10-01(2) |
| `fontes/fontes.json` | 38 fontes; 12 sem `esfera` (banca 7, portal_concursos 3, imprensa 2) |
| `/projects/sandbox/ibge_es.json` | 78 municípios; **os 78 códigos, nomes, slugs e microrregiões do Anexo A conferem 1:1** (conferido programaticamente) |
| Rede do ambiente | IBGE 200 (gzip), `https://ioes.dio.es.gov.br/dom/busca/busca/buscar/...` 200 (`hits.total` int = 63 no DOM e 16 no DIO, `_id` `11517_315`, `suplemento` "Edição 3099"), `https://www.vitoria.es.gov.br/` 200. Houve **um** timeout transitório no buscador: trate timeout isolado como ruído, não como fato |
| Python | sandbox 3.9.25; CI 3.11. Sem `match`, sem `X \| Y` em anotação avaliada em runtime |
| Data | `date -u` = 2026-10-01, igual à referência dos dados |

## Decisões deste plano (o que o design deixou aberto, ou onde ele conflita com o brief)

1. **O cadastro vive em `fontes/municipios-es.json`, não em `dados/municipios-es.json`.** O brief
   desta etapa pede `dados/`, mas o design §3 decide `fontes/` com razão lida no código
   (`dados/ESQUEMA.md` define "uma oportunidade = um arquivo JSON" e
   `validar.valida_diretorio()` reprova qualquer coisa fora dos seis subdiretórios de
   `comum.DIRETORIOS`), e §9.2/§10.1/§17 e a regra do `git add` sem `fontes/` dependem dessa
   escolha. Seguir o brief exigiria reabrir cinco seções do design aprovado; seguimos o design e
   registramos a divergência.
2. **Canal de diário dos 78 nasce `pendente` e é promovido depois.** `estado: "confirmado"` exige
   evidência observada, e o coletor que a produz só existe no bloco B. Então o bloco A escreve, para
   os 78, o canal `diario_oficial_agregador` (`fonte_id: "amunes-dom"`) com
   `estado: "pendente"`, `verificado_em: null`, `evidencia` dizendo "canal esperado do município;
   sem ato observado nesta curadoria" e pendência `canais:conferir_manual`; o item 15 promove a
   `confirmado` os municípios com ato em confiança alta numa coleta real. Isso satisfia §9.2 (existe
   canal de diário; pendência declarada) sem afirmar verificação que não houve.
3. **Timeout isolado não vira `nao_responde`.** §3.2 manda classificar timeout como
   `nao_responde`; medi um timeout transitório no buscador do IOES que depois respondeu em 1,0 s.
   Regra: `sondar_prefeituras.py` tenta **duas** vezes antes de concluir, e o resultado registrado em
   `evidencia` diz quantas tentativas houve. Se as duas falharem por timeout/DNS, vale a tabela de
   §3.2 (derivado não entra; catalogado entra `pendente` + `canais:nao_responde`).
4. **`canais:conferir_manual` é o motivo de qualquer canal `pendente` que não tenha resultado de
   sondagem conclusivo** (inclusive o canal de diário do item 2). O vocabulário de §3.1 tem três
   motivos e só este descreve "existe, falta conferência humana"; usar `nao_encontrado` seria dizer
   que se procurou e não há, o que é falso.
5. **Nenhum dos 53 registros de `dados/` é tocado.** O reforço de §9.3 foi conferido contra os 18
   valores distintos de `municipio`: os únicos dois fora do nome oficial do IBGE são
   `"Âmbito estadual (ES)"` (24×) e `"Diversos (ES) - Linhares e região"` (1×), ambos aceitos pelo
   ramo explícito do validador.
6. **Verificação não depende do buscador do IOES.** `ferramentas/testes.py` exercita o parsing com
   envelopes literais (função pura `_achados_de_resposta`); as execuções com rede
   (`--dry-run`, `--autoteste-ioes`, sondagem) são conferência adicional, nunca o único verificador.

## Convenções de execução (valem para todos os itens)

- Rodar sempre de dentro do worktree, com `DATA_REFERENCIA=2026-10-01` quando o resultado depender
  da data, para reprodutibilidade.
- **Nunca** rodar `python3 ferramentas/coletar.py` sem `--dry-run`, exceto no item 13
  (`--migrar-descobertas`): uma gravação real sobrescreveria `descobertas/descobertas.json`.
- `README.md` **só** muda por `python3 ferramentas/gerar_readme.py` (nunca à mão).
- `.agents/` é área de trabalho do agente: **nunca** entra em `git add`.
- Ao fim de cada item, `git status --short` não deve mostrar arquivo inesperado.

---

# Implementation Plan

## Bloco A — cadastro, catálogo e camada de leitura

- [ ] 1. Mover `_sem_acento`/`normalizar`/`slug` de `coletar.py` para `comum.py` **sem alterar a
      implementação**, acrescentar `chave_nome()` e `_padrao_de_chave()` (§3.3, §5.1) e os
      vocabulários novos (`ESFERAS_FONTE_VALIDAS`, `TIPOS_FONTE_COM_ESFERA`, `TIPOS_CANAL`,
      `NATUREZAS_ORGAO_VINCULADO`, `MOTIVOS_PENDENCIA`, `CATEGORIAS_ACHADO`, `ESCOPOS_MUNICIPIO`,
      `ORIGENS_MUNICIPIO`, `CAMINHO_MUNICIPIOS`). Em `coletar.py`, substituir as três definições por
      delegação (`normalizar = comum.normalizar`, etc.) para que nenhum call site existente mude
      (`coletar.py` usa `normalizar` nas linhas 133/324/330 e `slug` na 346).
      Files: `ferramentas/comum.py`, `ferramentas/coletar.py`
      Verify: `python3 ferramentas/validar.py` (exit 0) e `python3 ferramentas/gerar_readme.py --check`
      (exit 0) continuam passando; `python3 -c "import sys; sys.path.insert(0,'ferramentas'); import comum; p=comum._padrao_de_chave('CIM Polinorte'); assert all(p.search(comum.normalizar(t)) for t in ['ato do cim polinorte','ato do cim-polinorte','ato do cim/polinorte','ato do cim.polinorte']); assert not p.search('vila, '+'\x00'*20+', polinorte')"`
      não levanta.

- [ ] 2. Criar `fontes/municipios-es.json` com os 78 municípios (§3.1): `codigo_ibge`, `nome` e
      `microrregiao` copiados de `/projects/sandbox/ibge_es.json` (rebaixar para a API do IBGE só se o
      arquivo faltar), `slug` calculado por `comum.slug()`, `aliases` `[]` exceto Cachoeiro de
      Itapemirim (`["Cachoeiro do Itapemirim", "Cachoeiro"]`, §3.3), um canal
      `diario_oficial_agregador` `pendente` por município (decisão 2 deste plano) e
      `pendencias_verificacao: ["canais:conferir_manual"]`; mais `orgaos_vinculados` com as **8**
      entradas enumeradas em §4.1, com `pendencias_verificacao` exatamente como a tabela manda.
      Cabeçalho com `descricao`, `fonte_da_verdade`, `ibge_consultado_em: "2026-10-01"`,
      `total_esperado: 78`, `ultima_atualizacao`. Gerar por script descartável (não versionado) para
      não digitar 78 entradas à mão; gravar `ensure_ascii=False`, `indent=2`, newline final.
      Files: `fontes/municipios-es.json`
      Verify: `python3 -c` conferindo contra `/projects/sandbox/ibge_es.json` que há exatamente 78
      entradas, 0 `codigo_ibge` duplicado, 0 slug duplicado, 0 código faltante/excedente e
      `slug == comum.slug(nome)` em todas; `python3 ferramentas/validar.py` segue exit 0.

- [ ] 3. Acrescentar a `comum.py` o acesso ao cadastro: `carregar_municipios()` (erro com o caminho
      no texto, no estilo de `carregar_registros()`), `IndiceMunicipios` (namedtuple de 7 campos),
      `indice_municipios()` com `functools.lru_cache(maxsize=1)` — `por_slug`, `por_chave_nome`
      (nomes, aliases e nomes de órgão que resolvem para 1 slug), `padroes_ordenados`
      (`(padrao, slug, origem)`, uma entrada por nome **e** por alias, ordenada por comprimento
      decrescente de `chave_nome`), `padroes_orgaos` (`nome` e `sigla` com ≥3 caracteres),
      `orgaos_por_id`, `total_esperado`, `max_tokens_nome` **calculado** —, e as duas resoluções
      `resolver_municipio()` (consulta exata) e `resolver_municipio_em_texto()` (longest-first com
      máscara `"\x00"`, devolvendo `(None, None)` para zero **ou mais de um** município).
      Files: `ferramentas/comum.py`
      Verify: `python3 -c` assertando `resolver_municipio("Anchieta") == ("anchieta","nome")`,
      `resolver_municipio("Prefeitura de Anchieta") == (None,None)`,
      `resolver_municipio("Camara Municipal de Aracruz") == ("aracruz","orgao_vinculado")`,
      `resolver_municipio_em_texto("Prefeitura de Serra e de Vila Velha") == (None,None)` e
      `indice_municipios().max_tokens_nome == 8`; `python3 ferramentas/validar.py` exit 0.

- [ ] 4. Criar `ferramentas/testes.py` (`unittest` stdlib, executável por
      `python3 ferramentas/testes.py`) com os casos da camada `comum` previstos em §16: `slug()`
      sobre os 78 nomes comparado com **lista literal escrita no próprio teste** (dupla
      contabilidade, comentada), `chave_nome()` nas três grafias de "S. Mateus",
      `_padrao_de_chave()` nas quatro formas de `CIM Polinorte` **e** a não-travessia da máscara
      `\x00`, as duas resoluções de município (incluindo ambiguidade e `orgao_vinculado`),
      imutabilidade do índice (`AttributeError` ao atribuir campo) e `indice_municipios.cache_clear()`
      entre casos.
      Files: `ferramentas/testes.py`
      Verify: `python3 ferramentas/testes.py` (exit 0, todos os casos passam) no Python 3.9 do sandbox.

- [ ] 5. Criar `ferramentas/sondar_prefeituras.py` (uso único, fora do workflow, sem escrever no
      cadastro, §3.2): deriva `https://www.<slug sem hifens>.es.gov.br/`, substitui pelo candidato do
      catálogo quando houver fonte elegível (as 6: Vitória, Anchieta, Santa Maria de Jetibá, Aracruz,
      Cachoeiro, Vila Velha — raiz → `portal_prefeitura`, com caminho → `secao_concursos` com o
      caminho preservado), sonda com o `User-Agent` do projeto, sem seguir redirecionamento, timeout
      12 s, **duas tentativas** (decisão 3), e imprime TSV
      `slug / tipo / status / url / estado / pendência`. Rodar a sondagem e transcrever o resultado
      para `fontes/municipios-es.json` como canais tipados — 2xx/3xx → `confirmado` com
      `verificado_em` da sondagem; 403/406/429 → `pendente` + `canais:conferir_manual`; 404/NXDOMAIN/
      timeout nas duas tentativas → derivado não entra, catalogado entra `pendente` +
      `canais:nao_responde`. `evidencia` obrigatória em todo canal, citando a sondagem e o resultado.
      Precedência: diário fica em `1`; portal/seção recebem `2, 3, …`.
      Files: `ferramentas/sondar_prefeituras.py`, `fontes/municipios-es.json`
      Verify: `python3 ferramentas/sondar_prefeituras.py` imprime 78 linhas TSV e sai 0;
      `python3 -c` conferindo que todo canal tem `evidencia` não vazia, que `estado=="confirmado"`
      implica `verificado_em` não nulo e não futura, que `precedencia` é única por município e que
      `precedencia 1` é canal de diário; `python3 ferramentas/validar.py` exit 0.

- [ ] 6. Em `fontes/fontes.json`: preencher `"esfera": "nao_se_aplica"` nas 12 fontes sem o campo
      (banca 7, portal_concursos 3, imprensa 2 — §8), acrescentar as duas fontes novas
      `ioes-busca-dio` (`esfera: "estadual"`, com `observacao` dizendo que o índice inclui o caderno
      dos municípios) e `ioes-busca-dom` (`esfera: "municipal"`), ambas `tipo: "diario_oficial"`,
      `prioridade: 1`, `coletada_automaticamente: true`, e atualizar `ultima_atualizacao`.
      Files: `fontes/fontes.json`
      Verify: `python3 -c` assertando 40 fontes, nenhuma sem `esfera`, `esfera == "nao_se_aplica"`
      exatamente onde `tipo ∉ {oficial, diario_oficial}`, e ids únicos;
      `python3 ferramentas/validar.py` exit 0.

- [ ] 7. Criar `fontes/README.md` documentando os dois arquivos de `fontes/`, o vocabulário de `tipo`
      de canal e a regra de precedência (§3.1.1), o vocabulário de pendência com o produtor de cada
      motivo, o `User-Agent` usado na sondagem (o resultado depende dele) e a regra de admissão de
      alias (§3.3, imposta na revisão de PR e não pelo validador).
      Files: `fontes/README.md`
      Verify: `python3 ferramentas/validar.py` exit 0 e `python3 ferramentas/gerar_readme.py --check`
      exit 0 (o arquivo novo não afeta nenhum dos dois, o que é a confirmação de que nada regrediu).

## Bloco B — coletor (depende do bloco A)

- [ ] 8. Em `coletar.py`, acrescentar a infraestrutura de leitura e limpeza de texto: `_ler_bytes()`
      com `Accept-Encoding: identity` **e** `gzip.decompress()` quando o servidor responder gzip
      (o IBGE responde comprimido sem pedir), `_ler_com_retry()` com 1 retentativa após 2 s só para
      `URLError`/`socket.timeout`/`HTTPError >= 500`, `MES`, `PADROES_BOILERPLATE` (as 5 formas de
      §5.3, sem `protocolo \d+`), `_limpar_boilerplate()`, `DELIMITADOR_BLOCO`/`_blocos_de_ato()`
      (§6.5), `MARCAS_ANTES`/`MARCA_DEPOIS` (§5.3), `FRASES_IOES` e as duas bases de escopo.
      Files: `ferramentas/coletar.py`
      Verify: `python3 ferramentas/testes.py` com casos novos de `_limpar_boilerplate()` (as 4 formas
      reais de assinatura: dia da semana, data numérica, "de setembro 2026" sem o segundo "de",
      `cep:` — `"vitoria"` desaparece, o corpo do ato permanece) e de `_blocos_de_ato()` (3
      `protocolo N` → 3 blocos; sem delimitador → 1 bloco; bloco <40 caracteres descartado).

- [ ] 9. Implementar o casamento de município e órgão por bloco (§5.2, §5.2.1): passada de órgãos
      antes da de municípios, `finditer` coletando todas as ocorrências de um padrão, avaliação de
      confiança na janela 45/6 **sobre o texto mascarado** com `MARCA_DEPOIS.match` (não `search`),
      e só depois `sub` mascarando o padrão inteiro com `"\x00"` do mesmo comprimento; herança de
      município por aridade de `municipios_slugs` do órgão e `municipio_origem` gravado. Proibido usar
      `_coberto()` para município.
      Files: `ferramentas/coletar.py`
      Verify: `python3 ferramentas/testes.py` com os casos medidos: `"prefeitura de vila velha serra"`
      → `vila-velha` **alta** e `serra` **baixa**; `"municipio de santa maria de jetiba linhares"` →
      `linhares` **baixa**; `"Conceição do Castelo"` não credita Castelo; `"Cachoeiro de Itapemirim"`
      não credita Itapemirim; `"MUNICIPIO DE CACHOEIRO DO ITAPEMIRIM/ES"` → `cachoeiro-de-itapemirim`
      com `municipio_origem == "alias"` e confiança alta; `"instituto de previdencia dos servidores de
      cariacica"` e `"IPC"` → `orgao_vinculado_id == "ipc-cariacica"`; `"ARIES"` → slug `None`, escopo
      `intermunicipal`; regressão da armadilha Vitória (`("vitoria","alta")` ausente).

- [ ] 10. Implementar `_achados_de_resposta(envelope, escopo, frase, indice)` (pura, com os seis
      estágios de §6.5, pareamento de edital de §6.5, forma do achado de §6.7 e a validação por item
      de §13.1 usando **só** `.get()`, sem propagar `KeyError`/`TypeError`) e `coletar_ioes()`
      (paginação 0-based, `di:` pela janela, tetos, `time.sleep(0.2)`, diagnóstico em dict,
      ordenação explícita e colapso por `chave` antes do `return`, remoção de `_diario_id`/`_pagina`);
      registrar `ioes-busca-dio`/`ioes-busca-dom` em `FONTES` via `functools.partial`, criar
      `FONTES_COM_DIAGNOSTICO` e os argumentos de §13.3.
      Files: `ferramentas/coletar.py`
      Verify: `python3 ferramentas/testes.py` com envelopes literais (incluindo
      `{"hits": {"hits": [{}]}}`, `_source: null` e `hits.hits: "texto"` → `[]` sem exceção; dois
      envelopes embaralhados com o mesmo `sort` → mesma lista final; chave estável entre duas
      execuções); conferência com rede, opcional e não bloqueante:
      `python3 ferramentas/coletar.py --dry-run --fonte ioes-busca-dom --sem-conferir-ibge` sai 0 e
      relata municípios resolvidos.

- [ ] 11. Implementar a detecção de município não mapeado (§7.2): `PADROES_MENCAO` sobre o texto
      normalizado e limpo **por página** (estágio 4), `MAX_TOKENS_CANDIDATO = 4`,
      `classificar_mencao()` por prefixo de tokens usando `indice.max_tokens_nome`, os filtros
      obrigatórios (mínimo de caracteres, tokens genéricos, UF/capital de outro estado,
      `paginas_distintas >= 2 OR com_marca_uf`, consolidação por prefixo), `provavel_alias_de`
      conservador, e a **fusão acumulada** entre execuções com a regra escrita em §7.2, incluindo a
      remoção por `ultima_deteccao < referencia - janela*4`. Mudar `carregar_anterior()` para devolver
      `(achados_por_chave, bruto)` e atualizar o único call site.
      Files: `ferramentas/coletar.py`
      Verify: `python3 ferramentas/testes.py` com: `"joao neiva por falta disciplinar e"` →
      `("mapeado","joao-neiva")`; `"que trata esta lei"` → candidato; detecção **por injeção**
      (índice sem `sooretama` + trecho `"MUNICÍPIO DE SOORETAMA/ES"` → candidato; com o cadastro
      completo → nenhum); 1 ocorrência sem `/ES` descartada e com `/ES` aceita; fusão `1/1` + 1 nova
      ocorrência → `2/2` reportado, `primeira_deteccao` preservada, candidato de 29 dias removido.

- [ ] 12. Fechar o pipeline em `main()`: `normalizar_achado(achado, indice)` (ponto único, com
      `setdefault` e `resolver_municipio_em_texto` sobre `municipio` + `orgao` concatenados),
      `casar_estrito()` para `ato_diario`, filtro `novos` (só `oportunidade`) + `atos_novos`, backfill
      de `previo` nos **dois** ramos de preservação, retenção de `ato_diario`
      (`--retencao-atos-dias`, padrão 90, teto 365, `descartados_por_retencao`), `cobertura()` pura de
      5 parâmetros (§7.4), reconciliação IBGE com `--conferir-ibge`/`--sem-conferir-ibge`, as chaves
      novas do `saida`, `monta_relatorio_md(novos, relatorio_fontes, referencia, contexto)` com as
      seções condicionais e as saídas novas de `--saida-github` (`nao_mapeados`, `divergencia_ibge`,
      `municipios_com_sinal`, `primeira_vez`, `atos_diario_novos`, `truncado` agregado).
      Files: `ferramentas/coletar.py`
      Verify: `python3 ferramentas/testes.py` com: `normalizar_achado` sobre achado real de
      `concursosnobrasil-es` (`orgao: "Prefeitura de Anchieta"` → slug `anchieta`, escopo `municipal`,
      confiança `baixa`, origem `nome`), achado `SEDU`/`estadual` → `null`/`estadual`, achado
      `ato_diario` com confiança alta não sobrescrito; `casar_estrito()` nos três casos (sem número
      não casa, com `001/2026` casa, URL igual casa — e o mesmo achado em `casar()` **casaria**);
      filtro de novidade (2 oportunidades + 5 atos → `len(novos)==2`, `len(atos_novos)==5`); retenção
      (100 dias descartado e contado, 80 preservado, `oportunidade` intocada); `cobertura()` nos cinco
      recortes de §16, incluindo `com_registro_curado == 15` sobre os registros reais **e**
      `registros_intermunicipais_sem_atribuicao == 4`, janela vs acumulado, histórico monotônico e
      delta.

- [ ] 13. Acrescentar `--migrar-descobertas` (aplica `normalizar_achado()` a cada achado e regrava,
      sem rede, idempotente, preservando as chaves de topo) e **rodar** a migração no arquivo
      versionado, commitando o resultado junto com o código.
      Files: `ferramentas/coletar.py`, `descobertas/descobertas.json`
      Verify: `python3 ferramentas/coletar.py --migrar-descobertas` sai 0; rodar duas vezes produz
      arquivo idêntico (`git diff` vazio na segunda); `python3 -c` conferindo 37 achados, todos com
      `categoria` e `municipio_escopo`, `primeira_deteccao` preservada e as 8 chaves de topo intactas;
      `python3 ferramentas/testes.py` com o caso que compara as chaves do achado migrado com as de um
      achado novo normalizado.

- [ ] 14. Promover a `confirmado` os canais de diário dos municípios com ato observado: rodar
      `python3 ferramentas/coletar.py --dry-run --fonte ioes-busca-dom --fonte ioes-busca-dio` e, para
      cada slug com `municipio_confianca == "alta"`, atualizar o canal `diario_oficial_agregador` em
      `fontes/municipios-es.json` para `estado: "confirmado"`, `verificado_em` da coleta e `evidencia`
      citando o ato observado e a janela; retirar a pendência `canais:conferir_manual` quando ela
      existia **apenas** por causa desse canal. Municípios sem ato na janela permanecem `pendente` —
      é resultado correto (§3.2), não lacuna.
      Files: `fontes/municipios-es.json`
      Verify: `python3 -c` conferindo que todo canal `confirmado` tem `verificado_em` não nula e não
      futura, que todo município com algum canal `pendente` declara pendência de `canais`, e que todos
      os 78 seguem com canal de diário; `python3 ferramentas/validar.py` exit 0;
      `python3 ferramentas/testes.py` exit 0.

## Bloco C — validador (depende dos blocos A e B)

- [ ] 15. Acrescentar a `validar.py` as duas funções de arquivo, recebendo o dado **já carregado**
      (`valida_catalogo_fontes(rel, catalogo)` com import tardio de `coletar` para checar
      `coletada_automaticamente`, e `valida_cadastro_municipios(rel, cadastro, catalogo)` com todas as
      linhas de §9.1 e §9.2, incluindo canais, precedência, `estado`⇄`verificado_em`⇄pendência, a
      exigência "canal de diário **ou** `canais:nao_encontrado`", e `orgaos_vinculados` com a mesma
      severidade de `municipios`), mais os wrappers finos de leitura (ausência/JSON inválido = erro
      fatal) e as chamadas em `main()`; estender `--json` com `fontes`, `municipios`,
      `orgaos_vinculados`, `municipios_sem_cobertura`, `atos_diario` e `descartados_por_retencao`.
      Files: `ferramentas/validar.py`
      Verify: `python3 ferramentas/validar.py` exit 0 no repositório real;
      `python3 ferramentas/validar.py --json` traz as chaves novas; `python3 ferramentas/testes.py`
      com um dict em memória por defeito de §9.1/§9.2 **e** os casos "ok" que não devem gerar erro
      (município com um único canal de agregador confirmado; canal `pendente` com `verificado_em:
      null` + `canais:conferir_manual`; `agencia_reguladora` com 0 slugs e pendência).

- [ ] 16. Reforçar `valida_escopo()` (resolver `municipio` pelo cadastro com
      `comum.resolver_municipio()`; aceitar `"Âmbito estadual (ES)"` e prefixo `"Diversos (ES)"`;
      erro quando não resolve; avisos para `origem == "alias"`, `origem == "orgao_vinculado"` e
      registro intermunicipal cuja sede resolve) e `valida_descobertas()` (todas as linhas de §9.4:
      vocabulários, tolerância de legado por achado com fronteira `<= ibge_consultado_em`, coerência
      `municipio_codigo_ibge`/`municipio_slug`, contadores de menção com
      `paginas_distintas <= ocorrencias` e `len(exemplos) <= 3`, as quatro checagens de conjuntos de
      `cobertura_municipios`, aviso de `len(achados) > 5000`, aviso de chave de topo ausente).
      Files: `ferramentas/validar.py`
      Verify: `python3 ferramentas/validar.py` exit 0 (e os 3 avisos novos esperados de registro
      intermunicipal aparecem, sem virar erro); `python3 ferramentas/testes.py` com a tolerância de
      legado nos quatro casos (anterior → aviso, **igual** → aviso, posterior → erro,
      `categoria: "lixo"` → erro sempre).

## Bloco D — consumidores, esquema e workflow

- [ ] 17. Atualizar `gerar_readme.py`: filtro de `ato_diario` em `carregar_descobertas()`, três linhas
      novas no Panorama e a seção "Cobertura por município" em `<details>` com as 78 linhas
      (`Ato detectado` por pertinência a `slugs_com_achado_acumulado`; `Canal principal` pelo canal de
      `precedencia: 1` em texto legível), tratando `cobertura_municipios` ausente como `0`/`—` (§11.1);
      `carregar_municipios()` falhando aqui é fatal. Depois **regenerar** o README pelo gerador.
      Files: `ferramentas/gerar_readme.py`, `README.md`
      Verify: `python3 ferramentas/gerar_readme.py` grava; `python3 ferramentas/gerar_readme.py
      --check` exit 0; rodar o gerador duas vezes não muda o arquivo (determinismo);
      `python3 ferramentas/testes.py` com o caso "descobertas sem `cobertura_municipios`" → Panorama
      `0`, 78 linhas com `—`, `Registros curados` e `Canal principal` preenchidos.

- [ ] 18. Atualizar `gerar_relatorio.py` (`bloco_coleta()` separando oportunidades de atos de diário,
      com `atos_diario_novos`, `descartados_por_retencao`, sub-bloco "Cobertura municipal" e agregação
      por microrregião) e `gerar_email.py` (ignorar `ato_diario` em `classificar_descobertas()`, bloco
      curto de cobertura, `carregar_estado()` devolvendo 3 valores e `gravar_estado()` recebendo
      `cobertura_vistos`, com os dois call sites de `main()` e o ramo de estado corrompido devolvendo
      `({}, {}, {})`).
      Files: `ferramentas/gerar_relatorio.py`, `ferramentas/gerar_email.py`
      Verify: `python3 ferramentas/gerar_relatorio.py --tipo diario` exit 0 e `git status --short`
      sem arquivo inesperado; `python3 ferramentas/gerar_email.py` exit 0 ou 2 (2 = nada novo, é o
      estado atual); `python3 ferramentas/testes.py` com o caso de `carregar_estado()` (estado sem
      `cobertura_vistos` → `{}` na terceira posição; corrompido → `({}, {}, {})`).

- [ ] 19. Atualizar `dados/ESQUEMA.md`: parágrafo distinguindo a `esfera` do registro (vocabulário de
      quatro valores, **inalterado**) da `esfera` da fonte (`+ nao_se_aplica`), e referência a
      `fontes/municipios-es.json` como vocabulário do campo `municipio`.
      Files: `dados/ESQUEMA.md`
      Verify: `python3 ferramentas/validar.py` exit 0 e `python3 ferramentas/gerar_readme.py --check`
      exit 0 (nenhum registro de `dados/` muda, o que é o ponto).

- [ ] 20. Atualizar `.github/workflows/monitoramento.yml`: `fontes/**` e o próprio YAML nos gatilhos
      de `pull_request` e `push` (mantendo `descobertas/**` e `README.md` fora do `push`), condição da
      issue com as quatro cláusulas de §10.2, título montado com `if/then/fi` em quatro partes
      (§7.5) e o passo `python3 ferramentas/testes.py` em **dois** lugares (no job `validar`, antes de
      `validar.py`; no job `atualizar`, antes de "Revalidar depois das alteracoes").
      Files: `.github/workflows/monitoramento.yml`
      Verify: `python3 -c "import json; print('yaml ok')"` não serve — conferir com
      `python3 ferramentas/testes.py` (caso que lê o YAML como texto e assere `fontes/**` nos dois
      gatilhos, as quatro cláusulas da condição e os dois passos de teste) e, se `actionlint` estiver
      disponível no ambiente, rodá-lo; `python3 ferramentas/validar.py` exit 0.

## Bloco E — auditoria final

- [ ] 21. Auditoria completa ponta a ponta e correção do que ela achar: rodar a bateria inteira
      (`testes.py`, `validar.py`, `validar.py --json`, `gerar_readme.py --check`,
      `coletar.py --dry-run` com as quatro fontes, `coletar.py --dry-run --sem-conferir-ibge`,
      `coletar.py --autoteste-ioes`, `gerar_relatorio.py --tipo diario`, `gerar_email.py`), conferir
      compatibilidade 3.9 (o sandbox **é** 3.9; nenhuma sintaxe 3.10+), degradação graciosa (simular
      fonte fora do ar e exigir que a coleta siga e registre `status: "erro"`), os dois caminhos de
      detecção de município novo (B por texto, C por IBGE) e que os 53 registros de `dados/` seguem
      intactos (`git diff --stat dados/` vazio). Registrar o resultado em
      `.agents/auditoria-cobertura-municipios.md`, com uma linha por item auditado e o veredito.
      Files: `.agents/auditoria-cobertura-municipios.md` (+ correções onde a auditoria apontar)
      Verify: a bateria acima toda verde (`testes.py`, `validar.py`, `gerar_readme.py --check` com
      exit 0); `git status --short` mostrando apenas os arquivos previstos no plano e `.agents/`
      (nunca estagiado).

## Pendências declaradas (não são lacunas; são o resultado honesto)

- Canais `portal_prefeitura`/`secao_concursos` dos municípios cujo candidato derivado não responder
  ou responder 403 — `pendente` + pendência, nunca URL inventada (§3.2, §18.1).
- `diario_oficial_proprio` só para a Serra, e mesmo esse depende de conferência do seletor do IOES
  (§18.2); os demais nascem com o canal do agregador.
- `plataforma_inscricao` e `banca` por município nascem ausentes, porque a evidência existe por
  certame e não por município (§18.3).
- Composição de CIM Polinorte, Consórcio Caparaó e ARIES (`municipios_slugs: []` + pendência).
- `aliases` nasce com 2 entradas e cresce pelas issues de `municipios_nao_mapeados`.
- O brief desta etapa pede o cadastro em `dados/`; este plano segue o design (`fontes/`) — ver
  decisão 1.
