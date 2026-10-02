"""Script descartavel (nao versionado): transcreve o TSV da sondagem para o cadastro.

Le .agents/sondagem-2026-10-01.tsv (saida de ferramentas/sondar_prefeituras.py)
e acrescenta os canais tipados a fontes/municipios-es.json, com evidencia
citando a origem do candidato e o resultado medido.
"""

import json
import os
import sys

RAIZ = "/projects/sandbox/Concursos-Publicos-ES/.worktrees/cobertura-municipios"
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))

HOJE = "2026-10-01"
TSV = os.path.join(RAIZ, ".agents", "sondagem-2026-10-01.tsv")
CADASTRO = os.path.join(RAIZ, "fontes", "municipios-es.json")

# As 6 urls catalogadas elegiveis (slug -> fonte_id), como sondar_prefeituras.py
# as deriva do catalogo, mais a secao de Castelo, sondada a parte (a url
# catalogada nao e portal institucional, logo nao substitui o candidato
# derivado, mas o design manda cadastra-la como secao_concursos).
CATALOGADAS = {
    "anchieta": "prefeitura-anchieta",
    "aracruz": "prefeitura-aracruz",
    "cachoeiro-de-itapemirim": "prefeitura-cachoeiro",
    "santa-maria-de-jetiba": "prefeitura-santa-maria-jetiba",
    "vila-velha": "prefeitura-vila-velha",
    "vitoria": "prefeitura-vitoria",
}

EXTRAS = [
    # slug, tipo, rotulo de status, url, estado, pendencia, fonte_id
    (
        "castelo",
        "secao_concursos",
        "200",
        "https://educacao.castelo.es.gov.br/processos-seletivos",
        "confirmado",
        "-",
        "prefeitura-castelo",
    ),
]


def evidencia(fonte_id, url, rotulo, estado):
    origem = (
        "url catalogada em fontes.json (%s)" % fonte_id
        if fonte_id
        else "candidato derivado do slug"
    )
    if rotulo.startswith("timeout"):
        medido = "sondagem de %s deu timeout nas 2 tentativas" % HOJE
    elif rotulo.startswith("nxdomain"):
        medido = "host nao resolveu em DNS na sondagem de %s (2 tentativas)" % HOJE
    elif rotulo.startswith("tls") or rotulo.startswith("erro"):
        medido = "sondagem de %s falhou em %s (2 tentativas)" % (HOJE, rotulo.split()[0])
    elif rotulo in ("301", "302", "303", "307", "308"):
        medido = (
            "sondagem de %s respondeu HTTP %s, sem seguir o redirecionamento" % (HOJE, rotulo)
        )
    elif rotulo in ("403", "406", "429"):
        medido = (
            "sondagem de %s respondeu HTTP %s: o host existe e responde, mas bloqueia robo"
            % (HOJE, rotulo)
        )
    else:
        medido = "sondagem de %s respondeu HTTP %s" % (HOJE, rotulo)
    return "%s; %s" % (origem, medido)


linhas = []
with open(TSV, encoding="utf-8") as fh:
    for linha in fh:
        if not linha.strip():
            continue
        slug, tipo, rotulo, url, estado, pendencia = linha.rstrip("\n").split("\t")
        linhas.append((slug, tipo, rotulo, url, estado, pendencia, CATALOGADAS.get(slug)))
linhas.extend(EXTRAS)

por_slug = {}
for slug, tipo, rotulo, url, estado, pendencia, fonte_id in linhas:
    if estado == "nao_entra":
        continue
    por_slug.setdefault(slug, []).append(
        {
            "tipo": tipo,
            "precedencia": None,
            "url": url,
            "fonte_id": fonte_id,
            "estado": estado,
            "evidencia": evidencia(fonte_id, url, rotulo, estado),
            "verificado_em": HOJE if estado == "confirmado" else None,
            "_pendencia": pendencia,
        }
    )

with open(CADASTRO, encoding="utf-8") as fh:
    cadastro = json.load(fh)

for entrada in cadastro["municipios"]:
    novos = por_slug.get(entrada["slug"], [])
    # Ordem de utilidade para a curadoria humana: canal confirmado antes de
    # canal pendente; empate resolvido pelo tipo, para a ordem ser determinista.
    novos.sort(key=lambda c: (c["estado"] != "confirmado", c["tipo"]))
    precedencia = 2
    pendencias = list(entrada["pendencias_verificacao"])
    for canal in novos:
        canal["precedencia"] = precedencia
        precedencia += 1
        pend = canal.pop("_pendencia")
        if pend != "-" and pend not in pendencias:
            pendencias.append(pend)
        entrada["canais"].append(
            {
                "tipo": canal["tipo"],
                "precedencia": canal["precedencia"],
                "url": canal["url"],
                "fonte_id": canal["fonte_id"],
                "estado": canal["estado"],
                "evidencia": canal["evidencia"],
                "verificado_em": canal["verificado_em"],
            }
        )
    entrada["pendencias_verificacao"] = pendencias

with open(CADASTRO, "w", encoding="utf-8") as fh:
    json.dump(cadastro, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

print(
    "canais acrescentados: %d em %d municipios"
    % (sum(len(v) for v in por_slug.values()), len(por_slug))
)
