# Esquema dos registros de oportunidades

Cada oportunidade é um arquivo JSON independente, nomeado `<id>.json`, armazenado no
diretório correspondente ao seu **status atual**. Um arquivo = uma oportunidade.

## Convenção de dados ausentes

O escopo do projeto proíbe inventar informação. Quando um dado não está disponível
na fonte oficial:

| Tipo do campo | Valor a usar |
| ------------- | ------------ |
| Texto (`string`) | `"não informado"` |
| Número (`vagas_imediatas_total`, …) | `null` |
| Data (`inscricoes.inicio`, `prova.objetiva`, …) | `null` |
| Booleano (`cadastro_reserva`) | `null` |
| Lista (`beneficios`, …) | `[]` |

`null` significa "a fonte oficial não informa / ainda não definido". Nunca use `0`,
`""` ou uma data inventada para representar ausência de dado.

Todas as datas usam o formato **ISO 8601** (`YYYY-MM-DD`). Quando o edital fixa
hora limite relevante (ex.: `16h00`), a hora vai em `inscricoes.observacao`, não na data.

## Identificador único

O `id` é estável: **nunca muda**, mesmo quando a oportunidade troca de status ou de
diretório. Formato:

```
<tipo>-<orgao-slug>-<recorte>-<ano>
```

- `tipo`: `concurso` ou `ps` (processo seletivo)
- `orgao-slug`: sigla ou nome do órgão em minúsculas, sem acentos, separado por `-`,
  incluindo o município quando o órgão for municipal (`anchieta-es`, `camara-aracruz-es`)
- `recorte`: cargo, número do edital ou área que distingue a oportunidade dentro do
  mesmo órgão e ano (`guarda-municipal`, `021`, `oficial-investigador`)
- `ano`: ano de publicação do edital ou, para previstos/autorizados, o ano de referência

Exemplos: `concurso-anchieta-es-professor-2026`, `ps-sedu-es-diretor-escolar-33-2025`.

## Vocabulário de `status`

Os status seguem o ciclo de vida da oportunidade. A ordem abaixo é a progressão normal:

| `status` | Significado | Diretório |
| -------- | ----------- | --------- |
| `previsto` | Anunciado, em LOA/PPA ou declarado por autoridade, sem autorização formal | `dados/concursos/previstos/` |
| `autorizado` | Autorizado formalmente, ou com comissão formada / banca contratada | `dados/concursos/autorizados/` |
| `edital_publicado` | Edital publicado, inscrições ainda não iniciadas | `abertos/` |
| `inscricoes_abertas` | Período de inscrição em curso na data de verificação | `abertos/` |
| `inscricoes_encerradas` | Inscrições fechadas, certame em andamento | `encerrados/` |
| `prova_realizada` | Prova objetiva aplicada, demais etapas pendentes | `encerrados/` |
| `homologado` | Resultado final homologado | `encerrados/` |
| `cancelado` | Certame cancelado, suspenso ou anulado | `encerrados/` |

Mudança de status **move o arquivo** entre diretórios, preservando o `id` e acrescentando
uma entrada em `historico_status`. O registro antigo nunca é apagado.

Uma transição é **mecânica** quando decorre apenas de dado já presente no registro e da
passagem do tempo. São duas, feitas por `ferramentas/atualizar_prazos.py`:
`edital_publicado` → `inscricoes_abertas` quando `inscricoes.inicio` chega, e
`inscricoes_abertas` → `inscricoes_encerradas` quando `inscricoes.fim` fica no passado.
Nesses casos `ultima_verificacao` e `ultima_atualizacao` **não mudam**, porque nenhuma
fonte foi consultada e nada de novo foi apurado: só a entrada em `historico_status` é
acrescentada, declarando que a transição foi automática.

## Vocabulário de `esfera`

- `federal` — órgãos da União. Inclui **conselhos de fiscalização profissional**
  (CRF-ES, CREF22/ES, …), que são autarquias federais.
- `estadual` — órgãos do Estado do Espírito Santo.
- `municipal` — prefeituras, câmaras e autarquias municipais do ES.
- `intermunicipal` — consórcios públicos intermunicipais (CIM Polinorte, Consórcio Caparaó).

## Vocabulário de `tipo`

- `concurso_publico` — provimento de cargo efetivo.
- `processo_seletivo_simplificado` — contratação temporária / designação temporária.

## Vocabulário de `regime`

`estatutario`, `clt`, `designacao_temporaria`, `nao_informado`.

## Campos

| Campo | Tipo | Obrigatório | Descrição |
| ----- | ---- | ----------- | --------- |
| `id` | string | sim | Identificador único e estável (ver acima) |
| `orgao` | string | sim | Nome completo do órgão |
| `orgao_sigla` | string | sim | Sigla, ou `"não informado"` |
| `esfera` | enum | sim | Ver vocabulário |
| `municipio` | string | sim | Município de lotação. `"Diversos (ES)"` quando houver várias cidades; `"Âmbito estadual (ES)"` para lotação em todo o estado |
| `uf` | string | sim | Sempre `"ES"` — o escopo do repositório é exclusivamente o Espírito Santo |
| `tipo` | enum | sim | Ver vocabulário |
| `cargos` | lista de objetos | sim | Um objeto por cargo/especialidade do edital |
| `cargos[].nome` | string | sim | Nome do cargo como no edital |
| `cargos[].area` | string | sim | Área de atuação (`"Educação"`, `"Segurança pública"`, …) |
| `cargos[].vagas_imediatas` | número \| null | sim | Vagas de provimento imediato |
| `cargos[].cadastro_reserva` | bool \| null | sim | Há formação de CR para este cargo |
| `cargos[].escolaridade` | string | sim | Escolaridade exigida |
| `cargos[].requisitos` | string | sim | Requisitos adicionais (registro em conselho, CNH, idade, …) |
| `cargos[].remuneracao` | string | sim | Remuneração conforme o edital |
| `cargos[].jornada` | string | sim | Carga horária |
| `vagas_imediatas_total` | número \| null | sim | Soma das vagas imediatas do edital |
| `cadastro_reserva` | bool \| null | sim | Edital prevê cadastro de reserva |
| `escolaridade` | string | sim | Resumo dos níveis exigidos |
| `remuneracao` | objeto | sim | `{minima, maxima, descricao}` — valores em número (R$) ou `null` |
| `beneficios` | lista de strings | sim | Auxílio-alimentação, plano de saúde, … |
| `jornada` | string | sim | Resumo das jornadas |
| `edital_numero` | string | sim | Número/identificação do edital |
| `publicacao` | data \| null | sim | Data de publicação do edital |
| `inscricoes` | objeto | sim | `{inicio, fim, taxa, local, isencao, observacao}` |
| `prova` | objeto | sim | `{objetiva, outras_etapas[], observacao}` |
| `banca` | string | sim | Banca organizadora |
| `status` | enum | sim | Ver vocabulário |
| `regime` | enum | sim | Ver vocabulário |
| `validade` | string | sim | Validade do certame |
| `links` | objeto | sim | `{edital, pagina_oficial, banca}` — URLs ou `"não informado"` |
| `fontes` | lista de objetos | sim | `{titulo, url, tipo, consultado_em}`. `tipo`: `oficial`, `banca`, `diario_oficial`, `portal_concursos`, `imprensa` |
| `historico_status` | lista de objetos | sim | `{data, status, observacao}` — trilha de auditoria, apenas acrescentar |
| `ultima_verificacao` | data | sim | Data da última consulta às fontes |
| `ultima_atualizacao` | data | sim | Data da última alteração de conteúdo do registro. Nunca posterior a `ultima_verificacao`: conteúdo novo pressupõe fonte consultada |
| `observacoes` | string | sim | Divergências entre fontes, ressalvas, alertas. Usar `"não informado"` se vazio |

## Regra de precedência de fontes

Quando duas fontes divergem, vale a de maior prioridade e a divergência é **registrada
em `observacoes`** (nunca silenciada):

1. `oficial` — site do órgão, `diario_oficial`
2. `banca` — site da banca organizadora
3. `portal_concursos` — PCI Concursos, QConcursos e similares
4. `imprensa` — veículos jornalísticos

## Controle de duplicidade

Antes de criar um registro, verifique se já existe um com a mesma combinação de
**órgão + cargo + número do edital + ano**, ou o mesmo **link de edital**. Em caso
afirmativo, **atualize o registro existente** (e acrescente a `historico_status`)
em vez de criar outro. `ferramentas/validar.py` detecta duplicatas automaticamente.
