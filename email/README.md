# Resumos de e-mail

Arquivos `AAAA-MM-DD-resumo.md` gerados por `ferramentas/gerar_email.py`,
organizados por prioridade temporal. **Seção sem conteúdo não entra no resumo** e
a numeração acompanha apenas as seções presentes — um e-mail com seis "sem
novidades" esconde a única linha que importa. A ordem de prioridade é:

1. Inscrições encerrando em breve (até 10 dias)
2. Concursos com inscrições abertas
3. Novos editais publicados
4. Processos seletivos
5. Concursos previstos e autorizados
6. Outras atualizações — ordenadas pela próxima etapa (prova mais próxima primeiro)
7. Detectado automaticamente — achados da coleta ainda sem registro conferido

Cada item traz link direto para a fonte oficial.

A seção 7 é a única que não vem de `dados/`: são achados de
`descobertas/descobertas.json` que ainda não passaram por conferência de edital.
Entram no resumo apenas os detectados nos últimos 7 dias, sem registro curado
correspondente e com prazo de inscrição ainda em aberto — uma seleção já encerrada
não é novidade útil. Cada achado é anunciado **uma vez**: a chave fica guardada em
`.estado-envios.json`.

## Como o reenvio é evitado

`.estado-envios.json` guarda uma impressão digital (SHA-256 truncado) dos campos
relevantes de cada oportunidade: status, datas de inscrição, taxa, data de prova,
vagas, remuneração, banca e link do edital.

`ultima_verificacao` **não** entra na impressão digital — de propósito.
Reencontrar a mesma oportunidade sem alteração não gera novo alerta. Já uma
mudança de prazo, de quadro de vagas, de banca ou de status gera.

```bash
python3 ferramentas/gerar_email.py            # só o que mudou; atualiza o estado
python3 ferramentas/gerar_email.py --dry-run  # gera sem atualizar o estado
python3 ferramentas/gerar_email.py --forcar   # tudo, ignorando o estado
```

Código de saída `0` quando há conteúdo a enviar e `2` quando não há novidade —
o que permite ao workflow decidir se dispara o envio.

O arquivo de estado contém apenas identificadores e hashes: **nenhuma
credencial, endereço de e-mail ou dado pessoal**.

## Envio

Este diretório guarda os resumos **preparados**. O envio em si é feito pelo
workflow `.github/workflows/monitoramento.yml`, na execução diária das 8h, que lê
as credenciais SMTP de GitHub Secrets. Nenhuma credencial fica no repositório.

A lista de secrets e a ressalva sobre remetente Proton estão na seção
[Alertas por e-mail](../README.md#alertas-por-e-mail) do README principal.
