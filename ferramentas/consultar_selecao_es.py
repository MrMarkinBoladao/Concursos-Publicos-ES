#!/usr/bin/env python3
"""Abre um processo do portal Seleção ES e baixa o edital, para curadoria.

MOTIVO DE EXISTIR: a pagina de um processo no portal e uma SPA em Vue — baixar o
HTML devolve casca vazia, sem edital, sem prazo, sem cargo. Os dados vem de tres
endpoints que a pagina consome, e o arquivo vem de outro dominio. Este script
registra esse caminho para que a proxima curadoria nao precise redescobri-lo:

    GET  /processo-seletivo/{guid}/info          metadados e descricao
    POST /processo-seletivo/{guid}/publicacoes   lista de arquivos (paginada)
    GET  classico.selecao.es.gov.br/Arquivo/DownloadArquivo/{id}   o arquivo

O `guid` e o `identificadorExterno` que aparece na URL do processo e tambem no
resultado da coleta, em descobertas/descobertas.json.

O script NAO escreve em dados/: ele so apura. Preencher o registro conforme o
ESQUEMA.md continua sendo trabalho de leitura e julgamento.

Uso:
    python3 ferramentas/consultar_selecao_es.py <guid>
    python3 ferramentas/consultar_selecao_es.py <guid> --baixar
    python3 ferramentas/consultar_selecao_es.py <guid> --baixar --destino /tmp/editais
    python3 ferramentas/consultar_selecao_es.py <guid> --baixar --trecho "remunera|jornada"

Cuidado ao ler o resultado: um PDF de "extrato do Diario Oficial" costuma conter
varias publicacoes na mesma pagina, de orgaos diferentes. Valor encontrado ali nao
e necessariamente do certame que se esta apurando — confira no edital integro.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

NAVEGADOR = "Mozilla/5.0 (X11; Linux x86_64) Python-urllib monitoramento-concursos-es"
TIMEOUT = 60
BASE = "https://selecao.es.gov.br/processo-seletivo"
DOWNLOAD = "https://classico.selecao.es.gov.br/Arquivo/DownloadArquivo/%s"

# Nomes que indicam publicacao de acompanhamento, nao o edital de abertura.
RUIDO = r"classifica|convoca|resultado|heteroident|recurso|homologa|anexo|extrato"


def _abre(url, dados=None):
    cabecalhos = {"User-Agent": NAVEGADOR, "accept": "application/json"}
    corpo = None
    if dados is not None:
        corpo = json.dumps(dados).encode("utf-8")
        cabecalhos["content-type"] = "application/json"
    pedido = urllib.request.Request(url, data=corpo, headers=cabecalhos)
    return urllib.request.urlopen(pedido, timeout=TIMEOUT).read()


def info(guid):
    return json.loads(_abre("%s/%s/info" % (BASE, guid)))["value"]


def publicacoes(guid, quantidade=200):
    resposta = _abre(
        "%s/%s/publicacoes" % (BASE, guid),
        {"currentPage": 1, "resultsPerPage": quantidade},
    )
    return json.loads(resposta)["value"]["dados"]


def escolhe_edital(arquivos):
    """Melhor candidato a edital de abertura, preferindo a versao retificada."""
    candidatos = [a for a in arquivos if re.search(r"edital", a["nomeArquivo"], re.I)]
    limpos = [a for a in candidatos if not re.search(RUIDO, a["nomeArquivo"], re.I)]
    candidatos = limpos or candidatos
    if not candidatos:
        return None
    retificados = [a for a in candidatos if re.search(r"retific", a["nomeArquivo"], re.I)]
    return (retificados or candidatos)[0]


def baixa(arquivo, destino):
    os.makedirs(destino, exist_ok=True)
    nome = re.sub(r"[^\w.-]+", "-", arquivo["nomeArquivo"]).strip("-").lower()
    caminho = os.path.join(destino, "%s.%s" % (nome[:80], arquivo["extensao"]))
    with open(caminho, "wb") as fh:
        fh.write(_abre(DOWNLOAD % arquivo["id"]))
    return caminho


def texto_pdf(caminho):
    """Texto do PDF. Exige pypdf; devolve None se a biblioteca nao estiver instalada."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    leitor = PdfReader(caminho)
    bruto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    return re.sub(r"[ \t]+", " ", bruto)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta um processo seletivo no portal Selecao ES."
    )
    parser.add_argument("guid", help="identificadorExterno do processo, como na URL")
    parser.add_argument("--baixar", action="store_true", help="baixa o edital de abertura")
    parser.add_argument(
        "--destino",
        default=os.path.join(tempfile.gettempdir(), "editais-es"),
        help="diretorio para os downloads (padrao: temporario do sistema)",
    )
    parser.add_argument("--trecho", help="regex para exibir trechos do edital baixado")
    args = parser.parse_args()

    try:
        meta = info(args.guid)
    except Exception as exc:  # rede, guid inexistente, formato inesperado
        print("ERRO ao consultar o processo: %s" % type(exc).__name__, file=sys.stderr)
        return 1

    print("Órgão:      %s — %s" % (meta.get("siglaOrgao"), meta.get("nomeOrgao")))
    print("Processo:   %s" % meta.get("nome"))
    print(
        "Inscrições: %s até %s"
        % (meta.get("dataInicioInscricao"), meta.get("dataFimInscricao"))
    )
    print("Vigência:   %s" % meta.get("dataFimVigencia"))
    contato = " ".join(
        str(meta.get(campo) or "") for campo in ("contatoTelefone", "contatoEmail")
    ).strip()
    print("Contato:    %s" % (contato or comum.AUSENTE))
    print("\nDescrição:\n%s" % re.sub(r"\s+", " ", meta.get("descricao") or comum.AUSENTE))

    arquivos = publicacoes(args.guid)
    print("\nPublicações (%d):" % len(arquivos))
    for arquivo in arquivos[:15]:
        print(
            "  %-7s %s  %s"
            % (arquivo["id"], arquivo["dataUpload"][:10], arquivo["nomeArquivo"][:70])
        )
    if len(arquivos) > 15:
        print("  ... e mais %d." % (len(arquivos) - 15))

    escolhido = escolhe_edital(arquivos)
    if not escolhido:
        print("\nNenhum arquivo com cara de edital de abertura.")
        return 0
    print(
        "\nEdital de abertura (provável): %s (id %s)"
        % (escolhido["nomeArquivo"], escolhido["id"])
    )
    print("Download direto: %s" % (DOWNLOAD % escolhido["id"]))

    if not args.baixar:
        return 0

    caminho = baixa(escolhido, args.destino)
    print("Baixado em: %s" % caminho)

    conteudo = texto_pdf(caminho)
    if conteudo is None:
        print("Instale pypdf para extrair o texto: pip install pypdf")
        return 0
    if len(conteudo) < 500:
        print(
            "ATENÇÃO: quase nenhum texto extraído (%d caracteres). O PDF é "
            "provavelmente digitalizado; os dados terão de vir de outra fonte, e a "
            "pendência deve ficar registrada em 'observacoes'." % len(conteudo)
        )
        return 0

    print("Texto extraído: %d caracteres." % len(conteudo))
    print("Valores em R$: %s" % sorted(set(re.findall(r"R\$ ?[\d\.]+,\d{2}", conteudo)))[:15])
    print(
        "Jornadas citadas: %s"
        % sorted(set(re.findall(r"\d{2} ?h(?:oras)? ?semanais", conteudo, re.I)))[:8]
    )

    if args.trecho:
        for achado in list(re.finditer(args.trecho, conteudo, re.I))[:4]:
            inicio = max(0, achado.start() - 100)
            print("\n--- trecho ---")
            print(re.sub(r"\n{2,}", "\n", conteudo[inicio : inicio + 700]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
