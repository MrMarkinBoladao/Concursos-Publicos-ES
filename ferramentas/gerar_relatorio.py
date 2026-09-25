#!/usr/bin/env python3
"""Gera os relatorios diario, semanal e mensal a partir dos dados do repositorio.

O relatorio e derivado do que esta em dados/, descobertas/ e no historico do Git.
Nada e inferido: quando um dado nao pode ser determinado, o relatorio diz isso em
vez de estimar.

De onde vem cada informacao:
  * panorama e prazos            -> dados/ (via comum.carregar_registros)
  * registros novos no periodo   -> git log --diff-filter=A em dados/ + arquivos
                                    ainda nao versionados (para rodar antes do commit)
  * transicoes de status         -> campo historico_status de cada registro
  * registros alterados          -> campo ultima_atualizacao
  * coleta automatica            -> descobertas/descobertas.json
  * validacao                    -> execucao de ferramentas/validar.py

Periodos (sempre fechados, para o relatorio nao sair pela metade):
  diario   -> a data de referencia
  semanal  -> a ultima semana ISO completa (segunda a domingo) antes da referencia
  mensal   -> o ultimo mes completo antes da referencia

Uso:
    python3 ferramentas/gerar_relatorio.py                      # diario de hoje
    python3 ferramentas/gerar_relatorio.py --tipo semanal
    python3 ferramentas/gerar_relatorio.py --tipo mensal
    python3 ferramentas/gerar_relatorio.py --data 2026-09-24
    python3 ferramentas/gerar_relatorio.py --forcar             # sobrescreve

Um relatorio escrito a mao NUNCA e sobrescrito sem --forcar: o gerador reconhece
os arquivos que ele mesmo produziu pela marca no rodape e so reescreve esses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

DIR_RELATORIOS = os.path.join(comum.RAIZ, "relatorios")
CAMINHO_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas", "descobertas.json")

# Marca que identifica um arquivo gerado por esta ferramenta. Um relatorio sem
# esta marca foi escrito por uma pessoa e nao pode ser sobrescrito.
MARCA = "<!-- gerado-por: ferramentas/gerar_relatorio.py -->"

# Prazo que caracteriza "encerrando em breve", igual ao usado no resumo de e-mail.
JANELA_URGENTE = 10
# A partir de quantos dias sem consulta as fontes um registro entra em "pendencias".
JANELA_VERIFICACAO = 7

STATUS_ENCERRADOS = {"inscricoes_encerradas", "prova_realizada", "homologado", "cancelado"}


# ---------------------------------------------------------------- utilidades


def _sigla(reg) -> str:
    sigla = reg.get("orgao_sigla")
    if sigla and sigla != comum.AUSENTE:
        return sigla
    return reg.get("orgao") or comum.AUSENTE


def _git(*args):
    """Roda git e devolve stdout, ou None se o git nao estiver disponivel."""
    try:
        proc = subprocess.run(
            ["git", "-C", comum.RAIZ, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def arquivos_novos(inicio: dt.date, fim: dt.date):
    """Caminhos de dados/ criados no periodo. None se o Git nao responder.

    Soma duas fontes: os arquivos adicionados em commits do periodo e os que ainda
    nao foram versionados. A segunda parte e o que permite gerar o relatorio do dia
    ANTES do commit da propria execucao.
    """
    saida = _git(
        "log",
        "--diff-filter=A",
        "--name-only",
        "--pretty=format:",
        "--since=%s 00:00:00" % inicio.isoformat(),
        "--until=%s 23:59:59" % fim.isoformat(),
        "--",
        "dados",
    )
    if saida is None:
        return None

    novos = {
        linha.strip()
        for linha in saida.splitlines()
        if linha.strip().endswith(".json")
    }

    if fim >= comum.hoje():
        pendentes = _git("status", "--porcelain", "--", "dados")
        if pendentes:
            for linha in pendentes.splitlines():
                marca, _, caminho = linha.partition(" ")
                caminho = caminho.strip().strip('"')
                # Renomeados vem como "origem -> destino": interessa o destino.
                if "->" in caminho:
                    caminho = caminho.split("->")[-1].strip()
                if not caminho.endswith(".json"):
                    continue
                if marca.strip() in {"??", "A"}:
                    novos.add(caminho)
    return novos


def carregar_descobertas():
    if not os.path.exists(CAMINHO_DESCOBERTAS):
        return None
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def resultado_validacao():
    """Roda o validador e devolve (erros, avisos). None se nao der para rodar."""
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validar.py")
    try:
        proc = subprocess.run(
            [sys.executable, caminho],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    achado = re.search(r"Erros:\s*(\d+)\s*\|\s*Avisos:\s*(\d+)", proc.stdout)
    if not achado:
        return None
    return int(achado.group(1)), int(achado.group(2))


def no_periodo(valor, inicio: dt.date, fim: dt.date) -> bool:
    data = comum.data_ou_none(valor)
    return data is not None and inicio <= data <= fim


# ---------------------------------------------------------------- blocos


def bloco_panorama(registros, referencia, titulo="Panorama"):
    abertos = [r for _, r in registros if comum.esta_aberto(r, referencia)]
    previstos = [
        r for _, r in registros if r.get("status") in ("previsto", "autorizado")
    ]
    historicos = [r for _, r in registros if r.get("status") in STATUS_ENCERRADOS]
    vagas = sum(
        r.get("vagas_imediatas_total") or 0
        for r in abertos
        if r.get("vagas_imediatas_total")
    )
    linhas = [
        "## %s" % titulo,
        "",
        "| Indicador | Valor |",
        "| --------- | ----: |",
        "| Oportunidades monitoradas | %d |" % len(registros),
        "| Com inscrições abertas | %d |" % len(abertos),
        "| Vagas imediatas em aberto | %d |" % vagas,
        "| Concursos previstos / autorizados | %d |" % len(previstos),
        "| Registros históricos | %d |" % len(historicos),
    ]
    return linhas


def bloco_prazos(registros, referencia, janela=JANELA_URGENTE):
    linhas = ["## Prazos críticos (até %d dias)" % janela, ""]
    urgentes = []
    for _, reg in registros:
        if not comum.esta_aberto(reg, referencia):
            continue
        dias = comum.dias_para_encerrar(reg, referencia)
        if dias is None or dias < 0 or dias > janela:
            continue
        urgentes.append((dias, reg))
    if not urgentes:
        linhas.append("_Nenhuma inscrição encerra nos próximos %d dias._" % janela)
        return linhas

    urgentes.sort(key=lambda par: par[0])
    linhas += [
        "| Prazo | Órgão | Cargo | Vagas | Encerra em |",
        "| ----- | ----- | ----- | ----: | ---------: |",
    ]
    for dias, reg in urgentes:
        linhas.append(
            "| %s | %s | %s | %s | %s |"
            % (
                comum.br_data((reg.get("inscricoes") or {}).get("fim")),
                comum.escapar_celula(_sigla(reg)),
                comum.escapar_celula(comum.rotulo_cargos(reg, limite=1)),
                comum.resumo_vagas(reg),
                "hoje" if dias == 0 else "%d dia%s" % (dias, "" if dias == 1 else "s"),
            )
        )
    return linhas


def bloco_provas(registros, referencia, janela=15):
    proximas = []
    for _, reg in registros:
        dias = comum.dias_para_prova(reg, referencia)
        if dias is None or dias < 0 or dias > janela:
            continue
        proximas.append((dias, reg))
    if not proximas:
        return []
    proximas.sort(key=lambda par: par[0])
    linhas = ["## Provas nos próximos %d dias" % janela, ""]
    for dias, reg in proximas:
        linhas.append(
            "- **%s** — %s: prova em %s (%s)"
            % (
                _sigla(reg),
                comum.rotulo_cargos(reg, limite=1),
                comum.br_data((reg.get("prova") or {}).get("objetiva")),
                "hoje" if dias == 0 else "%d dia%s" % (dias, "" if dias == 1 else "s"),
            )
        )
    return linhas


def bloco_a_abrir(registros, referencia, janela=15):
    """Editais publicados cujas inscricoes ainda nao comecaram."""
    futuros = []
    for _, reg in registros:
        inicio = comum.data_ou_none((reg.get("inscricoes") or {}).get("inicio"))
        if inicio is None or inicio <= referencia:
            continue
        if (inicio - referencia).days > janela:
            continue
        futuros.append((inicio, reg))
    if not futuros:
        return []
    futuros.sort(key=lambda par: par[0])
    linhas = ["## Inscrições que abrem em breve", ""]
    for inicio, reg in futuros:
        linhas.append(
            "- **%s** — %s: inscrições de %s a %s"
            % (
                _sigla(reg),
                comum.rotulo_cargos(reg, limite=1),
                comum.br_data(inicio.isoformat()),
                comum.br_data((reg.get("inscricoes") or {}).get("fim")),
            )
        )
    return linhas


def bloco_novos(registros, novos_caminhos, inicio, fim):
    linhas = ["## Novos registros no período", ""]
    if novos_caminhos is None:
        linhas.append(
            "_Não foi possível determinar: o histórico do Git não pôde ser lido "
            "neste ambiente._"
        )
        return linhas, []

    por_caminho = {}
    for caminho, reg in registros:
        # O git devolve o caminho a partir da raiz do repositorio.
        por_caminho[os.path.join("dados", caminho).replace(os.sep, "/")] = reg

    novos = [por_caminho[c] for c in sorted(novos_caminhos) if c in por_caminho]
    if not novos:
        linhas.append("_Nenhum registro novo no período._")
        return linhas, []

    linhas += [
        "| id | Órgão | Tipo | Status | Vagas | Inscrições até |",
        "| -- | ----- | ---- | ------ | ----: | -------------- |",
    ]
    for reg in novos:
        linhas.append(
            "| `%s` | %s | %s | %s | %s | %s |"
            % (
                reg.get("id"),
                comum.escapar_celula(_sigla(reg)),
                "concurso" if reg.get("tipo") == "concurso_publico" else "processo seletivo",
                reg.get("status"),
                comum.resumo_vagas(reg),
                comum.br_data((reg.get("inscricoes") or {}).get("fim")),
            )
        )
    return linhas, novos


def bloco_transicoes(registros, inicio, fim, limite=60):
    linhas = ["## Mudanças de status no período", ""]
    eventos = []
    for _, reg in registros:
        for entrada in reg.get("historico_status") or []:
            if no_periodo(entrada.get("data"), inicio, fim):
                eventos.append((entrada.get("data"), reg, entrada))
    if not eventos:
        linhas.append("_Nenhuma mudança de status registrada no período._")
        return linhas

    eventos.sort(key=lambda t: (t[0], _sigla(t[1])))
    total = len(eventos)
    if limite and total > limite:
        linhas.append(
            "%d mudanças no período; as %d mais recentes estão na tabela. "
            "A trilha completa está no campo `historico_status` de cada registro."
            % (total, limite)
        )
        linhas.append("")
        eventos = eventos[-limite:]

    # A coluna de id evita que duas oportunidades do mesmo orgao no mesmo dia
    # (por exemplo, dois editais irmaos) apareçam como linhas repetidas.
    linhas += [
        "| Data | Órgão | Oportunidade | Status | Observação |",
        "| ---- | ----- | ------------ | ------ | ---------- |",
    ]
    for data, reg, entrada in eventos:
        observacao = entrada.get("observacao") or comum.AUSENTE
        if len(observacao) > 110:
            observacao = observacao[:107].rstrip() + "..."
        linhas.append(
            "| %s | %s | `%s` | %s | %s |"
            % (
                comum.br_data(data),
                comum.escapar_celula(_sigla(reg)),
                reg.get("id"),
                entrada.get("status"),
                comum.escapar_celula(observacao),
            )
        )
    return linhas


def bloco_alterados(registros, inicio, fim, ids_novos):
    linhas = ["## Registros alterados no período", ""]
    alterados = [
        reg
        for _, reg in registros
        if no_periodo(reg.get("ultima_atualizacao"), inicio, fim)
        and reg.get("id") not in ids_novos
    ]
    if not alterados:
        linhas.append("_Nenhum registro existente foi alterado no período._")
        return linhas
    for reg in sorted(alterados, key=lambda r: r.get("id") or ""):
        linhas.append(
            "- `%s` (%s) — atualizado em %s, status `%s`"
            % (
                reg.get("id"),
                _sigla(reg),
                comum.br_data(reg.get("ultima_atualizacao")),
                reg.get("status"),
            )
        )
    return linhas


def bloco_coleta(descobertas, inicio, fim):
    linhas = ["## Coleta automática", ""]
    if not descobertas:
        linhas.append(
            "_Sem dados de coleta: `descobertas/descobertas.json` não foi encontrado "
            "ou não pôde ser lido._"
        )
        return linhas

    linhas += [
        "Última execução registrada: **%s**."
        % comum.br_data(descobertas.get("gerado_em")),
        "",
        "| Fonte | Tipo | Resultado |",
        "| ----- | ---- | --------- |",
    ]
    for fonte in descobertas.get("fontes_consultadas") or []:
        situacao = fonte.get("status")
        detalhe = (
            "ok — %s achados" % fonte.get("achados", 0)
            if situacao == "ok"
            else "**falha** — %s" % (fonte.get("erro") or situacao)
        )
        linhas.append(
            "| %s | %s | %s |"
            % (
                comum.escapar_celula(fonte.get("nome") or fonte.get("id")),
                fonte.get("tipo") or comum.AUSENTE,
                comum.escapar_celula(detalhe),
            )
        )

    linhas += [
        "",
        "| Indicador | Valor |",
        "| --------- | ----: |",
        "| Achados na janela de %s dias | %s |"
        % (descobertas.get("janela_dias", "?"), descobertas.get("total_achados", 0)),
        "| Já cobertos por registro curado | %s |" % descobertas.get("ja_no_repositorio", 0),
        "| Pendentes de conferência | %s |" % descobertas.get("pendentes_de_curadoria", 0),
    ]

    novos = [
        achado
        for achado in descobertas.get("achados") or []
        if no_periodo(achado.get("primeira_deteccao"), inicio, fim)
    ]
    linhas.append("")
    if not novos:
        linhas.append("Nenhum achado novo detectado no período.")
        return linhas

    linhas += [
        "### Achados detectados no período (%d)" % len(novos),
        "",
        "Saída bruta da coleta, **sem conferência de edital**. Trate como pista.",
        "",
    ]
    for achado in novos:
        rotulo = achado.get("titulo") or achado.get("orgao") or comum.AUSENTE
        estado = (
            "já promovido a registro (`%s`)" % achado.get("registro_repositorio")
            if achado.get("no_repositorio")
            else "pendente de conferência"
        )
        linhas.append(
            "- [%s](%s) — %s, detectado em %s"
            % (
                comum.escapar_celula(rotulo),
                achado.get("url") or "",
                estado,
                comum.br_data(achado.get("primeira_deteccao")),
            )
        )
    return linhas


def bloco_pendencias(registros, referencia):
    linhas = ["## Pendências e qualidade dos dados", ""]

    fortes = {"oficial", "banca", "diario_oficial"}
    sem_fonte_forte = [
        reg
        for _, reg in registros
        if not any((f.get("tipo") in fortes) for f in reg.get("fontes") or [])
    ]
    atrasados = []
    for _, reg in registros:
        verificacao = comum.data_ou_none(reg.get("ultima_verificacao"))
        if verificacao is None:
            continue
        atraso = (referencia - verificacao).days
        if atraso > JANELA_VERIFICACAO:
            atrasados.append((atraso, reg))

    linhas += [
        "| Indicador | Valor |",
        "| --------- | ----: |",
        "| Registros sem fonte oficial, de banca ou de diário oficial | %d |"
        % len(sem_fonte_forte),
        "| Registros sem reverificação há mais de %d dias | %d |"
        % (JANELA_VERIFICACAO, len(atrasados)),
        "",
    ]

    if atrasados:
        atrasados.sort(key=lambda par: -par[0])
        linhas.append("### Reverificação mais atrasada")
        linhas.append("")
        for atraso, reg in atrasados[:10]:
            linhas.append(
                "- `%s` (%s) — última consulta às fontes em %s, há %d dias"
                % (
                    reg.get("id"),
                    _sigla(reg),
                    comum.br_data(reg.get("ultima_verificacao")),
                    atraso,
                )
            )
        if len(atrasados) > 10:
            linhas.append("- ... e mais %d registro(s)." % (len(atrasados) - 10))
        linhas.append("")

    linhas.append(
        "Registros sustentados apenas por imprensa ou portais seguem sinalizados "
        "pelo validador e trazem a ressalva em `observacoes`."
    )
    return linhas


def bloco_validacao():
    linhas = ["## Validação", ""]
    resultado = resultado_validacao()
    if resultado is None:
        linhas.append(
            "_Não foi possível executar `ferramentas/validar.py` neste ambiente._"
        )
        return linhas
    erros, avisos = resultado
    linhas.append(
        "`validar.py`: **%d erro%s** e %d aviso%s."
        % (erros, "" if erros == 1 else "s", avisos, "" if avisos == 1 else "s")
    )
    if erros:
        linhas.append("")
        linhas.append(
            "> Há erro de validação em aberto. Rode `python3 ferramentas/validar.py` "
            "para ver a lista e corrija antes da próxima publicação."
        )
    return linhas


def rodape(referencia, inicio, fim):
    return [
        "---",
        "",
        "Período coberto: %s a %s. Gerado em %s por `ferramentas/gerar_relatorio.py` "
        "a partir de `dados/`, `descobertas/` e do histórico do Git."
        % (
            comum.br_data(inicio.isoformat()),
            comum.br_data(fim.isoformat()),
            comum.br_data(referencia.isoformat()),
        ),
        "",
        "Este relatório é descritivo: ele mostra o que mudou na base, não substitui a "
        "conferência dos editais. A leitura de edital e a decisão de promover um achado "
        "a registro curado continuam sendo trabalho humano.",
        "",
        MARCA,
    ]


# ---------------------------------------------------------------- relatorios


def periodo_para(tipo: str, referencia: dt.date):
    """Devolve (inicio, fim, nome_arquivo, titulo) do periodo pedido."""
    if tipo == "diario":
        return (
            referencia,
            referencia,
            os.path.join("diarios", "%s.md" % referencia.isoformat()),
            "Relatório diário — %s" % referencia.strftime("%d/%m/%Y"),
        )

    if tipo == "semanal":
        # Ultima semana ISO completa: segunda a domingo anteriores a semana da referencia.
        segunda_atual = referencia - dt.timedelta(days=referencia.weekday())
        inicio = segunda_atual - dt.timedelta(days=7)
        fim = segunda_atual - dt.timedelta(days=1)
        ano, semana, _ = inicio.isocalendar()
        return (
            inicio,
            fim,
            os.path.join("semanais", "%04d-S%02d.md" % (ano, semana)),
            "Relatório semanal — semana %02d de %04d (%s a %s)"
            % (semana, ano, inicio.strftime("%d/%m"), fim.strftime("%d/%m/%Y")),
        )

    if tipo == "mensal":
        primeiro_do_mes = referencia.replace(day=1)
        fim = primeiro_do_mes - dt.timedelta(days=1)
        inicio = fim.replace(day=1)
        meses = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        return (
            inicio,
            fim,
            os.path.join("mensais", "%04d-%02d.md" % (inicio.year, inicio.month)),
            "Relatório mensal — %s de %d" % (meses[inicio.month - 1], inicio.year),
        )

    raise ValueError("tipo desconhecido: %s" % tipo)


def monta_relatorio(tipo, registros, descobertas, referencia, inicio, fim, titulo):
    novos_caminhos = arquivos_novos(inicio, fim)
    linhas_novos, novos = bloco_novos(registros, novos_caminhos, inicio, fim)
    ids_novos = {r.get("id") for r in novos}

    partes = ["# %s" % titulo, ""]

    if tipo == "diario":
        partes += [
            "Relatório gerado automaticamente a partir do estado da base em %s."
            % comum.br_data(referencia.isoformat()),
            "",
        ]
    else:
        partes += [
            "Consolidação do período de %s a %s, gerada a partir do estado atual da "
            "base e do histórico registrado em cada oportunidade."
            % (comum.br_data(inicio.isoformat()), comum.br_data(fim.isoformat())),
            "",
        ]

    blocos = [
        bloco_panorama(registros, referencia, "Panorama na geração do relatório"),
        linhas_novos,
        bloco_transicoes(registros, inicio, fim),
        bloco_alterados(registros, inicio, fim, ids_novos),
        bloco_prazos(registros, referencia),
        bloco_a_abrir(registros, referencia),
        bloco_provas(registros, referencia),
        bloco_coleta(descobertas, inicio, fim),
        bloco_pendencias(registros, referencia),
        bloco_validacao(),
    ]

    for bloco in blocos:
        if not bloco:
            continue
        partes += bloco
        partes.append("")

    partes += rodape(referencia, inicio, fim)
    return "\n".join(partes) + "\n"


def pode_escrever(caminho: str, forcar: bool):
    """(permitido, motivo). Nunca sobrescreve relatorio escrito a mao sem --forcar."""
    if not os.path.exists(caminho):
        return True, None
    if forcar:
        return True, None
    try:
        with open(caminho, encoding="utf-8") as fh:
            conteudo = fh.read()
    except OSError:
        return False, "arquivo existente nao pode ser lido"
    if MARCA in conteudo:
        return True, None
    return (
        False,
        "já existe e não foi gerado por esta ferramenta (provavelmente escrito à mão)",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera relatorios diario, semanal e mensal do monitoramento."
    )
    parser.add_argument(
        "--tipo",
        choices=("diario", "semanal", "mensal"),
        default="diario",
        help="cadencia do relatorio (padrao: diario)",
    )
    parser.add_argument("--data", help="data de referencia (AAAA-MM-DD; padrao: hoje)")
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="sobrescreve o arquivo mesmo que tenha sido escrito a mao",
    )
    parser.add_argument("--saida", help="caminho alternativo do arquivo de saida")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="imprime o relatorio na saida padrao, sem gravar",
    )
    args = parser.parse_args()

    referencia = dt.date.fromisoformat(args.data) if args.data else comum.hoje()
    inicio, fim, relativo, titulo = periodo_para(args.tipo, referencia)

    registros = comum.carregar_registros()
    descobertas = carregar_descobertas()
    conteudo = monta_relatorio(
        args.tipo, registros, descobertas, referencia, inicio, fim, titulo
    )

    if args.dry_run:
        sys.stdout.write(conteudo)
        return 0

    destino = args.saida or os.path.join(DIR_RELATORIOS, relativo)
    permitido, motivo = pode_escrever(destino, args.forcar)
    if not permitido:
        print(
            "Preservado: %s %s. Use --forcar para sobrescrever."
            % (os.path.relpath(destino, comum.RAIZ), motivo)
        )
        return 0

    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(conteudo)

    print(
        "Relatório %s gravado: %s (período %s a %s)"
        % (
            args.tipo,
            os.path.relpath(destino, comum.RAIZ),
            inicio.isoformat(),
            fim.isoformat(),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
