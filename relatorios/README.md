# Relatórios

Gerados por `ferramentas/gerar_relatorio.py` a partir de `dados/`,
`descobertas/` e do histórico do Git. O workflow de monitoramento os produz e
commita a cada execução.

| Diretório | Cadência | Período coberto | Conteúdo |
| --------- | -------- | --------------- | -------- |
| `diarios/` | Toda execução do monitoramento | O dia da execução | Novos registros, alterações, mudanças de status, prazos críticos, provas próximas, resultado da coleta e da validação |
| `semanais/` | Segundas-feiras | Última semana ISO fechada (segunda a domingo) | Consolidação da semana: registros criados, transições de status, prazos e provas à frente |
| `mensais/` | Dia 1º do mês | Último mês fechado | Balanço do mês, com a mesma estrutura em escala maior |

Nomes de arquivo: `diarios/AAAA-MM-DD.md`, `semanais/AAAA-Snn.md` (semana ISO),
`mensais/AAAA-MM.md`.

O período é sempre **fechado**: o relatório semanal não cobre a semana em curso e
o mensal não cobre o mês em curso, para não publicar consolidação pela metade.

## Gerar manualmente

```bash
python3 ferramentas/gerar_relatorio.py                    # diário de hoje
python3 ferramentas/gerar_relatorio.py --tipo semanal      # última semana fechada
python3 ferramentas/gerar_relatorio.py --tipo mensal       # último mês fechado
python3 ferramentas/gerar_relatorio.py --data 2026-09-20   # outra data de referência
python3 ferramentas/gerar_relatorio.py --dry-run           # imprime, não grava
python3 ferramentas/gerar_relatorio.py --forcar            # sobrescreve o arquivo
```

## Relatório à mão e relatório gerado

Todo arquivo produzido pela ferramenta termina com a marca
`<!-- gerado-por: ferramentas/gerar_relatorio.py -->`.

Um relatório **sem** essa marca foi escrito por uma pessoa e **não é
sobrescrito** — a ferramenta avisa e sai sem alterar nada. Só `--forcar`
sobrescreve. É o que permite substituir o relatório gerado de um dia por uma
análise escrita à mão, sem que a próxima execução apague o texto.

O relatório gerado é **descritivo**: mostra o que mudou na base e o que está
pendente. Ele não conta por que uma decisão de curadoria foi tomada, nem resolve
divergência entre fontes — isso continua indo para `historico/<ano>/` e para o
campo `observacoes` de cada registro.

Relatórios antigos não são apagados nem reescritos: são o registro do que se
sabia em cada data.
