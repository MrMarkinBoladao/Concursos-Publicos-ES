#!/usr/bin/env python3
"""Valida os registros de oportunidades do repositorio.

Verifica estrutura do JSON, vocabulario dos campos, coerencia entre status e
diretorio, coerencia de datas, escopo geografico (ES) e duplicidade.

Uso:
    python3 ferramentas/validar.py
    python3 ferramentas/validar.py --json    # saida legivel por maquina

Codigo de saida 0 quando nao ha ERROS (avisos nao reprovam), 1 caso contrario.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

CAMPOS_OBRIGATORIOS = [
    "id",
    "orgao",
    "orgao_sigla",
    "esfera",
    "municipio",
    "uf",
    "tipo",
    "cargos",
    "vagas_imediatas_total",
    "cadastro_reserva",
    "escolaridade",
    "remuneracao",
    "beneficios",
    "jornada",
    "edital_numero",
    "publicacao",
    "inscricoes",
    "prova",
    "banca",
    "status",
    "regime",
    "validade",
    "links",
    "fontes",
    "historico_status",
    "ultima_verificacao",
    "ultima_atualizacao",
    "observacoes",
]

CAMPOS_CARGO = [
    "nome",
    "area",
    "vagas_imediatas",
    "cadastro_reserva",
    "escolaridade",
    "requisitos",
    "remuneracao",
    "jornada",
]

RE_ID = re.compile(r"^(concurso|ps)-[a-z0-9-]+-\d{4}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_ID_FONTE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RE_CODIGO_IBGE = re.compile(r"^32\d{5}$")

# Caminho proprio em vez de importar coletar.CAMINHO_FONTES: o validador
# depende apenas de comum (ver o comentario do import tardio em
# valida_catalogo_fontes), e e o mesmo arranjo que CAMINHO_DESCOBERTAS ja usa.
CAMINHO_FONTES = os.path.join(comum.RAIZ, "fontes", "fontes.json")

# Conjuntos de chaves PERMITIDAS, escritos por extenso. Chave desconhecida e
# erro, e nao aviso, porque foi exatamente a ausencia dessa checagem que deixou
# 12 fontes sem 'esfera' passarem por meses: 'esferra:' digitado errado nao e
# campo novo, e campo perdido.
CHAVES_FONTE = {
    "id",
    "nome",
    "url",
    "tipo",
    "esfera",
    "prioridade",
    "observacao",
    "coletada_automaticamente",
}
CAMPOS_FONTE_OBRIGATORIOS = ("nome", "url", "tipo", "esfera", "prioridade")

CHAVES_MUNICIPIO = {
    "codigo_ibge",
    "nome",
    "slug",
    "aliases",
    "microrregiao",
    "canais",
    "pendencias_verificacao",
    "verificado_em",
}
CHAVES_CANAL = {
    "tipo",
    "precedencia",
    "url",
    "fonte_id",
    "estado",
    "evidencia",
    "verificado_em",
}
CHAVES_ORGAO = {
    "id",
    "nome",
    "aliases",
    "sigla",
    "natureza",
    "esfera",
    "municipios_slugs",
    "url",
    "fontes",
    "evidencia",
    "pendencias_verificacao",
    "verificado_em",
}

ESTADOS_CANAL = {"confirmado", "pendente"}
TIPOS_CANAL_DIARIO = {"diario_oficial_proprio", "diario_oficial_agregador"}

# Aridade de municipios_slugs por natureza, e nao uma regra unica: uma camara
# ou autarquia pertence a UM municipio, mas uma agencia reguladora
# multimunicipal nao pode ser forcada a creditar a sede.
NATUREZAS_DE_UM_MUNICIPIO = {
    "camara_municipal",
    "autarquia_municipal",
    "fundacao_municipal",
    "empresa_municipal",
}
NATUREZAS_INTERMUNICIPAIS = {"consorcio_intermunicipal", "agencia_reguladora"}

# Unico lugar onde o 78 aparece no codigo, e so como PISO HISTORICO: a
# contagem que vale e 'total_esperado' lida do cadastro, com a qual
# len(municipios) e comparada. Se o numero de municipios fosse literal aqui, o
# dia em que um 79o municipio fosse criado por lei — justamente o que a
# reconciliacao com o IBGE existe para detectar — deixaria o repositorio
# reprovado ate alguem editar este arquivo, edicao que ninguem lembraria de
# fazer. Por isso 'total_esperado != 78' e apenas AVISO ("confira contra o
# IBGE") e 'total_esperado < 78' e erro: o ES nunca teve menos de 78, logo um
# numero menor significa entrada apagada para "resolver" uma falha.
TOTAL_HISTORICO_MUNICIPIOS_ES = 78

# Limite de achados em quarentena acima do qual a retencao de ato_diario
# provavelmente parou de funcionar. Rede de seguranca: o sintoma aparece como
# aviso num arquivo que cresce, em vez de como lentidao inexplicada.
LIMITE_ACHADOS_QUARENTENA = 5000

# Valores do campo 'municipio' de dados/ que NAO sao nome de municipio e sao
# aceitos sem resolucao (medido: 24 registros no primeiro, 1 no segundo). O
# sufixo livre de "Diversos (ES) - Linhares e região" e descritivo e nao deve
# ser normalizado.
MUNICIPIO_AMBITO_ESTADUAL = "Âmbito estadual (ES)"
MUNICIPIO_PREFIXO_DIVERSOS = "Diversos (ES)"


class Relatorio:
    def __init__(self):
        self.erros = []
        self.avisos = []

    def erro(self, arquivo, mensagem):
        self.erros.append({"arquivo": arquivo, "mensagem": mensagem})

    def aviso(self, arquivo, mensagem):
        self.avisos.append({"arquivo": arquivo, "mensagem": mensagem})


def _valida_data(rel, arquivo, rotulo, valor, obrigatorio=False):
    """Confere formato ISO. Devolve o date correspondente, ou None."""
    if valor is None or valor == comum.AUSENTE:
        if obrigatorio:
            rel.erro(arquivo, "%s e obrigatorio e esta ausente" % rotulo)
        return None
    if not isinstance(valor, str) or not RE_DATA.match(valor):
        rel.erro(arquivo, "%s='%s' nao esta no formato AAAA-MM-DD" % (rotulo, valor))
        return None
    data = comum.data_ou_none(valor)
    if data is None:
        rel.erro(arquivo, "%s='%s' nao e uma data valida" % (rotulo, valor))
    return data


def valida_estrutura(rel, arquivo, reg):
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in reg:
            rel.erro(arquivo, "campo obrigatorio ausente: '%s'" % campo)

    if not isinstance(reg.get("cargos"), list) or not reg.get("cargos"):
        rel.erro(arquivo, "'cargos' deve ser uma lista com pelo menos um item")
    else:
        for i, cargo in enumerate(reg["cargos"]):
            if not isinstance(cargo, dict):
                rel.erro(arquivo, "cargos[%d] deve ser um objeto" % i)
                continue
            for campo in CAMPOS_CARGO:
                if campo not in cargo:
                    rel.erro(arquivo, "cargos[%d] sem o campo '%s'" % (i, campo))

    for campo, tipo, rotulo in (
        ("remuneracao", dict, "objeto"),
        ("inscricoes", dict, "objeto"),
        ("prova", dict, "objeto"),
        ("links", dict, "objeto"),
        ("beneficios", list, "lista"),
        ("fontes", list, "lista"),
        ("historico_status", list, "lista"),
    ):
        if campo in reg and not isinstance(reg[campo], tipo):
            rel.erro(arquivo, "'%s' deve ser um %s" % (campo, rotulo))


def valida_vocabulario(rel, arquivo, reg):
    if reg.get("status") not in comum.STATUS_VALIDOS:
        rel.erro(arquivo, "status invalido: '%s'" % reg.get("status"))
    if reg.get("esfera") not in comum.ESFERAS_VALIDAS:
        rel.erro(arquivo, "esfera invalida: '%s'" % reg.get("esfera"))
    if reg.get("tipo") not in comum.TIPOS_VALIDOS:
        rel.erro(arquivo, "tipo invalido: '%s'" % reg.get("tipo"))
    if reg.get("regime") not in comum.REGIMES_VALIDOS:
        rel.erro(arquivo, "regime invalido: '%s'" % reg.get("regime"))

    if not RE_ID.match(reg.get("id", "")):
        rel.erro(
            arquivo,
            "id '%s' fora do padrao <tipo>-<orgao>-<recorte>-<ano>" % reg.get("id"),
        )

    esperado = reg.get("id", "") + ".json"
    if os.path.basename(arquivo) != esperado:
        rel.erro(
            arquivo,
            "nome do arquivo difere do id: esperado '%s'" % esperado,
        )

    prefixo = "concurso-" if reg.get("tipo") == "concurso_publico" else "ps-"
    if reg.get("id", "") and not reg["id"].startswith(prefixo):
        rel.erro(
            arquivo,
            "id deveria comecar com '%s' para tipo '%s'" % (prefixo, reg.get("tipo")),
        )


def valida_escopo(rel, arquivo, reg, indice=None):
    """O repositorio cobre exclusivamente o Espirito Santo.

    O campo 'municipio' e resolvido CONTRA O CADASTRO, e nao apenas conferido
    como preenchido: nome de municipio e chave de agregacao da cobertura, e um
    registro com grafia divergente nao desaparece — ele CONTA ERRADO, o que e
    pior que falhar alto. Por isso nao resolver e erro, e nao aviso.

    A consulta e a EXATA (comum.resolver_municipio), nunca a de texto livre:
    aqui o valor e um campo curado e curto, e casamento parcial esconderia erro
    de digitacao em vez de aponta-lo.
    """
    if reg.get("uf") != "ES":
        rel.erro(arquivo, "fora de escopo: uf='%s' (esperado 'ES')" % reg.get("uf"))

    municipio = reg.get("municipio")
    if not municipio or municipio == comum.AUSENTE:
        rel.aviso(arquivo, "municipio nao informado — confirmar a lotacao no ES")
        return
    if not isinstance(municipio, str):
        rel.erro(arquivo, "municipio deve ser texto: %r" % (municipio,))
        return
    if municipio == MUNICIPIO_AMBITO_ESTADUAL or municipio.startswith(
        MUNICIPIO_PREFIXO_DIVERSOS
    ):
        return

    indice = indice or comum.indice_municipios()
    slug_mun, origem = comum.resolver_municipio(municipio, indice)
    if slug_mun is None:
        rel.erro(
            arquivo,
            "municipio '%s' nao consta de fontes/municipios-es.json (verifique a "
            "grafia ou acrescente alias)" % municipio,
        )
        return

    if origem == "alias":
        oficial = (indice.por_slug.get(slug_mun) or {}).get("nome")
        rel.aviso(
            arquivo,
            "municipio '%s' resolveu por alias; o nome oficial do IBGE e '%s'"
            % (municipio, oficial),
        )
    elif origem == "orgao_vinculado":
        rel.aviso(
            arquivo,
            "'%s' e nome de orgao vinculado, nao de municipio; use o nome oficial "
            "do municipio no campo 'municipio'" % municipio,
        )

    # Aviso, e nao erro, porque o dado nao esta errado: a sede e aquela mesmo.
    # O que esta errado e usar a sede como jurisdicao — e o calculo de
    # cobertura ja nao a credita.
    if reg.get("esfera") == "intermunicipal":
        rel.aviso(
            arquivo,
            "registro intermunicipal: o municipio de sede nao credita cobertura; "
            "declare a jurisdicao em orgaos_vinculados[].municipios_slugs",
        )


def valida_diretorio(rel, arquivo, reg):
    subdir = os.path.dirname(arquivo)
    permitidos = comum.DIRETORIOS.get(subdir)
    if permitidos is None:
        rel.erro(arquivo, "diretorio desconhecido: '%s'" % subdir)
        return
    if reg.get("status") not in permitidos:
        rel.erro(
            arquivo,
            "status '%s' nao pertence a '%s' (aceitos: %s)"
            % (reg.get("status"), subdir, ", ".join(sorted(permitidos))),
        )

    familia = "concursos" if reg.get("tipo") == "concurso_publico" else "processos-seletivos"
    if not subdir.startswith(familia):
        rel.erro(
            arquivo,
            "tipo '%s' deveria estar sob '%s/', nao '%s'"
            % (reg.get("tipo"), familia, subdir),
        )


def valida_datas(rel, arquivo, reg):
    hoje = comum.hoje()

    verificacao = _valida_data(rel, arquivo, "ultima_verificacao", reg.get("ultima_verificacao"), True)
    atualizacao = _valida_data(rel, arquivo, "ultima_atualizacao", reg.get("ultima_atualizacao"), True)
    publicacao = _valida_data(rel, arquivo, "publicacao", reg.get("publicacao"))

    insc = reg.get("inscricoes") or {}
    inicio = _valida_data(rel, arquivo, "inscricoes.inicio", insc.get("inicio"))
    fim = _valida_data(rel, arquivo, "inscricoes.fim", insc.get("fim"))

    prova = reg.get("prova") or {}
    objetiva = _valida_data(rel, arquivo, "prova.objetiva", prova.get("objetiva"))

    if verificacao and verificacao > hoje:
        rel.erro(arquivo, "ultima_verificacao esta no futuro")
    if atualizacao and verificacao and atualizacao > verificacao:
        rel.erro(arquivo, "ultima_atualizacao e posterior a ultima_verificacao")

    if inicio and fim and inicio > fim:
        rel.erro(arquivo, "inscricoes.inicio e posterior a inscricoes.fim")
    if publicacao and inicio and publicacao > inicio:
        rel.aviso(arquivo, "publicacao posterior ao inicio das inscricoes — confirmar")
    if fim and objetiva and objetiva < fim:
        rel.aviso(arquivo, "prova.objetiva anterior ao fim das inscricoes — confirmar")

    # Coerencia entre o prazo e o status declarado.
    if reg.get("status") == "inscricoes_abertas" and fim and fim < hoje:
        rel.erro(
            arquivo,
            "status 'inscricoes_abertas' mas o prazo terminou em %s — mover para "
            "'encerrados' e atualizar o status" % fim.isoformat(),
        )
    if reg.get("status") == "inscricoes_encerradas" and fim and fim > hoje:
        rel.erro(
            arquivo,
            "status 'inscricoes_encerradas' mas o prazo vai ate %s" % fim.isoformat(),
        )

    for i, entrada in enumerate(reg.get("historico_status") or []):
        if not isinstance(entrada, dict):
            rel.erro(arquivo, "historico_status[%d] deve ser um objeto" % i)
            continue
        _valida_data(rel, arquivo, "historico_status[%d].data" % i, entrada.get("data"), True)
        if entrada.get("status") not in comum.STATUS_VALIDOS:
            rel.erro(
                arquivo,
                "historico_status[%d].status invalido: '%s'" % (i, entrada.get("status")),
            )
        if "observacao" not in entrada:
            rel.aviso(arquivo, "historico_status[%d] sem 'observacao'" % i)


def valida_historico(rel, arquivo, reg):
    """O historico deve ser cronologico e terminar no status atual."""
    historico = [h for h in (reg.get("historico_status") or []) if isinstance(h, dict)]
    if not historico:
        rel.erro(arquivo, "historico_status esta vazio — todo registro precisa de trilha")
        return

    datas = [comum.data_ou_none(h.get("data")) for h in historico]
    if all(d is not None for d in datas) and datas != sorted(datas):
        rel.erro(arquivo, "historico_status nao esta em ordem cronologica")

    if historico[-1].get("status") != reg.get("status"):
        rel.erro(
            arquivo,
            "ultima entrada do historico ('%s') difere do status atual ('%s')"
            % (historico[-1].get("status"), reg.get("status")),
        )

    indices = [
        comum.ORDEM_STATUS.index(h["status"])
        for h in historico
        if h.get("status") in comum.ORDEM_STATUS
    ]
    if indices and indices != sorted(indices):
        rel.aviso(
            arquivo,
            "historico_status regride no ciclo de vida — confirmar se houve "
            "retificacao, suspensao ou reabertura de prazo",
        )


def valida_fontes(rel, arquivo, reg):
    fontes = [f for f in (reg.get("fontes") or []) if isinstance(f, dict)]
    if not fontes:
        rel.erro(arquivo, "sem fontes: todo registro precisa de fonte e link rastreavel")
        return

    for i, fonte in enumerate(fontes):
        for campo in ("titulo", "url", "tipo", "consultado_em"):
            if not fonte.get(campo):
                rel.erro(arquivo, "fontes[%d] sem o campo '%s'" % (i, campo))
        if fonte.get("tipo") and fonte["tipo"] not in comum.TIPOS_FONTE_VALIDOS:
            rel.erro(arquivo, "fontes[%d].tipo invalido: '%s'" % (i, fonte["tipo"]))
        url = fonte.get("url") or ""
        if url and not url.startswith("https://"):
            rel.aviso(arquivo, "fontes[%d].url nao usa HTTPS: %s" % (i, url))
        _valida_data(rel, arquivo, "fontes[%d].consultado_em" % i, fonte.get("consultado_em"))

    prioritarias = {"oficial", "diario_oficial", "banca"}
    if not any(f.get("tipo") in prioritarias for f in fontes):
        rel.aviso(
            arquivo,
            "nenhuma fonte oficial, de diario oficial ou de banca — dados "
            "sustentados apenas por imprensa/portais; validar antes de divulgar",
        )


def valida_coerencia_vagas(rel, arquivo, reg):
    total = reg.get("vagas_imediatas_total")
    if total is None:
        return
    por_cargo = [
        c.get("vagas_imediatas")
        for c in reg.get("cargos", [])
        if isinstance(c, dict)
    ]
    if any(v is None for v in por_cargo):
        return
    soma = sum(por_cargo)
    if soma != total:
        rel.aviso(
            arquivo,
            "soma das vagas por cargo (%d) difere de vagas_imediatas_total (%d)"
            % (soma, total),
        )


def valida_duplicidade(rel, registros):
    """Detecta ids repetidos e possiveis duplicatas por orgao+edital e por link."""
    por_id = defaultdict(list)
    por_chave = defaultdict(list)
    por_edital_url = defaultdict(list)

    for arquivo, reg in registros:
        por_id[reg.get("id")].append(arquivo)

        chave = (
            (reg.get("orgao") or "").strip().lower(),
            (reg.get("edital_numero") or "").strip().lower(),
        )
        if chave[0] and chave[1] and chave[1] != comum.AUSENTE:
            por_chave[chave].append(arquivo)

        url = (reg.get("links") or {}).get("edital")
        if url and url != comum.AUSENTE and url.startswith("http"):
            por_edital_url[url].append(arquivo)

    for identificador, arquivos in por_id.items():
        if len(arquivos) > 1:
            rel.erro(arquivos[0], "id duplicado '%s' em: %s" % (identificador, ", ".join(arquivos)))

    for (orgao, edital), arquivos in por_chave.items():
        if len(arquivos) > 1:
            rel.erro(
                arquivos[0],
                "possivel duplicata: mesmo orgao ('%s') e edital ('%s') em: %s"
                % (orgao, edital, ", ".join(arquivos)),
            )

    for url, arquivos in por_edital_url.items():
        if len(arquivos) > 1:
            rel.aviso(
                arquivos[0],
                "mesmo links.edital em varios registros (%s): confirmar se sao "
                "certames distintos ou duplicata — %s" % (url, ", ".join(arquivos)),
            )


# ------------------------------------- catalogo de fontes e cadastro de municipios
#
# As duas funcoes abaixo recebem o dado JA CARREGADO, e a leitura de disco fica
# nos wrappers finos carregar_catalogo_fontes()/comum.carregar_municipios().
# Sem isso cada caso de teste precisaria escrever um arquivo temporario so para
# exercitar uma linha de tabela, o que por si so justificaria repensar a
# assinatura.


def carregar_catalogo_fontes():
    """Wrapper fino de leitura de fontes/fontes.json.

    Levanta ValueError com o CAMINHO no texto quando o JSON e invalido, no
    mesmo contrato de comum.carregar_registros() e comum.carregar_municipios():
    aqui o arquivo e obrigatorio, e nao opcional. coletar.carregar_catalogo_fontes()
    engole a falha devolvendo {} de proposito (coleta degradada vale mais que
    coleta nenhuma); o validador faz o oposto, porque e ele o lugar onde
    catalogo ilegivel tem de reprovar.
    """
    with open(CAMINHO_FONTES, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON invalido em %s: %s" % (CAMINHO_FONTES, exc)) from exc


def _valida_data_nao_futura(rel, alvo, rotulo, valor, obrigatorio=False):
    """_valida_data() mais a checagem de data futura. Devolve o date ou None.

    Data de verificacao no futuro e afirmacao impossivel de ter sido observada:
    ou o ano esta errado, ou a linha foi copiada de outro lugar sem conferir.
    """
    data = _valida_data(rel, alvo, rotulo, valor, obrigatorio=obrigatorio)
    if data and data > comum.hoje():
        rel.erro(alvo, "%s='%s' esta no futuro" % (rotulo, valor))
        return None
    return data


def _valida_pendencias(rel, alvo, pendencias, chaves_permitidas):
    """Confere a forma 'campo[:motivo]' de pendencias_verificacao.

    'campo' tem de ser uma chave da propria entrada (pendencia sobre campo que
    nao existe nao tem como ser resolvida) e 'motivo', quando presente, tem de
    estar em comum.MOTIVOS_PENDENCIA, cujos tres valores tem produtor
    declarado. Devolve o conjunto de campos com pendencia declarada, que e o
    que as checagens de canal e de url nula consultam.
    """
    campos = set()
    if pendencias is None:
        return campos
    if not isinstance(pendencias, list):
        rel.erro(alvo, "pendencias_verificacao deve ser uma lista")
        return campos
    for item in pendencias:
        if not isinstance(item, str) or not item.strip():
            rel.erro(alvo, "pendencias_verificacao com item vazio ou nao textual: %r" % (item,))
            continue
        campo, separador, motivo = item.partition(":")
        if campo not in chaves_permitidas:
            rel.erro(
                alvo,
                "pendencias_verificacao '%s': '%s' nao e campo da entrada (aceitos: %s)"
                % (item, campo, ", ".join(sorted(chaves_permitidas))),
            )
            continue
        if separador and motivo not in comum.MOTIVOS_PENDENCIA:
            rel.erro(
                alvo,
                "pendencias_verificacao '%s': motivo invalido (aceitos: %s)"
                % (item, ", ".join(sorted(comum.MOTIVOS_PENDENCIA))),
            )
            continue
        campos.add(campo)
    return campos


def valida_catalogo_fontes(rel, catalogo):
    """Confere a forma de fontes/fontes.json (ja carregado).

    Nada no pipeline olhava para este arquivo, e foi assim que 12 fontes
    ficaram sem o campo 'esfera' sem ninguem notar.
    """
    # Import tardio e deliberado: 'coletar' e o unico dono legitimo do mapa
    # FONTES (e so ele sabe quais ids tem coletor), mas importa-lo no topo
    # arrastaria TIMEOUT, NAVEGADOR e o sys.path.insert do coletor para dentro
    # do validador, que hoje depende apenas de comum. Duplicar a lista em
    # comum.FONTES_COLETAVEIS seria a alternativa, e criaria duas fontes da
    # verdade que divergem no dia em que alguem acrescentar uma fonte.
    import coletar

    rotulo = os.path.relpath(CAMINHO_FONTES, comum.RAIZ)
    _valida_data_nao_futura(
        rel, rotulo, "ultima_atualizacao", catalogo.get("ultima_atualizacao"), obrigatorio=True
    )

    fontes = catalogo.get("fontes")
    if not isinstance(fontes, list) or not fontes:
        rel.erro(rotulo, "campo 'fontes' ausente ou nao e uma lista com itens")
        return

    vistos = set()
    for i, fonte in enumerate(fontes):
        if not isinstance(fonte, dict):
            rel.erro(rotulo, "fontes[%d] deve ser um objeto" % i)
            continue

        identificador = fonte.get("id")
        alvo = "%s[%s]" % (rotulo, identificador or "fontes[%d]" % i)

        desconhecidas = set(fonte) - CHAVES_FONTE
        if desconhecidas:
            rel.erro(alvo, "chave desconhecida: %s" % ", ".join(sorted(desconhecidas)))

        if not isinstance(identificador, str) or not RE_ID_FONTE.match(identificador):
            rel.erro(
                alvo,
                "id ausente ou fora do padrao ^[a-z0-9][a-z0-9-]*$: %r" % (identificador,),
            )
        elif identificador in vistos:
            rel.erro(alvo, "id duplicado no catalogo: '%s'" % identificador)
        else:
            vistos.add(identificador)

        for campo in CAMPOS_FONTE_OBRIGATORIOS:
            if fonte.get(campo) is None or fonte.get(campo) == "":
                rel.erro(alvo, "campo obrigatorio ausente ou vazio: '%s'" % campo)

        tipo = fonte.get("tipo")
        esfera = fonte.get("esfera")
        if tipo is not None and tipo not in comum.TIPOS_FONTE_VALIDOS:
            rel.erro(alvo, "tipo invalido: %r" % (tipo,))
        if esfera is not None and esfera not in comum.ESFERAS_FONTE_VALIDAS:
            rel.erro(alvo, "esfera invalida: %r" % (esfera,))
        elif tipo in comum.TIPOS_FONTE_VALIDOS and esfera is not None:
            # Os dois lados da mesma regra: fonte que E orgao publico tem de
            # declarar esfera de governo real, e fonte que nao e (banca,
            # portal, imprensa) tem de declarar 'nao_se_aplica'. A segunda
            # metade e o bug inverso do que motivou a checagem.
            if tipo in comum.TIPOS_FONTE_COM_ESFERA and esfera == "nao_se_aplica":
                rel.erro(
                    alvo,
                    "tipo '%s' e orgao publico e nao pode ter esfera 'nao_se_aplica'" % tipo,
                )
            elif tipo not in comum.TIPOS_FONTE_COM_ESFERA and esfera != "nao_se_aplica":
                rel.erro(
                    alvo,
                    "tipo '%s' nao pertence a esfera de governo: esfera deveria ser "
                    "'nao_se_aplica', nao '%s'" % (tipo, esfera),
                )

        prioridade = fonte.get("prioridade")
        if prioridade is not None and (
            not isinstance(prioridade, int)
            or isinstance(prioridade, bool)
            or not 1 <= prioridade <= 4
        ):
            rel.erro(alvo, "prioridade deve ser inteiro de 1 a 4: %r" % (prioridade,))

        url = fonte.get("url")
        if isinstance(url, str) and url and not url.startswith("https://"):
            rel.aviso(alvo, "url nao usa HTTPS: %s" % url)

        if fonte.get("coletada_automaticamente") and identificador not in coletar.FONTES:
            rel.aviso(
                alvo,
                "coletada_automaticamente=true mas nao ha coletor para '%s' em "
                "coletar.FONTES" % identificador,
            )


def valida_cadastro_municipios(rel, cadastro, catalogo):
    """Confere fontes/municipios-es.json (ja carregado) contra o catalogo.

    Devolve o numero de municipios sem NENHUM canal confirmado, que e a medida
    de lacuna de cobertura publicada em --json.
    """
    rotulo = os.path.relpath(comum.CAMINHO_MUNICIPIOS, comum.RAIZ)
    ids_fontes = {
        f.get("id") for f in (catalogo.get("fontes") or []) if isinstance(f, dict)
    }

    municipios = cadastro.get("municipios")
    if not isinstance(municipios, list) or not municipios:
        rel.erro(rotulo, "campo 'municipios' ausente ou nao e uma lista com itens")
        return 0

    total_esperado = cadastro.get("total_esperado")
    if not isinstance(total_esperado, int) or isinstance(total_esperado, bool):
        rel.erro(rotulo, "total_esperado ausente ou nao e inteiro: %r" % (total_esperado,))
    else:
        if len(municipios) != total_esperado:
            rel.erro(
                rotulo,
                "len(municipios)=%d difere de total_esperado=%d"
                % (len(municipios), total_esperado),
            )
        if total_esperado < TOTAL_HISTORICO_MUNICIPIOS_ES:
            rel.erro(
                rotulo,
                "total_esperado=%d e menor que o piso historico: o ES nunca teve "
                "menos de %d municipios"
                % (total_esperado, TOTAL_HISTORICO_MUNICIPIOS_ES),
            )
        elif total_esperado != TOTAL_HISTORICO_MUNICIPIOS_ES:
            rel.aviso(
                rotulo,
                "total_esperado=%d difere dos %d municipios conhecidos: confira "
                "contra o IBGE e atualize o README"
                % (total_esperado, TOTAL_HISTORICO_MUNICIPIOS_ES),
            )

    # Primeira passada so para os nomes: a colisao de alias e propriedade
    # GLOBAL do arquivo, e um alias declarado na primeira entrada pode colidir
    # com o nome da ultima.
    dono_da_chave = {}
    slugs = set()
    for entrada in municipios:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("slug"):
            slugs.add(entrada["slug"])
        if entrada.get("nome"):
            dono_da_chave.setdefault(comum.chave_nome(entrada["nome"]), entrada.get("slug"))

    vistos_codigo = set()
    vistos_slug = set()
    sem_cobertura = 0

    for i, entrada in enumerate(municipios):
        if not isinstance(entrada, dict):
            rel.erro(rotulo, "municipios[%d] deve ser um objeto" % i)
            continue

        slug_mun = entrada.get("slug")
        alvo = "%s[%s]" % (rotulo, slug_mun or "municipios[%d]" % i)

        desconhecidas = set(entrada) - CHAVES_MUNICIPIO
        if desconhecidas:
            rel.erro(alvo, "chave desconhecida: %s" % ", ".join(sorted(desconhecidas)))

        codigo = entrada.get("codigo_ibge")
        if (
            not isinstance(codigo, int)
            or isinstance(codigo, bool)
            or not RE_CODIGO_IBGE.match(str(codigo))
        ):
            rel.erro(
                alvo,
                "codigo_ibge deve ser inteiro de 7 digitos comecando com 32: %r" % (codigo,),
            )
        elif codigo in vistos_codigo:
            rel.erro(alvo, "codigo_ibge duplicado: %d" % codigo)
        else:
            vistos_codigo.add(codigo)

        nome = entrada.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            rel.erro(alvo, "nome ausente ou vazio: %r" % (nome,))
        else:
            if nome != nome.strip() or "  " in nome:
                rel.erro(alvo, "nome com espaco nas bordas ou espaco duplo: %r" % nome)
            # Slug RECALCULADO, nao conferido a olho: e a classe de bug mais
            # provavel deste cadastro ('Guaçuí', 'Iúna', 'Marataízes',
            # 'São Roque do Canaã'), e comparar elimina a possibilidade.
            esperado = comum.slug(nome)
            if slug_mun != esperado:
                rel.erro(
                    alvo,
                    "slug %r difere de comum.slug(nome)=%r" % (slug_mun, esperado),
                )

        if not isinstance(slug_mun, str) or not slug_mun:
            rel.erro(alvo, "slug ausente ou vazio: %r" % (slug_mun,))
        elif slug_mun in vistos_slug:
            rel.erro(alvo, "slug duplicado: '%s'" % slug_mun)
        else:
            vistos_slug.add(slug_mun)

        microrregiao = entrada.get("microrregiao")
        if not isinstance(microrregiao, str) or not microrregiao.strip():
            rel.erro(alvo, "microrregiao ausente ou vazia: %r" % (microrregiao,))

        aliases = entrada.get("aliases")
        if not isinstance(aliases, list):
            rel.erro(alvo, "aliases deve ser uma lista")
            aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                rel.erro(alvo, "alias vazio ou nao textual: %r" % (alias,))
                continue
            chave = comum.chave_nome(alias)
            if isinstance(nome, str) and chave == comum.chave_nome(nome):
                rel.aviso(alvo, "alias '%s' e redundante com o proprio nome" % alias)
                continue
            if chave in dono_da_chave and dono_da_chave[chave] != slug_mun:
                rel.erro(
                    alvo,
                    "alias '%s' colide com nome ou alias de '%s'"
                    % (alias, dono_da_chave[chave]),
                )
                continue
            dono_da_chave[chave] = slug_mun

        canais = entrada.get("canais")
        if not isinstance(canais, list):
            rel.erro(alvo, "canais deve ser uma lista")
            canais = []

        precedencias = set()
        tem_diario = False
        tem_confirmado = False
        tem_pendente = False
        for j, canal in enumerate(canais):
            alvo_canal = "%s canais[%d]" % (alvo, j)
            if not isinstance(canal, dict):
                rel.erro(alvo_canal, "canal deve ser um objeto")
                continue

            desconhecidas = set(canal) - CHAVES_CANAL
            if desconhecidas:
                rel.erro(alvo_canal, "chave desconhecida: %s" % ", ".join(sorted(desconhecidas)))

            tipo = canal.get("tipo")
            if tipo not in comum.TIPOS_CANAL:
                rel.erro(alvo_canal, "tipo de canal invalido: %r" % (tipo,))
            if tipo in TIPOS_CANAL_DIARIO:
                tem_diario = True

            url = canal.get("url")
            if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
                rel.erro(alvo_canal, "url deve ser null ou comecar com 'https://': %r" % (url,))
            if url is None and tipo != "banca":
                rel.erro(
                    alvo_canal,
                    "url null so e aceita em canal de banca; canal '%s' precisa de "
                    "endereco" % (tipo,),
                )

            estado = canal.get("estado")
            if estado not in ESTADOS_CANAL:
                rel.erro(
                    alvo_canal,
                    "estado invalido: %r (aceitos: confirmado, pendente)" % (estado,),
                )
            if estado == "confirmado":
                tem_confirmado = True
                # Confirmado sem data e afirmacao nao verificada: a data e o
                # que torna a evidencia auditavel.
                _valida_data_nao_futura(
                    rel, alvo_canal, "verificado_em", canal.get("verificado_em"), obrigatorio=True
                )
            else:
                tem_pendente = True
                if canal.get("verificado_em") is not None:
                    _valida_data_nao_futura(
                        rel, alvo_canal, "verificado_em", canal.get("verificado_em")
                    )

            evidencia = canal.get("evidencia")
            if not isinstance(evidencia, str) or not evidencia.strip():
                rel.erro(
                    alvo_canal,
                    "evidencia ausente ou vazia: e o campo que impede canal inventado",
                )

            fonte_id = canal.get("fonte_id")
            if fonte_id is not None and fonte_id not in ids_fontes:
                rel.erro(alvo_canal, "fonte_id inexistente em fontes.json: %r" % (fonte_id,))

            precedencia = canal.get("precedencia")
            if (
                not isinstance(precedencia, int)
                or isinstance(precedencia, bool)
                or precedencia < 1
            ):
                rel.erro(alvo_canal, "precedencia deve ser inteiro >= 1: %r" % (precedencia,))
            elif precedencia in precedencias:
                rel.erro(alvo_canal, "precedencia %d repetida no municipio" % precedencia)
            else:
                precedencias.add(precedencia)

        if tem_diario:
            # Havendo canal de diario, ele e o de precedencia 1: e o canal onde
            # o ato tem fe publica, e a ordem de consulta da curadoria tem de
            # comecar por ele.
            principais = [
                c for c in canais if isinstance(c, dict) and c.get("precedencia") == 1
            ]
            if not principais:
                rel.erro(alvo, "ha canal de diario mas nenhum canal tem precedencia 1")
            elif principais[0].get("tipo") not in TIPOS_CANAL_DIARIO:
                rel.erro(
                    alvo,
                    "precedencia 1 e do canal '%s' havendo canal de diario: o diario "
                    "tem de vir primeiro" % principais[0].get("tipo"),
                )

        campos_pendentes = _valida_pendencias(
            rel, alvo, entrada.get("pendencias_verificacao"), CHAVES_MUNICIPIO
        )

        # Ou existe canal de diario, OU a ausencia esta declarada como
        # pendencia de 'canais'. Escrito no vocabulario real do dado: a versao
        # anterior desta regra exigia 'url_diario_oficial:*', motivo que o
        # vocabulario nunca produz, e reprovava municipio curado corretamente.
        if not tem_diario and "canais" not in campos_pendentes:
            rel.erro(
                alvo,
                "sem canal de diario (diario_oficial_proprio/diario_oficial_agregador) "
                "e sem pendencia 'canais:...' declarada",
            )
        if tem_pendente and "canais" not in campos_pendentes:
            rel.erro(
                alvo,
                "ha canal com estado 'pendente' e nenhuma pendencia 'canais:...' na "
                "entrada: as duas declaracoes tem de concordar",
            )
        if not tem_confirmado:
            sem_cobertura += 1
            rel.aviso(alvo, "nenhum canal confirmado — lacuna real de cobertura")

    _valida_orgaos_vinculados(rel, rotulo, cadastro, ids_fontes, vistos_slug)
    return sem_cobertura


def _valida_orgaos_vinculados(rel, rotulo, cadastro, ids_fontes, slugs):
    """Bloco orgaos_vinculados, com a MESMA severidade das entradas de municipios.

    A assimetria anterior (id, natureza e aridade conferidos; forma, nenhuma)
    era a mesma que deixou 12 fontes sem 'esfera' passarem.
    """
    orgaos = cadastro.get("orgaos_vinculados")
    if orgaos is None:
        return
    if not isinstance(orgaos, list):
        rel.erro(rotulo, "orgaos_vinculados deve ser uma lista")
        return

    vistos_id = set()
    for i, orgao in enumerate(orgaos):
        if not isinstance(orgao, dict):
            rel.erro(rotulo, "orgaos_vinculados[%d] deve ser um objeto" % i)
            continue

        identificador = orgao.get("id")
        alvo = "%s orgaos_vinculados[%s]" % (rotulo, identificador or i)

        ausentes = CHAVES_ORGAO - set(orgao)
        if ausentes:
            rel.erro(alvo, "chave obrigatoria ausente: %s" % ", ".join(sorted(ausentes)))
        desconhecidas = set(orgao) - CHAVES_ORGAO
        if desconhecidas:
            rel.erro(alvo, "chave desconhecida: %s" % ", ".join(sorted(desconhecidas)))

        if not isinstance(identificador, str) or not identificador:
            rel.erro(alvo, "id ausente ou vazio: %r" % (identificador,))
        elif identificador in vistos_id:
            rel.erro(alvo, "id duplicado: '%s'" % identificador)
        elif identificador in slugs:
            rel.erro(
                alvo,
                "id '%s' colide com slug de municipio: orgao e municipio nao podem "
                "compartilhar identificador" % identificador,
            )
        else:
            vistos_id.add(identificador)

        natureza = orgao.get("natureza")
        if natureza not in comum.NATUREZAS_ORGAO_VINCULADO:
            rel.erro(alvo, "natureza invalida: %r" % (natureza,))

        pendencias = orgao.get("pendencias_verificacao")
        campos_pendentes = _valida_pendencias(rel, alvo, pendencias, CHAVES_ORGAO)

        if orgao.get("url") is None and "url:nao_encontrado" not in (
            pendencias if isinstance(pendencias, list) else []
        ):
            rel.erro(
                alvo,
                "url null sem a pendencia 'url:nao_encontrado' declarada: endereco "
                "nao encontrado e pendencia, nao silencio",
            )

        nome_orgao = orgao.get("nome")
        aliases_orgao = orgao.get("aliases")
        if not isinstance(aliases_orgao, list):
            rel.erro(alvo, "aliases deve ser uma lista")
            aliases_orgao = []
        vistas_alias = set()
        for alias in aliases_orgao:
            if not isinstance(alias, str) or not alias.strip():
                rel.erro(alvo, "alias vazio ou nao textual: %r" % (alias,))
                continue
            chave_alias = comum.chave_nome(alias)
            if isinstance(nome_orgao, str) and chave_alias == comum.chave_nome(nome_orgao):
                rel.aviso(alvo, "alias '%s' e redundante com o proprio nome" % alias)
                continue
            # Colisao com MUNICIPIO e erro, e nao aviso: 'slugs' aqui e o
            # conjunto dos 78: um alias de orgao que casasse com nome de
            # municipio faria o ato do orgao ser creditado ao municipio errado,
            # e o indice resolve por chave sem desempate possivel.
            if chave_alias in {comum.chave_nome(s) for s in slugs}:
                rel.erro(alvo, "alias '%s' colide com slug de municipio" % alias)
                continue
            if chave_alias in vistas_alias:
                rel.erro(alvo, "alias '%s' repetido no orgao" % alias)
                continue
            vistas_alias.add(chave_alias)

        # Mesma razao do campo homonimo no canal ("e o campo que impede canal
        # inventado"), aplicada ao orgao. O que se afirma aqui e mais arriscado
        # que uma URL: 'municipios_slugs' de um consorcio CREDITA jurisdicao a
        # 13 ou 18 municipios de uma vez, e antes deste campo a unica forma de
        # auditar de onde veio aquela lista era a descricao do PR, que nao
        # acompanha o arquivo. Exigir evidencia no proprio dado fecha isso.
        evidencia = orgao.get("evidencia")
        if not isinstance(evidencia, str) or not evidencia.strip():
            rel.erro(
                alvo,
                "evidencia ausente ou vazia: e o campo que impede jurisdicao e "
                "endereco inventados",
            )

        fontes = orgao.get("fontes")
        if fontes is not None and not isinstance(fontes, list):
            rel.erro(alvo, "fontes deve ser uma lista")
            fontes = []
        for fonte_id in fontes or []:
            if fonte_id not in ids_fontes:
                rel.erro(
                    alvo,
                    "fontes aponta para id inexistente em fontes.json: %r" % (fonte_id,),
                )

        _valida_data_nao_futura(
            rel, alvo, "verificado_em", orgao.get("verificado_em"), obrigatorio=True
        )

        municipios_slugs = orgao.get("municipios_slugs")
        if not isinstance(municipios_slugs, list):
            rel.erro(alvo, "municipios_slugs deve ser uma lista")
            municipios_slugs = []
        for slug_mun in municipios_slugs:
            if slug_mun not in slugs:
                rel.erro(alvo, "municipios_slugs aponta para slug inexistente: %r" % (slug_mun,))

        if natureza in NATUREZAS_DE_UM_MUNICIPIO and len(municipios_slugs) != 1:
            rel.erro(
                alvo,
                "natureza '%s' exige exatamente 1 municipio em municipios_slugs, "
                "e ha %d" % (natureza, len(municipios_slugs)),
            )
        if natureza in NATUREZAS_INTERMUNICIPAIS:
            if orgao.get("esfera") != "intermunicipal":
                rel.erro(
                    alvo,
                    "natureza '%s' exige esfera 'intermunicipal', e esta '%s'"
                    % (natureza, orgao.get("esfera")),
                )
            if not municipios_slugs and "municipios_slugs" not in campos_pendentes:
                rel.erro(
                    alvo,
                    "natureza '%s' com municipios_slugs vazio exige pendencia "
                    "'municipios_slugs:...' declarada" % natureza,
                )


CAMINHO_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas", "descobertas.json")

CAMPOS_DESCOBERTA = [
    "chave",
    "fonte_id",
    "orgao",
    "titulo",
    "url",
    "primeira_deteccao",
    "ultima_deteccao",
    "no_repositorio",
]


CAMPOS_NAO_MAPEADO = (
    "nome_detectado",
    "ocorrencias",
    "paginas_distintas",
    "com_marca_uf",
    "exemplos",
    "primeira_deteccao",
    "ultima_deteccao",
)

LISTAS_DE_SLUG_DA_COBERTURA = (
    "slugs_com_sinal",
    "slugs_com_sinal_historico",
    "slugs_com_achado_acumulado",
)


def valida_arquivo_descobertas(rel, cadastro, indice=None):
    """Wrapper fino de leitura: le descobertas/descobertas.json e delega.

    O arquivo e OPCIONAL (a coleta pode nunca ter rodado) e JSON invalido aqui
    e erro de relatorio, nao erro fatal: diferente do cadastro e do catalogo,
    este arquivo e saida de maquina, e o que interessa e reprovar o commit
    automatico que o gerou, com a mensagem apontando o arquivo.
    """
    if not os.path.exists(CAMINHO_DESCOBERTAS):
        return {"achados": 0, "atos_diario": 0, "descartados_por_retencao": 0}

    rotulo = os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ)
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except ValueError as exc:
        rel.erro(rotulo, "JSON invalido: %s" % exc)
        return {"achados": 0, "atos_diario": 0, "descartados_por_retencao": 0}

    return valida_descobertas(rel, dados, cadastro, indice)


def valida_descobertas(rel, dados, cadastro, indice=None):
    """Confere a saida JA CARREGADA de ferramentas/coletar.py.

    A coleta grava sem revisao humana, entao o pipeline precisa reprovar se ela
    produzir lixo: chave repetida, campo faltando, data invalida, tipo de fonte
    fora do vocabulario ou referencia a um registro de dados/ inexistente.

    Recebe o dict e o cadastro ja carregados pelo mesmo motivo das duas funcoes
    de arquivo acima: a tolerancia de legado depende de 'ibge_consultado_em' e
    os casos de teste precisam exercita-la sem escrever arquivo temporario.

    Devolve as contagens publicadas em --json: achados, atos de diario e
    descartados pela retencao.
    """
    rotulo = os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ)
    contagens = {"achados": 0, "atos_diario": 0, "descartados_por_retencao": 0}

    if not isinstance(dados, dict):
        rel.erro(rotulo, "raiz deve ser um objeto")
        return contagens

    descartados = dados.get("descartados_por_retencao")
    if isinstance(descartados, int) and not isinstance(descartados, bool):
        contagens["descartados_por_retencao"] = descartados

    _valida_data(rel, rotulo, "gerado_em", dados.get("gerado_em"), obrigatorio=True)

    achados = dados.get("achados")
    if not isinstance(achados, list):
        rel.erro(rotulo, "campo 'achados' ausente ou nao e lista")
        return contagens
    contagens["achados"] = len(achados)

    indice = indice or comum.indice_municipios()
    cadastro = cadastro or {}
    # Fronteira da tolerancia de legado: a data em que o vocabulario de
    # categoria/municipio_escopo passou a existir. Vem do cadastro, nunca de um
    # literal, porque e o cadastro que define quando a migracao foi possivel.
    fronteira_legado = comum.data_ou_none(cadastro.get("ibge_consultado_em"))
    total_esperado = cadastro.get("total_esperado")

    ids_validos = {reg.get("id") for _, reg in comum.carregar_registros()}
    vistas = set()

    for achado in achados:
        if not isinstance(achado, dict):
            rel.erro(rotulo, "achado que nao e objeto: %r" % (achado,))
            continue

        chave = achado.get("chave")
        alvo = "%s[%s]" % (rotulo, chave or "sem-chave")

        for campo in CAMPOS_DESCOBERTA:
            if campo not in achado:
                rel.erro(alvo, "campo obrigatorio ausente: '%s'" % campo)

        if chave:
            if chave in vistas:
                rel.erro(alvo, "chave repetida entre achados")
            vistas.add(chave)

        for rotulo_data in ("primeira_deteccao", "ultima_deteccao"):
            _valida_data(rel, alvo, rotulo_data, achado.get(rotulo_data))
        inscricoes = achado.get("inscricoes") or {}
        _valida_data(rel, alvo, "inscricoes.inicio", inscricoes.get("inicio"))
        _valida_data(rel, alvo, "inscricoes.fim", inscricoes.get("fim"))

        tipo_fonte = achado.get("fonte_tipo")
        if tipo_fonte and tipo_fonte != comum.AUSENTE:
            if tipo_fonte not in comum.TIPOS_FONTE_VALIDOS:
                rel.erro(alvo, "fonte_tipo invalido: %r" % tipo_fonte)

        estimado = achado.get("status_estimado")
        if estimado and estimado not in comum.STATUS_VALIDOS:
            rel.erro(alvo, "status_estimado fora do vocabulario: %r" % estimado)

        url = achado.get("url") or ""
        if url and not url.startswith(("http://", "https://")):
            rel.erro(alvo, "url deve ser absoluta: %r" % url)

        registro = achado.get("registro_repositorio")
        if achado.get("no_repositorio"):
            if not registro:
                rel.erro(alvo, "no_repositorio=true sem registro_repositorio")
            elif registro not in ids_validos:
                rel.erro(
                    alvo,
                    "registro_repositorio aponta para id inexistente: %r" % registro,
                )
        elif registro:
            rel.erro(alvo, "registro_repositorio preenchido com no_repositorio=false")

        # Tolerancia de legado, por achado: o arquivo versionado pode conter
        # achados gravados ANTES de o cadastro existir, e o job 'validar' roda
        # em todo PR e push SEM passar por coletar.py — logo o backfill do
        # coletor nao os alcanca. Sem esta tolerancia, o PR que acrescenta
        # estas checagens seria reprovado pelas proprias checagens que
        # acrescenta. A comparacao e '<=', e o '=' e MEDIDO: 2 dos 37 achados
        # versionados tem primeira_deteccao exatamente igual a fronteira,
        # porque o cadastro e commitado no mesmo dia em que a coleta anterior
        # rodou. Com '<', esses dois viram erro — o oposto do que a regra
        # existe para dar, e sem recuperacao automatica no CI.
        primeira = comum.data_ou_none(achado.get("primeira_deteccao"))
        legado = bool(fronteira_legado and primeira and primeira <= fronteira_legado)

        categoria = achado.get("categoria")
        escopo = achado.get("municipio_escopo")
        for campo, valor, vocabulario in (
            ("categoria", categoria, comum.CATEGORIAS_ACHADO),
            ("municipio_escopo", escopo, comum.ESCOPOS_MUNICIPIO),
        ):
            if valor is None:
                if legado:
                    rel.aviso(
                        alvo,
                        "sem '%s': achado anterior ao cadastro; rode "
                        "'python3 ferramentas/coletar.py --migrar-descobertas'" % campo,
                    )
                else:
                    rel.erro(alvo, "campo obrigatorio ausente: '%s'" % campo)
            elif valor not in vocabulario:
                # Valor PRESENTE e fora do vocabulario e erro sempre, inclusive
                # em legado: tolerancia e para campo que nao existia, nao para
                # valor inventado.
                rel.erro(
                    alvo,
                    "%s fora do vocabulario: %r (aceitos: %s)"
                    % (campo, valor, ", ".join(sorted(vocabulario))),
                )

        slug_mun = achado.get("municipio_slug")
        if slug_mun is not None and slug_mun not in indice.por_slug:
            rel.erro(alvo, "municipio_slug inexistente no cadastro: %r" % (slug_mun,))

        confianca = achado.get("municipio_confianca")
        if confianca not in (None, "alta", "baixa"):
            rel.erro(alvo, "municipio_confianca invalida: %r" % (confianca,))

        # municipio_origem AUSENTE e ok de proposito: o campo nao entra na
        # exigencia de presenca, para nao criar um quinto item de tolerancia de
        # legado.
        if "municipio_origem" in achado:
            origem = achado.get("municipio_origem")
            if origem is not None and origem not in comum.ORIGENS_MUNICIPIO:
                rel.erro(alvo, "municipio_origem fora do vocabulario: %r" % (origem,))
            if origem is not None and slug_mun is None:
                rel.erro(
                    alvo,
                    "municipio_origem=%r com municipio_slug nulo: origem sem "
                    "municipio resolvido e contradicao" % (origem,),
                )

        codigo = achado.get("municipio_codigo_ibge")
        if codigo is not None:
            esperado = (indice.por_slug.get(slug_mun) or {}).get("codigo_ibge")
            if codigo != esperado:
                rel.erro(
                    alvo,
                    "municipio_codigo_ibge %r incoerente com municipio_slug %r "
                    "(esperado %r)" % (codigo, slug_mun, esperado),
                )

        orgao_vinculado = achado.get("orgao_vinculado_id")
        if orgao_vinculado is not None and orgao_vinculado not in indice.orgaos_por_id:
            rel.erro(
                alvo,
                "orgao_vinculado_id inexistente no cadastro: %r" % (orgao_vinculado,),
            )

        if categoria == "ato_diario":
            contagens["atos_diario"] += 1
            # Slug nulo em ato de diario so e aceito quando o escopo DIZ que
            # nao ha municipio unico: ato publicado em diario sempre tem
            # municipio, logo slug nulo sem escopo que o explique e extracao
            # falhada passando por dado.
            if slug_mun is None and escopo not in ("indeterminado", "intermunicipal"):
                rel.erro(
                    alvo,
                    "ato_diario com municipio_slug nulo exige municipio_escopo "
                    "'indeterminado' ou 'intermunicipal', e esta %r" % (escopo,),
                )
            if (achado.get("inscricoes") or {}).get("fim"):
                rel.erro(
                    alvo,
                    "ato_diario com inscricoes.fim preenchido: o coletor nao extrai "
                    "prazo de ato de diario (sinal de regex sobre PDF)",
                )
        elif categoria == "oportunidade" and confianca == "alta":
            rel.erro(
                alvo,
                "oportunidade com municipio_confianca 'alta': portal de terceiro nao "
                "e evidencia de ato publicado",
            )

    if len(achados) > LIMITE_ACHADOS_QUARENTENA:
        rel.aviso(
            rotulo,
            "quarentena grande (%d achados); confira a retencao de 'ato_diario'"
            % len(achados),
        )

    _valida_nao_mapeados(rel, rotulo, dados, indice)
    _valida_reconciliacao_ibge(rel, rotulo, dados)
    _valida_cobertura_municipios(rel, rotulo, dados, indice, total_esperado)

    for fonte in dados.get("fontes_consultadas") or []:
        if fonte.get("status") == "erro":
            rel.aviso(
                rotulo,
                "fonte %s falhou na ultima coleta: %s"
                % (fonte.get("id"), fonte.get("erro")),
            )
        elif fonte.get("suspeita_extracao_vazia"):
            rel.aviso(
                rotulo,
                "fonte %s respondeu sem erro mas nao devolveu nenhum item; "
                "possivel mudanca de layout — conferir ferramentas/coletar.py"
                % fonte.get("id"),
            )

    # As tres chaves novas de topo ausentes = arquivo anterior ao cadastro.
    # Aviso, e nao erro, e as checagens dos blocos valem SO quando a chave
    # existe: o descobertas.json versionado hoje nao as tem, e o PR nao pode
    # reprovar por um bloco que a coleta seguinte vai escrever.
    for chave in ("cobertura_municipios", "municipios_nao_mapeados", "reconciliacao_ibge"):
        if chave not in dados:
            rel.aviso(
                rotulo,
                "chave '%s' ausente: descobertas.json anterior ao cadastro; rode a "
                "coleta" % chave,
            )

    return contagens


def _valida_nao_mapeados(rel, rotulo, dados, indice):
    """Candidatos a municipio nao mapeado (§7.2 do design)."""
    candidatos = dados.get("municipios_nao_mapeados")
    if candidatos is None:
        return
    if not isinstance(candidatos, list):
        rel.erro(rotulo, "municipios_nao_mapeados deve ser uma lista")
        return

    for i, candidato in enumerate(candidatos):
        alvo = "%s municipios_nao_mapeados[%d]" % (rotulo, i)
        if not isinstance(candidato, dict):
            rel.erro(alvo, "candidato deve ser um objeto")
            continue

        for campo in CAMPOS_NAO_MAPEADO:
            if candidato.get(campo) is None:
                rel.erro(alvo, "campo obrigatorio ausente: '%s'" % campo)
        for campo in ("primeira_deteccao", "ultima_deteccao"):
            _valida_data(rel, alvo, campo, candidato.get(campo))

        ocorrencias = candidato.get("ocorrencias")
        paginas = candidato.get("paginas_distintas")
        if isinstance(ocorrencias, int) and isinstance(paginas, int):
            # Contadores trocados: nao ha como ver o mesmo nome em mais paginas
            # do que o numero de vezes em que ele apareceu.
            if paginas > ocorrencias:
                rel.erro(
                    alvo,
                    "paginas_distintas (%d) maior que ocorrencias (%d): contadores "
                    "trocados" % (paginas, ocorrencias),
                )

        exemplos = candidato.get("exemplos")
        if exemplos is not None and not isinstance(exemplos, list):
            rel.erro(alvo, "exemplos deve ser uma lista")
        elif isinstance(exemplos, list):
            if len(exemplos) > 3:
                rel.erro(alvo, "exemplos tem %d itens; o maximo e 3" % len(exemplos))
            # A FORMA de cada exemplo e checada, e nao so a da lista: o exemplo
            # e consumido por exemplo.get("url") no coletor e no corpo da issue,
            # entao um item que nao seja objeto e defeito do arquivo e tem de ser
            # nomeado aqui — o coletor o descarta para nao cair, mas quem corrige
            # o arquivo precisa saber qual item esta errado.
            for posicao, exemplo in enumerate(exemplos):
                if not isinstance(exemplo, dict):
                    rel.erro(
                        alvo,
                        "exemplos[%d] deve ser um objeto com url/data/trecho "
                        "(recebido: %s)" % (posicao, type(exemplo).__name__),
                    )

        provavel = candidato.get("provavel_alias_de")
        if provavel is not None and provavel not in indice.por_slug:
            rel.erro(alvo, "provavel_alias_de aponta para slug inexistente: %r" % (provavel,))

    if candidatos:
        rel.aviso(
            rotulo,
            "%d candidato(s) em municipios_nao_mapeados: curadoria pendente "
            "(conferir 'provavel_alias_de' e cadastrar alias quando for o caso)"
            % len(candidatos),
        )


def _valida_reconciliacao_ibge(rel, rotulo, dados):
    """Resultado da conferencia do cadastro contra a lista oficial do IBGE.

    Tudo aviso: IBGE fora do ar nao pode reprovar PR, e divergencia e sinal de
    municipio novo ou renomeado, que exige mao humana no cadastro — nao defeito
    do arquivo gerado.
    """
    bloco = dados.get("reconciliacao_ibge")
    if bloco is None:
        return
    if not isinstance(bloco, dict):
        rel.erro(rotulo, "reconciliacao_ibge deve ser um objeto")
        return

    if bloco.get("status") == "erro":
        rel.aviso(
            rotulo,
            "reconciliacao com o IBGE falhou na ultima coleta: %s" % bloco.get("erro"),
        )
    for campo in ("ausentes_no_cadastro", "excedentes_no_cadastro"):
        divergencias = bloco.get(campo)
        if divergencias:
            rel.aviso(
                rotulo,
                "reconciliacao_ibge.%s nao esta vazio (%d): conferir e atualizar "
                "fontes/municipios-es.json a mao" % (campo, len(divergencias)),
            )


def _valida_cobertura_municipios(rel, rotulo, dados, indice, total_esperado):
    """Bloco cobertura_municipios: contagens e conjuntos tem de concordar."""
    bloco = dados.get("cobertura_municipios")
    if bloco is None:
        return
    if not isinstance(bloco, dict):
        rel.erro(rotulo, "cobertura_municipios deve ser um objeto")
        return

    total = bloco.get("total_municipios")
    if total_esperado is not None and total != total_esperado:
        rel.erro(
            rotulo,
            "cobertura_municipios.total_municipios=%r difere de total_esperado=%r do "
            "cadastro" % (total, total_esperado),
        )

    janela = bloco.get("com_achado_na_janela")
    acumulado = bloco.get("com_achado_acumulado")
    if isinstance(janela, int) and isinstance(total, int) and janela > total:
        rel.erro(
            rotulo,
            "com_achado_na_janela (%d) maior que total_municipios (%d)" % (janela, total),
        )
    if isinstance(janela, int) and isinstance(acumulado, int) and janela > acumulado:
        # A janela e subconjunto do acumulado por construcao.
        rel.erro(
            rotulo,
            "com_achado_na_janela (%d) maior que com_achado_acumulado (%d)"
            % (janela, acumulado),
        )

    lista_acumulada = bloco.get("slugs_com_achado_acumulado")
    if isinstance(lista_acumulada, list) and isinstance(acumulado, int):
        if acumulado != len(lista_acumulada):
            rel.erro(
                rotulo,
                "com_achado_acumulado (%d) difere de len(slugs_com_achado_acumulado) "
                "(%d)" % (acumulado, len(lista_acumulada)),
            )

    sinal = set(bloco.get("slugs_com_sinal") or [])
    historico = set(bloco.get("slugs_com_sinal_historico") or [])
    primeira_vez = set(bloco.get("vistos_pela_primeira_vez") or [])
    if not primeira_vez <= sinal:
        rel.erro(
            rotulo,
            "vistos_pela_primeira_vez tem slug fora de slugs_com_sinal: %s"
            % ", ".join(sorted(primeira_vez - sinal)),
        )
    if not sinal <= historico:
        # O historico e monotonico e contem o retrato de hoje.
        rel.erro(
            rotulo,
            "slugs_com_sinal tem slug fora de slugs_com_sinal_historico: %s"
            % ", ".join(sorted(sinal - historico)),
        )

    for campo in LISTAS_DE_SLUG_DA_COBERTURA:
        lista = bloco.get(campo)
        if lista is None:
            continue
        if not isinstance(lista, list):
            rel.erro(rotulo, "cobertura_municipios.%s deve ser uma lista" % campo)
            continue
        for slug_mun in lista:
            if slug_mun not in indice.por_slug:
                rel.erro(
                    rotulo,
                    "cobertura_municipios.%s tem slug inexistente no cadastro: %r"
                    % (campo, slug_mun),
                )
        if lista != sorted(lista):
            rel.erro(rotulo, "cobertura_municipios.%s nao esta ordenada" % campo)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida os dados de concursos do ES.")
    parser.add_argument("--json", action="store_true", help="saida em JSON")
    args = parser.parse_args()

    rel = Relatorio()
    try:
        registros = comum.carregar_registros()
    except ValueError as exc:
        print("ERRO FATAL: %s" % exc, file=sys.stderr)
        return 1

    if not registros:
        print("ERRO FATAL: nenhum registro encontrado em dados/", file=sys.stderr)
        return 1

    # Cadastro e catalogo sao OBRIGATORIOS e a falha e FATAL, com o caminho na
    # mensagem: sem eles o validador nao tem como resolver municipio nem
    # conferir fonte_id, e seguir com as checagens restantes daria um "aprovado"
    # que nao mediu o que importa.
    try:
        cadastro = comum.carregar_municipios()
        indice = comum.indice_municipios()
    except (OSError, ValueError) as exc:
        print(
            "ERRO FATAL: nao foi possivel ler o cadastro de municipios (%s): %s"
            % (comum.CAMINHO_MUNICIPIOS, exc),
            file=sys.stderr,
        )
        return 1
    try:
        catalogo = carregar_catalogo_fontes()
    except (OSError, ValueError) as exc:
        print(
            "ERRO FATAL: nao foi possivel ler o catalogo de fontes (%s): %s"
            % (CAMINHO_FONTES, exc),
            file=sys.stderr,
        )
        return 1

    valida_catalogo_fontes(rel, catalogo)
    sem_cobertura = valida_cadastro_municipios(rel, cadastro, catalogo)

    for arquivo, reg in registros:
        valida_estrutura(rel, arquivo, reg)
        valida_vocabulario(rel, arquivo, reg)
        valida_escopo(rel, arquivo, reg, indice)
        valida_diretorio(rel, arquivo, reg)
        valida_datas(rel, arquivo, reg)
        valida_historico(rel, arquivo, reg)
        valida_fontes(rel, arquivo, reg)
        valida_coerencia_vagas(rel, arquivo, reg)

    valida_duplicidade(rel, registros)
    descobertas = valida_arquivo_descobertas(rel, cadastro, indice)
    total_descobertas = descobertas["achados"]

    if args.json:
        print(
            json.dumps(
                {
                    "registros": len(registros),
                    "descobertas": total_descobertas,
                    "fontes": len(catalogo.get("fontes") or []),
                    "municipios": len(cadastro.get("municipios") or []),
                    "orgaos_vinculados": len(cadastro.get("orgaos_vinculados") or []),
                    "municipios_sem_cobertura": sem_cobertura,
                    "atos_diario": descobertas["atos_diario"],
                    "descartados_por_retencao": descobertas["descartados_por_retencao"],
                    "erros": rel.erros,
                    "avisos": rel.avisos,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("Registros analisados: %d" % len(registros))
        print("Descobertas analisadas: %d" % total_descobertas)
        print(
            "Fontes catalogadas: %d | Municipios: %d (sem canal confirmado: %d) | "
            "Orgaos vinculados: %d"
            % (
                len(catalogo.get("fontes") or []),
                len(cadastro.get("municipios") or []),
                sem_cobertura,
                len(cadastro.get("orgaos_vinculados") or []),
            )
        )
        print("Erros: %d | Avisos: %d" % (len(rel.erros), len(rel.avisos)))
        if rel.erros:
            print("\n--- ERROS (reprovam a validacao) ---")
            for item in rel.erros:
                print("  [ERRO] %s: %s" % (item["arquivo"], item["mensagem"]))
        if rel.avisos:
            print("\n--- AVISOS (revisar, nao reprovam) ---")
            for item in rel.avisos:
                print("  [aviso] %s: %s" % (item["arquivo"], item["mensagem"]))
        if not rel.erros:
            print("\nValidacao aprovada.")

    return 1 if rel.erros else 0


if __name__ == "__main__":
    sys.exit(main())
