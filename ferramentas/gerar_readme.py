#!/usr/bin/env python3
"""Regenera as tabelas de resumo do README.md a partir dos dados em dados/.

O texto do README fora dos marcadores e preservado. Apenas o bloco entre
    <!-- INICIO:TABELAS -->  e  <!-- FIM:TABELAS -->
e reescrito.

Uso:
    python3 ferramentas/gerar_readme.py
    python3 ferramentas/gerar_readme.py --check   # falha se o README estiver desatualizado
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

INICIO = "<!-- INICIO:TABELAS -->"
FIM = "<!-- FIM:TABELAS -->"
CAMINHO_README = os.path.join(comum.RAIZ, "README.md")
CAMINHO_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas", "descobertas.json")

# Quantas descobertas pendentes listar no README antes de resumir o excedente.
LIMITE_DESCOBERTAS = 25

# Usado por --check para reconstruir o bloco com a MESMA data de referencia que
# gerou o README atual. Sem isso, o --check falharia todo dia seguinte apenas
# porque o relogio avancou, mesmo sem nenhuma mudanca em dados/.
PADRAO_REFERENCIA = re.compile(
    r"\|\s*Última verificação das fontes\s*\|\s*\*\*(\d{2})/(\d{2})/(\d{4})\*\*\s*\|"
)

AVISO_GERADO = (
    "<!-- Bloco gerado automaticamente por ferramentas/gerar_readme.py. "
    "Nao edite a mao: as alteracoes serao sobrescritas. -->"
)


def referencia_registrada(texto_readme):
    """Data de referencia gravada no README atual, ou None se ausente/invalida."""
    achado = PADRAO_REFERENCIA.search(texto_readme)
    if not achado:
        return None
    dia, mes, ano = (int(p) for p in achado.groups())
    try:
        return dt.date(ano, mes, dia)
    except ValueError:
        return None


def _celula(texto) -> str:
    return comum.escapar_celula(texto)


def _urgencia(dias) -> str:
    """Marcador visual de urgencia do prazo."""
    if dias is None:
        return ""
    if dias <= 3:
        return " **(encerra em %d dia%s)**" % (dias, "" if dias == 1 else "s")
    if dias <= 7:
        return " (encerra em %d dias)" % dias
    return ""


def tabela_concursos_abertos(abertos, referencia):
    linhas = [
        "| Órgão | Cargo | Vagas | Salário | Inscrições até | Prova |",
        "| ----- | ----- | ----: | ------: | -------------- | ----- |",
    ]
    if not abertos:
        return "_Nenhum concurso com inscrições abertas na última verificação._"
    for reg in abertos:
        dias = comum.dias_para_encerrar(reg, referencia)
        orgao = comum.md_link(
            _celula(reg.get("orgao_sigla"))
            if reg.get("orgao_sigla") not in (None, comum.AUSENTE)
            else _celula(reg.get("orgao")),
            comum.link_principal(reg),
        )
        linhas.append(
            "| %s | %s | %s | %s | %s%s | %s |"
            % (
                orgao,
                _celula(comum.rotulo_cargos(reg)),
                _celula(comum.resumo_vagas(reg)),
                _celula(comum.faixa_remuneracao(reg)),
                comum.br_data(reg.get("inscricoes", {}).get("fim")),
                _urgencia(dias),
                comum.br_data(reg.get("prova", {}).get("objetiva")),
            )
        )
    return "\n".join(linhas)


def tabela_proximos(proximos):
    linhas = [
        "| Órgão | Cargo | Status | Previsão | Fonte |",
        "| ----- | ----- | ------ | -------- | ----- |",
    ]
    if not proximos:
        return "_Nenhum concurso previsto ou autorizado registrado._"
    rotulos = {"autorizado": "Autorizado / banca ou comissão definida", "previsto": "Previsto / anunciado"}
    for reg in proximos:
        previsao = reg.get("inscricoes", {}).get("observacao") or comum.AUSENTE
        if previsao.startswith("Edital ainda não publicado") or previsao.startswith("Certame"):
            previsao = "Edital não publicado"
        linhas.append(
            "| %s | %s | %s | %s | %s |"
            % (
                _celula(reg.get("orgao_sigla"))
                if reg.get("orgao_sigla") not in (None, comum.AUSENTE)
                else _celula(reg.get("orgao")),
                _celula(comum.rotulo_cargos(reg)),
                rotulos.get(reg.get("status"), reg.get("status")),
                _celula(previsao),
                comum.md_link("fonte", comum.link_principal(reg)) or comum.AUSENTE,
            )
        )
    return "\n".join(linhas)


def tabela_processos_seletivos(abertos, referencia):
    linhas = [
        "| Órgão | Cargo | Vagas | Inscrições até | Fonte |",
        "| ----- | ----- | ----: | -------------- | ----- |",
    ]
    if not abertos:
        return "_Nenhum processo seletivo com inscrições abertas na última verificação._"
    for reg in abertos:
        dias = comum.dias_para_encerrar(reg, referencia)
        linhas.append(
            "| %s | %s | %s | %s%s | %s |"
            % (
                _celula(reg.get("orgao_sigla"))
                if reg.get("orgao_sigla") not in (None, comum.AUSENTE)
                else _celula(reg.get("orgao")),
                _celula(comum.rotulo_cargos(reg)),
                _celula(comum.resumo_vagas(reg)),
                comum.br_data(reg.get("inscricoes", {}).get("fim")),
                _urgencia(dias),
                comum.md_link("fonte", comum.link_principal(reg)) or comum.AUSENTE,
            )
        )
    return "\n".join(linhas)


def tabela_historico(encerrados):
    linhas = [
        "| Órgão | Cargo | Vagas | Situação | Encerrou em | Fonte |",
        "| ----- | ----- | ----: | -------- | ----------- | ----- |",
    ]
    if not encerrados:
        return "_Nenhum registro histórico._"
    rotulos = {
        "inscricoes_encerradas": "Inscrições encerradas",
        "prova_realizada": "Prova realizada",
        "homologado": "Homologado",
        "cancelado": "Cancelado",
    }
    for reg in encerrados:
        linhas.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                _celula(reg.get("orgao_sigla"))
                if reg.get("orgao_sigla") not in (None, comum.AUSENTE)
                else _celula(reg.get("orgao")),
                _celula(comum.rotulo_cargos(reg, limite=1)),
                _celula(comum.resumo_vagas(reg)),
                rotulos.get(reg.get("status"), reg.get("status")),
                comum.br_data(reg.get("inscricoes", {}).get("fim")),
                comum.md_link("fonte", comum.link_principal(reg)) or comum.AUSENTE,
            )
        )
    return "\n".join(linhas)


def carregar_descobertas():
    """Achados pendentes da coleta automatica. Lista vazia se nao houver arquivo.

    Nunca falha: a coleta e opcional e o README precisa ser gerado mesmo quando
    descobertas/ ainda nao existe.
    """
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return []
    return [
        a
        for a in dados.get("achados", [])
        if not a.get("no_repositorio") and not a.get("ausente_na_fonte")
    ]


ROTULOS_STATUS_ESTIMADO = {
    "inscricoes_abertas": "Inscrições abertas",
    "edital_publicado": "Inscrições não iniciadas",
    "inscricoes_encerradas": "Inscrições encerradas",
    "previsto": "Previsto",
    "autorizado": "Autorizado",
}


def tabela_descobertas(achados):
    """Achados da coleta automatica ainda sem registro curado em dados/."""
    if not achados:
        return (
            "_Nenhuma pendência: tudo que as fontes automáticas listam já tem "
            "registro em `dados/`._"
        )

    ordenados = sorted(
        achados,
        key=lambda a: (
            (a.get("inscricoes") or {}).get("fim") or "",
            a.get("primeira_deteccao") or "",
        ),
        reverse=True,
    )
    linhas = [
        "| Órgão | Oportunidade | Situação na fonte | Inscrições até | Fonte |",
        "| ----- | ------------ | ----------------- | -------------- | ----- |",
    ]
    for achado in ordenados[:LIMITE_DESCOBERTAS]:
        sigla = achado.get("orgao_sigla")
        orgao = sigla if sigla and sigla != comum.AUSENTE else achado.get("orgao")
        situacao = ROTULOS_STATUS_ESTIMADO.get(
            achado.get("status_estimado"), comum.AUSENTE
        )
        linhas.append(
            "| %s | %s | %s | %s | %s |"
            % (
                _celula(orgao),
                comum.md_link(
                    _celula(achado.get("titulo")), achado.get("url") or ""
                )
                or _celula(achado.get("titulo")),
                situacao,
                comum.br_data((achado.get("inscricoes") or {}).get("fim")),
                _celula(achado.get("fonte_tipo")),
            )
        )
    if len(ordenados) > LIMITE_DESCOBERTAS:
        linhas.append("")
        linhas.append(
            "_E mais %d achado(s). Lista completa em `descobertas/descobertas.json`._"
            % (len(ordenados) - LIMITE_DESCOBERTAS)
        )
    return "\n".join(linhas)


def _chave_prazo(reg):
    """Ordena por prazo de inscricao, jogando os sem prazo para o fim."""
    fim = comum.data_ou_none(reg.get("inscricoes", {}).get("fim"))
    return (fim is None, fim or comum.hoje(), reg.get("orgao") or "")


def monta_bloco(registros, referencia):
    concursos = [r for _, r in registros if r.get("tipo") == "concurso_publico"]
    seletivos = [r for _, r in registros if r.get("tipo") == "processo_seletivo_simplificado"]

    concursos_abertos = sorted(
        [r for r in concursos if comum.esta_aberto(r, referencia)], key=_chave_prazo
    )
    seletivos_abertos = sorted(
        [r for r in seletivos if comum.esta_aberto(r, referencia)], key=_chave_prazo
    )
    proximos = sorted(
        [r for r in concursos if r.get("status") in ("previsto", "autorizado")],
        key=lambda r: (r.get("status") != "autorizado", r.get("orgao") or ""),
    )
    encerrados = sorted(
        [
            r
            for _, r in registros
            if r.get("status")
            in ("inscricoes_encerradas", "prova_realizada", "homologado", "cancelado")
        ],
        key=lambda r: (
            comum.data_ou_none(r.get("inscricoes", {}).get("fim")) or comum.hoje(),
        ),
        reverse=True,
    )

    total_vagas = sum(
        r.get("vagas_imediatas_total") or 0
        for r in concursos_abertos + seletivos_abertos
    )
    descobertas = carregar_descobertas()

    partes = [
        INICIO,
        AVISO_GERADO,
        "",
        "## Panorama",
        "",
        "| Indicador | Valor |",
        "| --------- | ----: |",
        "| Última verificação das fontes | **%s** |" % referencia.strftime("%d/%m/%Y"),
        "| Oportunidades monitoradas | %d |" % len(registros),
        "| Com inscrições abertas | %d |" % (len(concursos_abertos) + len(seletivos_abertos)),
        "| Vagas imediatas em aberto | %d |" % total_vagas,
        "| Concursos previstos / autorizados | %d |" % len(proximos),
        "| Registros históricos (encerrados ou em andamento) | %d |" % len(encerrados),
        "| Descobertas automáticas pendentes de conferência | %d |" % len(descobertas),
        "",
        "## Concursos com inscrições abertas",
        "",
        tabela_concursos_abertos(concursos_abertos, referencia),
        "",
        "## Próximos concursos",
        "",
        tabela_proximos(proximos),
        "",
        "## Processos seletivos",
        "",
        tabela_processos_seletivos(seletivos_abertos, referencia),
        "",
        "## Histórico (inscrições encerradas)",
        "",
        "Mantidos no repositório como arquivo histórico. Um certame com inscrições",
        "encerradas pode seguir em andamento nas etapas seguintes.",
        "",
        tabela_historico(encerrados),
        "",
        "## Detectado automaticamente — ainda não conferido",
        "",
        "> **Atenção:** esta seção é saída bruta de `ferramentas/coletar.py`. Os itens",
        "> abaixo foram vistos nas fontes mas **não passaram por conferência do edital**",
        "> e por isso não estão nas tabelas acima. Trate como pista, não como dado.",
        "> Detalhes em [`descobertas/`](descobertas/).",
        "",
        tabela_descobertas(descobertas),
        "",
        "_Dados atualizados em %s. Os valores são um resumo: consulte sempre o edital"
        " oficial antes de se inscrever._" % referencia.strftime("%d/%m/%Y"),
        FIM,
    ]
    return "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenera as tabelas do README.")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "nao escreve; retorna 1 se o README estiver dessincronizado dos dados. "
            "Reaproveita a data de referencia gravada no proprio README, para nao "
            "falhar apenas porque o dia mudou"
        ),
    )
    args = parser.parse_args()

    if not os.path.exists(CAMINHO_README):
        print("ERRO: README.md nao encontrado em %s" % CAMINHO_README, file=sys.stderr)
        return 1

    with open(CAMINHO_README, encoding="utf-8") as fh:
        atual = fh.read()

    if INICIO not in atual or FIM not in atual:
        print(
            "ERRO: marcadores %s / %s ausentes no README.md" % (INICIO, FIM),
            file=sys.stderr,
        )
        return 1

    # Em --check a comparacao precisa ser estavel no tempo: o bloco embute a data
    # do dia e contagens "encerra em N dias", entao gerar com hoje() acusaria
    # diferenca todo dia seguinte. Comparamos com a data que gerou o README.
    if args.check:
        referencia = referencia_registrada(atual) or comum.hoje()
    else:
        referencia = comum.hoje()

    registros = comum.carregar_registros()
    bloco = monta_bloco(registros, referencia)

    antes = atual.split(INICIO)[0]
    depois = atual.split(FIM)[1]
    novo = antes + bloco + depois

    if args.check:
        if novo != atual:
            print(
                "README.md esta dessincronizado dos dados (referencia %s). "
                "Rode: python3 ferramentas/gerar_readme.py"
                % referencia.strftime("%d/%m/%Y")
            )
            return 1
        print(
            "README.md esta sincronizado com os dados (referencia %s)."
            % referencia.strftime("%d/%m/%Y")
        )
        return 0

    if novo == atual:
        print("README.md ja estava atualizado (nenhuma alteracao).")
        return 0

    with open(CAMINHO_README, "w", encoding="utf-8") as fh:
        fh.write(novo)
    print("README.md atualizado com %d registros." % len(registros))
    return 0


if __name__ == "__main__":
    sys.exit(main())
