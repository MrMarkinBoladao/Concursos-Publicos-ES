"""Script descartavel (nao versionado): gera fontes/municipios-es.json.

Copia codigo_ibge/nome/microrregiao de /projects/sandbox/ibge_es.json, calcula
o slug por comum.slug() e escreve um canal de diario pendente por municipio,
mais as 8 entradas de orgaos_vinculados de design secao 4.1.
"""

import json
import os
import sys

RAIZ = "/projects/sandbox/Concursos-Publicos-ES/.worktrees/cobertura-municipios"
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))

import comum  # noqa: E402

HOJE = "2026-10-01"
ALIASES = {"cachoeiro-de-itapemirim": ["Cachoeiro do Itapemirim", "Cachoeiro"]}

with open("/projects/sandbox/ibge_es.json", encoding="utf-8") as fh:
    ibge = json.load(fh)

municipios = []
for item in sorted(ibge, key=lambda x: x["id"]):
    s = comum.slug(item["nome"])
    municipios.append(
        {
            "codigo_ibge": item["id"],
            "nome": item["nome"],
            "slug": s,
            "aliases": ALIASES.get(s, []),
            "microrregiao": item["microrregiao"]["nome"],
            "canais": [
                {
                    "tipo": "diario_oficial_agregador",
                    "precedencia": 1,
                    "url": "https://ioes.dio.es.gov.br/dom",
                    "fonte_id": "amunes-dom",
                    "estado": "pendente",
                    "evidencia": (
                        "canal esperado do municipio (DOM/AMUNES); sem ato observado "
                        "nesta curadoria"
                    ),
                    "verificado_em": None,
                }
            ],
            "pendencias_verificacao": ["canais:conferir_manual"],
            "verificado_em": HOJE,
        }
    )

orgaos = [
    {
        "id": "camara-aracruz",
        "nome": "Camara Municipal de Aracruz",
        "sigla": None,
        "natureza": "camara_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["aracruz"],
        "url": "https://www.aracruz.es.leg.br/transparencia/concurso-publico",
        "fontes": ["camara-aracruz"],
        "pendencias_verificacao": [],
        "verificado_em": HOJE,
    },
    {
        "id": "camara-cachoeiro-itapemirim",
        "nome": "Camara Municipal de Cachoeiro de Itapemirim",
        "sigla": None,
        "natureza": "camara_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["cachoeiro-de-itapemirim"],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "saae-aracruz",
        "nome": "Servico Autonomo de Agua e Esgoto de Aracruz",
        "sigla": "SAAE",
        "natureza": "autarquia_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["aracruz"],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "codeg-guarapari",
        "nome": "Companhia de Desenvolvimento de Guarapari",
        "sigla": "CODEG",
        "natureza": "empresa_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["guarapari"],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "ipc-cariacica",
        "nome": "Instituto de Previdencia dos Servidores de Cariacica",
        "sigla": "IPC",
        "natureza": "autarquia_municipal",
        "esfera": "municipal",
        "municipios_slugs": ["cariacica"],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "cim-polinorte",
        "nome": "Consorcio Publico da Regiao Polinorte",
        "sigla": "CIM Polinorte",
        "natureza": "consorcio_intermunicipal",
        "esfera": "intermunicipal",
        "municipios_slugs": [],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["municipios_slugs:nao_encontrado", "url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "consorcio-caparao",
        "nome": "Consorcio Publico da Regiao do Caparao",
        "sigla": None,
        "natureza": "consorcio_intermunicipal",
        "esfera": "intermunicipal",
        "municipios_slugs": [],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["municipios_slugs:nao_encontrado", "url:nao_encontrado"],
        "verificado_em": HOJE,
    },
    {
        "id": "aries",
        "nome": "Agencia Reguladora Intermunicipal de Saneamento Basico do ES",
        "sigla": "ARIES",
        "natureza": "agencia_reguladora",
        "esfera": "intermunicipal",
        "municipios_slugs": [],
        "url": None,
        "fontes": [],
        "pendencias_verificacao": ["municipios_slugs:nao_encontrado", "url:nao_encontrado"],
        "verificado_em": HOJE,
    },
]

cadastro = {
    "descricao": (
        "Cadastro canonico dos municipios do ES e dos canais por onde cada um publica "
        "informacao de emprego."
    ),
    "fonte_da_verdade": (
        "IBGE - Localidades, UF 32 "
        "(https://servicodados.ibge.gov.br/api/v1/localidades/estados/32/municipios)"
    ),
    "ibge_consultado_em": HOJE,
    "total_esperado": 78,
    "ultima_atualizacao": HOJE,
    "municipios": municipios,
    "orgaos_vinculados": orgaos,
}

destino = os.path.join(RAIZ, "fontes", "municipios-es.json")
with open(destino, "w", encoding="utf-8") as fh:
    json.dump(cadastro, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print("gravado %s com %d municipios" % (destino, len(municipios)))
