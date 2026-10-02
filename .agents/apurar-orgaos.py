"""Script de uso unico: apuracao documental dos orgaos vinculados (2026-10-02).

Preenche o que o passe anterior deixou declarado como pendencia em
fontes/municipios-es.json:

  - composicao de CIM Polinorte, CIM Caparao e ARIES (municipios_slugs), que
    estava [] com 'municipios_slugs:nao_encontrado';
  - url dos orgaos que estavam null com 'url:nao_encontrado';
  - o campo 'evidencia', novo no esquema do orgao, em TODAS as 8 entradas;
  - duas correcoes de nome contra a fonte oficial do proprio orgao.

Os nomes de municipio sao resolvidos contra o cadastro em vez de transcritos
como slug a mao: 13 + 13 + 18 = 44 transcricoes manuais seriam 44 chances de
digitar um slug que o validador so reprovaria depois. Se um nome nao resolver,
o script ABORTA em vez de gravar parcialmente.

Uso:
    python3 .agents/apurar-orgaos.py
"""

from __future__ import annotations

import json
import os
import sys
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CADASTRO = os.path.join(RAIZ, "fontes", "municipios-es.json")
HOJE = "2026-10-02"

# Fonte: pagina institucional do proprio consorcio, conferida em 2026-10-02.
POLINORTE = [
    "Aracruz", "Fundão", "Ibiraçu", "João Neiva", "Linhares", "Rio Bananal",
    "Santa Leopoldina", "Santa Teresa", "São Roque do Canaã", "Sooretama",
    "Viana", "Alegre", "Cariacica",
]
# Fonte: pagina de consorcios publicos da AMUNES, conferida em 2026-10-02.
CAPARAO = [
    "Alegre", "Apiacá", "Bom Jesus do Norte", "Divino de São Lourenço",
    "Dores do Rio Preto", "Guaçuí", "Ibatiba", "Ibitirama", "Irupi", "Iúna",
    "Jerônimo Monteiro", "Muniz Freire", "São José do Calçado",
]
# Fonte: pagina "Municipios Consorciados" do proprio site da ARIES, 2026-10-02.
ARIES = [
    "Alegre", "Alfredo Chaves", "Baixo Guandu", "Governador Lindenberg",
    "Ibiraçu", "Iconha", "Itaguaçu", "Itapemirim", "Itarana", "Jaguaré",
    "Jerônimo Monteiro", "João Neiva", "Linhares", "Mimoso do Sul",
    "Presidente Kennedy", "Rio Bananal", "Santa Leopoldina", "Vargem Alta",
]

EV_POLINORTE = (
    "composicao de 13 municipios lida na pagina institucional do proprio consorcio em "
    "2026-10-02 (https://www.cimpolinorte.es.gov.br/pagina/3/consorciados, HTTP 200), "
    "e conferida de forma independente contra a pagina de consorcios publicos da AMUNES "
    "(https://www.amunes.org.br/pagina/14/consorcios), que lista os MESMOS 13 para "
    "'CONSORCIO PUBLICO DA REGIAO POLINORTE - CIM POLINORTE', sede Ibiracu; url do "
    "consorcio respondeu HTTP 200 na sondagem do mesmo dia"
)
EV_CAPARAO = (
    "composicao de 13 municipios lida na pagina de consorcios publicos da AMUNES em "
    "2026-10-02 (https://www.amunes.org.br/pagina/14/consorcios), verbete 'CONSORCIO "
    "PUBLICO DO CAPARAO - CIM CAPARAO', sede Divino de Sao Lourenco; a identidade com o "
    "nome formal do registro ps-consorcio-caparao-es-2026 ('Consorcio Publico "
    "Intermunicipal de Desenvolvimento Sustentavel do Territorio do Caparao Capixaba') "
    "foi confirmada pela coincidencia de sede e endereco (Polo de Educacao Ambiental do "
    "Caparao, Patrimonio da Penha, Divino de Sao Lourenco) com a imprensa especializada "
    "que cobriu o certame; url https://consorciocaparao.es.gov.br/ respondeu HTTP 403 "
    "em 2026-10-02 (host existe e serve o portal, mas bloqueia robo), por isso "
    "'url:conferir_manual' segue declarada"
)
EV_ARIES = (
    "composicao de 18 municipios lida na pagina 'Municipios Consorciados' do proprio "
    "site da agencia em 2026-10-02 "
    "(https://aries.agr.br/municipios/municipios-consorciados, HTTP 200); a lista NAO "
    "foi copiada da do CISABES, que e entidade distinta e tem composicao diferente na "
    "mesma pagina da AMUNES; https://aries.agr.br/ respondeu HTTP 200 no mesmo dia"
)
EV_CAMARA_ARACRUZ = (
    "url catalogada como fonte 'camara-aracruz' em fontes/fontes.json e re-sondada em "
    "2026-10-02: https://www.aracruz.es.leg.br/transparencia/concurso-publico respondeu "
    "HTTP 200; jurisdicao de camara municipal e o proprio municipio, por definicao da "
    "natureza"
)
EV_CAMARA_CACHOEIRO = (
    "dominio institucional do legislativo localizado em 2026-10-02: "
    "https://www.cachoeirodeitapemirim.es.leg.br/ respondeu HTTP 200 e titula 'CAMARA "
    "MUNICIPAL DE CACHOEIRO DE ITAPEMIRIM', seguindo o mesmo padrao .es.leg.br da "
    "camara de Aracruz; NAO ha pagina dedicada de concurso: "
    "/transparencia/concurso-publico, /transparencia/concursos-publicos e "
    "/transparencia/concurso responderam 404, e /transparencia respondeu 200 — por isso "
    "a url registrada e a raiz institucional e nao uma secao de concursos inventada"
)
EV_SAAE = (
    "autarquia tem portal proprio, localizado em 2026-10-02: "
    "https://www.saaeara.es.gov.br/ respondeu HTTP 200 e a pagina de concursos "
    "https://www.saaeara.es.gov.br/institucional/recursos-humanos/concursos-publicos "
    "tambem respondeu HTTP 200 trazendo o Edital 001/2024 de concurso publico do "
    "proprio SAAE; registrada a pagina de concursos porque o eixo do cadastro e o canal "
    "de publicacao de informacao de emprego"
)
EV_CODEG = (
    "portal proprio localizado em 2026-10-02 sob o dominio da prefeitura: "
    "https://codeg.guarapari.es.gov.br/ respondeu HTTP 403 (bloqueio de robo, nao "
    "ausencia) e paginas internas do mesmo host estao indexadas publicamente "
    "(/transparencia/licitacao/, /pagina/ler/1145/sobre-o-codeg), o que atesta o host "
    "como portal da empresa; a mesma leitura corrigiu o NOME: o orgao se identifica "
    "como 'Companhia de Melhoramentos e Desenvolvimento Urbano de Guarapari', e nao "
    "'Companhia de Desenvolvimento de Guarapari'. Isso atende a pendencia escrita no "
    "proprio registro concurso-codeg-guarapari-es-2026 ('localizar a pagina oficial da "
    "CODEG'). 'url:conferir_manual' segue declarada por causa do 403"
)
EV_IPC = (
    "o instituto NAO tem dominio proprio: ipc.cariacica.es.gov.br nao resolve em DNS "
    "(2026-10-02), e a pagina institucional dele vive sob o portal da prefeitura, em "
    "https://www.cariacica.es.gov.br/pagina/ler/346/quem-somos-ipc, cuja existencia "
    "esta atestada por indexacao publica; www.cariacica.es.gov.br respondeu HTTP 403 na "
    "sondagem do mesmo dia, entao 'url:conferir_manual' segue declarada. O NOME foi "
    "alinhado ao que a propria prefeitura publica e ao que o registro "
    "ps-cariacica-es-ipc-previdenciario-2026 ja usava: 'Instituto de Previdencia dos "
    "Servidores Publicos do Municipio de Cariacica'"
)


def chave(texto):
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.lower().split())


def main():
    with open(CADASTRO, encoding="utf-8") as fh:
        cadastro = json.load(fh)

    por_nome = {chave(m["nome"]): m["slug"] for m in cadastro["municipios"]}

    def slugs(nomes, rotulo):
        saida, faltando = [], []
        for nome in nomes:
            slug = por_nome.get(chave(nome))
            if slug is None:
                faltando.append(nome)
            else:
                saida.append(slug)
        if faltando:
            sys.exit("ABORTADO: %s nao resolveu: %r" % (rotulo, faltando))
        if len(set(saida)) != len(saida):
            sys.exit("ABORTADO: %s tem slug repetido" % rotulo)
        return sorted(saida)

    novos = {
        "cim-polinorte": {
            "municipios_slugs": slugs(POLINORTE, "CIM Polinorte"),
            "url": "https://www.cimpolinorte.es.gov.br/",
            "evidencia": EV_POLINORTE,
            "pendencias_verificacao": [],
        },
        "consorcio-caparao": {
            "municipios_slugs": slugs(CAPARAO, "CIM Caparao"),
            "url": "https://consorciocaparao.es.gov.br/",
            "evidencia": EV_CAPARAO,
            "pendencias_verificacao": ["url:conferir_manual"],
        },
        "aries": {
            "municipios_slugs": slugs(ARIES, "ARIES"),
            "url": "https://aries.agr.br/",
            "evidencia": EV_ARIES,
            "pendencias_verificacao": [],
        },
        "camara-aracruz": {"evidencia": EV_CAMARA_ARACRUZ},
        "camara-cachoeiro-itapemirim": {
            "url": "https://www.cachoeirodeitapemirim.es.leg.br/",
            "evidencia": EV_CAMARA_CACHOEIRO,
            "pendencias_verificacao": [],
        },
        "saae-aracruz": {
            "url": "https://www.saaeara.es.gov.br/institucional/recursos-humanos/concursos-publicos",
            "evidencia": EV_SAAE,
            "pendencias_verificacao": [],
        },
        "codeg-guarapari": {
            "nome": "Companhia de Melhoramentos e Desenvolvimento Urbano de Guarapari",
            "url": "https://codeg.guarapari.es.gov.br/",
            "evidencia": EV_CODEG,
            "pendencias_verificacao": ["url:conferir_manual"],
        },
        "ipc-cariacica": {
            "nome": "Instituto de Previdencia dos Servidores Publicos do Municipio de Cariacica",
            "url": "https://www.cariacica.es.gov.br/pagina/ler/346/quem-somos-ipc",
            "evidencia": EV_IPC,
            "pendencias_verificacao": ["url:conferir_manual"],
        },
    }

    vistos = set()
    for orgao in cadastro["orgaos_vinculados"]:
        mudanca = novos.get(orgao["id"])
        if mudanca is None:
            sys.exit("ABORTADO: orgao sem apuracao prevista: %s" % orgao["id"])
        vistos.add(orgao["id"])
        orgao.update(mudanca)
        orgao["verificado_em"] = HOJE
        # Reordena para a ordem do esquema, com 'evidencia' logo depois de
        # 'fontes' e antes das pendencias, como no canal.
        ordem = [
            "id", "nome", "sigla", "natureza", "esfera", "municipios_slugs",
            "url", "fontes", "evidencia", "pendencias_verificacao", "verificado_em",
        ]
        reordenado = {k: orgao[k] for k in ordem}
        orgao.clear()
        orgao.update(reordenado)

    faltando = set(novos) - vistos
    if faltando:
        sys.exit("ABORTADO: apuracao prevista para orgao inexistente: %r" % sorted(faltando))

    cadastro["ultima_atualizacao"] = HOJE
    with open(CADASTRO, "w", encoding="utf-8") as fh:
        json.dump(cadastro, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for orgao in cadastro["orgaos_vinculados"]:
        print("%-30s %2d municipios  url=%s" % (
            orgao["id"], len(orgao["municipios_slugs"]), orgao["url"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
