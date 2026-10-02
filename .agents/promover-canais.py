#!/usr/bin/env python3
"""Uso unico (item 14): promove a 'confirmado' o canal de diario dos municipios
com ato observado em confianca alta numa coleta real. NAO e versionado.

Roda a coleta nos dois escopos, escolhe por municipio o ato mais recente
observado NO ESCOPO DOM (que e o canal cadastrado, url .../dom, fonte_id
amunes-dom) e reescreve fontes/municipios-es.json.
"""

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))

import coletar  # noqa: E402
import comum  # noqa: E402

JANELA = 7
indice = comum.indice_municipios()
referencia = comum.hoje()
di = (referencia - __import__("datetime").timedelta(days=JANELA)).isoformat()

achados = {}
for escopo in ("dom", "dio"):
    diag = {}
    lista = coletar.coletar_ioes(escopo=escopo, diagnostico=diag, janela_dias=JANELA,
                                 indice=indice)
    achados[escopo] = lista
    print("%s: %d achados, total relatado %s" % (escopo, len(lista),
                                                 diag.get("total_relatado")),
          file=sys.stderr)

melhor = {}
por_escopo = {"dom": set(), "dio": set()}
for escopo in ("dom", "dio"):
    for achado in achados[escopo]:
        slug = achado.get("municipio_slug")
        if not slug or achado.get("municipio_confianca") != "alta":
            continue
        por_escopo[escopo].add(slug)
        if escopo != "dom":
            continue
        atual = melhor.get(slug)
        chave = (achado.get("data_publicacao_ato") or "", achado.get("url") or "")
        if atual is None or chave > atual[0]:
            melhor[slug] = (chave, achado)

print("alta no DOM: %d | alta no DIO: %d | so no DIO: %s"
      % (len(por_escopo["dom"]), len(por_escopo["dio"]),
         sorted(por_escopo["dio"] - por_escopo["dom"])), file=sys.stderr)

caminho = comum.CAMINHO_MUNICIPIOS
cadastro = comum.carregar_municipios()
promovidos = []
for municipio in cadastro["municipios"]:
    dados = melhor.get(municipio["slug"])
    if not dados:
        continue
    achado = dados[1]
    # A evidencia NAO cita o titulo da pagina: o titulo vem do highlight e e da
    # PAGINA, enquanto a atribuicao de municipio e do BLOCO de ato — citar um
    # pelo outro afirmaria que o ato de outro municipio da mesma pagina e deste.
    # O que se afirma e o que foi medido: a pagina do DOM/AMUNES traz o nome do
    # municipio com marca institucional adjacente (confianca alta) num ato
    # devolvido pela busca por concurso/processo seletivo.
    atribuido = achado.get("orgao")
    sufixo = (
        "; ato atribuido a %s" % atribuido
        if atribuido and atribuido != comum.AUSENTE
        else ""
    )
    if achado.get("editais_citados") or ":edital-" in achado.get("chave", ""):
        sufixo += "; numero de edital no mesmo bloco de ato"
    for canal in municipio["canais"]:
        if canal["tipo"] != "diario_oficial_agregador":
            continue
        canal["estado"] = "confirmado"
        canal["verificado_em"] = referencia.isoformat()
        canal["evidencia"] = (
            "nome do municipio em confianca alta (marca institucional "
            "adjacente) na pagina do DOM/AMUNES de %s, edicao %s, pagina %s "
            "(%s), devolvida pela busca do IOES por \"concurso publico\" e "
            "\"processo seletivo\" na janela de %d dias (di: %s)%s"
            % (
                achado.get("data_publicacao_ato"),
                achado.get("edicao"),
                (achado.get("url") or "").rsplit("/", 1)[-1],
                achado.get("url"),
                JANELA,
                di,
                sufixo,
            )
        )
        promovidos.append(municipio["slug"])

    # A pendencia e recalculada a partir do estado real dos canais: so continua
    # declarada se algum canal pendente ainda a justifica.
    pendentes = [c for c in municipio["canais"] if c["estado"] == "pendente"]
    pendencias = []
    if any("respondeu HTTP" in (c.get("evidencia") or "") for c in pendentes):
        pendencias.append("canais:conferir_manual")
    if any(
        ("timeout" in (c.get("evidencia") or "") or "nao respondeu" in (c.get("evidencia") or ""))
        for c in pendentes
    ):
        pendencias.append("canais:nao_responde")
    outras = [p for p in municipio["pendencias_verificacao"]
              if not p.startswith("canais:")]
    municipio["pendencias_verificacao"] = pendencias + outras

cadastro["ultima_atualizacao"] = referencia.isoformat()
with open(caminho, "w", encoding="utf-8") as fh:
    json.dump(cadastro, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print("promovidos: %d -> %s" % (len(promovidos), sorted(promovidos)), file=sys.stderr)
