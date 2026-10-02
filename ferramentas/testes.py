"""Suite de testes das ferramentas de monitoramento.

unittest da biblioteca padrao, sem rede e sem dependencia externa, executavel
por:

    python3 ferramentas/testes.py

Nenhum caso aqui pode depender de rede: o workflow roda esta suite no job de
validacao, e teste que depende de terceiro nao pode reprovar PR.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import coletar  # noqa: E402
import comum  # noqa: E402
import gerar_email  # noqa: E402
import gerar_readme  # noqa: E402
import validar  # noqa: E402

# Os 78 municipios do ES com o slug ESPERADO, escritos aqui como literal.
# A dupla contabilidade e deliberada: comparar o cadastro consigo mesmo
# (slug == comum.slug(nome) lido do proprio arquivo) e circular e passaria
# ate com a funcao quebrada, porque os dois lados viriam da mesma fonte. A
# lista abaixo foi conferida contra a lista oficial do IBGE (UF 32) e e o
# segundo registro independente dos nomes: divergencia entre ela e o cadastro
# tem de falhar, e e isso que o caso de teste faz.
MUNICIPIOS_ES = [
    ("Afonso Cláudio", "afonso-claudio"),
    ("Água Doce do Norte", "agua-doce-do-norte"),
    ("Águia Branca", "aguia-branca"),
    ("Alegre", "alegre"),
    ("Alfredo Chaves", "alfredo-chaves"),
    ("Alto Rio Novo", "alto-rio-novo"),
    ("Anchieta", "anchieta"),
    ("Apiacá", "apiaca"),
    ("Aracruz", "aracruz"),
    ("Atílio Vivácqua", "atilio-vivacqua"),
    ("Baixo Guandu", "baixo-guandu"),
    ("Barra de São Francisco", "barra-de-sao-francisco"),
    ("Boa Esperança", "boa-esperanca"),
    ("Bom Jesus do Norte", "bom-jesus-do-norte"),
    ("Brejetuba", "brejetuba"),
    ("Cachoeiro de Itapemirim", "cachoeiro-de-itapemirim"),
    ("Cariacica", "cariacica"),
    ("Castelo", "castelo"),
    ("Colatina", "colatina"),
    ("Conceição da Barra", "conceicao-da-barra"),
    ("Conceição do Castelo", "conceicao-do-castelo"),
    ("Divino de São Lourenço", "divino-de-sao-lourenco"),
    ("Domingos Martins", "domingos-martins"),
    ("Dores do Rio Preto", "dores-do-rio-preto"),
    ("Ecoporanga", "ecoporanga"),
    ("Fundão", "fundao"),
    ("Governador Lindenberg", "governador-lindenberg"),
    ("Guaçuí", "guacui"),
    ("Guarapari", "guarapari"),
    ("Ibatiba", "ibatiba"),
    ("Ibiraçu", "ibiracu"),
    ("Ibitirama", "ibitirama"),
    ("Iconha", "iconha"),
    ("Irupi", "irupi"),
    ("Itaguaçu", "itaguacu"),
    ("Itapemirim", "itapemirim"),
    ("Itarana", "itarana"),
    ("Iúna", "iuna"),
    ("Jaguaré", "jaguare"),
    ("Jerônimo Monteiro", "jeronimo-monteiro"),
    ("João Neiva", "joao-neiva"),
    ("Laranja da Terra", "laranja-da-terra"),
    ("Linhares", "linhares"),
    ("Mantenópolis", "mantenopolis"),
    ("Marataízes", "marataizes"),
    ("Marechal Floriano", "marechal-floriano"),
    ("Marilândia", "marilandia"),
    ("Mimoso do Sul", "mimoso-do-sul"),
    ("Montanha", "montanha"),
    ("Mucurici", "mucurici"),
    ("Muniz Freire", "muniz-freire"),
    ("Muqui", "muqui"),
    ("Nova Venécia", "nova-venecia"),
    ("Pancas", "pancas"),
    ("Pedro Canário", "pedro-canario"),
    ("Pinheiros", "pinheiros"),
    ("Piúma", "piuma"),
    ("Ponto Belo", "ponto-belo"),
    ("Presidente Kennedy", "presidente-kennedy"),
    ("Rio Bananal", "rio-bananal"),
    ("Rio Novo do Sul", "rio-novo-do-sul"),
    ("Santa Leopoldina", "santa-leopoldina"),
    ("Santa Maria de Jetibá", "santa-maria-de-jetiba"),
    ("Santa Teresa", "santa-teresa"),
    ("São Domingos do Norte", "sao-domingos-do-norte"),
    ("São Gabriel da Palha", "sao-gabriel-da-palha"),
    ("São José do Calçado", "sao-jose-do-calcado"),
    ("São Mateus", "sao-mateus"),
    ("São Roque do Canaã", "sao-roque-do-canaa"),
    ("Serra", "serra"),
    ("Sooretama", "sooretama"),
    ("Vargem Alta", "vargem-alta"),
    ("Venda Nova do Imigrante", "venda-nova-do-imigrante"),
    ("Viana", "viana"),
    ("Vila Pavão", "vila-pavao"),
    ("Vila Valério", "vila-valerio"),
    ("Vila Velha", "vila-velha"),
    ("Vitória", "vitoria"),
]


class TesteNormalizacaoDeNome(unittest.TestCase):
    """slug(), chave_nome() e _padrao_de_chave(), as tres bases do casamento."""

    def test_slug_dos_78_nomes(self):
        self.assertEqual(len(MUNICIPIOS_ES), 78)
        self.assertEqual(len({s for _n, s in MUNICIPIOS_ES}), 78)
        for nome, esperado in MUNICIPIOS_ES:
            with self.subTest(nome=nome):
                self.assertEqual(comum.slug(nome), esperado)

    def test_cadastro_bate_com_a_lista_literal(self):
        # O cadastro versionado tem de concordar com a segunda contabilidade
        # acima, nome por nome e slug por slug.
        cadastro = comum.carregar_municipios()
        do_arquivo = [(m["nome"], m["slug"]) for m in cadastro["municipios"]]
        self.assertEqual(sorted(do_arquivo), sorted(MUNICIPIOS_ES))

    def test_chave_nome_colapsa_pontuacao(self):
        self.assertEqual(comum.chave_nome("S. Mateus"), "s mateus")
        self.assertEqual(comum.chave_nome("S.Mateus"), "s mateus")
        self.assertEqual(comum.chave_nome("S Mateus"), "s mateus")

    def test_padrao_de_chave_tolera_pontuacao(self):
        padrao = comum._padrao_de_chave("CIM Polinorte")
        for forma in ("cim polinorte", "cim-polinorte", "cim/polinorte", "cim.polinorte"):
            with self.subTest(forma=forma):
                self.assertTrue(padrao.search(comum.normalizar("ato do %s" % forma)))

    def test_padrao_de_chave_nao_atravessa_a_mascara(self):
        # Trava o separador [^a-z0-9\x00]+: com [^a-z0-9]+ o nome ja consumido
        # viraria ponte entre dois tokens distantes e 'Vila Pavao' casaria por
        # cima do trecho mascarado.
        padrao = comum._padrao_de_chave("Vila Pavão")
        self.assertFalse(padrao.search("vila, " + "\x00" * 20 + ", pavao"))
        self.assertTrue(padrao.search("ato do municipio de vila pavao"))


class TesteResolucaoDeMunicipio(unittest.TestCase):
    """As duas resolucoes, que existem porque os textos de entrada diferem."""

    def test_consulta_exata(self):
        self.assertEqual(comum.resolver_municipio("Anchieta"), ("anchieta", "nome"))
        self.assertEqual(comum.resolver_municipio("Prefeitura de Anchieta"), (None, None))
        self.assertEqual(
            comum.resolver_municipio("Camara Municipal de Aracruz"),
            ("aracruz", "orgao_vinculado"),
        )
        self.assertEqual(
            comum.resolver_municipio("Cachoeiro"), ("cachoeiro-de-itapemirim", "alias")
        )
        self.assertEqual(comum.resolver_municipio("Belo Horizonte"), (None, None))

    def test_texto_livre(self):
        self.assertEqual(
            comum.resolver_municipio_em_texto("Prefeitura de Anchieta"),
            ("anchieta", "nome"),
        )
        self.assertEqual(
            comum.resolver_municipio_em_texto("MUNICIPIO DE CACHOEIRO DO ITAPEMIRIM/ES"),
            ("cachoeiro-de-itapemirim", "alias"),
        )
        self.assertEqual(
            comum.resolver_municipio_em_texto("ato sem nome de municipio nenhum"),
            (None, None),
        )

    def test_ambiguidade_nao_e_desempatada_por_palpite(self):
        self.assertEqual(
            comum.resolver_municipio_em_texto("Prefeitura de Serra e de Vila Velha"),
            (None, None),
        )

    def test_longest_first_nao_credita_o_nome_contido(self):
        # Os dois unicos conflitos de subconjunto entre os 78 nomes. Se a
        # mascara nao consumisse o trecho, o texto resolveria para DOIS
        # municipios e as duas asercoes virariam (None, None).
        self.assertEqual(
            comum.resolver_municipio_em_texto("Conceição do Castelo"),
            ("conceicao-do-castelo", "nome"),
        )
        self.assertEqual(
            comum.resolver_municipio_em_texto("Cachoeiro de Itapemirim"),
            ("cachoeiro-de-itapemirim", "nome"),
        )


class TesteIndiceMunicipios(unittest.TestCase):
    """Forma e conteudo do indice memoizado."""

    def test_total_esperado_vem_do_arquivo(self):
        indice = comum.indice_municipios()
        self.assertEqual(indice.total_esperado, 78)
        self.assertEqual(len(indice.por_slug), 78)

    def test_max_tokens_nome_e_calculado(self):
        # 10, de 'instituto de previdencia dos servidores publicos do municipio
        # de cariacica' (era 8, de 'servico autonomo de agua e esgoto de
        # aracruz', antes do nome do IPC ser alinhado ao que a prefeitura
        # publica). Com o literal 4 (o maior nome de municipio) as chaves de
        # orgao de 5 a 10 tokens nunca seriam alcancadas pela poda por prefixo.
        indice = comum.indice_municipios()
        self.assertEqual(indice.max_tokens_nome, 10)

    def test_indice_e_imutavel(self):
        # Trava a regressao para dict memoizado: um dict devolvido pelo
        # lru_cache e compartilhado por referencia, e quem escrevesse nele
        # corromperia o indice de todos os outros chamadores.
        indice = comum.indice_municipios()
        with self.assertRaises(AttributeError):
            indice.por_slug = {}

    def test_orgao_entra_em_por_chave_nome_so_com_um_slug(self):
        indice = comum.indice_municipios()
        self.assertEqual(
            indice.por_chave_nome.get(
                "instituto de previdencia dos servidores publicos do municipio de cariacica"
            ),
            "cariacica",
        )
        # Orgao intermunicipal nao resolve para 1 municipio, logo nao entra.
        # Vale desde que a composicao do Polinorte era [] e continua valendo
        # agora que ela tem os 13 municipios apurados: 13 != 1.
        self.assertIsNone(
            indice.por_chave_nome.get("consorcio publico da regiao polinorte")
        )

    def test_padroes_orgaos_casam_nome_e_sigla(self):
        indice = comum.indice_municipios()
        casados = {
            orgao_id
            for padrao, orgao_id, _origem in indice.padroes_orgaos
            if padrao.search("ato do cim-polinorte e da aries")
        }
        self.assertEqual(casados, {"cim-polinorte", "aries"})
        origens = {
            origem
            for padrao, orgao_id, origem in indice.padroes_orgaos
            if orgao_id == "ipc-cariacica"
        }
        # 'alias' entra desde que o IPC passou a ter a forma encurtada em
        # aliases: as tres origens de padrao de orgao sao nome, alias e sigla.
        self.assertEqual(origens, {"nome", "alias", "sigla"})

    def test_padroes_ordenados_do_mais_longo_para_o_mais_curto(self):
        indice = comum.indice_municipios()
        texto = "secretaria de conceicao do castelo"
        primeiro = next(
            slug
            for padrao, slug, _origem in indice.padroes_ordenados
            if padrao.search(texto)
        )
        self.assertEqual(primeiro, "conceicao-do-castelo")


class TesteCadastroSubstituido(unittest.TestCase):
    """Indice construido sobre OUTRO cadastro, para provar que nada e literal.

    Estes casos trocam o arquivo lido, entao chamam
    comum.indice_municipios.cache_clear() no setUp e no tearDown: sem isso o
    indice memoizado contaminaria o caso seguinte.
    """

    def setUp(self):
        self._caminho_original = comum.CAMINHO_MUNICIPIOS
        self._temporario = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        cadastro = {
            "total_esperado": 2,
            "municipios": [
                {
                    "codigo_ibge": 3205309,
                    "nome": "Vitória",
                    "slug": "vitoria",
                    "aliases": [],
                    "microrregiao": "Vitória",
                    "canais": [],
                    "pendencias_verificacao": ["canais:nao_encontrado"],
                    "verificado_em": "2026-10-01",
                },
                {
                    "codigo_ibge": 3205002,
                    "nome": "Serra",
                    "slug": "serra",
                    "aliases": ["Vila da Serra"],
                    "microrregiao": "Vitória",
                    "canais": [],
                    "pendencias_verificacao": ["canais:nao_encontrado"],
                    "verificado_em": "2026-10-01",
                },
            ],
            "orgaos_vinculados": [],
        }
        json.dump(cadastro, self._temporario, ensure_ascii=False)
        self._temporario.close()
        comum.CAMINHO_MUNICIPIOS = self._temporario.name
        comum.indice_municipios.cache_clear()

    def tearDown(self):
        comum.CAMINHO_MUNICIPIOS = self._caminho_original
        os.unlink(self._temporario.name)
        comum.indice_municipios.cache_clear()

    def test_total_esperado_e_max_tokens_saem_do_arquivo(self):
        indice = comum.indice_municipios()
        self.assertEqual(indice.total_esperado, 2)
        self.assertEqual(sorted(indice.por_slug), ["serra", "vitoria"])
        self.assertEqual(indice.max_tokens_nome, 3)

    def test_alias_do_cadastro_substituido_resolve(self):
        self.assertEqual(comum.resolver_municipio("Vila da Serra"), ("serra", "alias"))
        self.assertEqual(comum.resolver_municipio("Anchieta"), (None, None))

    def test_json_invalido_cita_o_caminho(self):
        with open(comum.CAMINHO_MUNICIPIOS, "w", encoding="utf-8") as fh:
            fh.write("{isto nao e json")
        comum.indice_municipios.cache_clear()
        with self.assertRaises(ValueError) as capturado:
            comum.carregar_municipios()
        self.assertIn(comum.CAMINHO_MUNICIPIOS, str(capturado.exception))


class TesteVocabularios(unittest.TestCase):
    """Os vocabularios fechados que o cadastro e o catalogo usam."""

    def test_esfera_de_fonte_e_mais_larga_que_a_de_registro(self):
        self.assertEqual(
            comum.ESFERAS_FONTE_VALIDAS, comum.ESFERAS_VALIDAS | {"nao_se_aplica"}
        )
        self.assertNotIn("nao_se_aplica", comum.ESFERAS_VALIDAS)

    def test_tipos_de_canal_e_naturezas(self):
        self.assertEqual(len(comum.TIPOS_CANAL), 6)
        self.assertEqual(len(comum.NATUREZAS_ORGAO_VINCULADO), 6)
        self.assertEqual(
            comum.MOTIVOS_PENDENCIA,
            {"conferir_manual", "nao_responde", "nao_encontrado"},
        )


# --------------------------------------------------------------- coletor IOES
#
# Tudo abaixo exercita o coletor de diario oficial SEM REDE. O ponto de parsing
# e isolado de proposito: _achados_de_resposta() recebe um envelope JA
# desserializado e e funcao pura, entao os casos usam envelopes LITERAIS. A
# camada de rede (_ler_bytes/_ler_com_retry) nao e testada unitariamente — ela
# e fina justamente para que isso seja aceitavel.


def _pagina(texto):
    """Passa o texto pelos estagios 2 e 3 do pipeline (normalizar + limpar).

    Os casos escrevem o trecho como ele aparece no diario (caixa alta, com
    acento) e esta funcao aplica a mesma ordem que _achados_de_resposta()
    aplica: nenhum caso pode normalizar de um jeito proprio, senao mediria um
    pipeline que nao existe.
    """
    return coletar._limpar_boilerplate(comum.normalizar(texto))


def _pares_de_municipio(texto, indice=None):
    """(slug, confianca) de cada atribuicao do bloco, na ordem de descoberta."""
    indice = indice or comum.indice_municipios()
    return [
        (a["municipio_slug"], a["municipio_confianca"])
        for a in coletar._atribuicoes_do_bloco(_pagina(texto), indice)
    ]


@contextlib.contextmanager
def _indice_sem(slugs):
    """Indice construido sobre o cadastro real MENOS os municipios indicados.

    Serve a deteccao por injecao: "nao aparece ruido" e indistinguivel de "nao
    aparece nada", entao o caminho positivo da deteccao de municipio nao
    mapeado tem de ser exercitado removendo um municipio que o texto cita.
    """
    cadastro = comum.carregar_municipios()
    cadastro["municipios"] = [
        m for m in cadastro["municipios"] if m["slug"] not in set(slugs)
    ]
    original = comum.CAMINHO_MUNICIPIOS
    temporario = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(cadastro, temporario, ensure_ascii=False)
    temporario.close()
    comum.CAMINHO_MUNICIPIOS = temporario.name
    comum.indice_municipios.cache_clear()
    try:
        yield comum.indice_municipios()
    finally:
        comum.CAMINHO_MUNICIPIOS = original
        os.unlink(temporario.name)
        comum.indice_municipios.cache_clear()


def _item_ioes(ident="11517_315", conteudo="", data="2026-10-01", diario_id=11517,
               pagina=315, highlight=None, suplemento="Edição 3099"):
    """Item de hit no formato medido do buscador do IOES."""
    item = {
        "_id": ident,
        "_score": 1.0,
        "sort": [1790812800000],
        "diario": "DOM - AMUNES",
        "suplemento": suplemento,
        "_source": {
            "conteudo": conteudo,
            "data": data,
            "paginas": 363,
            "pagina": pagina,
            "pdf_id": 1155857,
            "year": "2026",
            "month": "10",
            "day": "01",
            "diario_id": diario_id,
            "tipo_edicao": 13,
        },
    }
    if highlight is not None:
        item["highlight"] = {"conteudo": highlight}
    return item


def _envelope_ioes(itens, total=None):
    # hits.total e int na forma medida (131); a forma dict com 'value' e
    # tolerada pelo coletor e tem caso proprio.
    return {
        "took": 7,
        "timed_out": False,
        "hits": {
            "total": len(itens) if total is None else total,
            "max_score": 1.0,
            "hits": itens,
        },
    }


# Assinatura de ato ESTADUAL nas quatro formas medidas em 144 paginas. Exigir
# dia da semana (ou data por extenso) foi o erro das duas versoes anteriores do
# padrao, e e o que fazia Vitoria liderar a cobertura em confianca alta.
ASSINATURAS_REAIS = (
    "Esta portaria entra em vigor na data de sua publicação. "
    "VITÓRIA (ES), QUINTA-FEIRA, 1 DE OUTUBRO DE 2026.",
    "a contar de 25/09/2026. Vitória-ES, 28/09/2026.",
    "divulgados no site www.selecao.es.gov.br, nota de convocação. "
    "Vitória/ES, 24 de setembro 2026.",
    "Instituto de Previdência - Vitória, ES, CEP: 29.050-000",
)


class TesteLimpezaEsegmentacao(unittest.TestCase):
    """_limpar_boilerplate() e _blocos_de_ato(), os estagios 3 e 5."""

    def test_as_quatro_formas_de_assinatura_somem(self):
        for assinatura in ASSINATURAS_REAIS:
            with self.subTest(assinatura=assinatura[:40]):
                self.assertNotIn("vitoria", _pagina(assinatura))

    def test_cabecalho_do_caderno_sai_e_o_corpo_do_ato_permanece(self):
        bruto = (
            "DOM/ES - Edição Nº3.099 315 quinta-feira, 1 de Outubro de 2026 "
            "DIÁRIO OFICIAL DOS MUNICÍPIOS CAPIXABAS 42 "
            "PREFEITURA MUNICIPAL DE SOORETAMA PORTARIA Nº 310/2026 "
            "NOMEIA CANDIDATO APROVADO EM CONCURSO PÚBLICO. "
            "Esta portaria entra em vigor na data de sua publicação. "
            "VITÓRIA-ES, 25 DE SETEMBRO DE 2026."
        )
        limpa = _pagina(bruto)
        self.assertNotIn("vitoria", limpa)
        self.assertIn("prefeitura municipal de sooretama", limpa)
        self.assertIn("nomeia candidato aprovado em concurso publico", limpa)

    def test_protocolo_sobrevive_a_limpeza(self):
        # 'protocolo \\d+' saiu de PADROES_BOILERPLATE exatamente para poder ser
        # delimitador de bloco: no passe anterior ele estava nos dois papeis ao
        # mesmo tempo, o que se autodestruia.
        limpa = _pagina("DIÁRIO OFICIAL DOS MUNICÍPIOS CAPIXABAS Protocolo 1234567")
        self.assertIn("protocolo 1234567", limpa)

    def test_tres_protocolos_dao_tres_blocos(self):
        corpo = "ato de nomeacao de candidato aprovado em concurso publico %d "
        texto = ((corpo % 1) + "protocolo 11 " + (corpo % 2) + "protocolo 22 "
                 + (corpo % 3))
        self.assertEqual(len(coletar._blocos_de_ato(texto)), 3)

    def test_pagina_sem_delimitador_e_um_bloco_unico(self):
        texto = "ato de nomeacao de candidato aprovado em concurso publico"
        self.assertEqual(coletar._blocos_de_ato(texto), [texto])

    def test_bloco_curto_e_descartado(self):
        longo = "ato de nomeacao de candidato aprovado em concurso publico 1"
        texto = "curto protocolo 11 " + longo
        blocos = coletar._blocos_de_ato(texto)
        self.assertEqual([b.strip() for b in blocos], [longo])


class TesteCasamentoEmBloco(unittest.TestCase):
    """Passada de orgaos + passada de municipios, com a mascara \\x00."""

    def test_marca_nao_vaza_para_o_municipio_seguinte(self):
        # Trava a mascara "\\x00": com espaco, serra sairia em confianca ALTA,
        # porque MARCAS_ANTES termina em \\s*$ e a marca de vila velha
        # atravessaria a mascara.
        self.assertEqual(
            _pares_de_municipio("PREFEITURA DE VILA VELHA SERRA edital de convocacao"),
            [("vila-velha", "alta"), ("serra", "baixa")],
        )

    def test_marca_nao_vaza_entre_jetiba_e_linhares(self):
        self.assertEqual(
            _pares_de_municipio("MUNICIPIO DE SANTA MARIA DE JETIBA LINHARES"),
            [("santa-maria-de-jetiba", "alta"), ("linhares", "baixa")],
        )

    def test_marca_distante_nao_vale(self):
        # Adjacencia, e nao "raio de 80 caracteres": foi essa troca que tirou
        # Vitoria da lideranca da cobertura.
        texto = "prefeitura municipal de " + ("x" * 300) + " serra"
        self.assertEqual(_pares_de_municipio(texto), [("serra", "baixa")])

    def test_sufixo_de_uf_adjacente_vale_como_marca(self):
        self.assertEqual(_pares_de_municipio("nomeacao em serra/es"), [("serra", "alta")])
        self.assertEqual(
            _pares_de_municipio("nomeacao em serra - es"), [("serra", "alta")]
        )

    def test_estado_do_espirito_santo_em_outro_trecho_nao_vale(self):
        texto = "estado do espirito santo torna publico o ato relativo a serra"
        self.assertEqual(_pares_de_municipio(texto), [("serra", "baixa")])

    def test_alias_em_texto_livre_segue_a_regra_de_adjacencia(self):
        indice = comum.indice_municipios()
        com_marca = coletar._atribuicoes_do_bloco(
            _pagina("MUNICIPIO DE CACHOEIRO DO ITAPEMIRIM/ES torna publico"), indice
        )
        self.assertEqual(
            [
                (a["municipio_slug"], a["municipio_confianca"], a["municipio_origem"])
                for a in com_marca
            ],
            [("cachoeiro-de-itapemirim", "alta", "alias")],
        )
        sem_marca = coletar._atribuicoes_do_bloco(
            _pagina("servidores lotados na unidade cachoeiro foram convocados"), indice
        )
        self.assertEqual(
            [
                (a["municipio_slug"], a["municipio_confianca"], a["municipio_origem"])
                for a in sem_marca
            ],
            [("cachoeiro-de-itapemirim", "baixa", "alias")],
        )

    def test_longest_first_nao_credita_o_nome_contido(self):
        self.assertEqual(
            _pares_de_municipio("PREFEITURA DE CONCEIÇÃO DO CASTELO"),
            [("conceicao-do-castelo", "alta")],
        )
        self.assertEqual(
            _pares_de_municipio("MUNICIPIO DE CACHOEIRO DE ITAPEMIRIM"),
            [("cachoeiro-de-itapemirim", "alta")],
        )

    def test_orgao_vinculado_credita_o_municipio_do_orgao(self):
        # As tres formas que o diario usa de fato: o nome oficial, a forma
        # encurtada (que vive em 'aliases' justamente para nao perder recall
        # quando 'nome' foi corrigido para o oficial) e a sigla.
        for texto in (
            "INSTITUTO DE PREVIDÊNCIA DOS SERVIDORES PÚBLICOS DO MUNICÍPIO DE "
            "CARIACICA torna publico",
            "INSTITUTO DE PREVIDÊNCIA DOS SERVIDORES DE CARIACICA torna publico",
            "o presidente do IPC torna publico o resultado",
        ):
            with self.subTest(texto=texto[:30]):
                atribuicoes = coletar._atribuicoes_do_bloco(
                    _pagina(texto), comum.indice_municipios()
                )
                self.assertEqual(len(atribuicoes), 1)
                self.assertEqual(atribuicoes[0]["orgao_vinculado_id"], "ipc-cariacica")
                self.assertEqual(atribuicoes[0]["municipio_slug"], "cariacica")
                self.assertEqual(atribuicoes[0]["municipio_confianca"], "alta")
                self.assertEqual(atribuicoes[0]["municipio_escopo"], "municipal")
                self.assertEqual(atribuicoes[0]["municipio_origem"], "orgao_vinculado")

    def test_orgao_intermunicipal_nao_credita_municipio(self):
        atribuicoes = coletar._atribuicoes_do_bloco(
            _pagina("A ARIES torna publico o processo seletivo"),
            comum.indice_municipios(),
        )
        self.assertEqual(len(atribuicoes), 1)
        self.assertEqual(atribuicoes[0]["orgao_vinculado_id"], "aries")
        self.assertIsNone(atribuicoes[0]["municipio_slug"])
        self.assertEqual(atribuicoes[0]["municipio_escopo"], "intermunicipal")

    def test_orgao_consome_o_nome_do_municipio_dentro_dele(self):
        # "servico autonomo de agua e esgoto de aracruz" e consumido como
        # orgao, e "aracruz" dentro dele nao e contado de novo.
        atribuicoes = coletar._atribuicoes_do_bloco(
            _pagina("Serviço Autônomo de Água e Esgoto de Aracruz PORTARIA 150"),
            comum.indice_municipios(),
        )
        self.assertEqual([a["orgao_vinculado_id"] for a in atribuicoes], ["saae-aracruz"])

    def test_regressao_da_armadilha_vitoria(self):
        # Cabecalho real do caderno + assinatura estadual + ato municipal.
        bruto = (
            "DOM/ES - Edição Nº3.099 42 quinta-feira, 1 de Outubro de 2026 "
            "PREFEITURA MUNICIPAL DE SOORETAMA PORTARIA Nº 310/2026 NOMEIA "
            "CANDIDATO APROVADO EM CONCURSO PÚBLICO. Esta portaria entra em "
            "vigor na data de sua publicação. VITÓRIA/ES, 24 de setembro 2026."
        )
        pares = _pares_de_municipio(bruto)
        self.assertNotIn(("vitoria", "alta"), pares)
        self.assertIn(("sooretama", "alta"), pares)

    def test_bloco_sem_municipio_nao_produz_atribuicao(self):
        # Pagina de continuacao: nunca herdar o municipio do bloco anterior.
        self.assertEqual(
            coletar._atribuicoes_do_bloco(
                _pagina("ficam homologadas as inscricoes relacionadas no anexo i"),
                comum.indice_municipios(),
            ),
            [],
        )


class TestePareamentoDeEdital(unittest.TestCase):
    """Regras de pareamento: 1 achado por (bloco, municipio) e faixa de ano."""

    def test_primeiro_numero_proximo_vence_e_os_demais_sao_citados(self):
        bloco = (
            "prefeitura de serra edital 001/2026 de convocacao, referente aos "
            "editais 002/2026 e 003/2026"
        )
        self.assertEqual(
            coletar._numeros_do_bloco(bloco, 2026), ("1/2026", ["2/2026", "3/2026"])
        )

    def test_ano_fora_da_faixa_e_descartado(self):
        bloco = (
            "edital de concurso publico cnpj 27.165.208/0001-98 nos termos da "
            "lei 17/2007 e do edital 004/2026"
        )
        principal, citados = coletar._numeros_do_bloco(bloco, 2026)
        self.assertEqual(principal, "4/2026")
        self.assertEqual(citados, [])

    def test_bloco_sem_numero_valido_nao_perde_o_achado(self):
        # O filtro de ano descarta o NUMERO, nunca o achado: o bloco cai na
        # chave por pagina e o municipio continua contando para a cobertura.
        conteudo = (
            "PREFEITURA MUNICIPAL DE SERRA edital de concurso público "
            "lei nº 17/2007 nomeia candidato aprovado"
        )
        achados = coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            comum.indice_municipios(),
        )
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["chave"], "ioes-dom:serra:11517-315")
        self.assertEqual(achados[0]["municipio_confianca"], "alta")

    def test_um_achado_por_municipio_no_bloco(self):
        conteudo = (
            "PREFEITURA MUNICIPAL DE SERRA edital 001/2026 nomeia candidatos "
            "lotados na secretaria, conforme o edital 001/2026 e o edital "
            "002/2026 do mesmo certame"
        )
        achados = coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            comum.indice_municipios(),
        )
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0]["chave"], "ioes-dom:serra:edital-1-2026")
        self.assertEqual(achados[0]["editais_citados"], ["2/2026"])


class TesteAchadosDeResposta(unittest.TestCase):
    """Forma do achado, degradacao de envelope malformado e determinismo."""

    def setUp(self):
        self.indice = comum.indice_municipios()

    def test_envelope_malformado_devolve_lista_vazia_sem_excecao(self):
        # Contrato de tratamento de erros: o laco de FONTES captura (URLError, OSError,
        # ValueError, RuntimeError), logo KeyError/TypeError aqui derrubaria a
        # coleta INTEIRA. Por isso todo acesso a campo de terceiro usa .get().
        for envelope in (
            {"hits": {"hits": [{}]}},
            {"hits": {"hits": [{"_id": "11517_315", "_source": None}]}},
            {"hits": {"hits": "texto"}},
            {"hits": "texto"},
            {"hits": None},
            {},
            None,
            "texto",
            [],
            {"hits": {"hits": [{"_id": "sem-formato", "_source": {}}]}},
            {"hits": {"hits": [{"_id": "11517_315", "_source": {"conteudo": 42}}]}},
        ):
            with self.subTest(envelope=repr(envelope)[:40]):
                with contextlib.redirect_stdout(io.StringIO()):
                    achados = coletar._achados_de_resposta(
                        envelope, "dom", "concurso publico", self.indice
                    )
                self.assertEqual(achados, [])

    def test_forma_do_achado(self):
        conteudo = (
            "PREFEITURA MUNICIPAL DE SOORETAMA edital de concurso público nº "
            "001/2026 nomeia candidato aprovado"
        )
        item = _item_ioes(
            conteudo=conteudo,
            highlight=["nomeia candidato aprovado em <strong>concurso público</strong>"],
        )
        achado = coletar._ordenar_e_colapsar(
            coletar._achados_de_resposta(
                _envelope_ioes([item]), "dom", "concurso publico", self.indice
            )
        )[0]
        self.assertEqual(achado["fonte_id"], "ioes-busca-dom")
        self.assertEqual(achado["categoria"], "ato_diario")
        self.assertEqual(
            achado["url"],
            "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11517/315",
        )
        self.assertEqual(
            achado["titulo"], "nomeia candidato aprovado em concurso público"
        )
        self.assertEqual(achado["edicao"], "3099")
        self.assertEqual(achado["data_publicacao_ato"], "2026-10-01")
        self.assertEqual(achado["tipo"], "concurso_publico")
        self.assertEqual(achado["inscricoes"], {"inicio": None, "fim": None})
        self.assertIsNone(achado["vagas_informadas"])
        self.assertFalse(achado["conteudo_truncado"])
        # Nome OFICIAL do cadastro, com acento — nunca o trecho normalizado.
        self.assertEqual(achado["municipio"], "Sooretama")
        self.assertEqual(achado["municipio_codigo_ibge"], 3205010)
        self.assertEqual(achado["municipio_slug"], "sooretama")
        self.assertEqual(achado["municipio_escopo"], "municipal")
        self.assertEqual(achado["esfera"], "municipal")
        self.assertEqual(achado["orgao"], "Prefeitura de Sooretama")
        self.assertIsNone(achado["orgao_vinculado_id"])
        self.assertNotIn("_diario_id", achado)

    def test_titulo_cai_no_conteudo_quando_nao_ha_highlight(self):
        conteudo = "PREFEITURA MUNICIPAL DE SERRA " + ("texto do ato " * 40)
        achado = coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            self.indice,
        )[0]
        self.assertEqual(len(achado["titulo"]), 200)

    def test_conteudo_longo_e_truncado_com_sinal(self):
        conteudo = "PREFEITURA MUNICIPAL DE SERRA " + ("a" * (coletar.LIMITE_CONTEUDO))
        diagnostico = {}
        achados = coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            self.indice,
            diagnostico,
        )
        self.assertTrue(achados[0]["conteudo_truncado"])
        self.assertEqual(diagnostico["paginas_truncadas"], 1)

    def test_data_invalida_nao_derruba_o_item(self):
        achado = coletar._achados_de_resposta(
            _envelope_ioes(
                [_item_ioes(conteudo="PREFEITURA MUNICIPAL DE SERRA ato", data="01/10/2026")]
            ),
            "dom",
            "concurso publico",
            self.indice,
        )[0]
        self.assertIsNone(achado["data_publicacao_ato"])

    def test_total_em_forma_de_dict_e_tolerado(self):
        hits = {"total": {"value": 7, "relation": "eq"}, "hits": []}
        self.assertEqual(coletar._total_de_hits(hits), 7)
        self.assertEqual(coletar._total_de_hits({"total": 7, "hits": []}), 7)
        self.assertIsNone(coletar._total_de_hits({"hits": []}))

    def test_chave_estavel_entre_duas_execucoes(self):
        envelope = _envelope_ioes(
            [
                _item_ioes(
                    conteudo="PREFEITURA MUNICIPAL DE SERRA edital de concurso "
                    "público nº 001/2026"
                )
            ]
        )
        primeira = coletar._achados_de_resposta(
            envelope, "dom", "concurso publico", self.indice
        )
        segunda = coletar._achados_de_resposta(
            copy.deepcopy(envelope), "dom", "concurso publico", self.indice
        )
        self.assertEqual([a["chave"] for a in primeira], [a["chave"] for a in segunda])
        self.assertEqual(primeira[0]["chave"], "ioes-dom:serra:edital-1-2026")

    def test_mesmo_edital_em_paginas_diferentes_tem_a_mesma_chave(self):
        conteudo = "PREFEITURA MUNICIPAL DE SERRA edital de concurso público nº 001/2026"
        achados = coletar._achados_de_resposta(
            _envelope_ioes(
                [
                    _item_ioes(ident="11517_315", conteudo=conteudo, pagina=315),
                    _item_ioes(ident="11517_316", conteudo=conteudo, pagina=316),
                ]
            ),
            "dom",
            "concurso publico",
            self.indice,
        )
        self.assertEqual({a["chave"] for a in achados}, {"ioes-dom:serra:edital-1-2026"})

    def test_ordenacao_e_colapso_sao_deterministicos(self):
        # Dois envelopes com os MESMOS itens embaralhados e o mesmo 'sort' (a
        # API ordena por dia, nao por item) produzem a mesma lista final. Sem a
        # ordenacao explicita, qual pagina "ganha" a chave variaria entre
        # execucoes.
        conteudo = "PREFEITURA MUNICIPAL DE SERRA ato de nomeacao em concurso público"
        itens = [
            _item_ioes(ident="11517_316", conteudo=conteudo, pagina=316),
            _item_ioes(ident="11516_310", conteudo=conteudo, diario_id=11516, pagina=310),
            _item_ioes(ident="11517_315", conteudo=conteudo, pagina=315),
        ]

        def extrair(ordem):
            return [
                a["url"]
                for a in coletar._ordenar_e_colapsar(
                    coletar._achados_de_resposta(
                        _envelope_ioes([copy.deepcopy(itens[i]) for i in ordem]),
                        "dom",
                        "concurso publico",
                        self.indice,
                    )
                )
            ]

        esperado = [
            "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11516/310",
            "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11517/315",
            "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11517/316",
        ]
        self.assertEqual(extrair([0, 1, 2]), esperado)
        self.assertEqual(extrair([2, 0, 1]), esperado)

    def test_colapso_mantem_uma_entrada_por_chave(self):
        # Dois blocos da MESMA pagina citando o mesmo municipio produzem a mesma
        # chave (a granularidade da chave sem numero e de pagina).
        conteudo = (
            "PREFEITURA MUNICIPAL DE SERRA nomeia candidato protocolo 111 "
            "PREFEITURA MUNICIPAL DE SERRA exonera servidor do mesmo quadro"
        )
        brutos = coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            self.indice,
        )
        self.assertEqual(len(brutos), 2)
        self.assertEqual(len(coletar._ordenar_e_colapsar(brutos)), 1)


class TesteColetorIoesSemRede(unittest.TestCase):
    """coletar_ioes() com a camada de leitura substituida — sem rede.

    A camada de rede nao e testada unitariamente (ela e fina de proposito), mas
    a politica de falha DO COLETOR e: pagina que falha e recuperavel, fonte
    inteira indisponivel tem de virar status 'erro' no laco de FONTES.
    """

    def setUp(self):
        self._original = coletar._ler_com_retry
        self.indice = comum.indice_municipios()

    def tearDown(self):
        coletar._ler_com_retry = self._original

    def test_fonte_inteira_indisponivel_levanta_para_o_laco_de_fontes(self):
        def explodir(url, cabecalhos=None):
            raise urllib.error.URLError("sem rede")

        coletar._ler_com_retry = explodir
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                coletar.coletar_ioes(escopo="dom", indice=self.indice)

    def test_resposta_valida_preenche_o_diagnostico(self):
        conteudo = (
            "PREFEITURA MUNICIPAL DE SERRA edital de concurso público nº 001/2026"
        )
        corpo = json.dumps(
            _envelope_ioes([_item_ioes(conteudo=conteudo)], total=1)
        )
        chamadas = []

        def responder(url, cabecalhos=None):
            chamadas.append(url)
            return corpo

        coletar._ler_com_retry = responder
        diagnostico = {}
        achados = coletar.coletar_ioes(
            escopo="dom", diagnostico=diagnostico, indice=self.indice
        )
        # Uma pagina por frase, com di: na janela e termo entre aspas.
        self.assertEqual(len(chamadas), 2)
        self.assertIn("/busca/busca/buscar/query/0/di:", chamadas[0])
        self.assertIn("q=%22concurso+publico%22", chamadas[0].replace("%20", "+"))
        self.assertFalse(diagnostico["truncado"])
        self.assertFalse(diagnostico["limite_achados_atingido"])
        self.assertEqual(diagnostico["total_relatado"], 2)
        self.assertEqual(diagnostico["paginas_truncadas"], 0)
        self.assertEqual(diagnostico["nao_mapeados"], [])
        # A mesma pagina devolvida para as duas frases colapsa numa chave.
        self.assertEqual(len(achados), 1)
        self.assertNotIn("_pagina", achados[0])

    def test_teto_de_achados_interrompe_a_coleta(self):
        conteudo = "PREFEITURA MUNICIPAL DE SERRA ato de nomeacao"
        itens = [
            _item_ioes(ident="11517_%d" % n, conteudo=conteudo, pagina=n)
            for n in range(1, 11)
        ]
        corpo = json.dumps(_envelope_ioes(itens, total=1000))
        coletar._ler_com_retry = lambda url, cabecalhos=None: corpo
        diagnostico = {}
        with contextlib.redirect_stdout(io.StringIO()):
            coletar.coletar_ioes(
                escopo="dom", diagnostico=diagnostico, max_achados=5,
                indice=self.indice,
            )
        self.assertTrue(diagnostico["limite_achados_atingido"])

    def test_teto_de_paginas_marca_truncado(self):
        conteudo = "PREFEITURA MUNICIPAL DE SERRA ato de nomeacao"
        itens = [
            _item_ioes(ident="11517_%d" % n, conteudo=conteudo, pagina=n)
            for n in range(1, 11)
        ]
        corpo = json.dumps(_envelope_ioes(itens, total=500))
        coletar._ler_com_retry = lambda url, cabecalhos=None: corpo
        diagnostico = {}
        with contextlib.redirect_stdout(io.StringIO()):
            coletar.coletar_ioes(
                escopo="dom", diagnostico=diagnostico, max_paginas=2,
                indice=self.indice,
            )
        self.assertTrue(diagnostico["truncado"])


class TesteMunicipioNaoMapeado(unittest.TestCase):
    """Deteccao (B): nome citado que nao resolve contra o cadastro."""

    def setUp(self):
        self.indice = comum.indice_municipios()

    def test_padroes_de_mencao_casam_texto_em_caixa_alta(self):
        # E o teste que o passe anterior nao tinha e que deixou o requisito
        # nascer morto: a versao com classe maiuscula produzia 1 captura em 144
        # paginas.
        texto = _pagina("PREFEITURA MUNICIPAL DE SOORETAMA/ES, no uso de suas")
        self.assertTrue(any(p.search(texto) for p in coletar.PADROES_MENCAO))

    def test_classificar_mencao_resolve_por_prefixo(self):
        self.assertEqual(
            coletar.classificar_mencao("joao neiva por falta disciplinar e", self.indice),
            ("mapeado", "joao-neiva"),
        )
        self.assertEqual(
            coletar.classificar_mencao("venda nova do imigrante far", self.indice),
            ("mapeado", "venda-nova-do-imigrante"),
        )
        self.assertEqual(
            coletar.classificar_mencao("que trata esta lei constitui", self.indice),
            ("candidato", "que trata esta lei"),
        )

    def test_candidato_e_podado_em_quatro_tokens(self):
        _situacao, nome = coletar.classificar_mencao(
            "xyzlandia do norte velha sede e tambem outra coisa", self.indice
        )
        self.assertEqual(len(nome.split()), coletar.MAX_TOKENS_CANDIDATO)

    def test_filtros_de_candidato(self):
        self.assertFalse(coletar._candidato_aceitavel("ab"))
        self.assertFalse(coletar._candidato_aceitavel("12345"))
        self.assertFalse(coletar._candidato_aceitavel("prefeitura municipal"))
        self.assertFalse(coletar._candidato_aceitavel("minas gerais"))
        self.assertTrue(coletar._candidato_aceitavel("sao roque canaa"))

    def test_deteccao_por_injecao(self):
        # "Nao aparece ruido" e indistinguivel de "nao aparece nada": o caminho
        # positivo e exercitado removendo Sooretama do cadastro.
        conteudo = (
            "PORTARIA Nº 310/2026 O PREFEITO DO MUNICÍPIO DE SOORETAMA/ES, no "
            "uso de suas atribuições, nomeia candidato aprovado em concurso "
            "público"
        )
        with _indice_sem(["sooretama"]) as indice:
            diagnostico = {}
            coletar._achados_de_resposta(
                _envelope_ioes([_item_ioes(conteudo=conteudo)]),
                "dom",
                "concurso publico",
                indice,
                diagnostico,
            )
            candidatos = coletar._consolidar_candidatos(
                diagnostico["mencoes"], "ioes-busca-dom"
            )
            self.assertEqual([c["nome_detectado"] for c in candidatos], ["sooretama"])
            self.assertTrue(candidatos[0]["com_marca_uf"])
            # 1 ocorrencia em 1 pagina, mas COM marca de UF: e por isso que a
            # disjuncao do filtro importa.
            reportados = coletar.fundir_nao_mapeados(
                [], candidatos, indice, dt.date(2026, 10, 1), 7
            )
            self.assertEqual([c["nome_detectado"] for c in reportados], ["sooretama"])

        # Com o cadastro completo, o mesmo texto nao produz candidato nenhum.
        diagnostico = {}
        coletar._achados_de_resposta(
            _envelope_ioes([_item_ioes(conteudo=conteudo)]),
            "dom",
            "concurso publico",
            self.indice,
            diagnostico,
        )
        self.assertEqual(
            coletar._consolidar_candidatos(diagnostico["mencoes"], "ioes-busca-dom"), []
        )

    def test_consolidacao_por_prefixo(self):
        with _indice_sem(["joao-neiva"]) as indice:
            conteudo = (
                "MUNICÍPIO DE JOÃO NEIVA/ES torna público. PREFEITURA MUNICIPAL "
                "DE JOÃO NEIVA POR FALTA DISCIPLINAR E, nos termos da lei"
            )
            diagnostico = {}
            coletar._achados_de_resposta(
                _envelope_ioes([_item_ioes(conteudo=conteudo)]),
                "dom",
                "concurso publico",
                indice,
                diagnostico,
            )
            candidatos = coletar._consolidar_candidatos(
                diagnostico["mencoes"], "ioes-busca-dom"
            )
            # Uma linha, e nao duas: 'joao neiva por falta' e a mesma captura
            # com excesso, e o mais curto absorve o mais longo.
            self.assertEqual([c["nome_detectado"] for c in candidatos], ["joao neiva"])
            self.assertEqual(candidatos[0]["ocorrencias"], 2)
            self.assertTrue(candidatos[0]["com_marca_uf"])

    def _candidato(self, **campos):
        base = {
            "nome_detectado": "sao roque canaa",
            "ocorrencias": 1,
            "paginas_distintas": 1,
            "com_marca_uf": False,
            "fontes": ["ioes-busca-dom"],
            "exemplos": [
                {
                    "url": "https://ioes.dio.es.gov.br/dom/portal/edicoes/download/11517/42",
                    "data": "2026-10-01",
                    "trecho": "...prefeitura municipal de sao roque canaa, estado...",
                }
            ],
        }
        base.update(campos)
        return base

    def test_uma_ocorrencia_sem_marca_de_uf_nao_e_reportada(self):
        self.assertEqual(
            coletar.fundir_nao_mapeados(
                [], [self._candidato()], self.indice, dt.date(2026, 10, 1), 7
            ),
            [],
        )

    def test_duas_paginas_distintas_passam(self):
        reportados = coletar.fundir_nao_mapeados(
            [],
            [self._candidato(ocorrencias=2, paginas_distintas=2)],
            self.indice,
            dt.date(2026, 10, 1),
            7,
        )
        self.assertEqual(len(reportados), 1)

    def test_fusao_acumula_entre_execucoes(self):
        # O caso que decide "acumulado e nao por execucao": um candidato visto
        # 1x por dia em pagina distinta nunca passaria de paginas_distintas==1
        # com contadores por execucao, e nunca seria reportado.
        anterior = [
            self._candidato(
                primeira_deteccao="2026-09-24", ultima_deteccao="2026-09-30"
            )
        ]
        reportados = coletar.fundir_nao_mapeados(
            anterior, [self._candidato()], self.indice, dt.date(2026, 10, 1), 7
        )
        self.assertEqual(len(reportados), 1)
        item = reportados[0]
        self.assertEqual(item["ocorrencias"], 2)
        self.assertEqual(item["paginas_distintas"], 2)
        self.assertEqual(item["primeira_deteccao"], "2026-09-24")
        self.assertEqual(item["ultima_deteccao"], "2026-10-01")
        self.assertEqual(item["fontes"], ["ioes-busca-dom"])
        self.assertLessEqual(len(item["exemplos"]), 3)
        # Sugestao conservadora: igualdade de tokens nao genericos ('do' e
        # token de ligacao), nunca distancia de edicao difusa.
        self.assertEqual(item["provavel_alias_de"], "sao-roque-do-canaa")
        self.assertEqual(item["sugestao"], "alias")

    def test_candidato_que_parou_de_aparecer_e_removido(self):
        anterior = [
            self._candidato(
                com_marca_uf=True,
                primeira_deteccao="2026-08-20",
                ultima_deteccao="2026-09-02",  # 29 dias = --janela-ioes-dias * 4
            )
        ]
        self.assertEqual(
            coletar.fundir_nao_mapeados(
                anterior, [], self.indice, dt.date(2026, 10, 1), 7
            ),
            [],
        )

    def test_sem_candidato_unico_a_sugestao_e_verificar(self):
        reportados = coletar.fundir_nao_mapeados(
            [],
            [
                self._candidato(
                    nome_detectado="que trata esta lei", com_marca_uf=True
                )
            ],
            self.indice,
            dt.date(2026, 10, 1),
            7,
        )
        self.assertIsNone(reportados[0]["provavel_alias_de"])
        self.assertEqual(reportados[0]["sugestao"], "verificar")

    def test_exemplos_sao_no_maximo_tres_de_paginas_distintas(self):
        exemplos = [
            {"url": "u%d" % n, "data": "2026-09-%02d" % (20 + n), "trecho": "t"}
            for n in range(5)
        ] + [{"url": "u1", "data": "2026-09-21", "trecho": "repetida"}]
        saida = coletar._exemplos_ordenados(exemplos)
        self.assertEqual([e["url"] for e in saida], ["u4", "u3", "u2"])

    def test_exemplo_malformado_do_arquivo_anterior_nao_derruba_a_fusao(self):
        # Defeito achado pela auditoria do item 21: fundir_nao_mapeados() roda em
        # main(), FORA do try/except por fonte, e copiava 'exemplos' do arquivo
        # anterior sem conferir a forma. Um exemplo em string (arquivo editado a
        # mao, ou formato de versao anterior) virava AttributeError em
        # exemplo.get("url") e derrubava a coleta do dia inteiro.
        anterior = [
            self._candidato(
                com_marca_uf=True,
                exemplos=["https://ioes.dio.es.gov.br/pagina/1", None, 7],
                primeira_deteccao="2026-09-30",
                ultima_deteccao="2026-09-30",
            )
        ]
        # Sem nenhum candidato novo: o ramo que copia o anterior verbatim, que e
        # o que alcancava monta_relatorio_md() sem passar por _exemplos_ordenados().
        reportados = coletar.fundir_nao_mapeados(
            anterior, [], self.indice, dt.date(2026, 10, 1), 7
        )
        self.assertEqual(len(reportados), 1)
        self.assertEqual(reportados[0]["exemplos"], [])

        # E com candidato novo na mesma execucao, o exemplo bom sobrevive.
        reportados = coletar.fundir_nao_mapeados(
            anterior, [self._candidato()], self.indice, dt.date(2026, 10, 1), 7
        )
        self.assertEqual(
            [e["data"] for e in reportados[0]["exemplos"]], ["2026-10-01"]
        )

    def test_corpo_da_issue_sobrevive_a_exemplo_malformado(self):
        # A outra ponta do mesmo defeito: o corpo da issue le exemplos[0]["url"].
        candidato = self._candidato(com_marca_uf=True, exemplos=[])
        candidato["provavel_alias_de"] = None
        candidato["sugestao"] = "verificar"
        texto = coletar.monta_relatorio_md(
            [],
            [
                {
                    "id": "ioes-busca-dom",
                    "nome": "IOES - DOM",
                    "tipo": "diario_oficial",
                    "status": "ok",
                    "achados": 0,
                }
            ],
            dt.date(2026, 10, 1),
            {"nao_mapeados": [candidato]},
        )
        self.assertIn("sao roque canaa", texto)


class TesteNormalizarAchado(unittest.TestCase):
    """Ponto unico dos campos de categoria e de municipio."""

    def setUp(self):
        self.indice = comum.indice_municipios()

    def test_oportunidade_resolve_em_texto_livre(self):
        # E a linha da tabela de normalizacao que resolver_municipio() (consulta
        # exata) nunca produziria: o teste falharia se alguem trocasse de volta.
        achado = coletar.normalizar_achado(
            {"orgao": "Prefeitura de Anchieta", "titulo": "Processo seletivo"},
            self.indice,
        )
        self.assertEqual(achado["categoria"], "oportunidade")
        self.assertEqual(achado["municipio_slug"], "anchieta")
        self.assertEqual(achado["municipio_escopo"], "municipal")
        self.assertEqual(achado["municipio_confianca"], "baixa")
        self.assertEqual(achado["municipio_origem"], "nome")
        self.assertEqual(achado["municipio_codigo_ibge"], 3200409)

    def test_oportunidade_estadual_sem_municipio(self):
        achado = coletar.normalizar_achado(
            {"orgao": "SEDU", "esfera": "estadual"}, self.indice
        )
        self.assertIsNone(achado["municipio_slug"])
        self.assertEqual(achado["municipio_escopo"], "estadual")
        self.assertIsNone(achado["municipio_confianca"])

    def test_oportunidade_ambigua_nao_e_desempatada(self):
        achado = coletar.normalizar_achado(
            {"orgao": "Prefeitura de Serra e de Vila Velha"}, self.indice
        )
        self.assertIsNone(achado["municipio_slug"])
        self.assertEqual(achado["municipio_escopo"], "indeterminado")

    def test_ato_de_diario_nao_e_sobrescrito(self):
        # setdefault e nao atribuicao: o coletor de diario JA resolveu o
        # municipio com evidencia de texto, e aquela resolucao e mais forte.
        achado = coletar.normalizar_achado(
            {
                "categoria": "ato_diario",
                "orgao": "Prefeitura de Serra",
                "municipio_slug": "serra",
                "municipio_confianca": "alta",
                "municipio_escopo": "municipal",
                "municipio_origem": "nome",
            },
            self.indice,
        )
        self.assertEqual(achado["municipio_confianca"], "alta")
        self.assertEqual(achado["municipio_slug"], "serra")
        self.assertFalse(achado["conteudo_truncado"])
        self.assertIsNone(achado["orgao_vinculado_id"])


class TesteCasarEstrito(unittest.TestCase):
    """Ato de diario casa com dados/ somente por evidencia forte."""

    def setUp(self):
        self.indice = coletar.indice_repositorio()

    def _ato(self, titulo, url=""):
        return {
            "categoria": "ato_diario",
            "orgao": "Prefeitura de Serra",
            "orgao_sigla": comum.AUSENTE,
            "titulo": titulo,
            "url": url,
        }

    def test_sem_numero_de_edital_nao_casa(self):
        ato = self._ato("nomeia candidato aprovado em concurso publico")
        self.assertIsNone(coletar.casar_estrito(ato, self.indice))
        # A asercao negativa prova que a distincao importa: a mesma entrada
        # casaria pelo ramo fraco de casar(), que e o bug que motivou a funcao.
        self.assertIsNotNone(coletar.casar(ato, self.indice))

    def test_numero_coincidente_casa(self):
        ato = self._ato("processo seletivo simplificado nº 007/2026 - resultado")
        self.assertEqual(
            coletar.casar_estrito(ato, self.indice), "ps-serra-es-sesa-007-2026"
        )

    def test_url_identica_casa(self):
        ato = self._ato(
            "ato qualquer",
            url="https://serra.es.gov.br/noticias/"
            "serra-abre-processo-seletivo-para-profissionais-da-saude",
        )
        self.assertEqual(
            coletar.casar_estrito(ato, self.indice), "ps-serra-es-sesa-007-2026"
        )


class TesteCobertura(unittest.TestCase):
    """cobertura(): funcao pura, a mesma regra para README, relatorio e e-mail."""

    def setUp(self):
        self.indice = comum.indice_municipios()
        self.registros = [reg for _caminho, reg in comum.carregar_registros()]
        self.referencia = dt.date(2026, 10, 1)

    def _achado(self, slug_mun, confianca="alta", ultima="2026-10-01"):
        return {
            "categoria": "ato_diario",
            "municipio_slug": slug_mun,
            "municipio_confianca": confianca,
            "ultima_deteccao": ultima,
        }

    def test_contagens_dos_registros_reais(self):
        bloco = coletar.cobertura(
            self.indice, self.registros, [], set(), self.referencia
        )
        self.assertEqual(bloco["total_municipios"], 78)
        # As DUAS metades do caso intermunicipal: Divino de Sao Lourenco
        # aparece somente em ps-consorcio-caparao-es-2026, que tem
        # esfera 'intermunicipal' — logo nao credita municipio (15, e nao 16)
        # e soma 1 em registros_intermunicipais_sem_atribuicao.
        self.assertEqual(bloco["com_registro_curado"], 15)
        self.assertEqual(bloco["registros_intermunicipais_sem_atribuicao"], 4)
        self.assertNotIn("divino-de-sao-lourenco", bloco["slugs_com_sinal"])
        # Vazio desde 2026-10-02: a composicao dos tres intermunicipais foi
        # apurada documentalmente (13 + 13 + 18 municipios), que era a condicao
        # que o proprio aviso do validador pedia. A lista volta a ter conteudo
        # se um novo orgao intermunicipal entrar sem composicao conhecida, e e
        # esse o caso que ela existe para expor.
        self.assertEqual(bloco["orgaos_vinculados_sem_municipio"], [])
        self.assertEqual(
            bloco["sem_sinal_algum"], 78 - len(bloco["slugs_com_sinal"])
        )

    def test_confianca_baixa_nao_conta(self):
        bloco = coletar.cobertura(
            self.indice,
            [],
            [self._achado("sooretama", confianca="baixa")],
            set(),
            self.referencia,
        )
        self.assertEqual(bloco["com_achado_na_janela"], 0)
        self.assertEqual(bloco["com_achado_acumulado"], 0)

    def test_janela_versus_acumulado(self):
        bloco = coletar.cobertura(
            self.indice,
            [],
            [
                self._achado("sooretama"),
                self._achado("mucurici", ultima="2026-09-20"),
            ],
            set(),
            self.referencia,
        )
        self.assertEqual(bloco["com_achado_na_janela"], 1)
        self.assertEqual(bloco["com_achado_acumulado"], 2)
        self.assertEqual(
            bloco["slugs_com_achado_acumulado"], ["mucurici", "sooretama"]
        )
        self.assertEqual(
            bloco["com_achado_acumulado"], len(bloco["slugs_com_achado_acumulado"])
        )
        # O achado antigo nao entra no retrato de hoje.
        self.assertEqual(bloco["slugs_com_sinal"], ["sooretama"])

    def test_delta_contra_o_historico(self):
        bloco = coletar.cobertura(
            self.indice,
            [],
            [self._achado("serra"), self._achado("sooretama")],
            {"serra"},
            self.referencia,
        )
        self.assertEqual(bloco["vistos_pela_primeira_vez"], ["sooretama"])
        bloco_zerado = coletar.cobertura(
            self.indice,
            [],
            [self._achado("serra"), self._achado("sooretama")],
            set(),
            self.referencia,
        )
        self.assertEqual(
            bloco_zerado["vistos_pela_primeira_vez"], ["serra", "sooretama"]
        )

    def test_historico_e_monotonico_e_nao_reanuncia(self):
        # Municipio que publicou antes e nao publicou agora SAI do retrato, mas
        # permanece no historico — e e isso que impede a issue de anunciar
        # "primeiro ato detectado em X" pela segunda vez.
        bloco = coletar.cobertura(
            self.indice,
            [],
            [self._achado("serra")],
            {"serra", "sooretama"},
            self.referencia,
        )
        self.assertEqual(bloco["slugs_com_sinal"], ["serra"])
        self.assertEqual(
            bloco["slugs_com_sinal_historico"], ["serra", "sooretama"]
        )
        self.assertEqual(bloco["vistos_pela_primeira_vez"], [])
        # Execucao seguinte, com Sooretama de volta: continua sem reanuncio.
        seguinte = coletar.cobertura(
            self.indice,
            [],
            [self._achado("serra"), self._achado("sooretama")],
            set(bloco["slugs_com_sinal_historico"]),
            self.referencia,
        )
        self.assertEqual(seguinte["vistos_pela_primeira_vez"], [])

    def test_leitura_tolerante_do_historico(self):
        self.assertEqual(coletar.historico_de_sinal({}), set())
        self.assertEqual(
            coletar.historico_de_sinal(
                {"cobertura_municipios": {"slugs_com_sinal": ["serra"]}}
            ),
            {"serra"},
        )
        self.assertEqual(
            coletar.historico_de_sinal(
                {
                    "cobertura_municipios": {
                        "slugs_com_sinal": ["serra"],
                        "slugs_com_sinal_historico": ["serra", "sooretama"],
                    }
                }
            ),
            {"serra", "sooretama"},
        )


class TesteReconciliacaoIBGE(unittest.TestCase):
    """Reconciliacao (C), nos ramos que nao dependem de rede."""

    def test_sem_conferir_devolve_nao_conferido(self):
        bloco = coletar.reconciliar_ibge(
            comum.indice_municipios(), dt.date(2026, 10, 1), conferir=False
        )
        self.assertEqual(bloco["status"], "nao_conferido")
        self.assertEqual(bloco["total_cadastro"], 78)
        self.assertIsNone(bloco["erro"])
        self.assertFalse(coletar.ha_divergencia_ibge(bloco))

    def test_divergencia_e_detectada_por_codigo_e_por_nome(self):
        self.assertTrue(
            coletar.ha_divergencia_ibge(
                {"ausentes_no_cadastro": [{"codigo_ibge": 3299999, "nome": "Novo"}]}
            )
        )
        self.assertTrue(
            coletar.ha_divergencia_ibge(
                {
                    "nomes_divergentes": [
                        {
                            "codigo_ibge": 3201209,
                            "nome_ibge": "Cachoeiro de Itapemirim",
                            "nome_cadastro": "Cachoeiro do Itapemirim",
                        }
                    ]
                }
            )
        )


class TesteMainDoColetor(unittest.TestCase):
    """main() de ponta a ponta, sem rede: fonte falsa e quarentena temporaria.

    O descobertas.json versionado NAO e tocado: DIR_DESCOBERTAS e
    CAMINHO_DESCOBERTAS apontam para um diretorio temporario, e por isso main()
    pode gravar de verdade — e e gravando que ele expoe descartados_por_retencao
    e as chaves novas do arquivo.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._estado = (
            coletar.DIR_DESCOBERTAS,
            coletar.CAMINHO_DESCOBERTAS,
            coletar.FONTES,
            sys.argv,
            os.environ.get("DATA_REFERENCIA"),
        )
        coletar.DIR_DESCOBERTAS = self._dir
        coletar.CAMINHO_DESCOBERTAS = os.path.join(self._dir, "descobertas.json")
        os.environ["DATA_REFERENCIA"] = "2026-10-01"

    def tearDown(self):
        (
            coletar.DIR_DESCOBERTAS,
            coletar.CAMINHO_DESCOBERTAS,
            coletar.FONTES,
            sys.argv,
            referencia,
        ) = self._estado
        if referencia is None:
            os.environ.pop("DATA_REFERENCIA", None)
        else:
            os.environ["DATA_REFERENCIA"] = referencia
        shutil.rmtree(self._dir)

    def _rodar(self, achados=(), anterior=None, extra=()):
        if anterior is not None:
            with open(coletar.CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
                json.dump(anterior, fh, ensure_ascii=False)
        copia = copy.deepcopy(list(achados))
        coletar.FONTES = {"fonte-de-teste": lambda: copia}
        sys.argv = (
            ["coletar.py", "--fonte", "fonte-de-teste", "--sem-conferir-ibge"]
            + list(extra)
        )
        with contextlib.redirect_stdout(io.StringIO()) as capturado:
            codigo = coletar.main()
        self.assertEqual(codigo, 0, capturado.getvalue())
        with open(coletar.CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            return json.load(fh), capturado.getvalue()

    def _oportunidade(self, chave, orgao):
        return {
            "chave": chave,
            "fonte_id": "fonte-de-teste",
            "orgao": orgao,
            "orgao_sigla": comum.AUSENTE,
            "titulo": "Processo seletivo",
            "esfera": None,
            "tipo": None,
            "inscricoes": {"inicio": None, "fim": None},
            "vagas_informadas": None,
            "url": "https://exemplo.invalido/%s" % chave,
        }

    def _ato(self, chave, slug_mun, data="2026-10-01"):
        return {
            "chave": chave,
            "fonte_id": "fonte-de-teste",
            "orgao": "Prefeitura de %s" % slug_mun,
            "orgao_sigla": comum.AUSENTE,
            "titulo": "nomeia candidato aprovado",
            "esfera": "municipal",
            "tipo": "concurso_publico",
            "inscricoes": {"inicio": None, "fim": None},
            "vagas_informadas": None,
            "url": "https://ioes.dio.es.gov.br/dom/%s" % chave,
            "categoria": "ato_diario",
            "data_publicacao_ato": data,
            "edicao": "3099",
            "editais_citados": [],
            "conteudo_truncado": False,
            "municipio": slug_mun.title(),
            "municipio_codigo_ibge": None,
            "municipio_slug": slug_mun,
            "municipio_confianca": "alta",
            "municipio_escopo": "municipal",
            "municipio_origem": "nome",
            "orgao_vinculado_id": None,
        }

    def test_so_oportunidade_e_novidade(self):
        achados = [
            self._oportunidade("op-1", "Prefeitura de Sooretama"),
            self._oportunidade("op-2", "Prefeitura de Mucurici"),
        ] + [self._ato("ato-%d" % n, "sooretama") for n in range(5)]
        saida_github = os.path.join(self._dir, "saida.txt")
        arquivo, _log = self._rodar(
            achados, extra=["--saida-github", saida_github]
        )
        with open(saida_github, encoding="utf-8") as fh:
            saidas = dict(
                linha.strip().split("=", 1) for linha in fh if "=" in linha
            )
        self.assertEqual(saidas["novos"], "2")
        self.assertEqual(saidas["atos_diario_novos"], "5")
        self.assertEqual(arquivo["atos_diario_novos"], 5)
        self.assertEqual(saidas["municipios_com_sinal"], "1")
        self.assertEqual(saidas["truncado"], "0")

    def test_retencao_so_alcanca_ato_de_diario(self):
        anterior = {
            "descricao": "x",
            "gerado_em": "2026-09-30",
            "janela_dias": 90,
            "total_achados": 3,
            "ja_no_repositorio": 0,
            "pendentes_de_curadoria": 3,
            "fontes_consultadas": [],
            "achados": [
                self._ato("ato-velho", "sooretama", data="2026-06-23"),  # 100 dias
                self._ato("ato-recente", "mucurici", data="2026-07-13"),  # 80 dias
                dict(
                    self._oportunidade("op-velha", "Prefeitura de Sooretama"),
                    primeira_deteccao="2026-06-23",
                    ultima_deteccao="2026-06-23",
                ),
            ],
        }
        arquivo, _log = self._rodar(anterior=anterior)
        self.assertEqual(arquivo["descartados_por_retencao"], 1)
        self.assertEqual(arquivo["retencao_atos_dias"], 90)
        chaves = {a["chave"] for a in arquivo["achados"]}
        self.assertEqual(chaves, {"ato-recente", "op-velha"})

    def test_backfill_de_achado_herdado(self):
        anterior = {
            "descricao": "x",
            "gerado_em": "2026-09-30",
            "janela_dias": 90,
            "total_achados": 1,
            "ja_no_repositorio": 0,
            "pendentes_de_curadoria": 1,
            "fontes_consultadas": [],
            "achados": [
                {
                    "chave": "legado-1",
                    "fonte_id": "fonte-de-teste",
                    "orgao": "ARIES",
                    "titulo": "ARIES",
                    "url": "https://exemplo.invalido/legado",
                    "primeira_deteccao": "2026-09-23",
                    "ultima_deteccao": "2026-09-30",
                    "no_repositorio": False,
                }
            ],
        }
        arquivo, _log = self._rodar(anterior=anterior)
        herdado = arquivo["achados"][0]
        self.assertEqual(herdado["categoria"], "oportunidade")
        self.assertEqual(herdado["municipio_escopo"], "indeterminado")
        self.assertIsNone(herdado["municipio_slug"])
        self.assertIsNone(herdado["municipio_confianca"])
        self.assertEqual(herdado["primeira_deteccao"], "2026-09-23")

    def test_chaves_do_arquivo_de_saida(self):
        arquivo, _log = self._rodar([self._oportunidade("op-1", "SEDU")])
        self.assertLessEqual(
            {
                "descricao",
                "gerado_em",
                "janela_dias",
                "total_achados",
                "ja_no_repositorio",
                "pendentes_de_curadoria",
                "fontes_consultadas",
                "achados",
                "janela_ioes_dias",
                "retencao_atos_dias",
                "descartados_por_retencao",
                "atos_diario_novos",
                "cobertura_municipios",
                "municipios_nao_mapeados",
                "reconciliacao_ibge",
            },
            set(arquivo),
        )
        self.assertEqual(arquivo["reconciliacao_ibge"]["status"], "nao_conferido")
        self.assertEqual(arquivo["cobertura_municipios"]["total_municipios"], 78)

    def test_teto_de_argumento_e_recusado(self):
        coletar.FONTES = {"fonte-de-teste": lambda: []}
        sys.argv = ["coletar.py", "--max-paginas-ioes", "1000"]
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as capturado:
                with contextlib.redirect_stderr(io.StringIO()):
                    coletar.main()
        self.assertEqual(capturado.exception.code, 2)

    def test_migracao_e_idempotente_e_escreve_as_mesmas_chaves(self):
        legado = {
            "descricao": "x",
            "gerado_em": "2026-09-30",
            "janela_dias": 90,
            "total_achados": 1,
            "ja_no_repositorio": 0,
            "pendentes_de_curadoria": 1,
            "fontes_consultadas": [],
            "achados": [
                {
                    "chave": "legado-1",
                    "fonte_id": "concursosnobrasil-es",
                    "orgao": "Prefeitura de Anchieta",
                    "titulo": "Prefeitura de Anchieta",
                    "url": "https://exemplo.invalido/legado",
                    "primeira_deteccao": "2026-09-23",
                    "ultima_deteccao": "2026-09-30",
                    "no_repositorio": False,
                }
            ],
        }
        campos_antes = set(legado["achados"][0])
        with open(coletar.CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
            json.dump(legado, fh, ensure_ascii=False, indent=2)

        def migrar():
            sys.argv = ["coletar.py", "--migrar-descobertas"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(coletar.main(), 0)
            with open(coletar.CAMINHO_DESCOBERTAS, "rb") as fh:
                return fh.read()

        primeira = migrar()
        self.assertEqual(primeira, migrar())  # idempotente

        migrado = json.loads(primeira.decode("utf-8"))["achados"][0]
        self.assertLessEqual(campos_antes, set(migrado))
        self.assertEqual(migrado["primeira_deteccao"], "2026-09-23")
        self.assertEqual(migrado["municipio_slug"], "anchieta")
        # O conjunto de campos escritos pela migracao e EXATAMENTE o de
        # normalizar_achado(): acrescentar campo em um so lugar falha aqui.
        novo = {
            "chave": "novo-1",
            "fonte_id": "concursosnobrasil-es",
            "orgao": "Prefeitura de Anchieta",
            "titulo": "Prefeitura de Anchieta",
            "url": "https://exemplo.invalido/novo",
            "primeira_deteccao": "2026-10-01",
            "ultima_deteccao": "2026-10-01",
            "no_repositorio": False,
        }
        campos_novo = set(novo)
        coletar.normalizar_achado(novo, comum.indice_municipios())
        self.assertEqual(set(migrado) - campos_antes, set(novo) - campos_novo)

    def test_arquivo_ausente_nao_e_erro_para_a_migracao(self):
        sys.argv = ["coletar.py", "--migrar-descobertas"]
        with contextlib.redirect_stdout(io.StringIO()) as capturado:
            self.assertEqual(coletar.main(), 0)
        self.assertIn("Nada a migrar", capturado.getvalue())

    def test_json_invalido_reprova_a_migracao(self):
        with open(coletar.CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
            fh.write("{isto nao e json")
        sys.argv = ["coletar.py", "--migrar-descobertas"]
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(coletar.main(), 1)
        with open(coletar.CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{isto nao e json")


# ------------------------------------------------------------------ validador
#
# As checagens novas de validar.py sao exercitadas com DICTS EM MEMORIA, nunca
# com arquivo temporario: e exatamente para isso que valida_catalogo_fontes() e
# valida_cadastro_municipios() recebem o dado ja carregado. Cada caso abaixo e
# uma linha das tabelas de secao 9.1/9.2 do design, e os casos "ok" valem tanto
# quanto os de defeito — a forma comum do dado (um unico canal de agregador
# confirmado) nao pode ser reprovada por uma regra escrita para o caso raro.

CATALOGO_DE_TESTE = {
    "ultima_atualizacao": "2026-10-01",
    "fontes": [
        {
            "id": "ioes-busca-dom",
            "nome": "Busca do DOM/AMUNES",
            "url": "https://ioes.dio.es.gov.br/dom",
            "tipo": "diario_oficial",
            "esfera": "municipal",
            "prioridade": 1,
            "coletada_automaticamente": True,
        },
        {
            "id": "banca-exemplo",
            "nome": "Banca Exemplo",
            "url": "https://banca.exemplo.org/",
            "tipo": "banca",
            "esfera": "nao_se_aplica",
            "prioridade": 3,
        },
    ],
}


def _fonte(**mudancas):
    """Fonte bem formada de tipo 'banca', com as mudancas do caso aplicadas."""
    fonte = {
        "id": "banca-exemplo",
        "nome": "Banca Exemplo",
        "url": "https://banca.exemplo.org/",
        "tipo": "banca",
        "esfera": "nao_se_aplica",
        "prioridade": 3,
    }
    fonte.update(mudancas)
    return fonte


def _canal_diario(**mudancas):
    canal = {
        "tipo": "diario_oficial_agregador",
        "precedencia": 1,
        "url": "https://ioes.dio.es.gov.br/dom",
        "fonte_id": "ioes-busca-dom",
        "estado": "confirmado",
        "evidencia": (
            "nome do municipio em confianca alta na pagina do DOM/AMUNES de "
            "2026-10-01, edicao 3099, pagina 322"
        ),
        "verificado_em": "2026-10-01",
    }
    canal.update(mudancas)
    return canal


def _municipio(**mudancas):
    """Municipio bem formado: UM unico canal de diario agregador confirmado.

    E o caso comum de secao 3.1 (quem publica so pelo DOM/AMUNES), e por isso
    serve ao mesmo tempo de base das mutacoes e de caso "ok".
    """
    entrada = {
        "codigo_ibge": 3205002,
        "nome": "Serra",
        "slug": "serra",
        "aliases": [],
        "microrregiao": "Vitória",
        "canais": [_canal_diario()],
        "pendencias_verificacao": [],
        "verificado_em": "2026-10-01",
    }
    entrada.update(mudancas)
    return entrada


def _municipio_vitoria(**mudancas):
    """Segunda entrada bem formada, para os casos que precisam de dois slugs."""
    return _municipio(codigo_ibge=3205309, nome="Vitória", slug="vitoria", **mudancas)


def _orgao(**mudancas):
    orgao = {
        "id": "camara-serra",
        "nome": "Camara Municipal da Serra",
        "aliases": [],
        "sigla": None,
        "natureza": "camara_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["serra"],
        "url": "https://www.cmserra.es.gov.br/concursos",
        "fontes": ["ioes-busca-dom"],
        "evidencia": "url sondada em 2026-10-01 com HTTP 200",
        "pendencias_verificacao": [],
        "verificado_em": "2026-10-01",
    }
    orgao.update(mudancas)
    return orgao


def _cadastro(municipios=None, orgaos=None, **mudancas):
    cadastro = {
        "ibge_consultado_em": "2026-10-01",
        "municipios": [_municipio()] if municipios is None else municipios,
        "orgaos_vinculados": [] if orgaos is None else orgaos,
    }
    cadastro["total_esperado"] = len(cadastro["municipios"])
    cadastro.update(mudancas)
    return cadastro


def _mensagens(rel):
    return (
        [item["mensagem"] for item in rel.erros],
        [item["mensagem"] for item in rel.avisos],
    )


class TesteValidadorDoCatalogo(unittest.TestCase):
    """Tabela de secao 9.1, com o catalogo em memoria."""

    def _rodar(self, fontes, ultima_atualizacao="2026-10-01"):
        rel = validar.Relatorio()
        validar.valida_catalogo_fontes(
            rel, {"ultima_atualizacao": ultima_atualizacao, "fontes": fontes}
        )
        return _mensagens(rel)

    def test_catalogo_bem_formado_nao_gera_nada(self):
        erros, avisos = self._rodar(CATALOGO_DE_TESTE["fontes"])
        self.assertEqual(erros, [])
        self.assertEqual(avisos, [])

    def test_orgao_publico_com_esfera_nao_se_aplica(self):
        erros, _ = self._rodar(
            [_fonte(tipo="diario_oficial", esfera="nao_se_aplica")]
        )
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("nao pode ter esfera 'nao_se_aplica'", erros[0])

    def test_fonte_que_nao_e_orgao_publico_com_esfera_de_governo(self):
        # O bug inverso: foi a falta desta metade que deixou 12 fontes sem
        # 'esfera' e, depois, uma banca com esfera estadual passar.
        erros, _ = self._rodar([_fonte(esfera="estadual")])
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("deveria ser 'nao_se_aplica'", erros[0])

    def test_chave_desconhecida_em_fonte(self):
        erros, _ = self._rodar([_fonte(esferra="nao_se_aplica")])
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("chave desconhecida: esferra", erros[0])

    def test_id_fora_do_padrao_e_prioridade_fora_da_faixa(self):
        erros, _ = self._rodar([_fonte(id="Banca_Exemplo", prioridade=9)])
        self.assertEqual(len(erros), 2, erros)

    def test_id_duplicado(self):
        erros, _ = self._rodar([_fonte(), _fonte()])
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("id duplicado", erros[0])

    def test_ultima_atualizacao_futura(self):
        erros, _ = self._rodar([_fonte()], ultima_atualizacao="2027-01-01")
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("esta no futuro", erros[0])

    def test_url_sem_https_e_aviso(self):
        erros, avisos = self._rodar([_fonte(url="http://banca.exemplo.org/")])
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("nao usa HTTPS", avisos[0])

    def test_coletada_automaticamente_sem_coletor_e_aviso(self):
        # Aviso, nao erro: o catalogo pode declarar a intencao antes de o
        # coletor existir. Exercita tambem o import tardio de 'coletar'.
        erros, avisos = self._rodar(
            [_fonte(id="portal-inexistente", coletada_automaticamente=True)]
        )
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("nao ha coletor", avisos[0])

    def test_import_de_coletar_e_tardio(self):
        """'coletar' so pode ser importado DENTRO de valida_catalogo_fontes().

        No topo do modulo ele arrastaria TIMEOUT, NAVEGADOR e o sys.path.insert
        do coletor para dentro do validador, que depende apenas de comum. O
        caso le a arvore sintatica porque a alternativa (conferir sys.modules)
        nao distingue "validar importou" de "o proprio teste importou".
        """
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validar.py")
        with open(caminho, encoding="utf-8") as fh:
            arvore = ast.parse(fh.read())

        importados_no_topo = {
            alias.name
            for no in arvore.body
            if isinstance(no, ast.Import)
            for alias in no.names
        }
        self.assertIn("comum", importados_no_topo)
        self.assertNotIn("coletar", importados_no_topo)

        funcao = next(
            no
            for no in arvore.body
            if isinstance(no, ast.FunctionDef) and no.name == "valida_catalogo_fontes"
        )
        dentro = {
            alias.name
            for no in ast.walk(funcao)
            if isinstance(no, ast.Import)
            for alias in no.names
        }
        self.assertEqual(dentro, {"coletar"})


class TesteValidadorDoCadastro(unittest.TestCase):
    """Tabela de secao 9.2, com o cadastro em memoria.

    As linhas de contagem total (total_esperado) sao filtradas das assercoes e
    testadas a parte: um cadastro de teste tem 1 ou 2 municipios e por isso
    dispara sempre o piso 'total_esperado < 78', que nada tem a ver com o
    defeito sob teste. Filtrar e o que torna "sai EXATAMENTE o erro esperado"
    uma afirmacao verificavel.
    """

    def _rodar(self, cadastro):
        rel = validar.Relatorio()
        validar.valida_cadastro_municipios(rel, cadastro, CATALOGO_DE_TESTE)
        erros, avisos = _mensagens(rel)
        return (
            [m for m in erros if not m.startswith(("total_esperado", "len(municipios)"))],
            avisos,
        )

    def _unico_erro(self, cadastro, trecho):
        erros, _ = self._rodar(cadastro)
        self.assertEqual(len(erros), 1, erros)
        self.assertIn(trecho, erros[0])

    # ----------------------------------------------------------- casos "ok"

    def test_um_unico_canal_de_agregador_confirmado_passa(self):
        erros, avisos = self._rodar(_cadastro())
        self.assertEqual(erros, [])
        self.assertEqual(avisos, [])

    def test_canal_pendente_com_data_nula_e_pendencia_declarada_passa(self):
        cadastro = _cadastro(
            [
                _municipio(
                    canais=[_canal_diario(estado="pendente", verificado_em=None)],
                    pendencias_verificacao=["canais:conferir_manual"],
                )
            ]
        )
        erros, avisos = self._rodar(cadastro)
        self.assertEqual(erros, [])
        # Sem canal confirmado e lacuna de cobertura: aviso, nunca erro.
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("nenhum canal confirmado", avisos[0])

    def test_agencia_reguladora_com_zero_slugs_e_pendencia_passa(self):
        cadastro = _cadastro(
            orgaos=[
                _orgao(
                    id="aries",
                    nome="Agencia Reguladora Intermunicipal de Saneamento",
                    sigla="ARIES",
                    natureza="agencia_reguladora",
                    esfera="intermunicipal",
                    municipios_slugs=[],
                    url=None,
                    pendencias_verificacao=[
                        "url:nao_encontrado",
                        "municipios_slugs:nao_encontrado",
                    ],
                )
            ]
        )
        erros, avisos = self._rodar(cadastro)
        self.assertEqual(erros, [])
        self.assertEqual(avisos, [])

    # -------------------------------------------------------- canais e slug

    def test_sem_canal_de_diario_e_sem_pendencia_de_canais(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[])]),
            "sem canal de diario",
        )

    def test_sem_canal_de_diario_com_pendencia_declarada_passa(self):
        cadastro = _cadastro(
            [_municipio(canais=[], pendencias_verificacao=["canais:nao_encontrado"])]
        )
        erros, _ = self._rodar(cadastro)
        self.assertEqual(erros, [])

    def test_canal_confirmado_sem_verificado_em(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[_canal_diario(verificado_em=None)])]),
            "verificado_em e obrigatorio",
        )

    def test_duas_precedencias_iguais_no_mesmo_municipio(self):
        canais = [
            _canal_diario(),
            _canal_diario(
                tipo="portal_prefeitura",
                precedencia=1,
                url="https://www.serra.es.gov.br/",
                fonte_id=None,
            ),
        ]
        self._unico_erro(_cadastro([_municipio(canais=canais)]), "precedencia 1 repetida")

    def test_precedencia_1_nao_e_de_diario_havendo_diario(self):
        canais = [
            _canal_diario(precedencia=2),
            _canal_diario(
                tipo="portal_prefeitura",
                precedencia=1,
                url="https://www.serra.es.gov.br/",
                fonte_id=None,
            ),
        ]
        self._unico_erro(
            _cadastro([_municipio(canais=canais)]), "o diario tem de vir primeiro"
        )

    def test_chave_desconhecida_em_canal(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[_canal_diario(observacao="sondado")])]),
            "chave desconhecida: observacao",
        )

    def test_canal_sem_evidencia(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[_canal_diario(evidencia="")])]),
            "evidencia ausente ou vazia",
        )

    def test_fonte_id_inexistente_no_catalogo(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[_canal_diario(fonte_id="nao-existe")])]),
            "fonte_id inexistente",
        )

    def test_url_nula_fora_de_canal_de_banca(self):
        self._unico_erro(
            _cadastro([_municipio(canais=[_canal_diario(url=None)])]),
            "url null so e aceita em canal de banca",
        )

    def test_canal_pendente_sem_pendencia_declarada(self):
        self._unico_erro(
            _cadastro(
                [_municipio(canais=[_canal_diario(estado="pendente", verificado_em=None)],
                            pendencias_verificacao=[])]
            ),
            "nenhuma pendencia 'canais:...'",
        )

    def test_pendencia_com_motivo_fora_do_vocabulario(self):
        self._unico_erro(
            _cadastro([_municipio(pendencias_verificacao=["canais:talvez"])]),
            "motivo invalido",
        )

    def test_pendencia_sobre_campo_que_nao_existe(self):
        self._unico_erro(
            _cadastro([_municipio(pendencias_verificacao=["url_diario_oficial:nao_encontrado"])]),
            "nao e campo da entrada",
        )

    def test_slug_escrito_a_mao_e_recalculado(self):
        # A classe de bug mais provavel do cadastro: slug acentuado digitado.
        self._unico_erro(
            _cadastro([_municipio(nome="São Roque do Canaã", slug="sao-roque-do-canaã")]),
            "difere de comum.slug(nome)",
        )

    def test_codigo_ibge_fora_da_forma(self):
        self._unico_erro(
            _cadastro([_municipio(codigo_ibge=5205002)]),
            "7 digitos comecando com 32",
        )

    def test_alias_colide_entre_municipios(self):
        # A colisao e propriedade GLOBAL do arquivo: nenhuma leitura isolada de
        # uma entrada a veria.
        cadastro = _cadastro(
            [_municipio(), _municipio_vitoria(aliases=["Serra"])]
        )
        self._unico_erro(cadastro, "colide com nome ou alias de 'serra'")

    def test_alias_redundante_com_o_nome_e_aviso(self):
        erros, avisos = self._rodar(_cadastro([_municipio(aliases=["SERRA"])]))
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("redundante com o proprio nome", avisos[0])

    def test_chave_desconhecida_em_municipio(self):
        self._unico_erro(
            _cadastro([_municipio(populacao=500000)]),
            "chave desconhecida: populacao",
        )

    # ------------------------------------------------------ total_esperado

    def test_total_esperado_abaixo_do_piso_e_erro(self):
        rel = validar.Relatorio()
        validar.valida_cadastro_municipios(
            rel, _cadastro(total_esperado=77), CATALOGO_DE_TESTE
        )
        erros, _ = _mensagens(rel)
        self.assertTrue(any("o ES nunca teve menos de 78" in m for m in erros), erros)

    def test_total_esperado_acima_de_78_e_aviso_e_nao_erro(self):
        # O 79o municipio criado por lei nao pode reprovar o repositorio: o
        # literal 78 e piso, e a contagem que vale vem do arquivo.
        municipios = [_municipio()] * 79
        rel = validar.Relatorio()
        validar.valida_cadastro_municipios(
            rel, _cadastro(municipios, total_esperado=79), CATALOGO_DE_TESTE
        )
        erros, avisos = _mensagens(rel)
        self.assertEqual([m for m in erros if m.startswith("total_esperado")], [])
        self.assertTrue(any("confira contra o IBGE" in m for m in avisos), avisos)

    def test_len_municipios_diferente_de_total_esperado(self):
        rel = validar.Relatorio()
        validar.valida_cadastro_municipios(
            rel, _cadastro(total_esperado=78), CATALOGO_DE_TESTE
        )
        erros, _ = _mensagens(rel)
        self.assertTrue(any(m.startswith("len(municipios)") for m in erros), erros)

    # --------------------------------------------------- orgaos_vinculados

    def test_orgao_com_url_nula_sem_pendencia(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(url=None)]),
            "url null sem a pendencia 'url:nao_encontrado'",
        )

    def test_chave_desconhecida_em_orgao(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(telefone="2733333333")]),
            "chave desconhecida: telefone",
        )

    def test_chave_obrigatoria_ausente_em_orgao(self):
        orgao = _orgao()
        del orgao["sigla"]
        self._unico_erro(_cadastro(orgaos=[orgao]), "chave obrigatoria ausente: sigla")

    def test_orgao_id_colidindo_com_slug_de_municipio(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(id="serra")]),
            "colide com slug de municipio",
        )

    def test_camara_com_dois_municipios(self):
        self._unico_erro(
            _cadastro(
                [_municipio(), _municipio_vitoria()],
                orgaos=[_orgao(municipios_slugs=["serra", "vitoria"])],
            ),
            "exige exatamente 1 municipio",
        )

    def test_consorcio_sem_esfera_intermunicipal(self):
        orgao = _orgao(
            id="consorcio-caparao",
            nome="Consorcio Publico do Caparao",
            natureza="consorcio_intermunicipal",
            esfera="municipal",
            municipios_slugs=["serra"],
        )
        self._unico_erro(_cadastro(orgaos=[orgao]), "exige esfera 'intermunicipal'")

    def test_orgao_com_slug_inexistente(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(municipios_slugs=["ilha-de-fora"])]),
            "aponta para slug inexistente",
        )

    def test_orgao_sem_verificado_em(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(verificado_em=None)]),
            "verificado_em e obrigatorio",
        )

    # --- 'evidencia' no orgao: o campo que impede jurisdicao inventada --------

    def test_orgao_sem_evidencia(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(evidencia=None)]),
            "evidencia ausente ou vazia",
        )

    def test_orgao_com_evidencia_so_de_espacos(self):
        # Espaco em branco nao e evidencia: sem o .strip() a regra seria
        # contornavel com uma string vazia disfarcada.
        self._unico_erro(
            _cadastro(orgaos=[_orgao(evidencia="   ")]),
            "evidencia ausente ou vazia",
        )

    def test_consorcio_com_13_municipios_e_evidencia_passa(self):
        # O caso REAL que a apuracao de 2026-10-02 produziu, reduzido a dois
        # municipios: consorcio intermunicipal com composicao preenchida, sem
        # pendencia de municipios_slugs, nao gera erro nenhum.
        orgao = _orgao(
            id="cim-exemplo",
            nome="Consorcio Publico de Exemplo",
            natureza="consorcio_intermunicipal",
            esfera="intermunicipal",
            municipios_slugs=["serra", "vitoria"],
            evidencia="composicao lida na pagina institucional do consorcio em 2026-10-02",
            pendencias_verificacao=[],
        )
        erros, _avisos = self._rodar(
            _cadastro([_municipio(), _municipio_vitoria()], orgaos=[orgao])
        )
        self.assertEqual(erros, [])

    # --- 'aliases' no orgao --------------------------------------------------

    def test_orgao_com_aliases_nao_lista(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(aliases="Camara da Serra")]),
            "aliases deve ser uma lista",
        )

    def test_orgao_com_alias_vazio(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(aliases=["  "])]),
            "alias vazio ou nao textual",
        )

    def test_alias_de_orgao_colidindo_com_municipio(self):
        # A colisao mais perigosa do cadastro: um alias de orgao que casa com
        # nome de municipio creditaria o ato ao municipio errado.
        self._unico_erro(
            _cadastro(orgaos=[_orgao(aliases=["Serra"])]),
            "colide com slug de municipio",
        )

    def test_alias_de_orgao_repetido(self):
        self._unico_erro(
            _cadastro(orgaos=[_orgao(aliases=["Camara da Serra", "camara da serra"])]),
            "repetido no orgao",
        )

    def test_alias_de_orgao_redundante_com_o_nome_e_aviso(self):
        erros, avisos = self._rodar(
            _cadastro(orgaos=[_orgao(aliases=["Camara Municipal da Serra"])])
        )
        self.assertEqual(erros, [])
        self.assertTrue(any("redundante com o proprio nome" in a for a in avisos), avisos)


class TesteValidadorDeEscopo(unittest.TestCase):
    """Reforco de secao 9.3: o campo 'municipio' de dados/ resolve no cadastro."""

    def _rodar(self, **mudancas):
        registro = {"uf": "ES", "municipio": "Serra", "esfera": "municipal"}
        registro.update(mudancas)
        rel = validar.Relatorio()
        validar.valida_escopo(rel, "dados/x.json", registro, comum.indice_municipios())
        return _mensagens(rel)

    def test_nome_oficial_passa(self):
        self.assertEqual(self._rodar(), ([], []))

    def test_os_dois_padroes_sem_municipio_passam(self):
        self.assertEqual(self._rodar(municipio="Âmbito estadual (ES)"), ([], []))
        self.assertEqual(
            self._rodar(municipio="Diversos (ES) - Linhares e região"), ([], [])
        )

    def test_grafia_divergente_e_erro(self):
        # Erro, e nao aviso: o nome e chave de agregacao da cobertura, e um
        # registro com grafia divergente nao desaparece — ele conta errado.
        erros, _ = self._rodar(municipio="Santa Maria do Jetibá")
        self.assertEqual(len(erros), 1, erros)
        self.assertIn("nao consta de fontes/municipios-es.json", erros[0])

    def test_alias_e_aviso_com_o_nome_oficial(self):
        erros, avisos = self._rodar(municipio="Cachoeiro do Itapemirim")
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("Cachoeiro de Itapemirim", avisos[0])

    def test_nome_de_orgao_vinculado_e_aviso(self):
        erros, avisos = self._rodar(municipio="Camara Municipal de Aracruz")
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("e nome de orgao vinculado", avisos[0])

    def test_intermunicipal_cuja_sede_resolve_e_aviso(self):
        erros, avisos = self._rodar(
            municipio="Divino de São Lourenço", esfera="intermunicipal"
        )
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn("nao credita cobertura", avisos[0])


class TesteValidadorDeDescobertas(unittest.TestCase):
    """Reforco de secao 9.4, com o dict de quarentena em memoria."""

    CADASTRO = {"ibge_consultado_em": "2026-10-01", "total_esperado": 78}

    def _rodar(self, achado=None, **topo):
        dados = {"gerado_em": "2026-10-01", "achados": [achado] if achado else []}
        dados.update(topo)
        rel = validar.Relatorio()
        validar.valida_descobertas(rel, dados, self.CADASTRO, comum.indice_municipios())
        return _mensagens(rel)

    def _achado(self, **mudancas):
        achado = {
            "chave": "selecao-es:exemplo",
            "fonte_id": "selecao-es",
            "orgao": "SEDU",
            "titulo": "Processo seletivo",
            "url": "https://selecao.es.gov.br/",
            "primeira_deteccao": "2026-09-30",
            "ultima_deteccao": "2026-10-01",
            "no_repositorio": False,
        }
        achado.update(mudancas)
        return achado

    def _sobre(self, mensagens, trecho):
        return [m for m in mensagens if trecho in m]

    # ------------------------------------------- tolerancia de legado (9.4)
    #
    # Os quatro casos que a regra existe para distinguir. O '<=' da fronteira e
    # MEDIDO: 2 dos 37 achados versionados tem primeira_deteccao igual a
    # ibge_consultado_em, e com '<' eles virariam erro — o oposto da tolerancia.

    def test_legado_anterior_a_fronteira_e_aviso(self):
        erros, avisos = self._rodar(self._achado(primeira_deteccao="2026-09-23"))
        self.assertEqual(self._sobre(erros, "categoria"), [])
        self.assertEqual(len(self._sobre(avisos, "sem 'categoria'")), 1, avisos)
        self.assertEqual(len(self._sobre(avisos, "sem 'municipio_escopo'")), 1, avisos)

    def test_legado_na_fronteira_e_aviso(self):
        erros, avisos = self._rodar(self._achado(primeira_deteccao="2026-10-01"))
        self.assertEqual(self._sobre(erros, "categoria"), [])
        self.assertEqual(len(self._sobre(avisos, "sem 'categoria'")), 1, avisos)

    def test_posterior_a_fronteira_e_erro(self):
        erros, _ = self._rodar(self._achado(primeira_deteccao="2026-10-02"))
        self.assertEqual(
            sorted(erros),
            [
                "campo obrigatorio ausente: 'categoria'",
                "campo obrigatorio ausente: 'municipio_escopo'",
            ],
        )

    def test_categoria_invalida_e_erro_nos_tres_casos(self):
        for data in ("2026-09-23", "2026-10-01", "2026-10-02"):
            erros, _ = self._rodar(
                self._achado(primeira_deteccao=data, categoria="lixo")
            )
            self.assertEqual(
                len(self._sobre(erros, "categoria fora do vocabulario")), 1, (data, erros)
            )

    # ------------------------------------------------- demais linhas de 9.4

    def test_oportunidade_com_confianca_alta_e_erro(self):
        erros, _ = self._rodar(
            self._achado(
                categoria="oportunidade",
                municipio_escopo="municipal",
                municipio_slug="serra",
                municipio_codigo_ibge=3205002,
                municipio_confianca="alta",
            )
        )
        self.assertEqual(len(self._sobre(erros, "portal de terceiro")), 1, erros)

    def test_ato_de_diario_com_prazo_de_inscricao_e_erro(self):
        erros, _ = self._rodar(
            self._achado(
                categoria="ato_diario",
                municipio_escopo="municipal",
                municipio_slug="serra",
                municipio_confianca="alta",
                inscricoes={"inicio": None, "fim": "2026-10-20"},
            )
        )
        self.assertEqual(len(self._sobre(erros, "inscricoes.fim preenchido")), 1, erros)

    def test_ato_de_diario_sem_slug_exige_escopo_que_explique(self):
        erros, _ = self._rodar(
            self._achado(categoria="ato_diario", municipio_escopo="municipal")
        )
        self.assertEqual(len(self._sobre(erros, "exige municipio_escopo")), 1, erros)

    def test_codigo_ibge_incoerente_com_o_slug(self):
        erros, _ = self._rodar(
            self._achado(
                categoria="oportunidade",
                municipio_escopo="municipal",
                municipio_slug="serra",
                municipio_codigo_ibge=3205309,
            )
        )
        self.assertEqual(len(self._sobre(erros, "incoerente")), 1, erros)

    def test_origem_sem_slug_e_contradicao(self):
        erros, _ = self._rodar(
            self._achado(
                categoria="oportunidade",
                municipio_escopo="estadual",
                municipio_slug=None,
                municipio_origem="nome",
            )
        )
        self.assertEqual(len(self._sobre(erros, "contradicao")), 1, erros)

    def test_origem_ausente_e_ok(self):
        erros, _ = self._rodar(
            self._achado(categoria="oportunidade", municipio_escopo="estadual")
        )
        self.assertEqual(erros, [])

    def test_contadores_de_nao_mapeado_trocados(self):
        candidato = {
            "nome_detectado": "santa maria ate a",
            "ocorrencias": 1,
            "paginas_distintas": 2,
            "com_marca_uf": False,
            "exemplos": [],
            "primeira_deteccao": "2026-10-01",
            "ultima_deteccao": "2026-10-01",
        }
        erros, avisos = self._rodar(municipios_nao_mapeados=[candidato])
        self.assertEqual(len(self._sobre(erros, "contadores trocados")), 1, erros)
        # Lista nao vazia e pendencia de curadoria, nao defeito: aviso.
        self.assertEqual(len(self._sobre(avisos, "curadoria pendente")), 1, avisos)

    def test_exemplo_de_nao_mapeado_que_nao_e_objeto_e_erro(self):
        # Defeito achado pela auditoria do item 21: a lista era conferida e a
        # FORMA de cada item nao, e o arquivo passava com 0 erros enquanto o
        # coletor caia com AttributeError em exemplo.get("url").
        candidato = {
            "nome_detectado": "santa maria ate a",
            "ocorrencias": 3,
            "paginas_distintas": 2,
            "com_marca_uf": True,
            "exemplos": ["https://ioes.dio.es.gov.br/pagina/1", {"url": "u"}],
            "primeira_deteccao": "2026-10-01",
            "ultima_deteccao": "2026-10-01",
        }
        erros, _ = self._rodar(municipios_nao_mapeados=[candidato])
        achados = self._sobre(erros, "exemplos[0] deve ser um objeto")
        self.assertEqual(len(achados), 1, erros)
        self.assertIn("str", achados[0])

    def test_cobertura_com_conjuntos_incoerentes(self):
        bloco = {
            "total_municipios": 78,
            "com_achado_na_janela": 2,
            "com_achado_acumulado": 1,
            "slugs_com_achado_acumulado": ["serra"],
            "slugs_com_sinal": ["vitoria"],
            "slugs_com_sinal_historico": [],
            "vistos_pela_primeira_vez": ["serra"],
        }
        erros, _ = self._rodar(cobertura_municipios=bloco)
        self.assertEqual(len(self._sobre(erros, "maior que com_achado_acumulado")), 1, erros)
        self.assertEqual(
            len(self._sobre(erros, "vistos_pela_primeira_vez tem slug fora")), 1, erros
        )
        self.assertEqual(
            len(self._sobre(erros, "slugs_com_sinal tem slug fora")), 1, erros
        )

    def test_cobertura_com_lista_fora_de_ordem_e_slug_inexistente(self):
        bloco = {
            "total_municipios": 78,
            "com_achado_na_janela": 0,
            "com_achado_acumulado": 2,
            "slugs_com_achado_acumulado": ["vitoria", "serra"],
            "slugs_com_sinal": [],
            "slugs_com_sinal_historico": ["ilha-de-fora"],
            "vistos_pela_primeira_vez": [],
        }
        erros, _ = self._rodar(cobertura_municipios=bloco)
        self.assertEqual(len(self._sobre(erros, "nao esta ordenada")), 1, erros)
        self.assertEqual(len(self._sobre(erros, "slug inexistente no cadastro")), 1, erros)

    def test_total_de_municipios_vem_do_cadastro(self):
        erros, _ = self._rodar(cobertura_municipios={"total_municipios": 77})
        self.assertEqual(len(self._sobre(erros, "difere de total_esperado")), 1, erros)

    def test_reconciliacao_com_erro_e_divergencia_sao_avisos(self):
        bloco = {
            "status": "erro",
            "erro": "URLError: timeout",
            "ausentes_no_cadastro": [{"codigo_ibge": 3200000, "nome": "Novo Municipio"}],
            "excedentes_no_cadastro": [],
        }
        erros, avisos = self._rodar(reconciliacao_ibge=bloco)
        self.assertEqual(erros, [])
        self.assertEqual(len(self._sobre(avisos, "reconciliacao com o IBGE falhou")), 1, avisos)
        self.assertEqual(len(self._sobre(avisos, "ausentes_no_cadastro")), 1, avisos)

    def test_chave_de_topo_ausente_e_aviso(self):
        _erros, avisos = self._rodar()
        for chave in ("cobertura_municipios", "municipios_nao_mapeados", "reconciliacao_ibge"):
            self.assertEqual(len(self._sobre(avisos, "chave '%s' ausente" % chave)), 1, avisos)


# --------------------------------------------------------------- consumidores
#
# README, e-mail e o proprio arquivo do workflow. O que estes casos travam nao e
# formatacao: e a regra de §11.1 ("bloco de cobertura AUSENTE nao zera o que vem
# do cadastro"), o estado de tres valores do e-mail e os quatro gatilhos do
# workflow — tres coisas que, quebradas, passariam silenciosamente no CI.


class TesteCoberturaNoReadme(unittest.TestCase):
    """Secao "Cobertura por municipio" e as tres linhas novas do Panorama.

    Os casos apontam gerar_readme.CAMINHO_DESCOBERTAS para um arquivo temporario
    e usam o cadastro e os registros REAIS: o ponto do caso e justamente que
    'Registros curados' e 'Canal principal' continuem corretos quando a coleta
    ainda nao publicou cobertura.
    """

    @classmethod
    def setUpClass(cls):
        cls.cadastro = comum.carregar_municipios()
        cls.indice = comum.indice_municipios()
        cls.registros = comum.carregar_registros()
        cls.referencia = dt.date(2026, 10, 1)

    def setUp(self):
        self._original = gerar_readme.CAMINHO_DESCOBERTAS
        self._dir = tempfile.mkdtemp()
        gerar_readme.CAMINHO_DESCOBERTAS = os.path.join(self._dir, "descobertas.json")

    def tearDown(self):
        gerar_readme.CAMINHO_DESCOBERTAS = self._original
        shutil.rmtree(self._dir)

    def _gravar(self, **chaves):
        dados = {
            "gerado_em": "2026-10-01",
            "janela_dias": 90,
            "total_achados": 2,
            "achados": [
                {
                    "chave": "op-1",
                    "categoria": "oportunidade",
                    "titulo": "Edital de concurso",
                    "orgao": "Prefeitura de Serra",
                    "url": "https://exemplo.es.gov.br/edital",
                    "fonte_tipo": "portal_concursos",
                    "primeira_deteccao": "2026-10-01",
                },
                {
                    "chave": "ato-1",
                    "categoria": "ato_diario",
                    "titulo": "Portaria de nomeacao",
                    "orgao": "Prefeitura de Vitoria",
                    "url": "https://ioes.dio.es.gov.br/dom",
                    "fonte_tipo": "diario_oficial",
                    "primeira_deteccao": "2026-10-01",
                },
            ],
        }
        dados.update(chaves)
        with open(gerar_readme.CAMINHO_DESCOBERTAS, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False)
        return dados

    def _linhas_de_municipio(self, bloco):
        trecho = bloco.split("<summary>")[1].split("</details>")[0]
        return [
            linha
            for linha in trecho.splitlines()
            if linha.startswith("| ")
            and not linha.startswith("| ---")
            and "| Município |" not in linha
        ]

    def _montar(self):
        return gerar_readme.monta_bloco(
            self.registros, self.referencia, self.cadastro, self.indice
        )

    def test_ato_de_diario_fica_fora_das_descobertas(self):
        self._gravar()
        achados = gerar_readme.carregar_descobertas()
        self.assertEqual([a["chave"] for a in achados], ["op-1"])

    def test_sem_bloco_de_cobertura_panorama_zera_e_coluna_sai_travessao(self):
        self._gravar()
        bloco = self._montar()

        self.assertIn("| Municípios do ES monitorados | 0 |", bloco)
        self.assertIn("| Municípios com registro curado | 0 |", bloco)
        self.assertIn("| Municípios com ato detectado na janela da coleta | 0 |", bloco)

        linhas = self._linhas_de_municipio(bloco)
        self.assertEqual(len(linhas), 78)
        # Coluna 'Ato detectado' (terceira) '—' em TODAS as linhas: sem o bloco
        # publicado nao ha como afirmar ato nenhum.
        self.assertEqual(
            {linha.split("|")[3].strip() for linha in linhas}, {"—"}
        )
        # ... e as duas colunas que NAO dependem da coleta seguem corretas: 15
        # municipios com registro curado (o mesmo numero de cobertura()) e canal
        # principal preenchido nas 78 linhas.
        com_curado = [linha for linha in linhas if linha.split("|")[2].strip() != "0"]
        self.assertEqual(len(com_curado), 15)
        self.assertEqual(
            [linha for linha in linhas if linha.split("|")[4].strip() == "—"], []
        )
        self.assertIn("| Vitória | 6 | — | DOM/AMUNES |", bloco)

    def test_bloco_e_deterministico_entre_duas_geracoes(self):
        self._gravar()
        self.assertEqual(self._montar(), self._montar())

    def test_com_bloco_de_cobertura_os_numeros_e_os_vistos_vem_do_arquivo(self):
        self._gravar(
            cobertura_municipios={
                "total_municipios": 78,
                "com_registro_curado": 15,
                "com_achado_na_janela": 41,
                "com_achado_acumulado": 2,
                "slugs_com_achado_acumulado": ["serra", "sooretama"],
            }
        )
        bloco = self._montar()
        self.assertIn("| Municípios do ES monitorados | 78 |", bloco)
        self.assertIn("| Municípios com registro curado | 15 |", bloco)
        self.assertIn("| Municípios com ato detectado na janela da coleta | 41 |", bloco)

        linhas = self._linhas_de_municipio(bloco)
        with_ato = [linha for linha in linhas if linha.split("|")[3].strip() == "✓"]
        self.assertEqual(len(with_ato), 2)
        # A Serra e o UNICO municipio com 'diario_oficial_proprio' no cadastro
        # (confirmado por varredura dos 78 caminhos candidatos no IOES), e por
        # isso e tambem o unico lugar onde o dado real exercita a renderizacao
        # de 'Diario proprio' ponta a ponta. Os demais saem como DOM/AMUNES.
        self.assertIn("| Serra | 1 | ✓ | Diário próprio |", bloco)
        self.assertIn("| Sooretama | 0 | ✓ | DOM/AMUNES |", bloco)

    def test_canal_principal_em_texto_legivel(self):
        self.assertEqual(
            gerar_readme.canal_principal(
                {"canais": [{"tipo": "diario_oficial_proprio", "precedencia": 1}]}
            ),
            "Diário próprio",
        )
        # Precedencia 1 ausente: a tabela nao inventa canal a partir do de
        # precedencia 2 — municipio sem canal de consulta primaria e lacuna.
        self.assertEqual(
            gerar_readme.canal_principal(
                {"canais": [{"tipo": "portal_prefeitura", "precedencia": 2}]}
            ),
            "—",
        )
        self.assertEqual(gerar_readme.canal_principal({"canais": []}), "—")


class TesteEstadoDoEmail(unittest.TestCase):
    """carregar_estado()/gravar_estado() com cobertura_vistos e o bloco curto."""

    def setUp(self):
        self._original = gerar_email.CAMINHO_ESTADO
        self._dir = tempfile.mkdtemp()
        gerar_email.CAMINHO_ESTADO = os.path.join(self._dir, ".estado-envios.json")

    def tearDown(self):
        gerar_email.CAMINHO_ESTADO = self._original
        shutil.rmtree(self._dir)

    def _gravar_bruto(self, texto):
        with open(gerar_email.CAMINHO_ESTADO, "w", encoding="utf-8") as fh:
            fh.write(texto)

    def test_estado_sem_cobertura_vistos_devolve_dict_vazio(self):
        self._gravar_bruto(
            json.dumps({"impressoes": {"a": "1"}, "descobertas": {"k": "2026-09-01"}})
        )
        impressoes, descobertas, cobertura = gerar_email.carregar_estado()
        self.assertEqual(impressoes, {"a": "1"})
        self.assertEqual(descobertas, {"k": "2026-09-01"})
        # {} e nao None: arquivo de versao anterior continua legivel, em vez de
        # ser tratado como primeira execucao (que reanunciaria tudo).
        self.assertEqual(cobertura, {})

    def test_estado_corrompido_devolve_tres_vazios(self):
        self._gravar_bruto("{isto nao e json")
        self.assertEqual(gerar_email.carregar_estado(), ({}, {}, {}))

    def test_estado_ausente_devolve_tres_vazios(self):
        self.assertEqual(gerar_email.carregar_estado(), ({}, {}, {}))

    def test_round_trip_preserva_as_tres_chaves(self):
        gerar_email.DIR_EMAIL = self._dir
        gerar_email.gravar_estado(
            {"id-1": "abc"},
            {"chave-1": "2026-10-01"},
            {"sooretama": "2026-10-01"},
            dt.date(2026, 10, 1),
        )
        self.assertEqual(
            gerar_email.carregar_estado(),
            ({"id-1": "abc"}, {"chave-1": "2026-10-01"}, {"sooretama": "2026-10-01"}),
        )

    def test_municipio_ja_anunciado_nao_volta_ao_resumo(self):
        dados = {
            "cobertura_municipios": {
                "vistos_pela_primeira_vez": ["laranja-da-terra", "sooretama"]
            },
            "municipios_nao_mapeados": [{"nome": "sooretama"}],
        }
        vistos = {"sooretama": "2026-09-20"}
        slugs, nao_mapeados, estado = gerar_email.classificar_cobertura(
            dados, vistos, False, dt.date(2026, 10, 1)
        )
        self.assertEqual(slugs, ["laranja-da-terra"])
        self.assertEqual(nao_mapeados, 1)
        # A data do primeiro anuncio de Sooretama e preservada; a de Laranja da
        # Terra e a de hoje.
        self.assertEqual(
            estado, {"sooretama": "2026-09-20", "laranja-da-terra": "2026-10-01"}
        )

        # --forcar reanuncia, mas NAO reescreve a data do primeiro anuncio.
        slugs, _nao_mapeados, estado = gerar_email.classificar_cobertura(
            dados, vistos, True, dt.date(2026, 10, 1)
        )
        self.assertEqual(slugs, ["laranja-da-terra", "sooretama"])
        self.assertEqual(estado["sooretama"], "2026-09-20")

    def test_sem_bloco_de_cobertura_nada_a_anunciar(self):
        slugs, nao_mapeados, estado = gerar_email.classificar_cobertura(
            {}, {}, False, dt.date(2026, 10, 1)
        )
        self.assertEqual((slugs, nao_mapeados, estado), ([], 0, {}))

    def test_bloco_curto_so_aparece_quando_ha_conteudo(self):
        nomes = {"sooretama": "Sooretama"}
        self.assertEqual(gerar_email._linhas_cobertura([], nomes, 0), [])
        texto = "\n".join(gerar_email._linhas_cobertura(["sooretama"], nomes, 2))
        self.assertIn("primeiro ato detectado em: Sooretama.", texto)
        self.assertIn("sem mapeamento no cadastro: 2", texto)

    def test_ato_de_diario_nao_entra_no_resumo(self):
        achados = [
            {"chave": "op-1", "categoria": "oportunidade", "primeira_deteccao": "2026-10-01"},
            {"chave": "ato-1", "categoria": "ato_diario", "primeira_deteccao": "2026-10-01"},
        ]
        novos, estado = gerar_email.classificar_descobertas(
            achados, dt.date(2026, 10, 1), {}, False
        )
        self.assertEqual([a["chave"] for a in novos], ["op-1"])
        # O ato tambem nao entra no estado: ele nunca sera "anunciado" por aqui,
        # e guardar a chave dele so faria o arquivo crescer sem uso.
        self.assertEqual(list(estado), ["op-1"])


class TesteWorkflow(unittest.TestCase):
    """O .yml lido como TEXTO. Sem pyyaml (dependencia externa e proibida), e o
    que importa aqui sao presencas literais: um gatilho ou uma clausula que
    desaparecesse nao reprovaria nenhum outro caso desta suite.
    """

    @classmethod
    def setUpClass(cls):
        caminho = os.path.join(
            comum.RAIZ, ".github", "workflows", "monitoramento.yml"
        )
        with open(caminho, encoding="utf-8") as fh:
            cls.texto = fh.read()

    def test_fontes_nos_dois_gatilhos(self):
        antes, _, depois = self.texto.partition("\n  push:")
        _, _, pull_request = antes.partition("\n  pull_request:")
        self.assertIn('- "fontes/**"', pull_request)
        self.assertIn('- "fontes/**"', depois.split("\npermissions:")[0])
        # O proprio workflow nos dois, para que editar o YAML passe pela
        # validacao que ele define.
        self.assertEqual(
            self.texto.count('- ".github/workflows/monitoramento.yml"'), 2
        )
        # descobertas/** fora dos dois; README.md so no pull_request.
        self.assertNotIn('"descobertas/**"', self.texto)
        self.assertEqual(self.texto.count('- "README.md"'), 1)

    def test_condicao_da_issue_tem_as_quatro_clausulas(self):
        for clausula in (
            "steps.coleta.outputs.novos != '0'",
            "steps.coleta.outputs.primeira_vez != '0'",
            "steps.coleta.outputs.nao_mapeados != '0'",
            "steps.coleta.outputs.divergencia_ibge == '1'",
        ):
            self.assertIn(clausula, self.texto)
        # Ato de diario e rotina diaria: nao pode abrir issue.
        self.assertNotIn("steps.coleta.outputs.atos_diario_novos", self.texto)

    def test_titulo_da_issue_montado_com_if_then_fi(self):
        trecho = self.texto.split("Abrir issue com os achados novos")[1].split(
            "\n  enviar_email:"
        )[0]
        # Quatro partes, uma por motivo. 'primeira_vez' e a que o passe anterior
        # esquecia: depois de 'novos' passar a contar so oportunidades, um dia
        # cuja unica noticia fosse "primeiro ato em Sooretama" ficaria sem titulo.
        montagem = trecho.split('partes=""')[1].split('titulo="Coleta')[0]
        self.assertEqual(montagem.count("if ["), 4)
        self.assertEqual(montagem.count("; then"), 4)
        self.assertEqual(montagem.count("fi\n"), 4)
        self.assertEqual(montagem.count('partes="${partes:+$partes, }'), 3)
        # Nunca '[ cond ] && atribuicao': com set -euo pipefail o passo abortaria
        # no primeiro teste falso.
        self.assertNotIn("] && partes", trecho)
        self.assertIn('titulo="Coleta automatica: ${partes:-sem novidade}', trecho)

    def test_suite_de_testes_roda_nos_dois_jobs(self):
        self.assertEqual(self.texto.count("python3 ferramentas/testes.py"), 2)
        validar, _, atualizar = self.texto.partition("\n  atualizar:")
        # No job validar, ANTES de validar.py; no job atualizar, antes da
        # revalidacao — o job validar nao roda na execucao agendada.
        self.assertLess(
            validar.index("python3 ferramentas/testes.py"),
            validar.index("python3 ferramentas/validar.py"),
        )
        self.assertLess(
            atualizar.index("python3 ferramentas/testes.py"),
            atualizar.index("Revalidar depois das alteracoes"),
        )

    def test_decisoes_que_o_design_manda_manter(self):
        # Sem needs: validar no job atualizar, e git add SEM fontes/ (o cadastro
        # e editado por humano, e ficar fora do git add e a garantia mecanica).
        # A comparacao e por LINHA, e nao por substring: o comentario que explica
        # a ausencia cita "needs: validar" no texto corrido.
        self.assertEqual(
            [l for l in self.texto.splitlines() if l.strip() == "needs: validar"], []
        )
        linha = [
            l for l in self.texto.splitlines() if l.strip().startswith("git add -A")
        ]
        self.assertEqual(len(linha), 1, linha)
        self.assertNotIn("fontes/", linha[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
