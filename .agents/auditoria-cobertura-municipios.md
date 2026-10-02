# Auditoria da cobertura dos 78 municípios do ES (item 21 do plano / FEAT-005)

Branch `cobertura-78-municipios-es`, worktree
`/projects/sandbox/Concursos-Publicos-ES/.worktrees/cobertura-municipios`.
Ambiente: Python **3.9.25** (o CI usa 3.11), `DATA_REFERENCIA=2026-10-01`, rede disponível.
Todos os comandos foram executados a partir da raiz do worktree.

O usuário pediu explicitamente para verificar **se o GitHub Actions consegue achar os municípios
novos e se não há bugs**. A resposta curta: **consegue, pelos dois caminhos**, e a auditoria achou
**um defeito real**, que foi corrigido e coberto por teste (linha X1/X2 abaixo). Nenhum outro
defeito de código ou de dado foi encontrado.

Regra seguida em toda simulação destrutiva: o arquivo real **nunca** foi escrito. Cadastro
reduzido, catálogo inválido, base do IOES em host inexistente e `descobertas.json` malformado
viveram em arquivo/diretório temporário ou em renomeação com `trap EXIT`, e cada bloco termina
confirmando `sha256` idêntico e `git status --short` limpo. Os roteiros de auditoria ficaram em
`/projects/sandbox/_audit/` (fora do repositório, não versionados).

---

## 1. Bateria completa

| # | Comando | Resultado | Veredito |
| - | ------- | --------- | -------- |
| B01 | `python3 ferramentas/testes.py` | `Ran 175 tests ... OK` | exit 0 — **ok** |
| B02 | `python3 ferramentas/validar.py` | `Validacao aprovada.` — 0 erros, 57 avisos | exit 0 — **ok** |
| B03 | `python3 ferramentas/validar.py --json` | registros 53, descobertas 37, fontes 40, municipios 78, orgaos_vinculados 8, municipios_sem_cobertura 21, atos_diario 0, descartados_por_retencao 0 | exit 0 — **ok** |
| B04 | `python3 ferramentas/gerar_readme.py --check` | `README.md esta sincronizado com os dados (referencia 01/10/2026).` | exit 0 — **ok** |
| B05 | `DATA_REFERENCIA=2026-10-01 python3 ferramentas/coletar.py --dry-run` | 4 fontes `ok` (concursosnobrasil-es 15, ioes-busca-dio 58, ioes-busca-dom 261, selecao-es 271) = 358 achados, 1 novo, 46/78 com sinal, `--dry-run: nada gravado.` | exit 0 — **ok** |
| B06 | `python3 ferramentas/coletar.py --dry-run --sem-conferir-ibge` | mesma coleta, sem consulta ao IBGE | exit 0 — **ok** |
| B07 | `python3 ferramentas/coletar.py --autoteste-ioes` | DIO 58 achados / 17 municípios (14 em alta); DOM 261 / 43 (41 em alta); 3 candidatos não mapeados, todos 1/1 | exit 0 — **ok** |
| B08 | `python3 ferramentas/gerar_relatorio.py --tipo diario` | relatório do dia já atualizado | exit 0 — **ok** |
| B09 | `python3 ferramentas/gerar_email.py` | `Nenhuma novidade ou alteracao relevante desde o ultimo resumo.` | exit **2** (estado "nada novo", previsto) — **ok** |
| B10 | `python3 -m py_compile ferramentas/*.py` | sem saída | exit 0 — **ok** |
| B11 | `coletar.py --dry-run --saida-github <arq>` | `novos=1 pendentes=325 total=358 nao_mapeados=0 divergencia_ibge=0 municipios_com_sinal=46 primeira_vez=48 atos_diario_novos=313 truncado=0` | as 9 saídas que o workflow consome estão presentes — **ok** |

`gerar_email.py` sair 2 é o contrato (`0` = há novidade, `2` = nada mudou); qualquer outro código
seria erro real.

## 2. Caminho (B) — município novo detectado pelo **texto do diário**

Executado ponta a ponta por `coletar.main()` com o cadastro apontado para uma cópia temporária, a
fonte `ioes-busca-dom` real e descobertas em diretório temporário.

| # | Comando / cenário | Resultado | Veredito |
| - | ----------------- | --------- | -------- |
| B-1 | cadastro **sem** `sooretama`, coleta real do DOM | `exit=0`, `municipios_nao_mapeados=['sooretama']`, `nao_mapeados=1` no `--saida-github` | **ok** — o caminho positivo existe e chega ao `$GITHUB_OUTPUT` |
| B-2 | cadastro **completo**, mesmo dia e mesma fonte | `exit=0`, `municipios_nao_mapeados=[]`, `nao_mapeados=0` | **ok** — nenhum falso positivo |
| B-3 | condição da issue no workflow (W6) | cláusula `nao_mapeados != '0' && != ''` presente | **ok** — a detecção de B-1 abre issue mesmo com `novos=0` |
| B-4 | título da issue com `nao_mapeados=1` e `novos=0` | `Coleta automatica: 1 municipio(s) sem mapeamento — 2026-10-01` | **ok** — o título diz o motivo real |
| B-5 | corpo da issue (`--relatorio-md`) | escrito **incondicionalmente** em `main()`, antes do `return` de `--dry-run`; cita o candidato não mapeado | **ok** — a issue nunca abre sem corpo |

"Lista vazia" em B-2 **não** é mecanismo morto: B-1 prova o caminho positivo com o mesmo código e a
mesma página do diário.

## 3. Caminho (C) — município novo detectado pela **lista do IBGE**

| # | Comando / cenário | Resultado | Veredito |
| - | ----------------- | --------- | -------- |
| C-1 | `reconciliar_ibge()` com o cadastro real | `status=ok total_ibge=78 total_cadastro=78`, `ausentes_no_cadastro=[] excedentes_no_cadastro=[] nomes_divergentes=[]`, `divergencia=0` | **ok** |
| C-2 | cadastro temporário **sem** `sooretama` | `status=ok total_ibge=78 total_cadastro=77`, `ausentes_no_cadastro=[{'codigo_ibge': 3205010, 'nome': 'Sooretama'}]`, `divergencia=1` | **ok** — acusa a ausência e nomeia o município |
| C-3 | mesma divergência via `coletar.main() --conferir-ibge` | `divergencia_ibge=1` no `--saida-github`; bloco `reconciliacao_ibge` gravado com `ausentes_no_cadastro` | **ok** — chega ao workflow |
| C-4 | cadastro versionado depois de C-1..C-3 | conteúdo **byte-idêntico**; `git status --short` só com `.agents/` | **ok** — a reconciliação **não** escreve no cadastro |
| C-5 | endpoint do IBGE em host inexistente | `status=erro`, `erro='URLError: ...'`, `divergencia=0`, coleta segue | **ok** — IBGE fora do ar não derruba nada |
| C-6 | 79º município acrescentado à mão (cópia temporária, `total_esperado=79`) | `valida_cadastro_municipios`: **0 erros**; 1 aviso `total_esperado=79 difere dos 78 municipios conhecidos: confira contra o IBGE` | **ok** — município novo é aviso, não reprovação (§9.2 / borda 23) |
| C-7 | 79 entradas com `total_esperado=78` | 1 **erro** `len(municipios)=79 difere de total_esperado=78` | **ok** — incoerência interna reprova |
| C-8 | tabela de cobertura do README com 79 | 81 linhas (79 + 2 de cabeçalho), `Vila Nova do Teste` presente | **ok** — nenhum literal 78 no gerador |

## 4. Degradação graciosa

| # | Comando / cenário | Resultado | Veredito |
| - | ----------------- | --------- | -------- |
| D-1 | `BASES_IOES['dom']` em host inexistente, coleta das duas fontes IOES | `ioes-busca-dom status=erro achados=0 erro='RuntimeError: buscador do IOES indisponivel no escopo dom: 2 tentativa(s) sem resposta utilizavel'`; `ioes-busca-dio status=ok achados=58`; **exit 0** | **ok** — fonte fora do ar não derruba a coleta |
| D-2 | o mesmo com `--exigir-fonte` e só a fonte morta | `ERRO: nenhuma fonte respondeu.` + `::error::nenhuma fonte respondeu nesta coleta`, **exit 1** | **ok** — a flag faz o que promete |
| D-3 | `_achados_de_resposta()` com 9 envelopes malformados (`{}`, `hits: None`, `hits.hits: "texto"`, `hits.hits: [{}]`, `_source: null`, `_id` fora do padrão, `conteudo: 42`, `hits.hits: None`, `total` negativo) | lista vazia nos 9, **nenhuma exceção** | **ok** — o contrato de §12 ("não propaga KeyError/TypeError") se sustenta |
| D-4 | `fontes/fontes.json` com JSON inválido → `coletar.py` | `::warning::catalogo de fontes ilegivel; metadados de fonte ficarao ausentes`, **exit 0** | **ok** — recuperável, como §12 manda |
| D-5 | `fontes/fontes.json` com JSON inválido → `validar.py` | `ERRO FATAL: nao foi possivel ler o catalogo de fontes (<caminho>): JSON invalido em <caminho>: ...`, **exit 1** | **ok** — fatal e com o caminho |
| D-6 | `--max-paginas-ioes 2` (teto forçado) | 2 avisos `coleta truncada em 'concurso publico' (20 de 63 hits lidos)` / `'processo seletivo' (20 de 131)`, `truncado=1` no `--saida-github` | **ok** — truncamento é visível, não silencioso |
| D-7 | `--janela-ioes-dias 0`, `--max-paginas-ioes 1000`, `--retencao-atos-dias 0` | `parser.error` com faixa explícita, **exit 2** nos três | **ok** — tetos de §13.3 valem |
| D-8 | catálogo e cadastro restaurados | `sha256` idêntico nos dois; `git status --short` só com `.agents/` | **ok** |

## 5. Configuração ilegível é fatal (§12)

Cadastro renomeado e, depois, com JSON truncado; restaurado por `trap EXIT`.

| # | Comando | Resultado | Veredito |
| - | ------- | --------- | -------- |
| F-1 | `validar.py` sem o cadastro | `ERRO FATAL: nao foi possivel ler o cadastro de municipios (<caminho>): [Errno 2] ...`, exit 1 | **ok** |
| F-2 | `gerar_readme.py --check` sem o cadastro | mesma mensagem, exit 1 (README **não** foi reescrito) | **ok** |
| F-3 | `gerar_relatorio.py --tipo diario --dry-run` sem o cadastro | mesma mensagem, exit 1 | **ok** |
| F-4 | `gerar_email.py --dry-run` sem o cadastro | mesma mensagem, exit 1 | **ok** |
| F-5 | `coletar.py --dry-run` sem o cadastro | `ERRO: cadastro de municipios ilegivel (<caminho>): ...`, exit 1 | **ok** |
| F-6 | os mesmos com JSON truncado | `... : JSON invalido em <caminho>: Expecting value: line 1 column 17`, exit 1 | **ok** — o caminho aparece nas duas formas de falha |
| F-7 | restauro | `sha256` idêntico; `git status --short` só com `.agents/` | **ok** |

## 6. Workflow, linha por linha, contra o design §10

`actionlint` **não existe neste sandbox** (`command -v actionlint` → 1) e `pyyaml` é dependência
externa proibida; a conferência estrutural foi feita com o parser YAML do Ruby 3.4.10 (W1–W8) e com
o `TesteWorkflow` da suíte, que lê o YAML como **texto**. Fica declarado: **o YAML não passou por
actionlint**.

| # | Item auditado | Resultado | Veredito |
| - | ------------- | --------- | -------- |
| W1 | `pull_request.paths` | `["dados/**", "fontes/**", "ferramentas/**", ".github/workflows/monitoramento.yml", "README.md"]` | **ok** — o bug de §10.1 está corrigido |
| W2 | `push.paths` | `["dados/**", "fontes/**", "ferramentas/**", ".github/workflows/monitoramento.yml"]` | **ok** — `descobertas/**` e `README.md` fora, pela razão certa (conteúdo do bot já revalidado antes do commit), e o comentário do arquivo diz isso |
| W3 | `push.branches` | `["main"]` | **ok** |
| W4 | jobs | `validar`, `atualizar`, `enviar_email` | **ok** |
| W5 | passos do job `validar` | checkout, setup-python 3.11, **Rodar a suite de testes**, Validar registros, Conferir README | **ok** — testes antes de `validar.py` |
| W6 | passos do job `atualizar` | ... Preparar resumo de e-mail, **Rodar a suite de testes**, Revalidar depois das alteracoes, Commitar, Abrir issue | **ok** — §10.3 satisfeito nos dois jobs (o job `validar` não roda no `schedule`) |
| W7 | condição da issue | exatamente 4 cláusulas: `novos`, `primeira_vez`, `nao_mapeados`, `divergencia_ibge == '1'`; `atos_diario_novos` **ausente** | **ok** — §10.2 |
| W8 | título da issue | 5 cenários executados em `bash` com `set -euo pipefail`: `1/0/0/0`, `0/0/1/0`, `0/0/0/1`, `0/2/1/1`, `0/0/0/0` → títulos corretos e **exit 0** em todos | **ok** — `if/then/fi`, sem `[ cond ] && atribuicao` |
| W9 | `needs: validar` no job `atualizar` | 0 ocorrências no arquivo (só o comentário que explica a ausência) | **ok** — ausência deliberada preservada |
| W10 | `git add` do commit do bot | `git add -A README.md email/ relatorios/ dados/ historico/ descobertas/` — **sem `fontes/`** | **ok** — garantia mecânica de que o cadastro só muda por mão humana |
| W11 | nenhuma ferramenta escreve em `fontes/` | varredura de `open(..., "w")` / `os.replace` / `shutil` em `ferramentas/*.py`: escrevem em `descobertas/`, `README.md`, `email/`, `relatorios/`, `dados/` (via `atualizar_prazos.py`) — nunca em `fontes/` | **ok** — W10 não deixa alteração órfã para trás |
| W12 | `permissions` | topo `contents: read`; job `atualizar` eleva para `contents: write` + `issues: write` | **ok** |

## 7. Integração ponta a ponta com uma coleta **real** (cenário do job `atualizar`)

É o único teste que faz a saída real do coletor atravessar os **quatro** consumidores de uma vez.
Coleta das 4 fontes gravada em diretório temporário; README, relatório e resumo também temporários;
caminhos dos módulos restaurados no `finally`.

| # | Etapa | Resultado | Veredito |
| - | ----- | --------- | -------- |
| I-1 | `coletar.main()` real | exit 0, 353 achados, **15 chaves de topo** (as 8 antigas + `atos_diario_novos`, `cobertura_municipios`, `descartados_por_retencao`, `janela_ioes_dias`, `municipios_nao_mapeados`, `reconciliacao_ibge`, `retencao_atos_dias`) | **ok** |
| I-2 | `validar.valida_descobertas()` sobre essa coleta | **0 erros e 0 avisos**; `{'achados': 353, 'atos_diario': 319, 'descartados_por_retencao': 0}` | **ok** — as checagens novas não reprovam a saída real |
| I-3 | `gerar_readme.monta_bloco()` duas vezes | **byte-idêntico**; Panorama `78 / 15 / 46`; 46 linhas com `✓` em "Ato detectado" | **ok** — determinístico e alimentado pelo bloco publicado |
| I-4 | `gerar_relatorio.py --tipo diario` | exit 0, com seção de cobertura e tabela de microrregiões | **ok** |
| I-5 | `gerar_email.py --forcar --dry-run` | exit 0, com `**Cobertura** — primeiro ato detectado em: Afonso Cláudio, Águia Branca, ...` | **ok** — §11.3 ao pé da letra |
| I-6 | `email/.estado-envios.json` | **não** foi tocado por `--dry-run` | **ok** |

## 8. Compatibilidade 3.9 e restrição de dependência

| # | Item | Resultado | Veredito |
| - | ---- | --------- | -------- |
| P-1 | toda a bateria no Python do sandbox | **3.9.25**, exit 0 em B01–B11 | **ok** — é a prova prática de 3.9, não uma promessa |
| P-2 | `statement match` | 0 ocorrências nos 11 arquivos de `ferramentas/` | **ok** |
| P-3 | `X \| Y` avaliado em runtime | 8 ocorrências de `BitOr`, **todas união de conjuntos** (`na_janela \| curados`, `ESFERAS_VALIDAS \| {...}`, `set(...) \| set(...)`): nenhuma é anotação de tipo nem `dict \| dict` | **ok** |
| P-4 | `from __future__ import annotations` | presente nos 11 arquivos de `ferramentas/` | **ok** |
| P-5 | imports fora da stdlib | nenhum nos módulos novos/alterados. Única ocorrência no repositório: `pypdf` em `ferramentas/consultar_selecao_es.py` — **pré-existente**, arquivo não tocado por este trabalho, import **tardio** dentro de `try/ImportError` com mensagem de instalação, e não usado pelo workflow | **ok** — nenhuma dependência introduzida |
| P-6 | `python3 -m py_compile ferramentas/*.py` | exit 0 em 3.9.25 | **ok** |

## 9. Invariantes de dado

| # | Item | Resultado | Veredito |
| - | ---- | --------- | -------- |
| V-1 | `git diff --stat dados/` (árvore vs HEAD) | **vazio** | **ok** |
| V-2 | `dados/` contra o commit base `ddd9867` | só `dados/ESQUEMA.md` (+15 linhas); **0** arquivos `.json` alterados | **ok** — os 53 registros intactos |
| V-3 | `comum.carregar_registros()` | 53 registros | **ok** |
| V-4 | cadastro: contagem | `total_esperado=78`, `len(municipios)=78`, 0 duplicata de slug | **ok** |
| V-5 | cadastro contra `/projects/sandbox/ibge_es.json` | 0 faltantes, 0 excedentes, 0 `slug != comum.slug(nome)`, 0 `codigo_ibge` divergente | **ok** |
| V-6 | canais: evidência e data | 148 canais, **0** sem evidência, **0** `confirmado` sem `verificado_em`, **0** `pendente` com `verificado_em`, **0** com url vazia | **ok** — nenhuma URL afirmada sem evidência |
| V-7 | canais por estado | 77 `confirmado` (36 de FEAT-001 + 41 promovidos por FEAT-002) e 71 `pendente` | **ok** (corrige o número da seção 12 abaixo) |
| V-8 | canal de precedência 1 | **0** municípios sem canal de precedência 1 | **ok** |
| V-9 | aliases | 2 aliases, **0** colisão entre municípios | **ok** |
| V-10 | `orgaos_vinculados` | 8 entradas; 7 com `url: null` e exatamente essas 7 com `url:nao_encontrado`; 3 com `municipios_slugs:nao_encontrado` (os 3 intermunicipais); 5 naturezas distintas | **ok** |
| V-11 | microrregiões | 13 microrregiões somando 78 municípios | **ok** |
| V-12 | `descobertas.json` versionado | 8 chaves de topo preservadas (`achados`, `descricao`, `fontes_consultadas`, `gerado_em`, `ja_no_repositorio`, `janela_dias`, `pendentes_de_curadoria`, `total_achados`); 37 achados, todos com `categoria` e `municipio_slug` | **ok** |
| V-13 | `--migrar-descobertas` duas vezes | exit 0/0, arquivo **byte-idêntico ao versionado** e idempotente; chaves de topo preservadas | **ok** — nada a restaurar |
| V-14 | `git status --short` ao fim | `M ferramentas/coletar.py`, `M ferramentas/testes.py`, `M ferramentas/validar.py` (a correção da seção 10) e `?? .agents/` | **ok** — nenhum arquivo inesperado; `.agents/` nunca estagiado |

## 10. Defeito encontrado e corrigido

**X — `exemplos` de `municipios_nao_mapeados` sem checagem de forma derrubava a coleta inteira.**

Reprodução (antes da correção), com um `descobertas.json` anterior cujo candidato trazia
`"exemplos": ["https://ioes.dio.es.gov.br/pagina/1"]` em vez de objetos:

| # | Comando | Antes | Depois |
| - | ------- | ----- | ------ |
| X-1 | `validar.valida_descobertas()` sobre o arquivo | **0 erros** (o arquivo passava no CI) | **1 erro**: `municipios_nao_mapeados[0]: exemplos[0] deve ser um objeto com url/data/trecho (recebido: str)` |
| X-2 | `coletar.main()` com esse arquivo como anterior | **`AttributeError: 'str' object has no attribute 'get'`** — coleta do dia **inteira** perdida | `exit=0` (sobreviveu) |
| X-3 | corpo da issue | não era gerado | cita o candidato normalmente |

Por que era defeito e não rigor excessivo: `validar.py` já conferia que `exemplos` era **lista** e
que tinha no máximo 3 itens, mas não a forma de cada item; e `fundir_nao_mapeados()` copiava os
exemplos do arquivo anterior **verbatim**, sem passar por `_exemplos_ordenados()`, quando o
candidato não voltava a aparecer. Como `fundir_nao_mapeados()` e `monta_relatorio_md()` rodam em
`main()`, **fora** do `try/except` por fonte, um único exemplo malformado produzia exatamente a
falha que o design §12 proíbe: arquivo aprovado pelo validador e coleta do dia perdida por
`AttributeError`.

Correção (duas camadas, nenhuma mudança de comportamento sobre dado válido):

- `ferramentas/coletar.py`, `fundir_nao_mapeados()`: exemplo que não é `dict` é **descartado** na
  ingestão do arquivo anterior — o candidato, que é o dado que importa, sobrevive. Fica no mesmo
  espírito do `isinstance(anterior, dict)` que a função já aplicava ao candidato.
- `ferramentas/validar.py`, `_valida_nao_mapeados()`: item de `exemplos` que não é objeto passa a
  ser **erro**, com a posição e o tipo recebido, para que quem corrige o arquivo saiba qual item
  está errado.
- `ferramentas/testes.py`: 3 casos novos (172 → 175) — fusão com exemplo em `str`/`None`/`int` no
  ramo que copia o anterior verbatim, preservação do exemplo bom quando há candidato novo na mesma
  execução, e corpo da issue com lista de exemplos vazia.

**Limite deliberado desta correção.** A mesma pergunta foi feita a outras formas de
`descobertas.json` anterior corrompido, e a resposta mostra que só este caso era defeito:

| Cenário no arquivo anterior | `validar.py` | `coletar.py` | Veredito |
| --------------------------- | ------------ | ------------ | -------- |
| `achados` com item `str` | 1 erro (`achado que nao e objeto`) | derruba | **aceitável** — o CI reprova o arquivo antes; falhar alto é honesto |
| `achados` com item `None` | 1 erro | derruba | **aceitável**, idem |
| `achados` não é lista | 1 erro (`campo 'achados' ausente ou nao e lista`) | derruba | **aceitável**, idem |
| `cobertura_municipios` é `str` | 1 erro (`deve ser um objeto`) | derruba | **aceitável**, idem |
| `fontes_consultadas` com item `str` | — | sobrevive | ok |
| `municipios_nao_mapeados` é `dict`, ou com item `str` | — | sobrevive | ok |
| **`exemplos` com item `str`** | **0 erro** | **derrubava** | **defeito — corrigido** |

## 11. Reexecução da bateria depois da correção

| Comando | Resultado |
| ------- | --------- |
| `python3 ferramentas/testes.py` | `Ran 175 tests ... OK`, exit 0 |
| `python3 ferramentas/validar.py` | `Validacao aprovada.`, exit 0 (0 erros, 57 avisos — os mesmos de antes) |
| `python3 ferramentas/validar.py --json` | exit 0, contadores idênticos aos de B03 |
| `python3 ferramentas/gerar_readme.py --check` | exit 0, README sincronizado |
| `coletar.py --dry-run` / `--sem-conferir-ibge` / `--autoteste-ioes` | exit 0 nos três |
| `gerar_relatorio.py --tipo diario` | exit 0 |
| `gerar_email.py` | exit 2 (nada novo) |
| `python3 -m py_compile ferramentas/*.py` | exit 0 |
| `git diff --stat dados/` | vazio |
| `git status --short` | 3 arquivos de `ferramentas/` + `?? .agents/` |

## 12. Divergências de registro encontradas (não são defeito de código)

1. **`findings` da FEAT-002 diz "118 confirmados no total"**; o cadastro tem **77** canais
   `confirmado` (V-7). 77 é o número coerente com as outras medições (36 municípios com canal
   confirmado em FEAT-001 + 41 canais de diário promovidos em FEAT-002, e 78 − 21
   `municipios_sem_cobertura` = 57 municípios com ao menos um confirmado). O dado está certo; o
   número no texto do `findings` está errado. Nada a corrigir no repositório.
2. **`findings` da FEAT-004 relata `gerar_email.py --forcar --dry-run --saida /tmp`**;
   `--saida` é **caminho de arquivo**, e passar um diretório levanta
   `IsADirectoryError` (medido nesta auditoria). O comando registrado não pode ter rodado como
   escrito. Não é defeito: o workflow não usa `--saida`, e com caminho de arquivo o comando sai 0
   (I-5).
3. **`findings` da FEAT-001 avisa** que o "5 das 8" da §9.2 do design não fecha com a tabela da
   §4.1. Medido aqui: **7 das 8** entradas de `orgaos_vinculados` têm `url:nao_encontrado` (V-10),
   porque 7 têm `url: null`. O aviso da FEAT-001 está correto e o número do design, não.

---

## Pendências declaradas

As do design §18, reconfirmadas por esta auditoria:

1. Canais `portal_prefeitura`/`secao_concursos` dos municípios cujo candidato de domínio responde
   403/406 ou não responde: ficam `pendente` + `canais:conferir_manual`, nunca URL inventada.
   Estado medido do cadastro: 53 municípios com `['canais:conferir_manual']`, 2 com
   `['canais:conferir_manual', 'canais:nao_responde']` (Cachoeiro de Itapemirim e Vila Velha) e 23
   sem pendência alguma.
2. `diario_oficial_proprio` só para a Serra, e mesmo esse depende de conferência do seletor
   "Outros Diários Oficiais" do IOES, **não** feita. Os demais nascem com o canal do agregador
   (DOM/AMUNES), que é o canal correto da maioria e não lacuna (borda 37).
3. `plataforma_inscricao` e `banca` por município nascem ausentes: a evidência existe por certame,
   não por município.
4. Composição de CIM Polinorte, Consórcio Caparaó e ARIES: `municipios_slugs: []` + pendência, até
   apuração documental.
5. `aliases` nasce com 2 entradas e cresce pelas issues de `municipios_nao_mapeados`, que entregam
   a evidência junto.
6. Estabilidade do endpoint `/busca/busca/buscar/` do IOES e da forma de `hits.total` (int hoje;
   Elasticsearch ≥7 devolveria dict): suposição sobre terceiro, mitigada por
   `suspeita_extracao_vazia`, `truncado` e `--autoteste-ioes`.
7. Os números de volume e cobertura valem para a janela medida (`di:2026-09-24`): 46 municípios com
   sinal hoje é ordem de grandeza, não garantia diária.
8. O brief pedia o cadastro em `dados/`; a implementação seguiu o design (`fontes/`) — decisão 1 do
   plano.

Abertas por esta auditoria:

9. **`actionlint` não existe no sandbox** e o YAML **não** passou por ele. A conferência foi
   estrutural (parser YAML do Ruby + `TesteWorkflow` sobre o texto) e comportamental (bloco do
   título executado em `bash`). O que nenhuma das duas cobre é erro de **expressão** do GitHub
   Actions — `steps.coleta.outputs.*` dentro de `if:` não é avaliável fora do runner. Recomendação:
   rodar `actionlint` no primeiro PR.
10. **Nenhum passo deste trabalho foi exercitado no runner real do GitHub.** `python-version:
    "3.11"` e o comportamento do `schedule` são verificados por leitura e por paridade de sintaxe
    3.9/3.11, não por execução. A primeira execução agendada é a prova final.
11. **`municipios_sem_cobertura == 21`** é a lacuna real que sobrou: 21 municípios sem nenhum canal
    confirmado. Cai quando atos forem observados neles, não por mudança de regra. Permanece como
    aviso, nunca erro.
12. **3 avisos de registro intermunicipal** (`ps-aries-es-*` ×2, `ps-consorcio-caparao-es-2026`) são
    permanentes por construção: a sede é aquela mesmo e não credita cobertura. Não devem ser
    silenciados.
13. **O relatório diário passará a listar ~319 bullets de ato de diário** a partir da primeira
    coleta agendada (369 medidos em I-4). O relatório é, por desenho, o registro bruto da coleta;
    filtrar o que ele lista é **decisão de produto** e fica declarada, não resolvida por conta
    própria.
14. **O bloco de cobertura do e-mail não dispara e-mail**: `novidades == 0 and not achados_novos`
    continua sendo o único critério de `exit 2`. Num dia cujo único fato seja "primeiro ato em
    Sooretama", quem notifica é a issue, e o anúncio por e-mail espera o próximo resumo com
    novidade (`cobertura_vistos` só é gravado quando o resumo sai, o que preserva o anúncio em vez
    de perdê-lo). Mudar isso é decisão de produto.
15. **Primeira coleta agendada publicará `primeira_vez` alto** (48 medido), porque o histórico
    nasce vazio. Correto por construção (borda 34); quem controla o anúncio é `cobertura_vistos`.
    Não deve ser "consertado".
