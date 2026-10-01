"""Suite de testes das ferramentas de monitoramento.

unittest da biblioteca padrao, sem rede e sem dependencia externa, executavel
por:

    python3 ferramentas/testes.py

Nenhum caso aqui pode depender de rede: o workflow roda esta suite no job de
validacao, e teste que depende de terceiro nao pode reprovar PR.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

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
        # 8, de 'servico autonomo de agua e esgoto de aracruz'. Com o literal 4
        # (o maior nome de municipio) as chaves de orgao de 5 a 8 tokens nunca
        # seriam alcancadas pela poda por prefixo.
        indice = comum.indice_municipios()
        self.assertEqual(indice.max_tokens_nome, 8)

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
            indice.por_chave_nome.get("instituto de previdencia dos servidores de cariacica"),
            "cariacica",
        )
        # Orgao intermunicipal nao resolve para 1 municipio, logo nao entra.
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
        self.assertEqual(origens, {"nome", "sigla"})

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
