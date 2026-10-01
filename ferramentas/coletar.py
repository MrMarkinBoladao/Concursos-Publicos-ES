#!/usr/bin/env python3
"""Coleta automatica de oportunidades do ES a partir de fontes publicas.

Esta ferramenta NAO escreve em dados/. O ESQUEMA.md proibe inventar
informacao, e nenhuma fonte de listagem fornece os ~30 campos exigidos por um
registro curado (cargos, remuneracao, jornada, requisitos, banca, validade...).
Portanto a coleta alimenta uma area de quarentena:

    descobertas/descobertas.json

Cada achado guarda apenas o que a fonte realmente informou, com a fonte e a
data de deteccao. Achados que casam com um registro de dados/ ficam marcados
como ja conhecidos; os que nao casam sao candidatos a curadoria.

Fontes implementadas:
  selecao-es            API JSON oficial do portal Selecao ES (prioridade 1)
  concursosnobrasil-es  Tabela HTML de portal de concursos (prioridade 3)
  ioes-busca-dio        Buscador do Diario Oficial do Estado (prioridade 1)
  ioes-busca-dom        Buscador do Diario Oficial dos Municipios (AMUNES)

Tolerancia a falhas: a indisponibilidade de uma fonte nao derruba a execucao.
O erro e registrado no relatorio e a coleta segue com as demais fontes, para
que o monitoramento diario nao pare por causa de um site fora do ar.

Uso:
    python3 ferramentas/coletar.py
    python3 ferramentas/coletar.py --fonte selecao-es
    python3 ferramentas/coletar.py --dry-run
    python3 ferramentas/coletar.py --saida-github "$GITHUB_OUTPUT"
    python3 ferramentas/coletar.py --migrar-descobertas
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import gzip
import http.cookiejar
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

DIR_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas")
CAMINHO_DESCOBERTAS = os.path.join(DIR_DESCOBERTAS, "descobertas.json")
CAMINHO_FONTES = os.path.join(comum.RAIZ, "fontes", "fontes.json")

NAVEGADOR = "Mozilla/5.0 (X11; Linux x86_64) Python-urllib monitoramento-concursos-es"
TIMEOUT = 30

URL_SELECAO = "https://selecao.es.gov.br"
URL_CNB = "https://concursosnobrasil.com/concursos/es"
URL_IBGE_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/estados/32/municipios"
)

# Orgaos nacionais aparecem na pagina estadual do portal; sao descartados pelo
# padrao do link (itens do ES ficam sob /concursos/es/).
MARCA_ES_NO_LINK = "/concursos/es/"

# As duas bases do buscador do IOES. A BASE define o ESCOPO, e sao dois acervos
# distintos: o DIO e o Diario Oficial do Estado (que inclui o "Caderno dos
# Municipios Capixabas") e o DOM e o Diario Oficial dos Municipios (AMUNES).
# Consultar os dois e obrigatorio: medido na janela de 7 dias, "concurso
# publico" deu 16 no DIO e 63 no DOM.
BASES_IOES = {
    "dio": "https://ioes.dio.es.gov.br",
    "dom": "https://ioes.dio.es.gov.br/dom",
}

# Duas frases de assunto, e nao 'edital': medido, q=edital da 161 hits no DIO na
# mesma janela com queda enorme de precisao (licitacao, chamamento publico e
# credenciamento, que nao sao objeto deste repositorio). As duas frases mapeiam
# o vocabulario de comum.TIPOS_VALIDOS.
FRASES_IOES = ("concurso publico", "processo seletivo")

TIPO_POR_FRASE = {
    "concurso publico": "concurso_publico",
    "processo seletivo": "processo_seletivo_simplificado",
}

# Teto do texto de uma pagina antes de normalizar e segmentar. Uma pagina de
# diario pode trazer tabela de classificacao com dezenas de milhares de
# caracteres, e o custo e regex sobre todo o texto x ~90 padroes x ate 1000
# itens. 20.000 caracteres cobrem com folga o cabecalho e o corpo do ato, que e
# onde o municipio aparece; o corte nunca e silencioso (conteudo_truncado no
# achado e paginas_truncadas no diagnostico da fonte).
LIMITE_CONTEUDO = 20000

# Ato de diario nao tem prazo de inscricao, logo a poda por 'inscricoes.fim'
# nunca o alcanca e o laco de preservacao o reanexaria para sempre. 90 dias e o
# horizonte em que um ato ainda e util para curadoria (um edital publicado ha
# tres meses ja foi promovido para dados/ ou ja foi descartado); o teto de 365
# existe para que um erro de digitacao no argumento nao transforme a quarentena
# em arquivo historico.
RETENCAO_ATO_DIARIO_DIAS = 90


# ---------------------------------------------------------------- utilitarios


# Os tres utilitarios de texto passaram a viver em comum.py, porque o cadastro
# de municipios e lido tambem pelo validador e pelos geradores. Aqui ficam como
# delegacao, e nao como reimplementacao, para que nenhum call site deste arquivo
# mude e para que exista uma unica implementacao de normalizacao no projeto.
_sem_acento = comum._sem_acento
normalizar = comum.normalizar
slug = comum.slug


def normalizar_url(url: str) -> str:
    if not url or url == comum.AUSENTE:
        return ""
    return re.sub(r"/+$", "", url.strip().lower())


def data_iso(valor):
    """Converte data da fonte para 'YYYY-MM-DD'. Aceita o ISO do .NET.

    O backend em .NET emite 7 digitos de fracao de segundo
    ('2020-11-27T23:59:59.9999999'), que datetime.fromisoformat rejeita no
    Python 3.11. Truncamos para 6 digitos antes de converter.
    """
    if not valor:
        return None
    texto = str(valor).strip()
    texto = re.sub(r"(\.\d{6})\d+", r"\1", texto)
    texto = re.sub(r"Z$", "+00:00", texto)
    try:
        return dt.datetime.fromisoformat(texto).date().isoformat()
    except ValueError:
        achado = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
        if achado:
            return achado.group(0)
        return None


# Palavras que nao distinguem um orgao de outro. Sem elas, "Prefeitura de
# Anchieta" reduz a {anchieta}, que e o que realmente identifica o registro.
TOKENS_GENERICOS = {
    "a", "as", "o", "os", "e", "de", "da", "do", "das", "dos", "no", "na", "em",
    "es", "espirito", "santo", "estado", "estadual", "estaduais", "ambito",
    "diversos", "uf", "brasil",
    "prefeitura", "prefeituras", "municipal", "municipais", "municipio",
    "camara", "consorcio", "publico", "publica", "publicos", "publicas",
    "secretaria", "secretarias", "instituto", "institucional", "fundacao",
    "companhia", "conselho", "regional", "departamento", "agencia",
    "superintendencia", "gerencia", "comissao", "permanente", "processos",
    "processo", "seletivo", "seletivos", "simplificado", "concurso",
    "concursos", "edital", "editais", "n", "no", "num", "numero",
    "tribunal", "justica", "ministerio", "defensoria", "policia", "banco",
    "regiao", "servidores", "servidor", "geral", "sa", "ltda",
}


def tokens_identidade(*textos):
    """Tokens que realmente identificam um orgao, sem palavras genericas."""
    tokens = set()
    for texto in textos:
        if not texto or texto == comum.AUSENTE:
            continue
        limpo = re.sub(r"\(.*?\)", " ", str(texto))  # "Âmbito estadual (ES)"
        for token in re.split(r"[^a-z0-9]+", normalizar(limpo)):
            if len(token) >= 3 and token not in TOKENS_GENERICOS:
                tokens.add(token)
            elif token.isdigit() and len(token) == 2:
                tokens.add(token)  # "22" de CREF22
    return tokens


def _coberto(token: str, universo) -> bool:
    """Token presente no universo, aceitando prefixo ('cref' cobre 'cref22').

    O prefixo exige 4 caracteres no lado curto. Com 3 seria frouxo: 'crf'
    passaria a casar com qualquer token iniciado por 'crf'.
    """
    if token in universo:
        return True
    for outro in universo:
        if len(token) >= 4 and outro.startswith(token):
            return True
        if len(outro) >= 4 and token.startswith(outro):
            return True
    return False


def numeros_de_edital(texto: str):
    """Extrai chaves de edital tipo '47/2025' de um titulo livre.

    Usado para casar 'SEDU - EDITAL DE CADASTRAMENTO Nº 47/2025' com o campo
    edital_numero do repositorio ('Edital de Cadastramento nº 47/2025 - SEDU').
    """
    achados = set()
    for numero, ano in re.findall(r"(\d{1,4})\s*/\s*(\d{4})", texto or ""):
        achados.add("%d/%s" % (int(numero), ano))
    return achados


def _abridor():
    """Opener com cookies — o endpoint oficial exige sessao + antiforgery."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def _ler(abridor, url, dados=None, cabecalhos=None):
    cab = {"User-Agent": NAVEGADOR, "Accept-Language": "pt-BR,pt;q=0.9"}
    cab.update(cabecalhos or {})
    req = urllib.request.Request(url, data=dados, headers=cab)
    with abridor.open(req, timeout=TIMEOUT) as resp:
        bruto = resp.read()
    codificacao = resp.headers.get_content_charset() or "utf-8"
    return bruto.decode(codificacao, "replace")


def _ler_bytes(url, cabecalhos=None):
    """Leitura crua para os endpoints que nao exigem sessao (IOES, IBGE).

    'Accept-Encoding: identity' pede texto puro, mas o servicodados.ibge.gov.br
    devolve gzip MESMO ASSIM (medido: 200 com Content-Encoding: gzip) e o
    urllib nao descomprime sozinho — sem este tratamento, json.loads quebraria
    em 100% das execucoes e a reconciliacao com o IBGE nasceria morta.

    Nao reaproveita _abridor(): o buscador do IOES nao exige sessao (verificado),
    e arrastar para ca o CookieJar que o Selecao ES precisa seria acoplamento
    sem motivo.
    """
    cab = {"User-Agent": NAVEGADOR, "Accept-Encoding": "identity"}
    cab.update(cabecalhos or {})
    req = urllib.request.Request(url, headers=cab)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        bruto = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            bruto = gzip.decompress(bruto)
        codificacao = resp.headers.get_content_charset() or "utf-8"
    return bruto.decode(codificacao, "replace")


def _ler_com_retry(url, cabecalhos=None):
    """_ler_bytes() com UMA retentativa apos 2 segundos.

    Retenta somente o que e indisponibilidade: URLError, socket.timeout e
    HTTPError com code >= 500. HTTPError 4xx NAO e retentado, porque 4xx e
    contrato errado (rota mudou, parametro invalido) e insistir nele so gastaria
    o orcamento de tempo do job. Uma tentativa extra basta: o cron e diario e a
    janela de 7 dias ja tolera um dia perdido — retry agressivo so aumentaria o
    risco de o job estourar tempo.
    """
    try:
        return _ler_bytes(url, cabecalhos)
    except urllib.error.HTTPError as erro:
        if erro.code < 500:
            raise
    except (urllib.error.URLError, socket.timeout):
        pass
    time.sleep(2)
    return _ler_bytes(url, cabecalhos)


# --------------------------------------------------------- catalogo de fontes


def carregar_catalogo_fontes():
    """Le fontes/fontes.json para reaproveitar nome e tipo ja catalogados."""
    try:
        with open(CAMINHO_FONTES, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {f["id"]: f for f in dados.get("fontes", []) if f.get("id")}


# ------------------------------------------------------- fonte: selecao.es.gov


def coletar_selecao_es():
    """Processos seletivos estaduais via API JSON oficial do Selecao ES.

    A pagina e uma SPA Vue: a listagem vem de POST /processos-seletivos/busca,
    protegido por token antiforgery lido do HTML e por cookie de sessao.
    """
    abridor = _abridor()
    pagina = _ler(abridor, URL_SELECAO + "/processos-seletivos")

    achado = re.search(
        r'id="RequestVerificationToken"[^>]*value="([^"]+)"', pagina
    ) or re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', pagina)
    if not achado:
        raise RuntimeError("token antiforgery nao encontrado no HTML do Selecao ES")

    corpo = json.dumps({"currentPage": 1, "resultsPerPage": 500}).encode("utf-8")
    bruto = _ler(
        abridor,
        URL_SELECAO + "/processos-seletivos/busca",
        dados=corpo,
        cabecalhos={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-ANTI-FORGERY-TOKEN": achado.group(1),
        },
    )
    envelope = json.loads(bruto)
    if not envelope.get("isSuccess", True):
        raise RuntimeError("Selecao ES respondeu erro: %s" % envelope.get("message"))

    registros = (envelope.get("value") or {}).get("dados") or []
    achados = []
    for item in registros:
        identificador = item.get("identificadorExterno")
        if not identificador:
            continue
        titulo = (item.get("nome") or "").strip()
        inicio = data_iso(item.get("dataInicioInscricao"))
        fim = data_iso(item.get("dataFimInscricao"))
        achados.append(
            {
                "chave": "selecao-es:%s" % identificador,
                "fonte_id": "selecao-es",
                "orgao": (item.get("nomeOrgao") or comum.AUSENTE).strip(),
                "orgao_sigla": (item.get("siglaOrgao") or comum.AUSENTE).strip(),
                "titulo": titulo or comum.AUSENTE,
                "esfera": "estadual",
                "tipo": "processo_seletivo_simplificado",
                "inscricoes": {"inicio": inicio, "fim": fim},
                "vagas_informadas": None,
                "url": "%s/processo-seletivo/%s/%s"
                % (URL_SELECAO, identificador, item.get("slug") or ""),
            }
        )
    return achados


# -------------------------------------------------- fonte: concursosnobrasil


class _LeitorTabela(HTMLParser):
    """Extrai linhas de tabela: textos das celulas e o primeiro href da linha.

    Escrito sobre html.parser porque o projeto e stdlib-only (ver comum.py).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.linhas = []
        self._linha = None
        self._celula = None
        self._href = None
        self._em_celula = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._linha = {"celulas": [], "href": None}
        elif tag in ("td", "th") and self._linha is not None:
            self._em_celula = True
            self._celula = []
        elif tag == "a" and self._linha is not None and self._linha["href"] is None:
            for nome, valor in attrs:
                if nome == "href" and valor:
                    self._linha["href"] = valor
                    break

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._linha is not None and self._em_celula:
            texto = re.sub(r"\s+", " ", "".join(self._celula or [])).strip()
            self._linha["celulas"].append(texto)
            self._em_celula = False
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            if self._linha["celulas"]:
                self.linhas.append(self._linha)
            self._linha = None

    def handle_data(self, dados):
        if self._em_celula and self._celula is not None:
            self._celula.append(dados)


def coletar_concursosnobrasil_es():
    """Concursos e seletivos do ES listados em portal de terceiros.

    Serve como sinal de descoberta: o portal noticia certames municipais que
    nao passam pelo Selecao ES. Confiabilidade baixa (prioridade 3), por isso
    o achado nunca entra em dados/ automaticamente.
    """
    html = _ler(_abridor(), URL_CNB)
    leitor = _LeitorTabela()
    leitor.feed(html)

    achados = []
    for linha in leitor.linhas:
        href = linha.get("href") or ""
        if MARCA_ES_NO_LINK not in href:
            continue  # orgao nacional listado na pagina estadual
        celulas = linha["celulas"]
        if not celulas:
            continue
        orgao = celulas[0]
        if not orgao or normalizar(orgao) in ("orgao", "órgão"):
            continue

        # O portal cola o rotulo de situacao no nome: 'CGUprevisto'.
        situacao = None
        for rotulo in ("previsto", "autorizado", "encerrado"):
            if normalizar(orgao).endswith(rotulo):
                orgao = orgao[: -len(rotulo)].strip()
                situacao = rotulo
                break

        vagas_texto = celulas[1] if len(celulas) > 1 else ""
        digitos = re.sub(r"[^\d]", "", vagas_texto or "")
        vagas = int(digitos) if digitos else None

        ano = None
        achado_ano = re.search(r"/(\d{4})/", href)
        if achado_ano:
            ano = achado_ano.group(1)

        achados.append(
            {
                "chave": "concursosnobrasil-es:%s" % slug(href.rsplit("/", 2)[-2] if href.endswith("/") else href.rsplit("/", 1)[-1])[:120],
                "fonte_id": "concursosnobrasil-es",
                "orgao": orgao,
                "orgao_sigla": comum.AUSENTE,
                "titulo": orgao if not situacao else "%s (%s)" % (orgao, situacao),
                "esfera": None,
                "tipo": None,
                "inscricoes": {"inicio": None, "fim": None},
                "vagas_informadas": vagas,
                "url": href,
                "ano_publicacao": ano,
                "situacao_portal": situacao,
            }
        )
    return achados


# ------------------------------------------- fonte: buscador do IOES (diarios)
#
# A estrategia e "poucas consultas por assunto + casamento local", e nao uma
# consulta por municipio: em vez de perguntar "ha concurso em Sooretama?" 78
# vezes, pergunta-se "quais atos de concurso sairam esta semana?" e os
# municipios sao descobertos A PARTIR da resposta. E isso que torna possivel
# detectar municipio nao mapeado — um scraper por prefeitura so veria o que ja
# esta cadastrado.
#
# Ordem do pipeline de texto, fixada aqui porque tres regras a consomem
# (casamento, confianca e deteccao de mencao). Sao SEIS estagios, quatro por
# pagina e dois por bloco, e esta e a unica ordem valida:
#
#   --- por PAGINA ---
#   1. truncar _source.conteudo em LIMITE_CONTEUDO -> conteudo_truncado
#   2. t = comum.normalizar(conteudo)
#   3. t = _limpar_boilerplate(t)          # pagina inteira, UMA vez
#   4. PADROES_MENCAO + classificar_mencao sobre t
#   --- por BLOCO ---
#   5. blocos = _blocos_de_ato(t)          # 'protocolo \d+' sobrevive a (3)
#   6. por bloco: passada de orgaos -> passada de municipios -> pareamento
#
# Limpar antes de segmentar e seguro por uma razao verificavel: 'protocolo \d+'
# NAO esta em PADROES_BOILERPLATE — ele saiu daquela lista exatamente para
# poder ser delimitador. Limpar por bloco, alem de divergir dos numeros
# medidos, quebraria assinaturas que atravessam a fronteira 'protocolo \d+'.

MES = (
    r"(?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro"
    r"|outubro|novembro|dezembro)"
)

# Cabecalho de caderno e linha de local-data de assinatura de ato ESTADUAL.
# Medida em 144 paginas, a assinatura aparece como "vitoria (es),
# quinta-feira, 1 de outubro de 2026.", "vitoria-es, 28/09/2026.",
# "vitoria/es, 24 de setembro 2026." (sem o segundo "de") e "vitoria, es,
# cep:". O dia da semana e OPCIONAL e o separador pode ser "(es)", "/es",
# "-es" ou ", es": exigir qualquer um deles foi o erro das duas versoes
# anteriores deste padrao, e e o que fazia Vitoria liderar a cobertura.
# 'protocolo \d+' NAO entra nesta lista: ele e o delimitador de bloco.
PADROES_BOILERPLATE = (
    r"diario oficial dos municipios capixabas\s*\d*",
    r"assinado digitalmente pelo dio.*?codigo de autenticacao:\s*\w+",
    r"dom/es - edicao n[o]?\s*[\d\.]+\s*\d*",
    r"vitoria\s*(?:\(es\)|[/-]\s*es|,\s*es)?\s*,?\s*"
    r"(?:(?:segunda|terca|quarta|quinta|sexta|sabado|domingo)-feira,?\s*)?"
    r"(?:\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}|\d{1,2}\s+de\s+" + MES
    + r"\s+(?:de\s+)?\d{4})",
    r"vitoria,?\s*es,?\s*cep:?\s*[\d\.\-]+",
)

# O diario separa atos por "Protocolo <n>". Medido em 144 paginas: 94 tem o
# delimitador (de 1 a 7 blocos por pagina) e 50 nao tem — TODAS as 50 no escopo
# DOM. Nessas 50, nenhuma tem simultaneamente >1 municipio e >1 numero de
# edital, ou seja, tratar a pagina sem "protocolo" como UM bloco nao
# reintroduz o produto cartesiano. Por isso nao ha segundo delimitador:
# inventar um por cabecalho de orgao seria especulacao sobre um caso que a
# medicao mostra inexistente.
DELIMITADOR_BLOCO = re.compile(r"protocolo \d+")

# Ancorado em $: a marca tem de terminar IMEDIATAMENTE antes do nome casado.
# "prefeitura municipal de serra" conta; "prefeitura ... 300 caracteres ...
# serra" nao conta. Foi a troca de "raio de 80 caracteres" por adjacencia que
# tirou Vitoria da lideranca da cobertura (medido: 0 ocorrencias em alta).
MARCAS_ANTES = re.compile(
    r"(municipio de|municipio da|prefeitura municipal de|prefeitura de"
    r"|camara municipal de|gabinete do prefeito de|prefeito municipal de"
    r"|saae de|servico autonomo de agua e esgoto de)\s*$"
)
# Sufixo de UF colado ao nome: "serra/es", "serra - es". Vale como marca porque
# e adjacente; "estado do espirito santo" em algum lugar da pagina NAO vale.
MARCA_DEPOIS = re.compile(r"\s*[/-]\s*es\b")

# Marcas que, alem de dar confianca alta, dizem que o ato e da administracao
# municipal — e so nesse caso o campo 'orgao' pode afirmar "Prefeitura de X".
# "serra/es" da confianca alta sem dizer de que orgao o ato e, e ali 'orgao'
# fica AUSENTE em vez de afirmar o que nao se sabe.
MARCAS_DE_PREFEITURA = ("prefeitura", "municipio", "prefeito")

# Capturas sobre o texto JA normalizado (minusculas, sem acento). O diario
# escreve "MUNICIPIO DE X/ES" em caixa alta; normalizar antes evita precisar de
# re.I e de classes acentuadas, que foi o erro da primeira versao destes
# padroes (medido: a versao com classe maiuscula produzia 1 captura em 144
# paginas; esta produz 137). O primeiro padrao e o unico que exige "/ES", e por
# isso e ele que marca com_marca_uf.
PADROES_MENCAO = (
    re.compile(r"municipio de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]\s*es\b"),
    re.compile(r"prefeitura (?:municipal )?de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]"),
    re.compile(r"camara municipal de ([a-z][a-z0-9'\.\- ]{2,60}?)\s*[/,-]"),
)

# Teto do NOME CANDIDATO gravado em municipios_nao_mapeados. E o maior nome
# oficial de municipio do ES (medido: 4 tokens, em 12 nomes), porque o
# candidato e um suposto nome de municipio e passar disso e so a frase que a
# captura engoliu. Nao confundir com indice.max_tokens_nome, que e o teto da
# BUSCA por prefixo e vale 8 (medido: 'servico autonomo de agua e esgoto de
# aracruz', uma chave de orgao): com o teto da busca em 4, as chaves de orgao
# de 5 a 8 tokens nunca seriam alcancadas pela poda e 'instituto de previdencia
# dos servidores de cariacica' viraria candidato eternamente.
MAX_TOKENS_CANDIDATO = 4

# Nome de UF e de capital de outro estado. Diario do ES cita convenio com
# outros entes, e sem esta lista curta "sao paulo" viraria candidato a
# municipio capixaba nao mapeado. Lista explicita, e nao heuristica: ela e
# conferivel por leitura.
NOMES_DE_OUTROS_ENTES = {
    "acre", "alagoas", "amapa", "amazonas", "bahia", "ceara",
    "distrito federal", "espirito santo", "goias", "maranhao", "mato grosso",
    "mato grosso do sul", "minas gerais", "para", "paraiba", "parana",
    "pernambuco", "piaui", "rio de janeiro", "rio grande do norte",
    "rio grande do sul", "rondonia", "roraima", "santa catarina", "sao paulo",
    "sergipe", "tocantins",
    "rio branco", "maceio", "macapa", "manaus", "salvador", "fortaleza",
    "brasilia", "goiania", "sao luis", "cuiaba", "campo grande",
    "belo horizonte", "belem", "joao pessoa", "curitiba", "recife", "teresina",
    "natal", "porto alegre", "porto velho", "boa vista", "florianopolis",
    "aracaju", "palmas",
}

# Termos que fazem de um "N/AAAA" um numero de edital, e nao um numero de lei,
# de processo ou de decreto. A proximidade exigida e de 200 caracteres.
TERMOS_DE_EDITAL = ("edital", "concurso publico", "processo seletivo")
PADRAO_NUMERO = re.compile(r"(\d{1,4})\s*/\s*(\d{4})")
PADRAO_ID_ITEM = re.compile(r"^\d+_\d+$")
PADRAO_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Tokens de ligacao, usados so na sugestao conservadora de alias.
TOKENS_DE_LIGACAO = {"de", "do", "da", "das", "dos", "e"}


def _limpar_boilerplate(texto):
    """Remove cabecalho de caderno e linha de assinatura do texto normalizado.

    Roda na PAGINA inteira e UMA vez (estagio 3): os numeros medidos — as 8
    ocorrencias residuais de 'vitoria' e as 50 capturas de mencao em 64 paginas
    — so se reproduzem com a limpeza aplicada a pagina, e limpar por bloco
    quebraria assinaturas que atravessam a fronteira 'protocolo \\d+'.
    """
    for padrao in PADROES_BOILERPLATE:
        texto = re.sub(padrao, " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _blocos_de_ato(texto_normalizado):
    """Segmenta a pagina em blocos de ato por 'Protocolo <n>'.

    Sem esta segmentacao, emitir "um achado por par (municipio, numero)"
    produziria o produto cartesiano: medido, 30 das 144 paginas tem >1
    municipio E >1 numero, e o par cartesiano daria 1.419 achados, dos quais a
    esmagadora maioria nao existe.
    """
    partes = [
        p for p in DELIMITADOR_BLOCO.split(texto_normalizado) if len(p.strip()) >= 40
    ]
    return partes or [texto_normalizado]


def _mascarar(padrao, texto):
    """Substitui cada trecho casado por '\\x00' do mesmo comprimento.

    A mascara e "\\x00" e nao espaco por um motivo que custou uma rodada de
    revisao para aparecer: MARCAS_ANTES termina em \\s*$, entao mascarar com
    espaco faz a marca do municipio ja casado "vazar" para o municipio seguinte
    ("PREFEITURA DE VILA VELHA SERRA" creditava SERRA em confianca alta). O
    \\x00 preserva os offsets igual ao espaco, mas nao casa com \\s nem com \\b,
    de modo que adjacencia volta a significar adjacencia. Listas de lotacao e
    cabecalhos de caderno poem nomes de municipio em sequencia com frequencia:
    nao e caso teorico.
    """
    return padrao.sub(lambda m: "\x00" * len(m.group(0)), texto)


def _atribuicoes_do_bloco(bloco, indice):
    """Municipios e orgaos creditados por UM bloco de ato.

    Devolve lista de dicts com municipio_slug, municipio_confianca,
    municipio_origem, municipio_escopo, orgao_vinculado_id e orgao — no maximo
    UM por municipio e no maximo um por orgao. Lista vazia significa bloco sem
    municipio e sem orgao identificavel; quem decide o que fazer com isso e
    _achados_de_resposta(), porque e proibido herdar o municipio do bloco ou da
    pagina anterior (a ordem das paginas no indice nao garante contiguidade, e
    a heranca inventaria atribuicao).

    Municipio usa igualdade de cadeia com fronteira de palavra, e nada mais.
    _coberto() NAO pode ser usado aqui: ela aceita casamento por prefixo a
    partir de 4 caracteres (medido: _coberto("serra", {"serrana"}) e True), o
    que para identidade de orgao e deliberado e para municipio produziria falso
    positivo.
    """
    t = bloco
    por_slug = {}
    sem_municipio = []

    # Passada de ORGAOS antes da de municipios, e mascarando igual: assim
    # "servico autonomo de agua e esgoto de aracruz" e consumido como orgao e a
    # palavra "aracruz" dentro dele nao e contada de novo como mencao solta de
    # municipio.
    vistos = set()
    for padrao, orgao_id, _origem in indice.padroes_orgaos:
        if not padrao.search(t):
            continue
        t = _mascarar(padrao, t)
        if orgao_id in vistos:
            continue  # o mesmo orgao casou por nome e por sigla
        vistos.add(orgao_id)
        orgao = indice.orgaos_por_id.get(orgao_id) or {}
        slugs = orgao.get("municipios_slugs") or []
        atribuicao = {
            "orgao_vinculado_id": orgao_id,
            "orgao": orgao.get("nome") or comum.AUSENTE,
            "municipio_slug": None,
            "municipio_confianca": None,
            "municipio_origem": None,
            "municipio_escopo": "indeterminado",
        }
        if len(slugs) == 1:
            # Nome de orgao casado e marca de contexto propria e vale confianca
            # ALTA: o nome do orgao E a evidencia de pertencimento, mais forte
            # que qualquer heuristica de adjacencia.
            atribuicao.update(
                {
                    "municipio_slug": slugs[0],
                    "municipio_confianca": "alta",
                    "municipio_origem": "orgao_vinculado",
                    "municipio_escopo": "municipal",
                }
            )
            por_slug[slugs[0]] = atribuicao
        else:
            # 0 ou N>1 slugs: o ato fica rastreavel ao orgao (orgao_vinculado_id
            # e gravado sempre) sem creditar municipio nenhum.
            if len(slugs) > 1 or orgao.get("esfera") == "intermunicipal":
                atribuicao["municipio_escopo"] = "intermunicipal"
            sem_municipio.append(atribuicao)

    for padrao, slug_mun, origem in indice.padroes_ordenados:
        # finditer, e nao sub: a regra de confianca precisa dos OFFSETS de cada
        # ocorrencia para ler a janela de 45/6 caracteres, e re.sub nao os
        # expoe. A janela e lida no texto MASCARADO, isto e, no mesmo t que
        # esta passada vai modificando — ler no original faria MARCAS_ANTES
        # enxergar a marca de um municipio que ja foi consumido.
        for achado in list(padrao.finditer(t)):
            antes = t[max(0, achado.start() - 45):achado.start()]
            depois = t[achado.end():achado.end() + 6]
            marca = MARCAS_ANTES.search(antes)
            # MARCA_DEPOIS.match e nao search: match ancora no inicio da fatia
            # de 6 caracteres, que e o que materializa a adjacencia; com search,
            # "serra xx/es" passaria a contar.
            alta = bool(marca) or bool(MARCA_DEPOIS.match(depois))
            municipal = bool(
                marca and any(x in marca.group(1) for x in MARCAS_DE_PREFEITURA)
            )
            atual = por_slug.get(slug_mun)
            if atual is None:
                nome = (indice.por_slug.get(slug_mun) or {}).get("nome") or slug_mun
                por_slug[slug_mun] = {
                    "orgao_vinculado_id": None,
                    "orgao": ("Prefeitura de %s" % nome) if municipal
                    else comum.AUSENTE,
                    "municipio_slug": slug_mun,
                    "municipio_confianca": "alta" if alta else "baixa",
                    "municipio_origem": origem,
                    "municipio_escopo": "municipal",
                }
            else:
                # Mesmo municipio nas duas situacoes no mesmo bloco: ALTA
                # prevalece. O id do orgao e a origem ja gravados nao sao
                # rebaixados — a passada de orgaos e evidencia mais forte.
                if alta:
                    atual["municipio_confianca"] = "alta"
                if municipal and atual["orgao"] == comum.AUSENTE:
                    nome = (indice.por_slug.get(slug_mun) or {}).get("nome") or slug_mun
                    atual["orgao"] = "Prefeitura de %s" % nome
        # Mascara DEPOIS de avaliar TODAS as ocorrencias deste padrao, nunca
        # intercalado: avaliar e mascarar de uma em uma faria a 2a ocorrencia do
        # mesmo nome ler a 1a ja mascarada, e o resultado medido depende disso.
        t = _mascarar(padrao, t)

    return list(por_slug.values()) + sem_municipio


def _numeros_do_bloco(bloco, ano_corrente):
    """(numero principal, demais numeros citados) do bloco.

    No maximo 1 achado por (bloco, municipio): havendo varios numeros, vale o
    primeiro que apareca a <=200 caracteres de 'edital', 'concurso publico' ou
    'processo seletivo', e os demais vao para editais_citados em vez de
    multiplicar achados.

    Numero cujo ano esteja fora de [ano-4, ano+1] e descartado: medido na
    amostra, isso mata o '0001' de fragmento de CNPJ (55 ocorrencias), '17/2007'
    e numeros de lei de 1958 a 2021. A faixa e de 4 anos para tras porque ha ato
    de 2026 nomeando candidato de 'concurso publico 01/2022', caso real na
    amostra. O filtro e seguro porque descarta o NUMERO e nao o achado: bloco
    cujos numeros foram todos rejeitados cai na chave por pagina e o municipio
    continua contando para a cobertura.
    """
    posicoes = []
    for termo in TERMOS_DE_EDITAL:
        inicio = bloco.find(termo)
        while inicio != -1:
            posicoes.append(inicio)
            inicio = bloco.find(termo, inicio + 1)

    principal = None
    citados = []
    for achado in PADRAO_NUMERO.finditer(bloco):
        ano = int(achado.group(2))
        if not (ano_corrente - 4 <= ano <= ano_corrente + 1):
            continue
        numero = "%d/%d" % (int(achado.group(1)), ano)
        perto = any(abs(p - achado.start()) <= 200 for p in posicoes)
        if principal is None and perto:
            principal = numero
            continue
        if numero != principal and numero not in citados:
            citados.append(numero)
    return principal, citados


def classificar_mencao(captura, indice):
    """Resolve a captura por PREFIXO de tokens, do mais longo para o mais curto.

    A captura do diario engole texto depois do nome ("joao neiva por falta
    disciplinar e"): medido, 6 de 7 capturas nao resolvidas eram municipio REAL
    seguido de frase. Testar prefixos do mais longo para o mais curto resolve
    'venda nova do imigrante' antes de tentar 'venda nova', e so chama de
    candidato o que nao resolve em NENHUM tamanho.

    Os dois tetos tem papeis diferentes e por isso numeros diferentes: o da
    BUSCA e indice.max_tokens_nome (hoje 8, calculado do cadastro), e subi-lo so
    pode resolver MAIS capturas, nunca menos; o do CANDIDATO gravado e
    MAX_TOKENS_CANDIDATO = 4, e e ele que mantem a linha da issue como
    'que trata esta lei' em vez de um paragrafo inteiro.
    """
    toks = comum.chave_nome(captura).split()
    for n in range(min(len(toks), indice.max_tokens_nome), 0, -1):
        prefixo = " ".join(toks[:n])
        slug_mun = indice.por_chave_nome.get(prefixo)
        if slug_mun:
            return "mapeado", slug_mun
    return "candidato", " ".join(toks[:MAX_TOKENS_CANDIDATO])


def _candidato_aceitavel(nome):
    """Filtros que impedem a deteccao de virar gerador de ruido."""
    if len(nome) < 3 or nome.isdigit():
        return False
    toks = nome.split()
    if not toks or all(t in TOKENS_GENERICOS for t in toks):
        return False
    if nome in NOMES_DE_OUTROS_ENTES:
        return False
    return True


def _trecho_de_contexto(texto, inicio, fim):
    """Trecho curto em volta da captura, para a evidencia da issue."""
    bruto = texto[max(0, inicio - 40):fim + 40]
    return "..." + re.sub(r"\s+", " ", bruto).strip() + "..."


def _mencoes_da_pagina(texto, indice, url, data):
    """Capturas de nome de municipio na PAGINA (estagio 4).

    Por pagina e nao por bloco porque o objetivo aqui e descobrir QUE NOMES de
    municipio o diario cita, nao associa-los a um ato; rodar por bloco daria
    contagens e exemplos diferentes dos medidos, sem ganho.
    """
    saida = []
    for ordem, padrao in enumerate(PADROES_MENCAO):
        for achado in padrao.finditer(texto):
            situacao, valor = classificar_mencao(achado.group(1), indice)
            if situacao == "mapeado" or not _candidato_aceitavel(valor):
                continue
            saida.append(
                {
                    "nome_detectado": valor,
                    # Somente o primeiro padrao exige "/ES"; e ele que da a
                    # marca de UF, segundo termo da disjuncao do filtro.
                    "com_marca_uf": ordem == 0,
                    "url": url,
                    "data": data,
                    "trecho": _trecho_de_contexto(texto, achado.start(), achado.end()),
                }
            )
    return saida


def _exemplos_ordenados(brutos, limite=3):
    """Ate 'limite' exemplos, de paginas DISTINTAS, preferindo os mais recentes."""
    ordenados = sorted(brutos, key=lambda e: (e.get("data") or "", e.get("url") or ""),
                       reverse=True)
    saida = []
    paginas = set()
    for exemplo in ordenados:
        if exemplo.get("url") in paginas:
            continue
        paginas.add(exemplo.get("url"))
        saida.append(
            {
                "url": exemplo.get("url"),
                "data": exemplo.get("data"),
                "trecho": exemplo.get("trecho"),
            }
        )
        if len(saida) >= limite:
            break
    return saida


def _consolidar_candidatos(mencoes, fonte_id):
    """Agrupa as capturas desta execucao por nome podado e consolida por prefixo.

    Consolidacao por prefixo: 'joao neiva' (18 ocorrencias) e 'joao neiva por
    falta' (3) sao o MESMO candidato visto com excesso de captura, e sem isto
    virariam duas linhas da mesma issue. O mais CURTO absorve o mais longo.

    O filtro 'paginas_distintas >= 2 OR com_marca_uf' NAO e aplicado aqui: ele
    vale sobre os contadores ACUMULADOS entre execucoes, e e aplicado na fusao.
    """
    por_nome = {}
    for mencao in mencoes:
        item = por_nome.setdefault(
            mencao["nome_detectado"],
            {
                "nome_detectado": mencao["nome_detectado"],
                "ocorrencias": 0,
                "paginas": set(),
                "com_marca_uf": False,
                "fontes": [fonte_id],
                "exemplos_brutos": [],
            },
        )
        item["ocorrencias"] += 1
        item["paginas"].add(mencao["url"])
        item["com_marca_uf"] = item["com_marca_uf"] or mencao["com_marca_uf"]
        item["exemplos_brutos"].append(mencao)

    for longo in sorted(por_nome, key=lambda n: -len(n.split())):
        if longo not in por_nome:
            continue
        toks = longo.split()
        for curto in sorted(por_nome, key=lambda n: len(n.split())):
            if curto == longo or curto not in por_nome:
                continue
            outros = curto.split()
            if len(outros) < len(toks) and toks[:len(outros)] == outros:
                alvo, origem = por_nome[curto], por_nome.pop(longo)
                alvo["ocorrencias"] += origem["ocorrencias"]
                alvo["paginas"] |= origem["paginas"]
                alvo["com_marca_uf"] = alvo["com_marca_uf"] or origem["com_marca_uf"]
                alvo["exemplos_brutos"].extend(origem["exemplos_brutos"])
                break

    saida = []
    for item in por_nome.values():
        saida.append(
            {
                "nome_detectado": item["nome_detectado"],
                # Dois contadores com papeis diferentes: 'ocorrencias' dimensiona
                # a relevancia na issue; 'paginas_distintas' e o que o filtro usa.
                "ocorrencias": item["ocorrencias"],
                "paginas_distintas": len(item["paginas"]),
                "com_marca_uf": item["com_marca_uf"],
                "fontes": item["fontes"],
                "exemplos": _exemplos_ordenados(item["exemplos_brutos"]),
            }
        )
    saida.sort(key=lambda c: (-c["ocorrencias"], c["nome_detectado"]))
    return saida


def _total_de_hits(hits):
    """hits.total tolerando int (forma medida) e dict com 'value'.

    O Elasticsearch mudou a forma de total entre versoes; tolerar as duas custa
    uma linha e evita quebra silenciosa no dia em que o IOES atualizar.
    """
    total = hits.get("total")
    if isinstance(total, dict):
        total = total.get("value")
    return total if isinstance(total, int) and total >= 0 else None


def _titulo_do_item(item, conteudo):
    """Primeiro trecho de highlight, sem tags, colapsado e truncado em 200.

    highlight e o trecho RELEVANTE da pagina (o que casou a frase buscada), e
    por isso serve de titulo; _source.conteudo e o texto completo e serve ao
    casamento de municipio. Sem highlight, cai nos 200 primeiros caracteres do
    conteudo — nunca inventa titulo.
    """
    trechos = (item.get("highlight") or {}).get("conteudo")
    bruto = ""
    if isinstance(trechos, list):
        for trecho in trechos:
            if isinstance(trecho, str) and trecho.strip():
                bruto = re.sub(r"<[^>]+>", "", trecho)
                break
    if not bruto:
        bruto = conteudo
    limpo = re.sub(r"\s+", " ", bruto).strip()
    return limpo[:200] or comum.AUSENTE


def _edicao_do_item(item):
    """Numero da edicao extraido de 'suplemento'.

    'suplemento' e o ROTULO da edicao, e nao indicador de suplemento: medido
    "Edicao 3099", "Edicao 26821". Guardamos o numero e nada mais e inferido.
    """
    suplemento = item.get("suplemento")
    if not isinstance(suplemento, str):
        return None
    achado = re.search(r"(\d[\d\.]*)$", suplemento.strip())
    return achado.group(1) if achado else None


def _achados_de_resposta(envelope, escopo, frase, indice, diagnostico=None):
    """Achados de UM envelope ja desserializado do buscador. Funcao PURA.

    Contrato, e nao recomendacao de implementacao: esta funcao NAO propaga
    KeyError nem TypeError. O laco de FONTES captura (URLError, OSError,
    ValueError, RuntimeError), logo um envelope malformado que levantasse
    KeyError/TypeError derrubaria a coleta INTEIRA, contra a degradacao graciosa
    que o resto do arquivo promete. Por isso todo acesso a campo de terceiro usa
    .get(), e item invalido e ignorado com aviso.

    'diagnostico', quando e um dict, recebe 'mencoes' (capturas de municipio nao
    mapeado da pagina) e 'paginas_truncadas'. E o canal de metadados sem mudar o
    retorno, que e uma LISTA de achados.
    """
    diag = diagnostico if diagnostico is not None else {}
    diag.setdefault("mencoes", [])
    diag.setdefault("paginas_truncadas", 0)

    if not isinstance(envelope, dict):
        return []
    hits = envelope.get("hits")
    if not isinstance(hits, dict):
        return []
    itens = hits.get("hits")
    if not isinstance(itens, list):
        return []

    base = BASES_IOES.get(escopo, "")
    fonte_id = "ioes-busca-%s" % escopo
    ano_corrente = comum.hoje().year
    achados = []

    for item in itens:
        if not isinstance(item, dict):
            print("::warning::item do IOES ignorado: nao e objeto")
            continue
        identificador = item.get("_id")
        if not isinstance(identificador, str) or not PADRAO_ID_ITEM.match(identificador):
            print("::warning::item do IOES ignorado: _id inesperado %r" % (identificador,))
            continue
        origem = item.get("_source")
        if not isinstance(origem, dict):
            print("::warning::item %s ignorado: _source ausente" % identificador)
            continue

        diario_id = str(origem.get("diario_id") or "")
        pagina = str(origem.get("pagina") or "")
        if not diario_id.isdigit() or not pagina.isdigit():
            print(
                "::warning::item %s ignorado: diario_id/pagina ausentes"
                % identificador
            )
            continue

        data = origem.get("data")
        if not isinstance(data, str) or not PADRAO_DATA_ISO.match(data):
            data = None  # data invalida nao derruba o item

        conteudo = origem.get("conteudo")
        conteudo = conteudo if isinstance(conteudo, str) else ""
        truncado = len(conteudo) > LIMITE_CONTEUDO
        if truncado:
            conteudo = conteudo[:LIMITE_CONTEUDO]
            diag["paginas_truncadas"] += 1

        # URL de citacao: o PDF DA PAGINA (verificado respondendo 200,
        # application/pdf). Aponta para o ato, e nao para a edicao inteira.
        url = "%s/portal/edicoes/download/%s/%s" % (base, diario_id, pagina)
        titulo = _titulo_do_item(item, conteudo)

        texto = _limpar_boilerplate(comum.normalizar(conteudo))
        diag["mencoes"].extend(_mencoes_da_pagina(texto, indice, url, data))

        for bloco in _blocos_de_ato(texto):
            numero, citados = _numeros_do_bloco(bloco, ano_corrente)
            atribuicoes = _atribuicoes_do_bloco(bloco, indice)
            if not atribuicoes:
                # Pagina de continuacao: o ato prossegue sem repetir o nome do
                # municipio. Escopo indeterminado, e NUNCA herdar do bloco
                # anterior.
                atribuicoes = [
                    {
                        "orgao_vinculado_id": None,
                        "orgao": comum.AUSENTE,
                        "municipio_slug": None,
                        "municipio_confianca": None,
                        "municipio_origem": None,
                        "municipio_escopo": "indeterminado",
                    }
                ]
            for atribuicao in atribuicoes:
                slug_mun = atribuicao["municipio_slug"]
                entrada = indice.por_slug.get(slug_mun) or {}
                if numero:
                    chave = "ioes-%s:%s:edital-%s" % (
                        escopo,
                        slug_mun or "indeterminado",
                        numero.replace("/", "-"),
                    )
                else:
                    chave = "ioes-%s:%s:%s-%s" % (
                        escopo,
                        slug_mun or "indeterminado",
                        diario_id,
                        pagina,
                    )
                escopo_mun = atribuicao["municipio_escopo"]
                achados.append(
                    {
                        "chave": chave,
                        "fonte_id": fonte_id,
                        "orgao": atribuicao["orgao"],
                        "orgao_sigla": comum.AUSENTE,
                        "titulo": titulo,
                        "esfera": (
                            "municipal" if escopo_mun == "municipal"
                            else ("intermunicipal" if escopo_mun == "intermunicipal"
                                  else None)
                        ),
                        "tipo": TIPO_POR_FRASE.get(frase),
                        # A pagina do diario nao informa prazo de forma
                        # confiavel, e extrair data por regex de PDF seria
                        # inventar dado. Mesmo motivo para vagas_informadas.
                        "inscricoes": {"inicio": None, "fim": None},
                        "vagas_informadas": None,
                        "url": url,
                        "categoria": "ato_diario",
                        "data_publicacao_ato": data,
                        "edicao": _edicao_do_item(item),
                        "editais_citados": citados,
                        "conteudo_truncado": truncado,
                        # Nome OFICIAL do cadastro, com acento — nunca o trecho
                        # casado no texto, que esta normalizado e sem acento. E
                        # a mesma grafia que os registros de dados/ usam.
                        "municipio": entrada.get("nome") or comum.AUSENTE,
                        "municipio_codigo_ibge": entrada.get("codigo_ibge"),
                        "municipio_slug": slug_mun,
                        "municipio_confianca": atribuicao["municipio_confianca"],
                        "municipio_escopo": escopo_mun,
                        "municipio_origem": atribuicao["municipio_origem"],
                        "orgao_vinculado_id": atribuicao["orgao_vinculado_id"],
                        # Auxiliares internos ao coletor, removidos antes de
                        # devolver: servem so a ordenacao deterministica.
                        "_diario_id": diario_id,
                        "_pagina": pagina,
                    }
                )
    return achados


def _ordenar_e_colapsar(candidatos):
    """Ordena por chave explicita e colapsa por 'chave', mantendo o primeiro.

    Ordem: data mais RECENTE primeiro; dentro da data, menor diario_id e menor
    pagina. A API ordena por DIA, nao por item (medido: o campo 'sort' e o
    timestamp do dia, igual para todos os itens da data), entao sem este
    desempate qual pagina "ganha" a chave varia entre execucoes — e com ela
    titulo, url e edicao, gerando ruido diario em descobertas.json e risco no
    gerar_readme.py --check.

    O colapso acontece AQUI, e nao no 'vistos' de main(): dois blocos da mesma
    pagina que citem o mesmo municipio produzem, pela chave sem numero, a MESMA
    chave, e deixar o descarte para main() faria quem sobrevive depender da
    ordem de iteracao de um conjunto construido fora do coletor, isto e, de
    codigo que nao conhece esta ordenacao. main() segue com o 'vistos' dele,
    que protege contra colisao ENTRE fontes.

    Os auxiliares _diario_id/_pagina sao removidos aqui: o prefixo '_' marca
    "interno ao coletor", e grava-los ampliaria CAMPOS_DESCOBERTA sem razao.
    """
    ordenados = sorted(
        candidatos,
        key=lambda a: (a["data_publicacao_ato"] or "", -int(a["_diario_id"]),
                       -int(a["_pagina"])),
        reverse=True,
    )
    final = []
    vistos = set()
    for achado in ordenados:
        if achado["chave"] in vistos:
            continue
        vistos.add(achado["chave"])
        achado.pop("_diario_id", None)
        achado.pop("_pagina", None)
        final.append(achado)
    return final


def coletar_ioes(escopo="dom", diagnostico=None, janela_dias=7, max_paginas=20,
                 max_achados=1000, indice=None):
    """Devolve LISTA de achados, como as outras fontes.

    Quando 'diagnostico' e um dict, escreve nele 'truncado',
    'limite_achados_atingido', 'total_relatado', 'paginas_truncadas' e
    'nao_mapeados'. E o canal de retorno dos metadados sem mudar o contrato
    (lista) que as outras fontes ja cumprem — mudar o contrato quebraria a
    degradacao graciosa do laco de FONTES, que e o que faz uma fonte fora do ar
    nao derrubar a coleta.

    Uma fonte por escopo (registradas com functools.partial) em vez de uma
    fonte que varre os dois: assim 'suspeita_extracao_vazia' vale por escopo,
    '--fonte ioes-busca-dom' e possivel, cada fonte declara a esfera verdadeira
    e a degradacao graciosa por escopo sai de graca.
    """
    indice = indice or comum.indice_municipios()
    base = BASES_IOES[escopo]
    fonte_id = "ioes-busca-%s" % escopo
    diag = diagnostico if diagnostico is not None else {}
    diag["truncado"] = False
    diag["limite_achados_atingido"] = False
    diag["total_relatado"] = 0

    interno = {"mencoes": [], "paginas_truncadas": 0}
    candidatos = []
    # Falha de pagina e recuperavel (a paginacao daquele par para e os
    # resultados ja acumulados valem), mas falhar em TODAS as tentativas e a
    # fonte inteira indisponivel: nesse caso levantamos, para que o laco de
    # FONTES registre status 'erro' nesta fonte e siga com as outras. Devolver
    # [] faria uma fonte fora do ar aparecer como 'ok: 0 achados'.
    paginas_lidas = 0
    falhas = 0
    # di: sem df:, porque a janela corre para tras a partir de hoje. Os filtros
    # de data sao indispensaveis: sem janela, q=Sooretama devolve 14.415 hits
    # com documentos de 2019 e 2022.
    di = (comum.hoje() - dt.timedelta(days=janela_dias)).isoformat()

    for frase in FRASES_IOES:
        termo = urllib.parse.quote('"%s"' % frase)
        itens_lidos = 0
        total = None
        pagina = 0
        while pagina < max_paginas:
            url = "%s/busca/busca/buscar/query/%d/di:%s/?1=1&q=%s" % (
                base,
                pagina,  # a paginacao do buscador e 0-based, 10 por pagina
                di,
                termo,
            )
            try:
                envelope = json.loads(_ler_com_retry(url))
            except urllib.error.HTTPError as erro:
                print(
                    "::warning::%s: HTTP %s em %r pagina %d"
                    % (fonte_id, erro.code, frase, pagina)
                )
                falhas += 1
                break
            except (urllib.error.URLError, socket.timeout, OSError) as erro:
                print(
                    "::warning::%s: %s em %r pagina %d"
                    % (fonte_id, type(erro).__name__, frase, pagina)
                )
                falhas += 1
                break
            except ValueError:
                print(
                    "::warning::resposta inesperada do IOES (%s, %r, pagina %d)"
                    % (fonte_id, frase, pagina)
                )
                falhas += 1
                break

            paginas_lidas += 1
            hits = envelope.get("hits") if isinstance(envelope, dict) else None
            if not isinstance(hits, dict) or not isinstance(hits.get("hits"), list):
                print(
                    "::warning::resposta inesperada do IOES (%s, %r, pagina %d)"
                    % (fonte_id, frase, pagina)
                )
                break
            itens = hits["hits"]
            if not itens:
                break  # fim natural da paginacao
            if total is None:
                total = _total_de_hits(hits)
                diag["total_relatado"] += total or 0

            candidatos.extend(
                _achados_de_resposta(envelope, escopo, frase, indice, interno)
            )
            itens_lidos += len(itens)
            if len(candidatos) >= max_achados:
                diag["limite_achados_atingido"] = True
                print(
                    "::warning::%s: teto de %d achados atingido em %r"
                    % (fonte_id, max_achados, frase)
                )
                break
            if total is not None and itens_lidos >= total:
                break
            pagina += 1
            time.sleep(0.2)  # cortesia com o servidor do IOES
        else:
            # Saiu pelo teto de paginas com hits ainda por ler: truncamento
            # recorrente e lacuna de cobertura e precisa de olho humano.
            if total is not None and itens_lidos < total:
                diag["truncado"] = True
                print(
                    "::warning::%s: coleta truncada em %r (%d de %d hits lidos)"
                    % (fonte_id, frase, itens_lidos, total)
                )
        if diag["limite_achados_atingido"]:
            break

    if not paginas_lidas and falhas:
        raise RuntimeError(
            "buscador do IOES indisponivel no escopo %s: %d tentativa(s) sem "
            "resposta utilizavel" % (escopo, falhas)
        )

    final = _ordenar_e_colapsar(candidatos)
    diag["paginas_truncadas"] = interno["paginas_truncadas"]
    diag["nao_mapeados"] = _consolidar_candidatos(interno["mencoes"], fonte_id)
    return final


FONTES = {
    "selecao-es": coletar_selecao_es,
    "concursosnobrasil-es": coletar_concursosnobrasil_es,
    # functools.partial em vez de duas funcoes: o corpo e identico e o escopo e
    # o unico parametro que muda. Registrar as duas em FONTES faz o laco de
    # main() dar a degradacao graciosa DE GRACA e por escopo — se o DOM cair, o
    # DIO aparece como 'ok' em fontes_consultadas e o DOM como 'erro'.
    "ioes-busca-dio": functools.partial(coletar_ioes, escopo="dio"),
    "ioes-busca-dom": functools.partial(coletar_ioes, escopo="dom"),
}

# Conjunto explicito em vez de fonte_id.startswith("ioes-busca"): o modo de
# chamada e contrato da funcao, nao propriedade do nome dela. Com o prefixo,
# acrescentar um terceiro escopo (ou renomear um id) mudaria silenciosamente a
# forma como main() chama o coletor.
FONTES_COM_DIAGNOSTICO = {"ioes-busca-dio", "ioes-busca-dom"}


# ------------------------------------------------------------------ casamento


def indice_repositorio():
    """Resumo de dados/ usado para reconhecer achados ja curados."""
    por_url = {}
    registros = []
    for _, reg in comum.carregar_registros():
        rid = reg.get("id")

        urls = {normalizar_url(v) for v in (reg.get("links") or {}).values()}
        urls |= {normalizar_url(f.get("url")) for f in reg.get("fontes") or []}
        for url in urls:
            # URL so de dominio ('https://selecao.es.gov.br/') casaria com tudo.
            if url and url.count("/") > 2:
                por_url.setdefault(url, rid)

        achado_ano = re.search(r"(\d{4})$", rid or "")
        registros.append(
            {
                "id": rid,
                # Tokens do nome do orgao e da sigla. Separados do municipio de
                # proposito: 'Prefeitura de Vitoria' nao pode casar com o
                # CREF22 so porque o CREF22 tem lotacao em Vitoria.
                "nome_tokens": tokens_identidade(
                    reg.get("orgao"), reg.get("orgao_sigla")
                ),
                "local_tokens": tokens_identidade(reg.get("municipio")),
                "editais": numeros_de_edital(reg.get("edital_numero") or ""),
                "ano": int(achado_ano.group(1)) if achado_ano else None,
            }
        )
    return {"url": por_url, "registros": registros}


def casar(achado, indice):
    """Id do registro de dados/ correspondente ao achado, ou None.

    Tres regras, da mais forte para a mais fraca. Nao existe casamento por
    numero de edital isolado: '001/2026' se repete entre orgaos diferentes e
    produziria falso positivo.
    """
    url = normalizar_url(achado.get("url"))
    if url and url in indice["url"]:
        return indice["url"][url]

    tokens_achado = tokens_identidade(achado.get("orgao"), achado.get("orgao_sigla"))
    if not tokens_achado:
        return None
    editais_achado = numeros_de_edital(achado.get("titulo") or "")

    # Quando a fonte informa o numero do edital, ele e decisivo: exigimos que
    # bata. Sem isso, 'SEDU EDITAL 28/2026' seria considerado igual ao
    # 'ps-sedu-es-casf-47-2025' apenas por ser da mesma secretaria, e um edital
    # novo nunca apareceria como novidade.
    if editais_achado:
        for reg in indice["registros"]:
            if not reg["editais"] & editais_achado:
                continue
            universo = reg["nome_tokens"] | reg["local_tokens"]
            if universo and all(_coberto(t, universo) for t in tokens_achado):
                return reg["id"]
        return None

    ano_achado = achado.get("ano_publicacao")
    ano_achado = int(ano_achado) if str(ano_achado or "").isdigit() else None

    def _proximo(reg):
        return not (ano_achado and reg["ano"] and abs(reg["ano"] - ano_achado) > 1)

    # Fonte sem numero de edital (portal que so nomeia o orgao). Primeiro
    # tentamos pelo nome do orgao; o municipio entra apenas como reforco.
    for usar_local in (False, True):
        for reg in indice["registros"]:
            universo = reg["nome_tokens"] | (
                reg["local_tokens"] if usar_local else set()
            )
            if not universo or not _proximo(reg):
                continue
            if all(_coberto(t, universo) for t in tokens_achado):
                return reg["id"]
    return None


def casar_estrito(achado, indice):
    """Como casar(), mas SOMENTE por evidencia forte: url normalizada igual, ou
    numero de edital coincidente mais cobertura de tokens de orgao.

    Ato de diario casa com registro curado somente assim. O ramo final de
    casar() (por tokens de orgao, sem numero) casaria qualquer ato de Serra com
    qualquer certame de Serra, porque tokens_identidade('Prefeitura de Serra')
    devolve {'serra'} (medido — 'prefeitura' e 'de' estao em TOKENS_GENERICOS) e
    _coberto() ainda aceita prefixo. Um ato de nomeacao marcado como 'ja no
    repositorio' sairia da fila de curadoria sem ter sido conferido, que e o
    pior desfecho possivel para a quarentena.

    casar() e tokens_identidade() seguem SEM alteracao: o problema nao e o
    comportamento delas para o caso em que foram escritas, e aplica-las a um
    tipo de achado que nao existia. Para achado de oportunidade o ramo fraco
    continua valendo — ali o orgao e o titulo vem de um portal de concursos, e
    nao de texto corrido de diario.
    """
    url = normalizar_url(achado.get("url"))
    if url and url in indice["url"]:
        return indice["url"][url]

    tokens_achado = tokens_identidade(achado.get("orgao"), achado.get("orgao_sigla"))
    if not tokens_achado:
        return None
    editais_achado = numeros_de_edital(achado.get("titulo") or "")
    if not editais_achado:
        return None
    for reg in indice["registros"]:
        if not reg["editais"] & editais_achado:
            continue
        universo = reg["nome_tokens"] | reg["local_tokens"]
        if universo and all(_coberto(t, universo) for t in tokens_achado):
            return reg["id"]
    return None


def normalizar_achado(achado, indice):
    """Garante os campos de categoria/municipio em TODO achado, de qualquer fonte.

    Ponto unico de proposito: nenhuma fonte precisa conhecer o vocabulario novo,
    e o validador nunca ve achado sem os campos obrigatorios. Sem este ponto,
    cada coletor novo teria de lembrar de preencher os campos de categoria e de
    municipio (slug, codigo_ibge, confianca, escopo, origem), e esquecer um
    deles so apareceria como CI vermelho depois do merge. E a mesma funcao que
    --migrar-descobertas aplica, para que exista UMA lista de campos.

    Usa setdefault e nao atribuicao: o coletor de diario JA resolveu municipio
    com evidencia de texto, e essa resolucao e mais forte que a daqui.
    """
    achado.setdefault("categoria", "oportunidade")

    if achado["categoria"] == "oportunidade":
        # Portal de terceiro nao e evidencia de ato: o nome do municipio vem de
        # um campo de formulario, nao de um diario oficial. Por isso confianca
        # 'baixa' por construcao, e por isso achado de oportunidade NUNCA entra
        # na cobertura — a metrica mede atividade observada em ato.
        #
        # resolver_municipio_em_texto e nao resolver_municipio: nos achados
        # reais destas fontes o campo e 'ARIES', 'SEDU', 'Prefeitura de
        # Anchieta', 'Camara Municipal de ...'. A consulta EXATA por chave
        # devolveria None em praticamente todos e municipio_slug nasceria sempre
        # nulo. Os dois campos vao CONCATENADOS porque o nome do municipio pode
        # estar em qualquer um dos dois, e a passada longest-first lida com
        # texto livre.
        alvo = " ".join(
            x for x in (achado.get("municipio"), achado.get("orgao")) if x
        )
        slug_mun, origem = comum.resolver_municipio_em_texto(alvo, indice)
        achado.setdefault("municipio_slug", slug_mun)
        achado.setdefault(
            "municipio_codigo_ibge",
            (indice.por_slug[slug_mun]["codigo_ibge"] if slug_mun else None),
        )
        achado.setdefault("municipio_confianca", "baixa" if slug_mun else None)
        achado.setdefault("municipio_origem", origem)
        achado.setdefault(
            "municipio_escopo",
            "municipal" if slug_mun
            else ("estadual" if achado.get("esfera") == "estadual"
                  else "indeterminado"),
        )
    achado.setdefault("municipio_origem", None)
    achado.setdefault("orgao_vinculado_id", None)
    achado.setdefault("conteudo_truncado", False)
    return achado


def status_estimado(achado, referencia):
    """Status derivado das datas oficiais de inscricao, quando existirem."""
    inicio = comum.data_ou_none((achado.get("inscricoes") or {}).get("inicio"))
    fim = comum.data_ou_none((achado.get("inscricoes") or {}).get("fim"))
    if inicio and referencia < inicio:
        return "edital_publicado"
    if fim and referencia > fim:
        return "inscricoes_encerradas"
    if inicio and fim and inicio <= referencia <= fim:
        return "inscricoes_abertas"
    if achado.get("situacao_portal") in ("previsto", "autorizado"):
        return achado["situacao_portal"]
    return None


# ------------------------------------------------ cobertura e nao mapeados


def cobertura(indice, registros, achados, slugs_com_sinal_historico_antes, referencia):
    """Bloco cobertura_municipios. Funcao pura: recebe o indice do cadastro, os
    registros de dados/, a lista final de achados, o conjunto HISTORICO de slugs
    que ja tiveram sinal em QUALQUER execucao anterior, e a data de referencia.
    Devolve dict.

    O quarto parametro e historico, e nao o retrato da janela anterior, porque
    'vistos_pela_primeira_vez' precisa significar "primeira vez em todas as
    execucoes": com o retrato, um municipio que publica hoje, fica uma semana
    sem publicar e volta seria anunciado DE NOVO como primeiro ato.

    'referencia' entra porque com_achado_na_janela conta apenas achados vistos
    NESTA execucao, e a lista final inclui preservados de execucoes anteriores.

    Nao e calculada dentro de fonte nenhuma: e chamada por main() depois do
    laco, para que '--fonte selecao-es' isolado tambem produza o bloco. Pura
    para ser testavel sem rede e sem disco.
    """
    antes = set(slugs_com_sinal_historico_antes or ())
    hoje_iso = referencia.isoformat()

    curados = set()
    intermunicipais = 0
    for registro in registros:
        # Registro intermunicipal nao credita municipio nenhum: um processo do
        # Consorcio Caparao nao e atividade do municipio de Divino de Sao
        # Lourenco. Medido nos 53 registros: 16 nomes oficiais distintos no
        # total, 15 depois de excluir os intermunicipais — e 15 e o valor do
        # campo.
        if registro.get("esfera") == "intermunicipal":
            intermunicipais += 1
            continue
        slug_mun, _origem = comum.resolver_municipio(registro.get("municipio"), indice)
        if slug_mun:
            curados.add(slug_mun)

    na_janela = set()
    acumulado = set()
    for achado in achados:
        if achado.get("municipio_confianca") != "alta":
            continue  # confianca baixa entra na quarentena, mas nao na metrica
        slug_mun = achado.get("municipio_slug")
        if not slug_mun:
            continue
        acumulado.add(slug_mun)
        if achado.get("ultima_deteccao") == hoje_iso:
            na_janela.add(slug_mun)

    com_sinal = na_janela | curados
    historico = antes | com_sinal
    todos = set(indice.por_slug)
    return {
        # total_esperado do cadastro, NUNCA o literal 78: um 79o municipio nao
        # pode reprovar o repositorio.
        "total_municipios": indice.total_esperado,
        "com_registro_curado": len(curados),
        "com_achado_na_janela": len(na_janela),
        "com_achado_acumulado": len(acumulado),
        "sem_sinal_algum": len(todos - com_sinal),
        "slugs_com_achado_acumulado": sorted(acumulado),
        "slugs_com_sinal": sorted(com_sinal),
        "slugs_com_sinal_historico": sorted(historico),
        "vistos_pela_primeira_vez": sorted(com_sinal - antes),
        "sem_sinal_slugs": sorted(todos - com_sinal),
        "orgaos_vinculados_sem_municipio": sorted(
            oid
            for oid, orgao in indice.orgaos_por_id.items()
            if not (orgao.get("municipios_slugs") or [])
        ),
        "registros_intermunicipais_sem_atribuicao": intermunicipais,
    }


def historico_de_sinal(bruto):
    """Conjunto historico de slugs com sinal, lido do descobertas.json anterior.

    Leitura tolerante de proposito: um arquivo gravado por versao intermediaria
    pode ter apenas 'slugs_com_sinal', e um arquivo anterior ao cadastro nao tem
    o bloco — nesse caso vale set(), e todos os slugs com sinal entram no delta,
    o que e correto na primeira execucao com cadastro.
    """
    bloco = (bruto or {}).get("cobertura_municipios") or {}
    return set(
        bloco.get("slugs_com_sinal_historico")
        or bloco.get("slugs_com_sinal")
        or []
    )


def _provavel_alias_de(nome, indice):
    """Municipio provavel para o candidato, ou None.

    Regra conservadora e explicita: igualdade dos conjuntos de tokens nao
    genericos, ou diferenca de exatamente UM token de ligacao ('de', 'do',
    'da'). Nada de distancia de edicao difusa — sugestao errada faria alguem
    cadastrar alias indevido. Sem candidato unico, devolve None.
    """
    alvo = {t for t in nome.split() if t not in TOKENS_GENERICOS}
    if not alvo:
        return None
    achados = set()
    for slug_mun, entrada in indice.por_slug.items():
        nomes = [entrada.get("nome")] + list(entrada.get("aliases") or [])
        for candidato in nomes:
            toks = {
                t
                for t in comum.chave_nome(candidato).split()
                if t not in TOKENS_GENERICOS
            }
            if not toks:
                continue
            diferenca = toks ^ alvo
            if not diferenca or (
                len(diferenca) == 1 and diferenca <= TOKENS_DE_LIGACAO
            ):
                achados.add(slug_mun)
    return next(iter(achados)) if len(achados) == 1 else None


def fundir_nao_mapeados(anteriores, atuais, indice, referencia, janela_dias):
    """Funde os candidatos do arquivo anterior com os desta execucao.

    Contadores ACUMULADOS, e nao por execucao, por um caso que decide: um
    candidato real que apareca 1x por dia em pagina distinta e sem '/ES' tem, na
    semana, 7 paginas distintas — mas, com contadores por execucao, nunca passa
    de paginas_distintas == 1 e NUNCA e reportado. O aprendizado de alias
    depende exatamente desse candidato. Como a janela do IOES e de 7 dias e as
    execucoes se sobrepoem, o acumulado conta a mesma ocorrencia mais de uma
    vez: isso e aceito, porque ocorrencias e paginas_distintas sao medidas de
    INSISTENCIA do candidato, e nao inventario de paginas. A remocao por
    ultima_deteccao e o que impede o acumulado de crescer para sempre.
    """
    hoje_iso = referencia.isoformat()
    limite = (referencia - dt.timedelta(days=janela_dias * 4)).isoformat()

    fundidos = {}
    for anterior in anteriores or []:
        if not isinstance(anterior, dict) or not anterior.get("nome_detectado"):
            continue
        fundidos[anterior["nome_detectado"]] = {
            "nome_detectado": anterior["nome_detectado"],
            "ocorrencias": anterior.get("ocorrencias") or 0,
            "paginas_distintas": anterior.get("paginas_distintas") or 0,
            "com_marca_uf": bool(anterior.get("com_marca_uf")),
            "fontes": list(anterior.get("fontes") or []),
            # Exemplo que nao e dict so chega aqui por arquivo editado a mao ou
            # por formato de versao anterior, e e descartado em vez de
            # propagado: _exemplos_ordenados() e monta_relatorio_md() fazem
            # exemplo.get("url"), e os dois rodam em main(), FORA do try/except
            # por fonte — um unico exemplo malformado derrubaria a coleta do dia
            # inteiro com AttributeError, que e exatamente o que a degradacao
            # graciosa proibe. O candidato, que e o dado que importa, sobrevive.
            "exemplos": [
                e for e in (anterior.get("exemplos") or []) if isinstance(e, dict)
            ],
            "primeira_deteccao": anterior.get("primeira_deteccao") or hoje_iso,
            "ultima_deteccao": anterior.get("ultima_deteccao") or hoje_iso,
        }

    for atual in atuais or []:
        nome = atual["nome_detectado"]
        alvo = fundidos.get(nome)
        if alvo is None:
            alvo = fundidos[nome] = {
                "nome_detectado": nome,
                "ocorrencias": 0,
                "paginas_distintas": 0,
                "com_marca_uf": False,
                "fontes": [],
                "exemplos": [],
                "primeira_deteccao": hoje_iso,
                "ultima_deteccao": hoje_iso,
            }
        alvo["ocorrencias"] += atual["ocorrencias"]
        alvo["paginas_distintas"] += atual["paginas_distintas"]
        alvo["com_marca_uf"] = alvo["com_marca_uf"] or atual["com_marca_uf"]
        alvo["fontes"] = sorted(set(alvo["fontes"]) | set(atual["fontes"]))
        alvo["ultima_deteccao"] = hoje_iso
        alvo["exemplos"] = _exemplos_ordenados(
            list(atual["exemplos"]) + list(alvo["exemplos"])
        )

    saida = []
    for item in fundidos.values():
        # Candidato que parou de aparecer sai INTEIRO da lista, zerando os
        # contadores junto; sem isso o acumulado cresceria para sempre.
        if item["ultima_deteccao"] < limite:
            continue
        # Filtro aplicado aos ACUMULADOS: ocorrencia unica sem '/ES' e quase
        # sempre OCR ruim, mas a disjuncao importa — na deteccao por injecao,
        # 'sooretama' apareceu em 1 pagina e so e reportado porque veio com a
        # marca de UF.
        if item["paginas_distintas"] < 2 and not item["com_marca_uf"]:
            continue
        provavel = _provavel_alias_de(item["nome_detectado"], indice)
        item["provavel_alias_de"] = provavel
        item["sugestao"] = "alias" if provavel else "verificar"
        saida.append(item)
    saida.sort(key=lambda c: (-c["ocorrencias"], c["nome_detectado"]))
    return saida


def reconciliar_ibge(indice, referencia, conferir=True):
    """Compara o cadastro com a lista oficial do IBGE (UF 32).

    Criacao de municipio e lei estadual e o IBGE e quem publica a lista, logo
    esta e a segunda via de deteccao de municipio novo, independente do texto
    dos diarios. Falha NAO e fatal: status 'erro' + ::warning:: e a coleta
    segue — o IBGE fora do ar nao pode derrubar o monitoramento. Divergencia
    NUNCA altera o cadastro: ela abre issue, porque escrever 78->79 municipios
    sem revisao humana violaria a curadoria (e um endpoint que respondesse
    errado uma vez corromperia a fonte da verdade).

    len != 78 nao e erro — e exatamente o sinal que se quer detectar.
    """
    bloco = {
        "status": "nao_conferido",
        "consultado_em": None,
        "total_ibge": None,
        "total_cadastro": len(indice.por_slug),
        "ausentes_no_cadastro": [],
        "excedentes_no_cadastro": [],
        "nomes_divergentes": [],
        "erro": None,
    }
    if not conferir:
        return bloco

    bloco["consultado_em"] = referencia.isoformat()
    try:
        dados = json.loads(_ler_com_retry(URL_IBGE_MUNICIPIOS))
        if not isinstance(dados, list) or not dados:
            raise ValueError("lista de municipios vazia ou inesperada")
        oficiais = {}
        for item in dados:
            if not isinstance(item, dict):
                raise ValueError("item da lista do IBGE nao e objeto")
            codigo = item.get("id")
            nome = item.get("nome")
            if not isinstance(codigo, int) or not str(codigo).startswith("32"):
                raise ValueError("codigo de municipio inesperado: %r" % (codigo,))
            if not isinstance(nome, str) or not nome.strip():
                raise ValueError("nome de municipio vazio no codigo %s" % codigo)
            oficiais[codigo] = nome.strip()
    except (urllib.error.URLError, socket.timeout, OSError, ValueError) as erro:
        bloco["status"] = "erro"
        bloco["erro"] = "%s: %s" % (type(erro).__name__, erro)
        print("::warning::reconciliacao com o IBGE falhou: %s" % bloco["erro"])
        return bloco

    por_codigo = {
        entrada.get("codigo_ibge"): entrada for entrada in indice.por_slug.values()
    }
    bloco["status"] = "ok"
    bloco["total_ibge"] = len(oficiais)
    bloco["ausentes_no_cadastro"] = [
        {"codigo_ibge": codigo, "nome": nome}
        for codigo, nome in sorted(oficiais.items())
        if codigo not in por_codigo
    ]
    bloco["excedentes_no_cadastro"] = [
        {"codigo_ibge": codigo, "nome": (por_codigo[codigo] or {}).get("nome")}
        for codigo in sorted(c for c in por_codigo if c not in oficiais)
    ]
    bloco["nomes_divergentes"] = [
        {
            "codigo_ibge": codigo,
            "nome_ibge": nome,
            "nome_cadastro": por_codigo[codigo].get("nome"),
        }
        for codigo, nome in sorted(oficiais.items())
        if codigo in por_codigo and por_codigo[codigo].get("nome") != nome
    ]
    return bloco


def ha_divergencia_ibge(bloco):
    """True quando a reconciliacao achou diferenca que exige mao humana."""
    return bool(
        (bloco or {}).get("ausentes_no_cadastro")
        or (bloco or {}).get("excedentes_no_cadastro")
        or (bloco or {}).get("nomes_divergentes")
    )


# --------------------------------------------------------------------- estado


def monta_relatorio_md(novos, relatorio_fontes, referencia, contexto=None):
    """Corpo da issue aberta automaticamente quando surge achado novo.

    'contexto' e um dict com as chaves 'cobertura' (bloco de cobertura),
    'nao_mapeados' (lista de candidatos), 'reconciliacao' (bloco do IBGE),
    'atos_novos' (lista) e 'truncado' (bool agregado). Um dict e nao cinco
    parametros posicionais: a funcao ja tinha tres, e a cada secao condicional
    nova a assinatura cresceria de novo. Chave ausente e tratada como SECAO
    AUSENTE (a secao e condicional de qualquer modo), de modo que um chamador de
    teste pode passar {}.
    """
    contexto = contexto or {}
    cobertura_bloco = contexto.get("cobertura") or {}
    nao_mapeados = contexto.get("nao_mapeados") or []
    reconciliacao = contexto.get("reconciliacao") or {}
    atos_novos = contexto.get("atos_novos") or []
    primeira_vez = cobertura_bloco.get("vistos_pela_primeira_vez") or []

    # A issue passa a abrir tambem quando novos == 0 (primeiro ato num
    # municipio, candidato sem mapeamento, divergencia com o IBGE). Sem esta
    # frase condicional ela chegaria negando o proprio motivo de existir.
    motivos = ["**%d** oportunidade(s) sem registro em `dados/`" % len(novos)]
    if primeira_vez:
        motivos.append("**%d** municipio(s) com o primeiro ato detectado" % len(primeira_vez))
    if nao_mapeados:
        motivos.append("**%d** municipio(s) citado(s) sem mapeamento" % len(nao_mapeados))
    if ha_divergencia_ibge(reconciliacao):
        motivos.append("**divergencia** com a lista do IBGE")

    linhas = [
        "A coleta automatica de %s encontrou %s."
        % (referencia.strftime("%d/%m/%Y"), "; ".join(motivos)),
        "",
        "> Estes itens sao **pistas nao conferidas**. Antes de criar o registro, "
        "abra o link e leia o edital na fonte oficial.",
        "",
    ]
    if novos:
        linhas += [
            "| Órgão | Oportunidade | Inscrições | Fonte |",
            "| ----- | ------------ | ---------- | ----- |",
        ]
        for achado in novos:
            sigla = achado.get("orgao_sigla")
            orgao = sigla if sigla and sigla != comum.AUSENTE else achado.get("orgao")
            inscricoes = achado.get("inscricoes") or {}
            prazo = " a ".join(
                x for x in (inscricoes.get("inicio"), inscricoes.get("fim")) if x
            )
            titulo = (achado.get("titulo") or "").replace("|", "\\|")
            linhas.append(
                "| %s | [%s](%s) | %s | `%s` |"
                % (
                    (orgao or comum.AUSENTE).replace("|", "\\|"),
                    titulo,
                    achado.get("url") or "",
                    prazo or comum.AUSENTE,
                    achado.get("fonte_tipo") or comum.AUSENTE,
                )
            )
        linhas.append("")

    if atos_novos:
        # Linha de RESUMO, nunca tabela: a tabela de oportunidades tem colunas
        # 'Inscricoes' e 'Oportunidade' que um ato de nomeacao nao preenche.
        linhas += [
            "Atos de diario oficial novos nesta coleta: **%d** — ver "
            "`descobertas/descobertas.json`." % len(atos_novos),
            "",
        ]

    if cobertura_bloco:
        linhas += [
            "Cobertura: **%s/%s** municipios com sinal na janela; %s sem sinal algum."
            % (
                cobertura_bloco.get("com_achado_na_janela"),
                cobertura_bloco.get("total_municipios"),
                cobertura_bloco.get("sem_sinal_algum"),
            ),
            "",
        ]
    if primeira_vez:
        linhas += [
            "Primeiro ato detectado em: %s"
            % ", ".join(primeira_vez),
            "",
        ]

    if nao_mapeados:
        linhas += [
            "### Municipios citados sem mapeamento",
            "",
            "| Nome detectado | Ocorrências | Provável alias de | Exemplo |",
            "| -------------- | ----------: | ----------------- | ------- |",
        ]
        for candidato in nao_mapeados:
            exemplos = candidato.get("exemplos") or []
            exemplo = (exemplos[0].get("url") if exemplos else "") or ""
            linhas.append(
                "| %s | %d | %s | %s |"
                % (
                    candidato.get("nome_detectado"),
                    candidato.get("ocorrencias") or 0,
                    candidato.get("provavel_alias_de") or comum.AUSENTE,
                    exemplo,
                )
            )
        linhas += [
            "",
            "Se for variante de um municipio existente, acrescente o alias em "
            "`fontes/municipios-es.json`; se for municipio real que falta, abra "
            "a entrada nova **a mao** (o coletor nunca escreve no cadastro).",
            "",
        ]

    if ha_divergencia_ibge(reconciliacao):
        linhas += ["### Divergência com a lista do IBGE", ""]
        for item in reconciliacao.get("ausentes_no_cadastro") or []:
            linhas.append(
                "- ausente no cadastro: `%s` %s"
                % (item.get("codigo_ibge"), item.get("nome"))
            )
        for item in reconciliacao.get("excedentes_no_cadastro") or []:
            linhas.append(
                "- excedente no cadastro: `%s` %s"
                % (item.get("codigo_ibge"), item.get("nome"))
            )
        for item in reconciliacao.get("nomes_divergentes") or []:
            linhas.append(
                "- nome divergente em `%s`: IBGE %r, cadastro %r"
                % (
                    item.get("codigo_ibge"),
                    item.get("nome_ibge"),
                    item.get("nome_cadastro"),
                )
            )
        linhas += [
            "",
            "Atualize `fontes/municipios-es.json` **manualmente**: divergencia "
            "nunca altera o cadastro automaticamente.",
            "",
        ]

    if contexto.get("truncado"):
        linhas += [
            "### Coleta truncada",
            "",
            "Algum escopo do buscador do IOES atingiu o teto de paginas ou de "
            "achados nesta execucao: ha hits na janela que ficaram de fora. "
            "Truncamento recorrente e lacuna de cobertura — reveja "
            "`--max-paginas-ioes` / `--max-achados-ioes`.",
            "",
        ]

    linhas += ["### Fontes consultadas", ""]
    for fonte in relatorio_fontes:
        if fonte["status"] == "ok":
            linhas.append(
                "- `%s` (%s): %d item(ns)"
                % (fonte["id"], fonte["tipo"], fonte["achados"])
            )
        else:
            linhas.append(
                "- `%s` (%s): **falhou** — %s"
                % (fonte["id"], fonte["tipo"], fonte.get("erro"))
            )
    linhas += [
        "",
        "---",
        "_Issue aberta automaticamente pelo workflow de monitoramento. "
        "A lista completa fica em `descobertas/descobertas.json`._",
    ]
    return "\n".join(linhas) + "\n"


def carregar_anterior():
    """Devolve (achados_por_chave, bruto). 'bruto' e o dict inteiro do arquivo,
    necessario para preservar municipios_nao_mapeados e o historico de cobertura
    entre execucoes — a versao anterior devolvia so os achados e jogava fora o
    resto, e nao havia como ler a lista anterior sem mudar a funcao.
    """
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {}, {}
    return (
        {a["chave"]: a for a in dados.get("achados", []) if a.get("chave")},
        dados,
    )


def gravar_descobertas(saida):
    """Grava descobertas.json no formato do projeto (ensure_ascii=False,
    indent=2, newline final)."""
    os.makedirs(DIR_DESCOBERTAS, exist_ok=True)
    with open(CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
        json.dump(saida, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def migrar_descobertas(indice):
    """Aplica normalizar_achado() a cada achado do arquivo versionado e regrava.

    Definido como "aplica normalizar_achado()" e nao como uma lista propria de
    campos: com a definicao por funcao existe UM lugar com a lista de campos, e
    a migracao nao pode divergir do backfill na primeira mudanca de esquema.
    Sem rede, sem coleta e idempotente (setdefault). Arquivo ausente nao e erro
    (a coleta pode nunca ter rodado); JSON invalido e fatal, porque regravar em
    cima de JSON invalido perderia o original.
    """
    if not os.path.exists(CAMINHO_DESCOBERTAS):
        print("Nada a migrar: %s nao existe." % os.path.relpath(
            CAMINHO_DESCOBERTAS, comum.RAIZ))
        return 0
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except ValueError as erro:
        print(
            "ERRO: %s tem JSON invalido (%s); nada foi regravado."
            % (CAMINHO_DESCOBERTAS, erro),
            file=sys.stderr,
        )
        return 1

    achados = dados.get("achados") or []
    for achado in achados:
        if isinstance(achado, dict):
            normalizar_achado(achado, indice)
    gravar_descobertas(dados)
    print(
        "Migrados %d achado(s) em %s."
        % (len(achados), os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ))
    )
    return 0


def autoteste_ioes(indice, janela_dias, max_paginas, max_achados):
    """Consulta real por escopo, para auditoria manual de mudanca de layout.

    NAO roda no workflow: teste que depende de terceiro nao pode reprovar PR.
    """
    for escopo in sorted(BASES_IOES):
        diag = {}
        try:
            achados = coletar_ioes(
                escopo=escopo,
                diagnostico=diag,
                janela_dias=janela_dias,
                max_paginas=max_paginas,
                max_achados=max_achados,
                indice=indice,
            )
        except (urllib.error.URLError, OSError, ValueError) as erro:
            print("  %-16s FALHOU: %s: %s" % (escopo, type(erro).__name__, erro))
            continue
        resolvidos = sorted(
            {a["municipio_slug"] for a in achados if a.get("municipio_slug")}
        )
        altos = sorted(
            {
                a["municipio_slug"]
                for a in achados
                if a.get("municipio_slug") and a.get("municipio_confianca") == "alta"
            }
        )
        print(
            "  %-16s total relatado %s | %d achados | %d municipios (%d em alta)"
            % (escopo, diag.get("total_relatado"), len(achados), len(resolvidos),
               len(altos))
        )
        print("    alta: %s" % (", ".join(altos) or "-"))
        print(
            "    nao mapeados: %s"
            % (
                ", ".join(
                    "%s(%d/%d%s)"
                    % (
                        c["nome_detectado"],
                        c["ocorrencias"],
                        c["paginas_distintas"],
                        "/uf" if c["com_marca_uf"] else "",
                    )
                    for c in diag.get("nao_mapeados") or []
                )
                or "-"
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta oportunidades do ES.")
    parser.add_argument(
        "--fonte",
        action="append",
        choices=sorted(FONTES),
        help="coletar apenas a(s) fonte(s) indicada(s); padrao: todas",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="nao grava, apenas relata"
    )
    parser.add_argument(
        "--saida-github",
        help="arquivo estilo $GITHUB_OUTPUT onde gravar novos=/total=",
    )
    parser.add_argument(
        "--relatorio-md",
        help="grava um resumo Markdown dos achados novos (corpo da issue)",
    )
    parser.add_argument(
        "--exigir-fonte",
        action="store_true",
        help="retorna erro se nenhuma fonte responder (padrao: tolera)",
    )
    parser.add_argument(
        "--janela-dias",
        type=int,
        default=90,
        help=(
            "descarta achados cujas inscricoes encerraram ha mais de N dias. "
            "O Selecao ES devolve o acervo desde 2015; sem janela o monitoramento "
            "afogaria em historico irrelevante. Padrao: 90"
        ),
    )
    # Janela do buscador do IOES. E parametro SEPARADO de --janela-dias (que
    # trata de descarte por prazo de inscricao encerrado): sao conceitos
    # distintos, e misturar os dois faria o operador mudar um e quebrar o outro.
    parser.add_argument(
        "--janela-ioes-dias",
        type=int,
        default=7,
        help=(
            "janela de busca no diario oficial (di: = hoje - N). Sete dias "
            "cobrem o cron diario e absorvem alguns dias de falha. Padrao: 7"
        ),
    )
    parser.add_argument(
        "--max-paginas-ioes",
        type=int,
        default=20,
        help=(
            "teto de paginas por escopo e frase no IOES (10 itens por pagina). "
            "Padrao: 20 — 200 resultados cobrem os 131 hits medidos com folga"
        ),
    )
    parser.add_argument(
        "--max-achados-ioes",
        type=int,
        default=1000,
        help="teto de achados por fonte do IOES. Padrao: 1000",
    )
    # Duas flags para o mesmo destino precisam de dest e default escritos, senao
    # o padrao depende da ordem de declaracao. Ligada por padrao: conferir a
    # lista oficial custa 1 requisicao por execucao.
    parser.add_argument(
        "--conferir-ibge",
        dest="conferir_ibge",
        action="store_true",
        default=True,
        help="confere o cadastro contra a lista do IBGE (padrao)",
    )
    parser.add_argument(
        "--sem-conferir-ibge",
        dest="conferir_ibge",
        action="store_false",
        help="nao consulta o IBGE nesta execucao",
    )
    parser.add_argument(
        "--retencao-atos-dias",
        type=int,
        default=RETENCAO_ATO_DIARIO_DIAS,
        help=(
            "descarta ato de diario publicado ha mais de N dias. Ato de diario "
            "nao tem prazo de inscricao, logo a poda por inscricoes.fim nunca o "
            "alcanca. Padrao: %d" % RETENCAO_ATO_DIARIO_DIAS
        ),
    )
    parser.add_argument(
        "--migrar-descobertas",
        action="store_true",
        help=(
            "aplica a normalizacao de achado ao descobertas.json versionado e "
            "regrava (sem rede, idempotente)"
        ),
    )
    parser.add_argument(
        "--autoteste-ioes",
        action="store_true",
        help="consulta real por escopo e relata o que foi extraido (com rede)",
    )
    args = parser.parse_args()

    # Os tetos existem para que um erro de digitacao (--max-paginas-ioes 1000)
    # nao transforme o cron diario em varredura de acervo.
    for nome, valor, teto in (
        ("--janela-ioes-dias", args.janela_ioes_dias, 365),
        ("--max-paginas-ioes", args.max_paginas_ioes, 100),
        ("--max-achados-ioes", args.max_achados_ioes, 5000),
        ("--retencao-atos-dias", args.retencao_atos_dias, 365),
    ):
        if valor < 1 or valor > teto:
            parser.error("%s deve estar entre 1 e %d (recebido: %d)"
                         % (nome, teto, valor))

    referencia = comum.hoje()

    # O cadastro e configuracao versionada: se esta quebrado, qualquer numero
    # produzido adiante e falso, e falhar alto e a unica resposta honesta.
    # Fonte externa fora do ar e condicao esperada do mundo e nao e fatal.
    try:
        indice_mun = comum.indice_municipios()
    except (OSError, ValueError, KeyError, TypeError) as erro:
        print(
            "ERRO: cadastro de municipios ilegivel (%s): %s"
            % (comum.CAMINHO_MUNICIPIOS, erro),
            file=sys.stderr,
        )
        print("::error::cadastro de municipios ilegivel")
        return 1

    if args.migrar_descobertas:
        return migrar_descobertas(indice_mun)

    if args.autoteste_ioes:
        return autoteste_ioes(
            indice_mun,
            args.janela_ioes_dias,
            args.max_paginas_ioes,
            args.max_achados_ioes,
        )

    limite_antiguidade = referencia - dt.timedelta(days=args.janela_dias)
    limite_retencao = referencia - dt.timedelta(days=args.retencao_atos_dias)
    catalogo = carregar_catalogo_fontes()
    if not catalogo:
        print(
            "::warning::catalogo de fontes ilegivel; metadados de fonte "
            "ficarao ausentes"
        )
    anterior, bruto_anterior = carregar_anterior()
    indice = indice_repositorio()
    registros_dados = [reg for _caminho, reg in comum.carregar_registros()]
    escolhidas = args.fonte or sorted(FONTES)

    relatorio_fontes = []
    achados = []
    houve_sucesso = False
    nao_mapeados_brutos = []
    truncado_agregado = False

    # Quantos achados cada fonte trouxe na ultima coleta. Serve para detectar
    # parser quebrado: a fonte responde 200, o codigo nao levanta erro, mas o
    # HTML mudou e a extracao passa a devolver zero.
    contagem_anterior = {}
    for previo in anterior.values():
        fid = previo.get("fonte_id")
        contagem_anterior[fid] = contagem_anterior.get(fid, 0) + 1

    for fonte_id in escolhidas:
        meta = catalogo.get(fonte_id, {})
        try:
            diag = {}
            chamavel = FONTES[fonte_id]
            if fonte_id in FONTES_COM_DIAGNOSTICO:
                brutos = chamavel(
                    diagnostico=diag,
                    janela_dias=args.janela_ioes_dias,
                    max_paginas=args.max_paginas_ioes,
                    max_achados=args.max_achados_ioes,
                    indice=indice_mun,
                )
            else:
                brutos = chamavel()
            houve_sucesso = True
            achados.extend(brutos)
            registro_fonte = {
                "id": fonte_id,
                "nome": meta.get("nome", fonte_id),
                "tipo": meta.get("tipo", comum.AUSENTE),
                "status": "ok",
                "achados": len(brutos),
            }
            # O diagnostico vai inteiro para o relatorio da fonte, menos
            # nao_mapeados: aquela lista precisa ser fundida com a do arquivo
            # anterior e vive em bloco proprio do descobertas.json.
            registro_fonte.update(
                {k: v for k, v in diag.items() if k != "nao_mapeados"}
            )
            nao_mapeados_brutos.extend(diag.get("nao_mapeados") or [])
            truncado_agregado = truncado_agregado or bool(
                diag.get("truncado") or diag.get("limite_achados_atingido")
            )
            if not brutos and contagem_anterior.get(fonte_id):
                registro_fonte["suspeita_extracao_vazia"] = True
                print(
                    "::warning::fonte %s respondeu sem erro mas devolveu 0 itens "
                    "(antes tinha %d). Possivel mudanca de layout: conferir o "
                    "coletor." % (fonte_id, contagem_anterior[fonte_id])
                )
            relatorio_fontes.append(registro_fonte)
            print("  %-22s ok: %d achados" % (fonte_id, len(brutos)))
        except (urllib.error.URLError, OSError, ValueError, RuntimeError) as erro:
            relatorio_fontes.append(
                {
                    "id": fonte_id,
                    "nome": meta.get("nome", fonte_id),
                    "tipo": meta.get("tipo", comum.AUSENTE),
                    "status": "erro",
                    "erro": "%s: %s" % (type(erro).__name__, erro),
                    "achados": 0,
                }
            )
            print("  %-22s FALHOU: %s: %s" % (fonte_id, type(erro).__name__, erro))
            print("::warning::fonte %s indisponivel nesta execucao" % fonte_id)

    if not houve_sucesso:
        print("ERRO: nenhuma fonte respondeu.", file=sys.stderr)
        # Anotacao visivel no resumo da execucao do GitHub Actions, para que uma
        # coleta que parou de funcionar nao passe despercebida.
        print("::error::nenhuma fonte respondeu nesta coleta")
        if args.exigir_fonte:
            return 1

    # Enriquecimento e preservacao da primeira deteccao.
    novos = []
    atos_novos = []
    finais = []
    vistos = set()
    descartados_antigos = 0
    descartados_invalidos = 0
    descartados_por_retencao = 0
    for achado in achados:
        # Um achado sem chave nao pode ser comparado entre execucoes. Descartar
        # com aviso e melhor que derrubar a coleta inteira: se um dia o parser
        # de uma fonte produzir lixo, as demais fontes seguem funcionando.
        if not isinstance(achado, dict) or not achado.get("chave"):
            descartados_invalidos += 1
            print(
                "::warning::achado invalido descartado (sem chave) da fonte %s"
                % (achado.get("fonte_id") if isinstance(achado, dict) else "?")
            )
            continue
        chave = achado["chave"]
        if chave in vistos:
            continue
        vistos.add(chave)

        fim = comum.data_ou_none((achado.get("inscricoes") or {}).get("fim"))
        if fim and fim < limite_antiguidade:
            descartados_antigos += 1
            continue

        meta = catalogo.get(achado.get("fonte_id"), {})
        achado["fonte_tipo"] = meta.get("tipo", comum.AUSENTE)
        achado["uf"] = "ES"
        achado["status_estimado"] = status_estimado(achado, referencia)
        # Ponto unico, antes de QUALQUER decisao: o casamento, o filtro de
        # novidade e a cobertura dependem de 'categoria' e dos campos de
        # municipio, e nenhuma fonte precisa conhecer esse vocabulario.
        normalizar_achado(achado, indice_mun)
        registro = (
            casar(achado, indice)
            if achado["categoria"] == "oportunidade"
            else casar_estrito(achado, indice)
        )
        achado["no_repositorio"] = registro is not None
        achado["registro_repositorio"] = registro
        achado["ultima_deteccao"] = referencia.isoformat()

        previo = anterior.get(chave)
        if previo:
            achado["primeira_deteccao"] = previo.get(
                "primeira_deteccao", referencia.isoformat()
            )
        else:
            achado["primeira_deteccao"] = referencia.isoformat()
            # So oportunidade e 'novidade'. Ato de diario pode ser nomeacao,
            # convocacao ou homologacao: contar isso como vaga nova poria
            # centenas de linhas por dia na tabela da issue, todas com
            # 'Inscricoes: nao informado', e faria o titulo mentir.
            if registro is None and achado.get("categoria") == "oportunidade":
                novos.append(achado)
            elif registro is None:
                atos_novos.append(achado)
        finais.append(achado)

    # Achados que sumiram da fonte nesta execucao continuam registrados, com a
    # ultima_deteccao antiga, para nao perder rastro do que ja foi visto.
    fontes_ok = {f["id"] for f in relatorio_fontes if f["status"] == "ok"}
    for chave, previo in anterior.items():
        if chave in vistos:
            continue
        # Achado herdado de execucao anterior ao cadastro de municipios. O
        # default e 'oportunidade' porque so as duas fontes de oportunidade
        # existiam quando esses achados foram gravados. Sem este backfill o
        # validador reprovaria o proprio commit automatico, todos os dias, por
        # falta de um campo que a execucao antiga nao tinha como gravar.
        previo.setdefault("categoria", "oportunidade")
        previo.setdefault("municipio_slug", None)
        previo.setdefault("municipio_escopo", "indeterminado")
        previo.setdefault("municipio_confianca", None)

        fim = comum.data_ou_none((previo.get("inscricoes") or {}).get("fim"))
        if fim and fim < limite_antiguidade:
            continue  # saiu da janela de relevancia
        # Retencao propria por categoria: ato de diario tem inscricoes nulas
        # por decisao, logo a poda acima nunca o alcanca e este laco o
        # reanexaria para sempre, fazendo o arquivo (que o bot commita
        # diariamente) crescer algumas dezenas de entradas por dia. A retencao
        # NAO se aplica a 'oportunidade': ali a poda por inscricoes.fim ja
        # funciona e e a regra semanticamente correta (la a data existe).
        if previo.get("categoria") == "ato_diario":
            marca = comum.data_ou_none(previo.get("data_publicacao_ato")) or (
                comum.data_ou_none(previo.get("ultima_deteccao"))
            )
            if marca and marca < limite_retencao:
                descartados_por_retencao += 1
                continue
        if previo.get("fonte_id") not in fontes_ok:
            finais.append(previo)  # fonte offline: preserva sem alterar
        else:
            previo["ausente_na_fonte"] = True
            finais.append(previo)

    finais.sort(
        key=lambda a: (
            a.get("fonte_id") or "",
            (a.get("inscricoes") or {}).get("fim") or "",
            a.get("orgao") or "",
        )
    )

    pendentes = [a for a in finais if not a.get("no_repositorio")]
    cobertura_bloco = cobertura(
        indice_mun,
        registros_dados,
        finais,
        historico_de_sinal(bruto_anterior),
        referencia,
    )
    nao_mapeados = fundir_nao_mapeados(
        bruto_anterior.get("municipios_nao_mapeados"),
        nao_mapeados_brutos,
        indice_mun,
        referencia,
        args.janela_ioes_dias,
    )
    reconciliacao = reconciliar_ibge(indice_mun, referencia, args.conferir_ibge)
    saida = {
        "descricao": (
            "Achados da coleta automatica. AREA DE QUARENTENA: nao e dado "
            "curado. Cada achado traz apenas o que a fonte informou. Promover "
            "para dados/ exige conferir o edital na fonte oficial."
        ),
        "gerado_em": referencia.isoformat(),
        "janela_dias": args.janela_dias,
        "total_achados": len(finais),
        "ja_no_repositorio": len(finais) - len(pendentes),
        "pendentes_de_curadoria": len(pendentes),
        "fontes_consultadas": relatorio_fontes,
        "achados": finais,
        # Chaves novas. Nenhuma das 8 acima e renomeada ou removida:
        # gerar_relatorio, gerar_email, gerar_readme e validar leem todas elas.
        "janela_ioes_dias": args.janela_ioes_dias,
        "retencao_atos_dias": args.retencao_atos_dias,
        "descartados_por_retencao": descartados_por_retencao,
        "atos_diario_novos": len(atos_novos),
        "cobertura_municipios": cobertura_bloco,
        "municipios_nao_mapeados": nao_mapeados,
        "reconciliacao_ibge": reconciliacao,
    }

    print(
        "\nTotal: %d achados | %d ja em dados/ | %d pendentes | %d novos hoje"
        % (len(finais), len(finais) - len(pendentes), len(pendentes), len(novos))
    )
    print(
        "Atos de diario novos: %d | municipios com sinal na janela: %d/%s "
        "| sem sinal algum: %d"
        % (
            len(atos_novos),
            cobertura_bloco["com_achado_na_janela"],
            cobertura_bloco["total_municipios"],
            cobertura_bloco["sem_sinal_algum"],
        )
    )
    if cobertura_bloco["vistos_pela_primeira_vez"]:
        print(
            "Primeiro ato detectado em: %s"
            % ", ".join(cobertura_bloco["vistos_pela_primeira_vez"])
        )
    if nao_mapeados:
        print("Municipios citados sem mapeamento: %d" % len(nao_mapeados))
        for candidato in nao_mapeados:
            print(
                "  %-40s %d ocorrencia(s) em %d pagina(s)%s"
                % (
                    candidato["nome_detectado"],
                    candidato["ocorrencias"],
                    candidato["paginas_distintas"],
                    " — provavel alias de %s" % candidato["provavel_alias_de"]
                    if candidato["provavel_alias_de"]
                    else "",
                )
            )
    if reconciliacao["status"] == "ok" and ha_divergencia_ibge(reconciliacao):
        print("::warning::cadastro de municipios divergente da lista do IBGE")
    if descartados_antigos:
        print(
            "Fora da janela de %d dias (descartados): %d"
            % (args.janela_dias, descartados_antigos)
        )
    if descartados_por_retencao:
        print(
            "Atos de diario fora da retencao de %d dias (descartados): %d"
            % (args.retencao_atos_dias, descartados_por_retencao)
        )
    if descartados_invalidos:
        print("Achados invalidos descartados: %d" % descartados_invalidos)
    for achado in novos:
        print(
            "  NOVO [%s] %s — %s"
            % (achado["fonte_id"], achado.get("orgao"), achado.get("titulo"))
        )

    if args.saida_github:
        with open(args.saida_github, "a", encoding="utf-8") as fh:
            # 'novos' continua significando OPORTUNIDADES novas, e e por isso
            # que ele volta a ser um numero pequeno; os atos de diario tem
            # saida propria.
            fh.write("novos=%d\n" % len(novos))
            fh.write("pendentes=%d\n" % len(pendentes))
            fh.write("total=%d\n" % len(finais))
            fh.write("nao_mapeados=%d\n" % len(nao_mapeados))
            fh.write(
                "divergencia_ibge=%d\n" % (1 if ha_divergencia_ibge(reconciliacao) else 0)
            )
            fh.write(
                "municipios_com_sinal=%d\n" % cobertura_bloco["com_achado_na_janela"]
            )
            fh.write(
                "primeira_vez=%d\n"
                % len(cobertura_bloco["vistos_pela_primeira_vez"])
            )
            fh.write("atos_diario_novos=%d\n" % len(atos_novos))
            # Agregado por OR entre os diagnosticos: ha duas fontes IOES e uma
            # so saida, e o DOM truncado nao pode ser escondido por o DIO ter
            # caido dentro do teto (o volume esta no DOM).
            fh.write("truncado=%d\n" % (1 if truncado_agregado else 0))

    if args.relatorio_md:
        with open(args.relatorio_md, "w", encoding="utf-8") as fh:
            fh.write(
                monta_relatorio_md(
                    novos,
                    relatorio_fontes,
                    referencia,
                    {
                        "cobertura": cobertura_bloco,
                        "nao_mapeados": nao_mapeados,
                        "reconciliacao": reconciliacao,
                        "atos_novos": atos_novos,
                        "truncado": truncado_agregado,
                    },
                )
            )

    if args.dry_run:
        print("\n--dry-run: nada gravado.")
        return 0

    gravar_descobertas(saida)
    print("Gravado: %s" % os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
