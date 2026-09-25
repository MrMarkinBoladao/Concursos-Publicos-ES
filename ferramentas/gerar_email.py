#!/usr/bin/env python3
"""Monta o resumo de e-mail com novidades e alteracoes relevantes.

Regras implementadas:
  * organizacao por prioridade temporal (prazo primeiro);
  * cada item traz link direto para a fonte oficial;
  * nao reenvia informacao identica: cada oportunidade tem uma "impressao
    digital" dos campos relevantes, guardada em email/.estado-envios.json.
    Se nada mudou, o item nao entra no resumo.

Uso:
    python3 ferramentas/gerar_email.py                # gera e atualiza o estado
    python3 ferramentas/gerar_email.py --dry-run      # gera sem gravar estado
    python3 ferramentas/gerar_email.py --forcar       # ignora o estado anterior

Codigo de saida 0 se ha conteudo a enviar, 2 se nao ha novidade (nao e erro).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

DIR_EMAIL = os.path.join(comum.RAIZ, "email")
CAMINHO_ESTADO = os.path.join(DIR_EMAIL, ".estado-envios.json")
CAMINHO_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas", "descobertas.json")

# Prazo, em dias, que caracteriza "encerrando em breve". Dez dias dao margem
# para separar documentacao, pedir isencao de taxa e pagar o boleto.
JANELA_URGENTE = 10
# Janela, em dias, para considerar um edital/alteracao como "novidade".
JANELA_NOVIDADE = 7


def impressao_digital(reg) -> str:
    """Hash dos campos cuja mudanca justifica um novo alerta.

    Deliberadamente NAO inclui 'ultima_verificacao': reencontrar a mesma
    oportunidade sem alteracao nao deve gerar e-mail.
    """
    relevantes = {
        "status": reg.get("status"),
        "inscricoes_inicio": (reg.get("inscricoes") or {}).get("inicio"),
        "inscricoes_fim": (reg.get("inscricoes") or {}).get("fim"),
        "inscricoes_taxa": (reg.get("inscricoes") or {}).get("taxa"),
        "prova": (reg.get("prova") or {}).get("objetiva"),
        "vagas": reg.get("vagas_imediatas_total"),
        "remuneracao": (reg.get("remuneracao") or {}).get("maxima"),
        "banca": reg.get("banca"),
        "edital": (reg.get("links") or {}).get("edital"),
        "edital_numero": reg.get("edital_numero"),
    }
    bruto = json.dumps(relevantes, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def carregar_estado():
    """Devolve (impressoes dos registros, chaves de achados ja anunciados)."""
    if not os.path.exists(CAMINHO_ESTADO):
        return {}, {}
    try:
        with open(CAMINHO_ESTADO, encoding="utf-8") as fh:
            estado = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Estado corrompido: trata como primeira execucao em vez de falhar.
        return {}, {}
    return estado.get("impressoes", {}), estado.get("descobertas", {})


def gravar_estado(impressoes, descobertas, referencia):
    os.makedirs(DIR_EMAIL, exist_ok=True)
    with open(CAMINHO_ESTADO, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "descricao": (
                    "Impressoes digitais das oportunidades e chaves dos achados da "
                    "coleta no ultimo resumo enviado. Usado para nao reenviar "
                    "informacao identica. Nao contem dados sensiveis nem credenciais."
                ),
                "ultima_geracao": referencia.isoformat(),
                "impressoes": impressoes,
                "descobertas": descobertas,
            },
            fh,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        fh.write("\n")


def carregar_descobertas():
    """Achados da coleta automatica. Lista vazia se o arquivo nao existir."""
    if not os.path.exists(CAMINHO_DESCOBERTAS):
        return []
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            return json.load(fh).get("achados") or []
    except (json.JSONDecodeError, OSError):
        return []


def classificar_descobertas(achados, referencia, conhecidas, forcar):
    """Separa os achados ainda nao anunciados por e-mail.

    Entra no resumo o achado que (a) ainda nao tem registro curado em dados/,
    (b) nunca foi anunciado e (c) foi detectado pela primeira vez na janela de
    novidade. Todos os pendentes entram no estado, para que um achado antigo nao
    seja anunciado como novidade em execucoes futuras.
    """
    novos = []
    estado = {}
    for achado in achados:
        if achado.get("no_repositorio"):
            # Ja existe registro curado: o alerta sai pelo registro, nao aqui.
            continue
        chave = achado.get("chave")
        if not chave:
            continue
        deteccao = comum.data_ou_none(achado.get("primeira_deteccao"))
        estado[chave] = achado.get("primeira_deteccao")
        if chave in conhecidas and not forcar:
            continue
        if deteccao is not None and (referencia - deteccao).days > JANELA_NOVIDADE:
            continue
        # Oportunidade com prazo de inscricao vencido nao e "nova vaga": fica
        # registrada em descobertas/ para historico, mas nao entra no e-mail.
        fim = comum.data_ou_none((achado.get("inscricoes") or {}).get("fim"))
        if fim is not None and fim < referencia:
            continue
        novos.append(achado)

    novos.sort(key=lambda a: (a.get("primeira_deteccao") or "", a.get("orgao") or ""))
    return novos, estado


def _item_descoberta(achado):
    """Formata um achado da coleta como item de lista do e-mail."""
    rotulo = achado.get("orgao") or achado.get("titulo") or comum.AUSENTE
    linhas = ["- **%s**" % rotulo]

    titulo = achado.get("titulo")
    if titulo and titulo != rotulo:
        linhas.append("  - %s" % titulo)

    detalhes = []
    vagas = achado.get("vagas_informadas")
    if vagas:
        detalhes.append("Vagas informadas pela fonte: %s" % vagas)
    fim = (achado.get("inscricoes") or {}).get("fim")
    if fim:
        detalhes.append("Inscrições até %s" % comum.br_data(fim))
    situacao = achado.get("situacao_portal")
    if situacao:
        detalhes.append("Situação na fonte: %s" % situacao)
    if detalhes:
        linhas.append("  - " + " | ".join(detalhes))

    linhas.append(
        "  - Fonte (%s): %s"
        % (achado.get("fonte_tipo") or comum.AUSENTE, achado.get("url") or comum.AUSENTE)
    )
    return "\n".join(linhas)


def _item(reg, referencia, nota=None):
    """Formata uma oportunidade como item de lista do e-mail."""
    url = comum.link_principal(reg)
    titulo = "%s — %s" % (
        reg.get("orgao_sigla")
        if reg.get("orgao_sigla") not in (None, comum.AUSENTE)
        else reg.get("orgao"),
        comum.rotulo_cargos(reg, limite=2),
    )
    linhas = ["- **%s**" % titulo]

    detalhes = []
    vagas = comum.resumo_vagas(reg)
    if vagas != comum.AUSENTE:
        detalhes.append("Vagas: %s" % vagas)
    remuneracao = comum.faixa_remuneracao(reg)
    if remuneracao != comum.AUSENTE:
        detalhes.append("Remuneração: %s" % remuneracao)
    escolaridade = reg.get("escolaridade")
    if escolaridade and escolaridade != comum.AUSENTE:
        detalhes.append("Escolaridade: %s" % escolaridade)
    if detalhes:
        linhas.append("  - " + " | ".join(detalhes))

    prazo = []
    fim = (reg.get("inscricoes") or {}).get("fim")
    if fim:
        dias = comum.dias_para_encerrar(reg, referencia)
        texto = "Inscrições até %s" % comum.br_data(fim)
        if dias is not None and dias >= 0:
            texto += " (%d dia%s)" % (dias, "" if dias == 1 else "s")
        prazo.append(texto)
    taxa = (reg.get("inscricoes") or {}).get("taxa")
    if taxa and taxa != comum.AUSENTE:
        prazo.append("Taxa: %s" % taxa)
    prova = (reg.get("prova") or {}).get("objetiva")
    if prova:
        prazo.append("Prova: %s" % comum.br_data(prova))
    if prazo:
        linhas.append("  - " + " | ".join(prazo))

    banca = reg.get("banca")
    if banca and banca != comum.AUSENTE:
        linhas.append("  - Banca: %s" % banca)

    dias_prova = comum.dias_para_prova(reg, referencia)
    if dias_prova is not None and 0 <= dias_prova <= JANELA_URGENTE:
        linhas.append(
            "  - **PROVA EM %d DIA%s (%s)** — conferir local de prova no site da banca"
            % (dias_prova, "" if dias_prova == 1 else "S", comum.br_data(prova))
        )

    if nota:
        linhas.append("  - %s" % nota)

    if url:
        linhas.append("  - Fonte oficial: %s" % url)
    else:
        linhas.append("  - Fonte oficial: não informado")

    return "\n".join(linhas)


def classificar(registros, referencia, conhecidas, forcar):
    """Separa os registros nas secoes do e-mail, respeitando o estado anterior."""
    secoes = {
        "encerrando": [],
        "abertos": [],
        "novos_editais": [],
        "seletivos": [],
        "previstos": [],
        "outras": [],
    }
    impressoes = {}
    novidades = 0

    for _, reg in registros:
        identificador = reg.get("id")
        digital = impressao_digital(reg)
        impressoes[identificador] = digital

        anterior = conhecidas.get(identificador)
        mudou = forcar or anterior is None or anterior != digital
        if not mudou:
            continue
        novidades += 1
        nota = "Novo no monitoramento." if anterior is None else "Informação alterada desde o último resumo."

        status = reg.get("status")
        aberto = comum.esta_aberto(reg, referencia)
        dias = comum.dias_para_encerrar(reg, referencia)
        publicacao = comum.data_ou_none(reg.get("publicacao"))
        edital_novo = (
            publicacao is not None
            and 0 <= (referencia - publicacao).days <= JANELA_NOVIDADE
        )

        if aberto and dias is not None and 0 <= dias <= JANELA_URGENTE:
            secoes["encerrando"].append((reg, nota))
        elif edital_novo:
            secoes["novos_editais"].append((reg, nota))
        elif aberto and reg.get("tipo") == "concurso_publico":
            secoes["abertos"].append((reg, nota))
        elif aberto:
            secoes["seletivos"].append((reg, nota))
        elif status in ("previsto", "autorizado"):
            secoes["previstos"].append((reg, nota))
        else:
            secoes["outras"].append((reg, nota))

    for chave in ("encerrando", "abertos", "seletivos"):
        secoes[chave].sort(
            key=lambda par: (
                comum.dias_para_encerrar(par[0], referencia) is None,
                comum.dias_para_encerrar(par[0], referencia) or 0,
            )
        )
    def _ordem_outras(par):
        """Prova futura mais proxima primeiro; depois sem prova; por fim as passadas."""
        dias = comum.dias_para_prova(par[0], referencia)
        if dias is None:
            return (1, 0)
        if dias >= 0:
            return (0, dias)
        return (2, -dias)

    # Em "outras" o que importa e a proxima etapa do certame, nao o prazo de inscricao.
    secoes["outras"].sort(key=_ordem_outras)

    return secoes, impressoes, novidades


def monta_email(secoes, referencia, total_registros, achados=None):
    achados = achados or []
    ordem = [
        ("encerrando", "1. Inscrições encerrando em breve (até %d dias)" % JANELA_URGENTE),
        ("abertos", "2. Concursos com inscrições abertas"),
        ("novos_editais", "3. Novos editais publicados"),
        ("seletivos", "4. Processos seletivos"),
        ("previstos", "5. Concursos previstos e autorizados"),
        ("outras", "6. Outras atualizações"),
    ]

    total = sum(len(secoes[chave]) for chave, _ in ordem)
    urgentes = len(secoes["encerrando"])

    assunto = "Concursos ES %s — %d atualizações%s%s" % (
        referencia.strftime("%d/%m"),
        total,
        (", %d achado%s novo%s" % (len(achados), "" if len(achados) == 1 else "s", "" if len(achados) == 1 else "s"))
        if achados
        else "",
        (", %d com prazo curto" % urgentes) if urgentes else "",
    )

    partes = [
        "# %s" % assunto,
        "",
        "**Assunto sugerido:** %s" % assunto,
        "",
        "Resumo do monitoramento de concursos públicos e processos seletivos do",
        "Espírito Santo. Base de %d oportunidades acompanhadas; %d item(ns) com"
        % (total_registros, total),
        "novidade ou alteração relevante desde o último resumo.",
        "",
        "Itens sem alteração desde o último envio foram omitidos de propósito.",
        "",
    ]

    for chave, titulo in ordem:
        itens = secoes[chave]
        partes.append("## %s" % titulo)
        partes.append("")
        if not itens:
            partes.append("_Sem novidades nesta seção._")
        else:
            for reg, nota in itens:
                partes.append(_item(reg, referencia, nota))
        partes.append("")

    # A coleta automatica encontra oportunidades antes de existir registro curado.
    # Vao para o fim do e-mail, com o aviso de que nao passaram por conferencia.
    partes.append("## 7. Detectado automaticamente — ainda não conferido")
    partes.append("")
    if not achados:
        partes.append("_Sem novidades nesta seção._")
    else:
        partes += [
            "Oportunidades vistas nas fontes que **ainda não têm registro conferido**",
            "no monitoramento. São pistas: o edital não foi lido, e cargos, vagas e",
            "prazos podem estar incompletos ou errados. Confira na fonte antes de agir.",
            "",
        ]
        for achado in achados:
            partes.append(_item_descoberta(achado))
    partes.append("")

    partes += [
        "---",
        "",
        "Os dados são um resumo do que foi apurado nas fontes listadas em cada",
        "registro. **Confirme sempre no edital oficial** antes de se inscrever:",
        "prazos e quadros de vagas mudam por retificação.",
        "",
        "Gerado automaticamente em %s por `ferramentas/gerar_email.py`."
        % referencia.strftime("%d/%m/%Y"),
    ]
    return assunto, "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o resumo de e-mail.")
    parser.add_argument("--dry-run", action="store_true", help="nao grava o estado")
    parser.add_argument("--forcar", action="store_true", help="ignora o estado anterior")
    parser.add_argument("--saida", help="caminho do arquivo de saida")
    args = parser.parse_args()

    referencia = comum.hoje()
    registros = comum.carregar_registros()
    conhecidas, descobertas_conhecidas = carregar_estado()
    if args.forcar:
        conhecidas = {}

    secoes, impressoes, novidades = classificar(registros, referencia, conhecidas, args.forcar)
    achados_novos, estado_descobertas = classificar_descobertas(
        carregar_descobertas(), referencia, descobertas_conhecidas, args.forcar
    )

    if novidades == 0 and not achados_novos:
        print(
            "Nenhuma novidade ou alteracao relevante desde o ultimo resumo. "
            "Nada a enviar (%d oportunidades verificadas)." % len(registros)
        )
        return 2

    assunto, corpo = monta_email(secoes, referencia, len(registros), achados_novos)

    destino = args.saida or os.path.join(
        DIR_EMAIL, "%s-resumo.md" % referencia.isoformat()
    )
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(corpo + "\n")

    if not args.dry_run:
        gravar_estado(impressoes, estado_descobertas, referencia)

    print("Resumo gerado: %s" % os.path.relpath(destino, comum.RAIZ))
    print("Assunto: %s" % assunto)
    print("Itens com novidade: %d de %d oportunidades." % (novidades, len(registros)))
    if achados_novos:
        print(
            "Achados da coleta ainda nao conferidos incluidos no resumo: %d."
            % len(achados_novos)
        )
    if args.dry_run:
        print("(dry-run: estado de envios nao atualizado)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
