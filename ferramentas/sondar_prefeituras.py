"""Sondagem de uso unico dos candidatos de canal de portal/secao dos municipios.

Este script NAO e chamado pelo workflow e NAO escreve no cadastro. Ele existe
para a curadoria: 78 requisicoes nao cabem no cron diario (o orcamento de rede
do caminho agendado e a coleta), e escrita automatica em fontes/ violaria a
decisao de manter o commit do bot longe do cadastro. A saida e TSV para o
curador transcrever para fontes/municipios-es.json.

Candidato de cada municipio, em uma linha:
  1. derivado  -> https://www.<slug sem hifens>.es.gov.br/  (a formula que o
     estado usa de fato; e palpite de candidato, nunca previsao: Cachoeiro de
     Itapemirim usa www.cachoeiro.es.gov.br e nao www.cachoeirodeitapemirim...);
  2. catalogado -> quando existe fonte em fontes/fontes.json com
     tipo 'oficial', esfera 'municipal', id comecando com 'prefeitura-' e host
     institucional do municipio (host comecando com 'www.'), essa URL substitui
     o derivado. Hoje da 6: Vitoria, Anchieta, Santa Maria de Jetiba, Aracruz,
     Cachoeiro e Vila Velha. Host com outro subdominio (educacao.castelo...)
     NAO e portal institucional e nao substitui o derivado.

O tipo do canal vem da forma da URL, e o caminho nunca e descartado: URL de
raiz vira 'portal_prefeitura'; URL com caminho vira 'secao_concursos' com o
caminho preservado (e a secao de editais que a curadoria quer abrir).

Classificacao do resultado (a tabela de aceitacao do design):
  2xx / 3xx                 -> canal 'confirmado', verificado_em = hoje
  403 / 406 / 429           -> canal REGISTRADO 'pendente' + canais:conferir_manual
                               (o host existe e responde; bloqueio de robo nao
                               e ausencia)
  404 / NXDOMAIN / timeout  -> candidato DERIVADO nao entra como canal;
  / erro TLS                   candidato CATALOGADO entra 'pendente'
                               + canais:nao_responde
Qualquer outro status HTTP (5xx, por exemplo) e inconclusivo e nao e ausencia:
o host respondeu, entao o canal entra 'pendente' + canais:conferir_manual.

DUAS tentativas antes de concluir falha de rede: foi medido um timeout
transitorio que depois respondeu em 1,0 s, e timeout isolado e ruido, nao fato.
So https://, sem seguir redirecionamento, timeout de 12 s por tentativa.

Uso:
    python3 ferramentas/sondar_prefeituras.py
"""

from __future__ import annotations

import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import coletar  # noqa: E402
import comum  # noqa: E402

TIMEOUT_SONDAGEM = 12
TENTATIVAS = 2
PAUSA_ENTRE_TENTATIVAS = 2

STATUS_BLOQUEIO = {403, 406, 429}


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Impede o urllib de seguir 3xx.

    Seguir o redirecionamento responderia a pergunta errada: o que a curadoria
    precisa saber e se AQUELE endereco responde, nao onde ele termina. Com
    redirect_request devolvendo None, o 301/302 chega como HTTPError e e
    classificado como resposta (confirmado), que e o que a tabela manda.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def candidatos(cadastro=None, catalogo=None):
    """Lista de (slug, tipo_canal, url, origem) com UM candidato por municipio."""
    cadastro = cadastro or comum.carregar_municipios()
    catalogo = catalogo if catalogo is not None else coletar.carregar_catalogo_fontes()
    catalogadas = _urls_catalogadas(catalogo)

    lista = []
    for entrada in cadastro.get("municipios") or []:
        slug = entrada.get("slug")
        url = catalogadas.get(slug)
        origem = "catalogo" if url else "derivacao"
        if not url:
            url = "https://www.%s.es.gov.br/" % slug.replace("-", "")
        lista.append((slug, _tipo_de_canal(url), url, origem))
    return lista


def _urls_catalogadas(catalogo):
    """{slug: url} das fontes de portal institucional de prefeitura.

    O criterio e o do design: tipo 'oficial', esfera 'municipal', id com
    prefixo 'prefeitura-' e host institucional (comeca com 'www.'). O slug sai
    do nome da fonte resolvido contra o cadastro, e nao do id, porque o id e
    abreviado ('prefeitura-cachoeiro', 'prefeitura-santa-maria-jetiba') e so o
    nome traz a grafia que o cadastro conhece.
    """
    urls = {}
    for fonte in catalogo.values():
        if fonte.get("tipo") != "oficial" or fonte.get("esfera") != "municipal":
            continue
        if not str(fonte.get("id") or "").startswith("prefeitura-"):
            continue
        url = fonte.get("url") or ""
        partes = urllib.parse.urlsplit(url)
        if partes.scheme != "https" or not partes.netloc.startswith("www."):
            continue
        slug, _origem = comum.resolver_municipio_em_texto(fonte.get("nome"))
        if slug:
            urls[slug] = url
    return urls


def _tipo_de_canal(url):
    """URL de raiz e portal institucional; URL com caminho e secao de concursos."""
    caminho = urllib.parse.urlsplit(url).path
    return "portal_prefeitura" if caminho in ("", "/") else "secao_concursos"


def sondar(url, tentativas=TENTATIVAS):
    """Sonda a URL e devolve (status, rotulo).

    status e o codigo HTTP quando o host respondeu, e None quando nao houve
    resposta nenhuma. O rotulo e o texto que vai para a coluna de status do TSV
    e para a evidencia do canal.
    """
    abridor = urllib.request.build_opener(_SemRedirecionamento)
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": coletar.NAVEGADOR, "Accept": "*/*"}
    )
    rotulo = "erro"
    for tentativa in range(1, tentativas + 1):
        try:
            with abridor.open(requisicao, timeout=TIMEOUT_SONDAGEM) as resposta:
                return resposta.getcode(), str(resposta.getcode())
        except urllib.error.HTTPError as exc:
            # 3xx tambem chega aqui, porque o redirecionamento nao e seguido.
            return exc.code, str(exc.code)
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            rotulo = _rotulo_de_falha(exc)
            if tentativa < tentativas:
                time.sleep(PAUSA_ENTRE_TENTATIVAS)
    return None, "%s (%d tentativas)" % (rotulo, tentativas)


def _rotulo_de_falha(exc):
    """Classifica a falha de rede em nxdomain / timeout / tls / erro."""
    razao = getattr(exc, "reason", exc)
    texto = comum.normalizar(str(razao))
    if isinstance(razao, socket.timeout) or "timed out" in texto:
        return "timeout"
    if "name or service not known" in texto or "nodename nor servname" in texto:
        return "nxdomain"
    if "certificate" in texto or "ssl" in texto or "tls" in texto:
        return "tls"
    return "erro"


def classificar(status, origem):
    """(estado, pendencia) do canal, pela tabela de aceitacao do design.

    estado 'nao_entra' e o unico caso em que nada e gravado: candidato derivado
    que nao respondeu e palpite nao confirmado, e palpite nao vira dado. URL
    catalogada que nao responde e dado de procedencia conhecida, e apaga-la
    perderia informacao real.
    """
    if status is not None and 200 <= status < 400:
        return "confirmado", "-"
    if status in STATUS_BLOQUEIO:
        return "pendente", "canais:conferir_manual"
    if status is not None:
        return "pendente", "canais:conferir_manual"
    if origem == "catalogo":
        return "pendente", "canais:nao_responde"
    return "nao_entra", "-"


def main():
    for slug, tipo, url, origem in candidatos():
        status, rotulo = sondar(url)
        estado, pendencia = classificar(status, origem)
        print("\t".join([slug, tipo, rotulo, url, estado, pendencia]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
