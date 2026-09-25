#!/usr/bin/env python3
"""Encerra registros cujo prazo de inscricao ja passou.

Por que existe: o validador reprova um registro com status 'inscricoes_abertas' e
prazo vencido — e com razao, porque a tabela do README passaria a mentir. Mas isso
travava a execucao agendada no primeiro prazo que vencesse, e junto com ela o
README, os relatorios e o e-mail de alerta. Esta ferramenta faz a unica parte
dessa transicao que NAO exige julgamento: virar a chave quando a data registrada
no proprio edital passou.

O que faz, para cada registro em abertos/ com status 'inscricoes_abertas' ou
'edital_publicado' e 'inscricoes.fim' anterior a data de referencia:
  * muda o status para 'inscricoes_encerradas';
  * acrescenta entrada em historico_status, datada no fim das inscricoes, dizendo
    explicitamente que a transicao foi automatica e que a fonte nao foi reconsultada;
  * move o arquivo para o diretorio 'encerrados/' correspondente.

O que NAO faz, de proposito:
  * nao altera 'ultima_verificacao' — nenhuma fonte foi consultada aqui, e dizer o
    contrario seria mentir no campo que serve justamente para medir isso;
  * nao altera 'ultima_atualizacao' — nada de novo foi apurado sobre a oportunidade.
    O prazo ja estava no registro; o que mudou foi o calendario. Mexer nesse campo
    sem ter consultado fonte alguma tambem violaria a regra do validador de que uma
    atualizacao de conteudo nao pode ser mais recente que a ultima verificacao. A
    trilha da transicao fica em historico_status, que e o lugar dela;
  * nao reescreve 'observacoes', que e texto curado por pessoa;
  * nao infere nada sobre as etapas seguintes do certame (prova, resultado): o
    status vira 'inscricoes_encerradas' e para ai.

Limite conhecido: se a fonte prorrogou o prazo e o registro nao foi atualizado, o
certame sera encerrado aqui indevidamente. A trilha em historico_status deixa claro
que foi transicao automatica pelo prazo registrado, e a correcao e mover o registro
de volta ao reverificar a fonte. Prazo prorrogado sem ninguem notar e justamente um
dos casos que o alerta diario existe para provocar.

Uso:
    python3 ferramentas/encerrar_vencidos.py
    python3 ferramentas/encerrar_vencidos.py --dry-run
    DATA_REFERENCIA=2026-10-01 python3 ferramentas/encerrar_vencidos.py --dry-run
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

# Status que representam inscricao em curso ou por comecar, logo sujeitos a vencer.
STATUS_ALVO = {"inscricoes_abertas", "edital_publicado"}


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


def encerrar(relativo: str, registro, referencia, fim) -> None:
    caminho_origem = os.path.join(comum.DIR_DADOS, relativo)
    relativo_destino = destino_encerrado(relativo)
    caminho_destino = os.path.join(comum.DIR_DADOS, relativo_destino)

    with open(caminho_origem, encoding="utf-8") as fh:
        dados = json.load(fh, object_pairs_hook=collections.OrderedDict)

    historico = [h for h in (dados.get("historico_status") or []) if isinstance(h, dict)]
    # A entrada e datada no fim das inscricoes, que e quando o fato ocorreu. Se o
    # registro ja tiver entrada posterior a essa data, usa a data da ultima entrada
    # para nao quebrar a ordem cronologica exigida pelo validador — o prazo real
    # continua explicito no texto da observacao.
    data_entrada = fim.isoformat()
    datas_existentes = [h.get("data") for h in historico if h.get("data")]
    if datas_existentes:
        data_entrada = max(data_entrada, max(datas_existentes))

    dados["status"] = "inscricoes_encerradas"
    dados.setdefault("historico_status", []).append(
        collections.OrderedDict(
            [
                ("data", data_entrada),
                ("status", "inscricoes_encerradas"),
                (
                    "observacao",
                    "Encerramento registrado automaticamente em %s pelo prazo do "
                    "edital (%s) já constante do registro. A fonte não foi "
                    "reconsultada nesta transição: confirmar se não houve prorrogação."
                    % (referencia.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")),
                ),
            ]
        )
    )

    with open(caminho_origem, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    mover(caminho_origem, caminho_destino)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encerra registros com prazo de inscricao vencido."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="relata sem alterar nem mover arquivos"
    )
    parser.add_argument(
        "--saida-github",
        dest="saida_github",
        help="arquivo estilo $GITHUB_OUTPUT onde gravar encerrados=",
    )
    args = parser.parse_args()

    referencia = comum.hoje()
    vencidos = []

    for relativo, registro in comum.carregar_registros():
        if "abertos" not in relativo.replace(os.sep, "/").split("/"):
            continue
        if registro.get("status") not in STATUS_ALVO:
            continue
        fim = comum.data_ou_none((registro.get("inscricoes") or {}).get("fim"))
        if fim is None or fim >= referencia:
            continue
        vencidos.append((relativo, registro, fim))

    if not vencidos:
        print(
            "Nenhum registro com prazo vencido em %s."
            % referencia.strftime("%d/%m/%Y")
        )
    else:
        for relativo, registro, fim in vencidos:
            print(
                "%s %s (%s) — prazo encerrou em %s, status '%s' -> "
                "'inscricoes_encerradas'"
                % (
                    "[dry-run]" if args.dry_run else "encerrado:",
                    registro.get("id"),
                    registro.get("orgao_sigla") or registro.get("orgao"),
                    comum.br_data(fim.isoformat()),
                    registro.get("status"),
                )
            )
            if not args.dry_run:
                encerrar(relativo, registro, referencia, fim)

        print(
            "\n%d registro(s) %s. Confirme na fonte se algum prazo foi prorrogado."
            % (
                len(vencidos),
                "seriam encerrados" if args.dry_run else "encerrados e movidos para 'encerrados/'",
            )
        )

    if args.saida_github:
        with open(args.saida_github, "a", encoding="utf-8") as fh:
            fh.write("encerrados=%d\n" % len(vencidos))

    return 0


if __name__ == "__main__":
    sys.exit(main())
