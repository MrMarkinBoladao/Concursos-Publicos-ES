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

Tolerancia a falhas: a indisponibilidade de uma fonte nao derruba a execucao.
O erro e registrado no relatorio e a coleta segue com as demais fontes, para
que o monitoramento diario nao pare por causa de um site fora do ar.

Uso:
    python3 ferramentas/coletar.py
    python3 ferramentas/coletar.py --fonte selecao-es
    python3 ferramentas/coletar.py --dry-run
    python3 ferramentas/coletar.py --saida-github "$GITHUB_OUTPUT"
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import re
import sys
import unicodedata
import urllib.error
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

# Orgaos nacionais aparecem na pagina estadual do portal; sao descartados pelo
# padrao do link (itens do ES ficam sob /concursos/es/).
MARCA_ES_NO_LINK = "/concursos/es/"


# ---------------------------------------------------------------- utilitarios


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, espacos colapsados. Para comparar nomes."""
    return re.sub(r"\s+", " ", _sem_acento(texto or "").lower()).strip()


def slug(texto: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(texto))
    return base.strip("-")


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


FONTES = {
    "selecao-es": coletar_selecao_es,
    "concursosnobrasil-es": coletar_concursosnobrasil_es,
}


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


# --------------------------------------------------------------------- estado


def monta_relatorio_md(novos, relatorio_fontes, referencia):
    """Corpo da issue aberta automaticamente quando surge achado novo."""
    linhas = [
        "A coleta automatica de %s encontrou **%d** oportunidade(s) que ainda nao "
        "tem registro em `dados/`." % (referencia.strftime("%d/%m/%Y"), len(novos)),
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
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {a["chave"]: a for a in dados.get("achados", []) if a.get("chave")}


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
    args = parser.parse_args()

    referencia = comum.hoje()
    limite_antiguidade = referencia - dt.timedelta(days=args.janela_dias)
    catalogo = carregar_catalogo_fontes()
    anterior = carregar_anterior()
    indice = indice_repositorio()
    escolhidas = args.fonte or sorted(FONTES)

    relatorio_fontes = []
    achados = []
    houve_sucesso = False

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
            brutos = FONTES[fonte_id]()
            houve_sucesso = True
            achados.extend(brutos)
            registro_fonte = {
                "id": fonte_id,
                "nome": meta.get("nome", fonte_id),
                "tipo": meta.get("tipo", comum.AUSENTE),
                "status": "ok",
                "achados": len(brutos),
            }
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
    finais = []
    vistos = set()
    descartados_antigos = 0
    descartados_invalidos = 0
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
        registro = casar(achado, indice)
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
            if registro is None:
                novos.append(achado)
        finais.append(achado)

    # Achados que sumiram da fonte nesta execucao continuam registrados, com a
    # ultima_deteccao antiga, para nao perder rastro do que ja foi visto.
    fontes_ok = {f["id"] for f in relatorio_fontes if f["status"] == "ok"}
    for chave, previo in anterior.items():
        if chave in vistos:
            continue
        fim = comum.data_ou_none((previo.get("inscricoes") or {}).get("fim"))
        if fim and fim < limite_antiguidade:
            continue  # saiu da janela de relevancia
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
    }

    print(
        "\nTotal: %d achados | %d ja em dados/ | %d pendentes | %d novos hoje"
        % (len(finais), len(finais) - len(pendentes), len(pendentes), len(novos))
    )
    if descartados_antigos:
        print(
            "Fora da janela de %d dias (descartados): %d"
            % (args.janela_dias, descartados_antigos)
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
            fh.write("novos=%d\n" % len(novos))
            fh.write("pendentes=%d\n" % len(pendentes))
            fh.write("total=%d\n" % len(finais))

    if args.relatorio_md:
        with open(args.relatorio_md, "w", encoding="utf-8") as fh:
            fh.write(monta_relatorio_md(novos, relatorio_fontes, referencia))

    if args.dry_run:
        print("\n--dry-run: nada gravado.")
        return 0

    os.makedirs(DIR_DESCOBERTAS, exist_ok=True)
    with open(CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
        json.dump(saida, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("Gravado: %s" % os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
