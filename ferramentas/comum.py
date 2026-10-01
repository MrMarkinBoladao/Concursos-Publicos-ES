"""Funcoes compartilhadas pelas ferramentas de monitoramento.

Carrega os registros de oportunidades do diretorio dados/ e expoe utilitarios
de formatacao usados pelo validador, pelo gerador de README e pelo gerador de
e-mail. Sem dependencias externas: apenas biblioteca padrao do Python 3.
"""

from __future__ import annotations

import collections
import datetime as _dt
import functools
import json
import os
import re
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_DADOS = os.path.join(RAIZ, "dados")
CAMINHO_MUNICIPIOS = os.path.join(RAIZ, "fontes", "municipios-es.json")

AUSENTE = "não informado"

# Diretorio -> status aceitos naquele diretorio.
DIRETORIOS = {
    os.path.join("concursos", "abertos"): {"edital_publicado", "inscricoes_abertas"},
    os.path.join("concursos", "encerrados"): {
        "inscricoes_encerradas",
        "prova_realizada",
        "homologado",
        "cancelado",
    },
    os.path.join("concursos", "previstos"): {"previsto"},
    os.path.join("concursos", "autorizados"): {"autorizado"},
    os.path.join("processos-seletivos", "abertos"): {
        "edital_publicado",
        "inscricoes_abertas",
    },
    os.path.join("processos-seletivos", "encerrados"): {
        "inscricoes_encerradas",
        "prova_realizada",
        "homologado",
        "cancelado",
    },
}

STATUS_VALIDOS = {
    "previsto",
    "autorizado",
    "edital_publicado",
    "inscricoes_abertas",
    "inscricoes_encerradas",
    "prova_realizada",
    "homologado",
    "cancelado",
}

# Ordem do ciclo de vida, usada para detectar regressoes de status.
ORDEM_STATUS = [
    "previsto",
    "autorizado",
    "edital_publicado",
    "inscricoes_abertas",
    "inscricoes_encerradas",
    "prova_realizada",
    "homologado",
]

ESFERAS_VALIDAS = {"federal", "estadual", "municipal", "intermunicipal"}
TIPOS_VALIDOS = {"concurso_publico", "processo_seletivo_simplificado"}
REGIMES_VALIDOS = {"estatutario", "clt", "designacao_temporaria", "nao_informado"}
TIPOS_FONTE_VALIDOS = {
    "oficial",
    "banca",
    "diario_oficial",
    "portal_concursos",
    "imprensa",
}

# Vocabulario de esfera do CATALOGO DE FONTES, que e mais largo que o dos
# registros de dados/. Uma banca ou um portal de concursos nao pertence a
# nenhuma esfera de governo: 'nao_se_aplica' diz isso de forma verificavel, em
# vez de forcar um nivel de governo falso ou de usar "nao informado", que
# significaria "nao sabemos" — e nos sabemos.
ESFERAS_FONTE_VALIDAS = ESFERAS_VALIDAS | {"nao_se_aplica"}

# Tipos de fonte que SAO orgao publico e portanto devem declarar esfera de
# governo real; os demais devem declarar 'nao_se_aplica'.
TIPOS_FONTE_COM_ESFERA = {"oficial", "diario_oficial"}

# Canais por onde um municipio publica informacao de emprego. Um por pergunta
# que a curadoria faz; 'precedencia: 1' e sempre um canal de diario quando
# existir algum, porque e o canal onde o ato tem fe publica.
TIPOS_CANAL = {
    "diario_oficial_proprio",
    "diario_oficial_agregador",
    "portal_prefeitura",
    "secao_concursos",
    "plataforma_inscricao",
    "banca",
}

# Natureza de orgao vinculado a municipio (camara, autarquia, consorcio...).
# Orgao vinculado nao e entrada de primeira classe do cadastro e nao tem
# canais: ele existe para o casamento de texto e para atribuir o ato ao(s)
# municipio(s) do orgao.
NATUREZAS_ORGAO_VINCULADO = {
    "camara_municipal",
    "autarquia_municipal",
    "fundacao_municipal",
    "empresa_municipal",
    "consorcio_intermunicipal",
    "agencia_reguladora",
}

# Motivo de pendencia de verificacao, cada um com produtor declarado:
# conferir_manual = sondagem com 403/406/429 (ou canal sem sondagem
# conclusiva); nao_responde = sondagem com 404/NXDOMAIN/timeout/erro TLS;
# nao_encontrado = curadoria procurou e nada achou. Motivo sem produtor seria
# vocabulario morto, exigido pelo validador e nunca escrito no dado.
MOTIVOS_PENDENCIA = {"conferir_manual", "nao_responde", "nao_encontrado"}

# Categoria do achado de quarentena: so 'oportunidade' e novidade de vaga; ato
# de diario pode ser nomeacao, convocacao ou homologacao.
CATEGORIAS_ACHADO = {"oportunidade", "ato_diario"}

# Escopo territorial do achado, dito positivamente: slug nulo deixa de
# significar duas coisas diferentes ("estadual" e "nao sei").
ESCOPOS_MUNICIPIO = {
    "municipal",
    "intermunicipal",
    "estadual",
    "federal",
    "indeterminado",
}

# Como o municipio foi resolvido. Gravado no achado para que a cobertura seja
# auditavel ("Aracruz contou por que?") e para que um alias errado possa ser
# rastreado ate os achados que creditou.
ORIGENS_MUNICIPIO = {"nome", "alias", "orgao_vinculado"}


# ------------------------------------------------- normalizacao de texto
# As tres primeiras funcoes nasceram em coletar.py e vivem aqui sem nenhuma
# alteracao de implementacao: o cadastro de municipios precisa ser lido tambem
# por validar.py, gerar_readme.py, gerar_relatorio.py e gerar_email.py, e
# reescrever uma normalizacao conferida nos 78 nomes so criaria risco. Em
# coletar.py os nomes antigos continuam existindo como delegacao.


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, espacos colapsados. Para comparar nomes."""
    return re.sub(r"\s+", " ", _sem_acento(texto or "").lower()).strip()


def slug(texto: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(texto))
    return base.strip("-")


def chave_nome(texto: str) -> str:
    """Normaliza E colapsa pontuacao: 'S. Mateus', 'S.Mateus' e 'S Mateus' viram
    a mesma chave. normalizar() sozinho nao faz isso, e sem este colapso um alias
    abreviado casaria apenas com a grafia exata que alguem digitou no cadastro.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalizar(texto))).strip()


def _padrao_de_chave(texto: str):
    """Compila a chave canonica em padrao tolerante a pontuacao: 'cim-polinorte',
    'cim/polinorte', 'cim.polinorte' e 'cim polinorte' casam o mesmo padrao
    (medido com as quatro formas). O texto de trabalho fica em normalizar(), e
    nao em chave_nome(), porque boilerplate, MARCA_DEPOIS e PADROES_MENCAO
    dependem da pontuacao que chave_nome() apagaria.

    O separador exclui \\x00 DE PROPOSITO. Com [^a-z0-9]+ a mascara do
    casamento em texto livre passaria a valer como separador e um nome ja
    consumido viraria ponte entre dois tokens distantes: medido em
    'secretaria de vila, conceicao do castelo, pavao e outros', depois de
    mascarar 'conceicao do castelo', o padrao de 'Vila Pavao' CASA com
    [^a-z0-9]+ e NAO casa com [^a-z0-9\\x00]+. E a mesma razao pela qual a
    mascara e \\x00 e nao espaco, vista do lado do padrao.
    """
    toks = [re.escape(t) for t in chave_nome(texto).split()]
    return re.compile(r"\b" + r"[^a-z0-9\x00]+".join(toks) + r"\b")


def hoje() -> _dt.date:
    """Data de referencia. Respeita DATA_REFERENCIA para execucoes reproduziveis."""
    valor = os.environ.get("DATA_REFERENCIA")
    if valor:
        return _dt.date.fromisoformat(valor)
    return _dt.date.today()


def carregar_registros():
    """Le todos os registros de dados/ e devolve lista de (caminho_relativo, dict).

    Levanta ValueError com o caminho do arquivo quando o JSON e invalido, para
    que o erro seja acionavel.
    """
    registros = []
    for subdir in DIRETORIOS:
        caminho_dir = os.path.join(DIR_DADOS, subdir)
        if not os.path.isdir(caminho_dir):
            continue
        for nome in sorted(os.listdir(caminho_dir)):
            if not nome.endswith(".json"):
                continue
            caminho = os.path.join(caminho_dir, nome)
            with open(caminho, encoding="utf-8") as fh:
                try:
                    dados = json.load(fh)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "JSON invalido em %s: %s" % (os.path.join(subdir, nome), exc)
                    ) from exc
            registros.append((os.path.join(subdir, nome), dados))
    return registros


# --------------------------------------------- cadastro de municipios do ES

# O indice e um namedtuple, e nao um dict, por causa do lru_cache: um dict
# memoizado e devolvido POR REFERENCIA, e um chamador que escrevesse nele
# corromperia o indice de todos os outros pelo resto do processo. namedtuple e
# imutavel, stdlib e 3.9-compativel. Acesso e SEMPRE por atributo
# (indice.por_slug), nunca por chave (indice["por_slug"]).
IndiceMunicipios = collections.namedtuple(
    "IndiceMunicipios",
    "por_slug por_chave_nome padroes_ordenados padroes_orgaos orgaos_por_id "
    "total_esperado max_tokens_nome",
)


def carregar_municipios():
    """Dict completo do cadastro de fontes/municipios-es.json.

    Levanta ValueError com o caminho quando o JSON e invalido, no mesmo estilo
    de carregar_registros(), para que o erro seja acionavel.
    """
    with open(CAMINHO_MUNICIPIOS, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "JSON invalido em %s: %s" % (CAMINHO_MUNICIPIOS, exc)
            ) from exc


@functools.lru_cache(maxsize=1)
def indice_municipios() -> IndiceMunicipios:
    """IndiceMunicipios memoizado. A memoizacao nao e otimizacao prematura:
    valida_escopo() chama resolver_municipio() uma vez por registro (53 hoje) e
    o coletor chama por pagina (ate 1000), e sem cache cada chamada releria e
    reindexaria o arquivo inteiro.

    Quem trocar o cadastro em teste chama indice_municipios.cache_clear().
    """
    cadastro = carregar_municipios()
    municipios = cadastro.get("municipios") or []
    orgaos = cadastro.get("orgaos_vinculados") or []

    por_slug = {}
    por_chave_nome = {}
    padroes = []
    for entrada in municipios:
        s = entrada.get("slug")
        por_slug[s] = entrada
        por_chave_nome.setdefault(chave_nome(entrada.get("nome")), s)
        padroes.append((chave_nome(entrada.get("nome")), s, "nome"))
        for alias in entrada.get("aliases") or []:
            por_chave_nome.setdefault(chave_nome(alias), s)
            padroes.append((chave_nome(alias), s, "alias"))

    orgaos_por_id = {}
    padroes_org = []
    for orgao in orgaos:
        orgaos_por_id[orgao.get("id")] = orgao
        slugs = orgao.get("municipios_slugs") or []
        # Nome de orgao entra em por_chave_nome somente quando resolve para
        # EXATAMENTE 1 municipio: o validador usa a origem para avisar, em vez
        # de tratar 'Camara Municipal de Aracruz' como se fosse o municipio.
        # Nunca sobrescreve chave de municipio (o setdefault acima ja venceu).
        if len(slugs) == 1:
            por_chave_nome.setdefault(chave_nome(orgao.get("nome")), slugs[0])
        padroes_org.append((chave_nome(orgao.get("nome")), orgao.get("id"), "nome"))
        sigla = orgao.get("sigla")
        # Sigla com menos de 3 caracteres casaria com qualquer sopa de letras
        # do diario.
        if sigla and len(chave_nome(sigla)) >= 3:
            padroes_org.append((chave_nome(sigla), orgao.get("id"), "sigla"))

    # Ordenacao por comprimento decrescente da chave: e ela que faz
    # "conceicao do castelo" ser testada antes de "castelo" e consumir o
    # trecho. O segundo termo da chave de ordenacao so existe para a ordem ser
    # determinista entre chaves de mesmo comprimento.
    def _ordenado(itens):
        return [
            (_padrao_de_chave(chave), alvo, origem)
            for chave, alvo, origem in sorted(itens, key=lambda x: (-len(x[0]), x[0]))
        ]

    return IndiceMunicipios(
        por_slug=por_slug,
        por_chave_nome=por_chave_nome,
        padroes_ordenados=_ordenado(padroes),
        padroes_orgaos=_ordenado(padroes_org),
        orgaos_por_id=orgaos_por_id,
        # total_esperado vem do arquivo: o literal 78 no codigo deixaria o
        # repositorio reprovado no dia em que um 79o municipio fosse criado.
        total_esperado=cadastro.get("total_esperado"),
        # Calculado, nao literal: e o teto da busca por prefixo, e hoje vale 8
        # ('servico autonomo de agua e esgoto de aracruz'). Com o literal 4 (o
        # maior nome de municipio) as chaves de orgao de 5 a 8 tokens nunca
        # seriam alcancadas.
        max_tokens_nome=max(len(k.split()) for k in por_chave_nome),
    )


def resolver_municipio(texto, indice=None):
    """Consulta EXATA por chave_nome(), para texto CURTO e ja curado: o campo
    'municipio' de um registro de dados/. Devolve (slug, origem) com origem em
    {'nome', 'alias', 'orgao_vinculado'}, ou (None, None).

    'orgao_vinculado' e o caso em que a chave casada e o nome de um orgao
    vinculado que resolve para exatamente 1 slug (esses nomes estao em
    por_chave_nome): o validador usa a origem para avisar, em vez de tratar
    'Camara Municipal de Aracruz' como se fosse o municipio Aracruz.

    Sao duas funcoes de resolucao, e nao uma, porque os textos de entrada sao
    de naturezas diferentes: aqui o texto e um nome ja curado, e qualquer coisa
    alem dele e ruido; em resolver_municipio_em_texto() o texto e livre.
    """
    indice = indice or indice_municipios()
    chave = chave_nome(texto)
    s = indice.por_chave_nome.get(chave)
    if s is None:
        return (None, None)
    entrada = indice.por_slug.get(s) or {}
    if chave == chave_nome(entrada.get("nome")):
        return (s, "nome")
    if any(chave == chave_nome(a) for a in entrada.get("aliases") or []):
        return (s, "alias")
    return (s, "orgao_vinculado")


def resolver_municipio_em_texto(texto, indice=None):
    """Passada longest-first sobre TEXTO LIVRE (titulo, nome de orgao, conteudo
    de pagina). Devolve (slug, origem) quando o texto resolve para UM unico
    municipio; (None, None) quando resolve zero OU mais de um.

    Ambiguidade nunca e desempatada por palpite: 'Prefeitura de Serra e de Vila
    Velha' devolve (None, None), nao a primeira ocorrencia. Esta e a funcao que
    a normalizacao de achado usa para 'oportunidade' — a consulta exata
    devolveria None em praticamente todos, porque ali o texto e 'Prefeitura de
    Anchieta', 'ARIES', 'SEDU'.
    """
    indice = indice or indice_municipios()
    trabalho = normalizar(texto)
    achados = {}
    for padrao, s, origem in indice.padroes_ordenados:
        if padrao.search(trabalho):
            achados.setdefault(s, origem)
            # Mascara com "\x00", e nao com espaco: o \x00 preserva os offsets
            # mas nao casa com \s nem com \b, de modo que um nome consumido nao
            # vira ponte entre dois tokens distantes nem empresta sua marca de
            # contexto ao municipio seguinte.
            trabalho = padrao.sub(lambda m: "\x00" * len(m.group(0)), trabalho)
    if len(achados) != 1:
        return (None, None)
    s = next(iter(achados))
    return (s, achados[s])


def data_ou_none(valor):
    """Converte string ISO em date. Devolve None para None/vazio/'nao informado'."""
    if not valor or valor == AUSENTE:
        return None
    try:
        return _dt.date.fromisoformat(valor)
    except (ValueError, TypeError):
        return None


def esta_aberto(registro, referencia=None) -> bool:
    """True se as inscricoes estao em curso na data de referencia."""
    if registro.get("status") not in {"inscricoes_abertas", "edital_publicado"}:
        return False
    referencia = referencia or hoje()
    fim = data_ou_none(registro.get("inscricoes", {}).get("fim"))
    if fim is None:
        # Sem prazo conhecido, confia no status declarado.
        return registro.get("status") == "inscricoes_abertas"
    return fim >= referencia


def dias_para_encerrar(registro, referencia=None):
    """Dias restantes de inscricao, ou None se nao houver prazo conhecido."""
    fim = data_ou_none(registro.get("inscricoes", {}).get("fim"))
    if fim is None:
        return None
    return (fim - (referencia or hoje())).days


def br_data(valor) -> str:
    """Formata data ISO como DD/MM/AAAA. Devolve 'nao informado' se ausente."""
    data = data_ou_none(valor)
    return data.strftime("%d/%m/%Y") if data else AUSENTE


def br_moeda(valor) -> str:
    """Formata numero como R$ 1.234,56. Devolve 'nao informado' se ausente."""
    if valor is None:
        return AUSENTE
    texto = "{:,.2f}".format(float(valor))
    return "R$ " + texto.replace(",", "@").replace(".", ",").replace("@", ".")


def faixa_remuneracao(registro) -> str:
    """Resume a remuneracao de um registro em uma celula de tabela."""
    rem = registro.get("remuneracao") or {}
    minimo, maximo = rem.get("minima"), rem.get("maxima")
    if minimo is None and maximo is None:
        return AUSENTE
    if minimo is not None and maximo is not None:
        if abs(float(minimo) - float(maximo)) < 0.01:
            return br_moeda(minimo)
        return "%s a %s" % (br_moeda(minimo), br_moeda(maximo))
    return ("até " + br_moeda(maximo)) if maximo is not None else ("a partir de " + br_moeda(minimo))


def resumo_vagas(registro) -> str:
    """Resume o quadro de vagas: imediatas e/ou cadastro de reserva."""
    total = registro.get("vagas_imediatas_total")
    cr = registro.get("cadastro_reserva")
    if total is None:
        return "CR" if cr else AUSENTE
    if total == 0:
        return "CR" if cr else "0"
    return ("%d + CR" % total) if cr else str(total)


def rotulo_cargos(registro, limite: int = 2) -> str:
    """Nomes dos cargos, truncados para caber em uma celula de tabela."""
    nomes = [
        c.get("nome", AUSENTE)
        for c in registro.get("cargos", [])
        if c.get("nome") and c.get("nome") != AUSENTE
    ]
    if not nomes:
        return AUSENTE
    nomes = [n if len(n) <= 70 else n[:67].rstrip() + "..." for n in nomes]
    if len(nomes) <= limite:
        return "; ".join(nomes)
    restantes = len(nomes) - limite
    return "%s e mais %d cargo%s" % (
        "; ".join(nomes[:limite]),
        restantes,
        "" if restantes == 1 else "s",
    )


def dias_para_prova(registro, referencia=None):
    """Dias restantes para a prova objetiva, ou None se nao houver data."""
    prova = data_ou_none((registro.get("prova") or {}).get("objetiva"))
    if prova is None:
        return None
    return (prova - (referencia or hoje())).days


def link_principal(registro) -> str:
    """Melhor URL disponivel: edital, senao pagina oficial, senao banca."""
    links = registro.get("links") or {}
    for chave in ("edital", "pagina_oficial", "banca"):
        valor = links.get(chave)
        if valor and valor != AUSENTE and valor.startswith("http"):
            return valor
    for fonte in registro.get("fontes") or []:
        url = fonte.get("url")
        if url and url.startswith("http"):
            return url
    return ""


def md_link(texto: str, url: str) -> str:
    """Monta link Markdown, ou apenas o texto se nao houver URL."""
    return "[%s](%s)" % (texto, url) if url else texto


def escapar_celula(texto: str) -> str:
    """Neutraliza caracteres que quebrariam uma celula de tabela Markdown."""
    return str(texto).replace("|", "\\|").replace("\n", " ").strip()
