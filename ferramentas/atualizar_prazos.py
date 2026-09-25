#!/usr/bin/env python3
"""Aplica as transicoes de status que decorrem so do calendario.

Duas transicoes sao MECANICAS: nao dependem de consultar fonte nenhuma, porque a
data que as dispara ja esta gravada no proprio registro. Esta ferramenta faz
exatamente essas duas, e nada mais:

    edital_publicado   -> inscricoes_abertas      quando inscricoes.inicio chega
    inscricoes_abertas -> inscricoes_encerradas   quando inscricoes.fim passa
    (edital_publicado  -> inscricoes_encerradas   quando o periodo inteiro passa)

Por que existe: o validador reprova um registro com status 'inscricoes_abertas' e
prazo vencido — e com razao, porque a tabela do README passaria a mentir. Isso
travava a execucao agendada no primeiro prazo que vencesse, e junto com ela o
README, os relatorios e o e-mail de alerta. A abertura entrou depois, pelo motivo
oposto: sem ela, o dia em que as inscricoes comecam passa sem gerar alerta nenhum.

O que faz em cada transicao:
  * muda o status;
  * acrescenta entrada em historico_status datada no dia do fato (inicio ou fim
    das inscricoes), dizendo explicitamente que a transicao foi automatica e que a
    fonte nao foi reconsultada;
  * move o arquivo para 'encerrados/' quando encerra. A abertura nao move nada:
    'edital_publicado' e 'inscricoes_abertas' vivem no mesmo diretorio.

O que NAO faz, de proposito:
  * nao altera 'ultima_verificacao' — nenhuma fonte foi consultada aqui, e dizer o
    contrario seria mentir no campo que serve justamente para medir isso;
  * nao altera 'ultima_atualizacao' — nada de novo foi apurado sobre a oportunidade.
    As datas ja estavam no registro; o que mudou foi o calendario. Mexer nesse campo
    sem ter consultado fonte alguma tambem violaria a regra do validador de que uma
    atualizacao de conteudo nao pode ser mais recente que a ultima verificacao. A
    trilha da transicao fica em historico_status, que e o lugar dela;
  * nao reescreve 'observacoes', que e texto curado por pessoa;
  * nao infere nada sobre as etapas seguintes do certame (prova, resultado).

Limites conhecidos, e eles apontam para lados diferentes:
  * ENCERRAMENTO: se a fonte prorrogou o prazo e o registro nao foi atualizado, o
    certame e encerrado aqui indevidamente. O erro esconde uma inscricao que ainda
    estava aberta.
  * ABERTURA: se a fonte adiou o inicio e o registro nao foi atualizado, o registro
    passa a afirmar 'inscricoes_abertas' antes da hora. O erro manda alguem tentar
    se inscrever num sistema que ainda nao abriu.
  Nos dois casos a entrada em historico_status diz que foi transicao automatica pelo
  prazo registrado, e a correcao e reverificar a fonte. Retificacao de cronograma
  sem ninguem notar e justamente um dos casos que o alerta diario existe para provocar.

Uso:
    python3 ferramentas/atualizar_prazos.py
    python3 ferramentas/atualizar_prazos.py --dry-run
    DATA_REFERENCIA=2026-10-01 python3 ferramentas/atualizar_prazos.py --dry-run
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402


def destino_encerrado(relativo: str) -> str:
    """Traduz 'concursos/abertos/x.json' em 'concursos/encerrados/x.json'."""
    partes = relativo.replace(os.sep, "/").split("/")
    if len(partes) != 3 or partes[1] != "abertos":
        raise ValueError("caminho inesperado para registro aberto: %s" % relativo)
    return "/".join([partes[0], "encerrados", partes[2]])


def mover(origem_abs: str, destino_abs: str) -> None:
    """Move preservando o rastro no Git quando o git estiver disponivel."""
    os.makedirs(os.path.dirname(destino_abs), exist_ok=True)
    try:
        proc = subprocess.run(
            ["git", "-C", comum.RAIZ, "mv", origem_abs, destino_abs],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    # Sem git (ou arquivo ainda nao versionado): move pelo sistema de arquivos.
    os.replace(origem_abs, destino_abs)


def transicoes_pendentes(registro, referencia):
    """Lista [(status_novo, data_do_fato)] a aplicar, em ordem cronologica."""
    status = registro.get("status")
    insc = registro.get("inscricoes") or {}
    inicio = comum.data_ou_none(insc.get("inicio"))
    fim = comum.data_ou_none(insc.get("fim"))

    pendentes = []
    if status == "edital_publicado" and inicio is not None and inicio <= referencia:
        pendentes.append(("inscricoes_abertas", inicio))
        status = "inscricoes_abertas"
    if status in ("edital_publicado", "inscricoes_abertas") and fim is not None and fim < referencia:
        pendentes.append(("inscricoes_encerradas", fim))
    return pendentes


def _texto(status_novo, referencia, data_fato) -> str:
    if status_novo == "inscricoes_abertas":
        return (
            "Abertura registrada automaticamente em %s pela data de início das "
            "inscrições (%s) já constante do registro. A fonte não foi reconsultada "
            "nesta transição: confirmar se a abertura não foi adiada."
            % (referencia.strftime("%d/%m/%Y"), data_fato.strftime("%d/%m/%Y"))
        )
    return (
        "Encerramento registrado automaticamente em %s pelo prazo do edital (%s) já "
        "constante do registro. A fonte não foi reconsultada nesta transição: "
        "confirmar se não houve prorrogação."
        % (referencia.strftime("%d/%m/%Y"), data_fato.strftime("%d/%m/%Y"))
    )


def aplicar(relativo: str, pendentes, referencia) -> None:
    caminho = os.path.join(comum.DIR_DADOS, relativo)
    with open(caminho, encoding="utf-8") as fh:
        dados = json.load(fh, object_pairs_hook=collections.OrderedDict)

    historico = dados.setdefault("historico_status", [])
    for status_novo, data_fato in pendentes:
        # A entrada e datada no dia do fato. Se o registro ja tiver entrada
        # posterior, usa a data da ultima para nao quebrar a ordem cronologica
        # exigida pelo validador — a data real segue explicita na observacao.
        datas = [
            h.get("data")
            for h in historico
            if isinstance(h, dict) and h.get("data")
        ]
        data_entrada = data_fato.isoformat()
        if datas:
            data_entrada = max(data_entrada, max(datas))
        historico.append(
            collections.OrderedDict(
                [
                    ("data", data_entrada),
                    ("status", status_novo),
                    ("observacao", _texto(status_novo, referencia, data_fato)),
                ]
            )
        )
        dados["status"] = status_novo

    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    if dados["status"] == "inscricoes_encerradas":
        mover(caminho, os.path.join(comum.DIR_DADOS, destino_encerrado(relativo)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aplica as transicoes de status que decorrem dos prazos registrados."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="relata sem alterar nem mover arquivos"
    )
    parser.add_argument(
        "--saida-github",
        dest="saida_github",
        help="arquivo estilo $GITHUB_OUTPUT onde gravar abertos=/encerrados=",
    )
    args = parser.parse_args()

    referencia = comum.hoje()
    abertos = encerrados = 0

    for relativo, registro in comum.carregar_registros():
        if "abertos" not in relativo.replace(os.sep, "/").split("/"):
            continue
        pendentes = transicoes_pendentes(registro, referencia)
        if not pendentes:
            continue

        for status_novo, data_fato in pendentes:
            if status_novo == "inscricoes_abertas":
                abertos += 1
                verbo = "inscrições abertas desde"
            else:
                encerrados += 1
                verbo = "prazo encerrado em"
            print(
                "%s %s (%s) — %s %s: status -> '%s'"
                % (
                    "[dry-run]" if args.dry_run else "aplicado:",
                    registro.get("id"),
                    registro.get("orgao_sigla") or registro.get("orgao"),
                    verbo,
                    comum.br_data(data_fato.isoformat()),
                    status_novo,
                )
            )
        if not args.dry_run:
            aplicar(relativo, pendentes, referencia)

    if not abertos and not encerrados:
        print(
            "Nenhuma transição de prazo pendente em %s."
            % referencia.strftime("%d/%m/%Y")
        )
    else:
        print(
            "\n%d abertura(s) e %d encerramento(s) %s. Confirme na fonte se algum "
            "cronograma foi retificado."
            % (
                abertos,
                encerrados,
                "seriam aplicados" if args.dry_run else "aplicados",
            )
        )

    if args.saida_github:
        with open(args.saida_github, "a", encoding="utf-8") as fh:
            fh.write("abertos=%d\n" % abertos)
            fh.write("encerrados=%d\n" % encerrados)

    return 0


if __name__ == "__main__":
    sys.exit(main())
