"""Funcoes compartilhadas pelas ferramentas de monitoramento.

Carrega os registros de oportunidades do diretorio dados/ e expoe utilitarios
de formatacao usados pelo validador, pelo gerador de README e pelo gerador de
e-mail. Sem dependencias externas: apenas biblioteca padrao do Python 3.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_DADOS = os.path.join(RAIZ, "dados")

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
