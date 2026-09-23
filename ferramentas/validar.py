#!/usr/bin/env python3
"""Valida os registros de oportunidades do repositorio.

Verifica estrutura do JSON, vocabulario dos campos, coerencia entre status e
diretorio, coerencia de datas, escopo geografico (ES) e duplicidade.

Uso:
    python3 ferramentas/validar.py
    python3 ferramentas/validar.py --json    # saida legivel por maquina

Codigo de saida 0 quando nao ha ERROS (avisos nao reprovam), 1 caso contrario.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

CAMPOS_OBRIGATORIOS = [
    "id",
    "orgao",
    "orgao_sigla",
    "esfera",
    "municipio",
    "uf",
    "tipo",
    "cargos",
    "vagas_imediatas_total",
    "cadastro_reserva",
    "escolaridade",
    "remuneracao",
    "beneficios",
    "jornada",
    "edital_numero",
    "publicacao",
    "inscricoes",
    "prova",
    "banca",
    "status",
    "regime",
    "validade",
    "links",
    "fontes",
    "historico_status",
    "ultima_verificacao",
    "ultima_atualizacao",
    "observacoes",
]

CAMPOS_CARGO = [
    "nome",
    "area",
    "vagas_imediatas",
    "cadastro_reserva",
    "escolaridade",
    "requisitos",
    "remuneracao",
    "jornada",
]

RE_ID = re.compile(r"^(concurso|ps)-[a-z0-9-]+-\d{4}$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Relatorio:
    def __init__(self):
        self.erros = []
        self.avisos = []

    def erro(self, arquivo, mensagem):
        self.erros.append({"arquivo": arquivo, "mensagem": mensagem})

    def aviso(self, arquivo, mensagem):
        self.avisos.append({"arquivo": arquivo, "mensagem": mensagem})


def _valida_data(rel, arquivo, rotulo, valor, obrigatorio=False):
    """Confere formato ISO. Devolve o date correspondente, ou None."""
    if valor is None or valor == comum.AUSENTE:
        if obrigatorio:
            rel.erro(arquivo, "%s e obrigatorio e esta ausente" % rotulo)
        return None
    if not isinstance(valor, str) or not RE_DATA.match(valor):
        rel.erro(arquivo, "%s='%s' nao esta no formato AAAA-MM-DD" % (rotulo, valor))
        return None
    data = comum.data_ou_none(valor)
    if data is None:
        rel.erro(arquivo, "%s='%s' nao e uma data valida" % (rotulo, valor))
    return data


def valida_estrutura(rel, arquivo, reg):
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in reg:
            rel.erro(arquivo, "campo obrigatorio ausente: '%s'" % campo)

    if not isinstance(reg.get("cargos"), list) or not reg.get("cargos"):
        rel.erro(arquivo, "'cargos' deve ser uma lista com pelo menos um item")
    else:
        for i, cargo in enumerate(reg["cargos"]):
            if not isinstance(cargo, dict):
                rel.erro(arquivo, "cargos[%d] deve ser um objeto" % i)
                continue
            for campo in CAMPOS_CARGO:
                if campo not in cargo:
                    rel.erro(arquivo, "cargos[%d] sem o campo '%s'" % (i, campo))

    for campo, tipo, rotulo in (
        ("remuneracao", dict, "objeto"),
        ("inscricoes", dict, "objeto"),
        ("prova", dict, "objeto"),
        ("links", dict, "objeto"),
        ("beneficios", list, "lista"),
        ("fontes", list, "lista"),
        ("historico_status", list, "lista"),
    ):
        if campo in reg and not isinstance(reg[campo], tipo):
            rel.erro(arquivo, "'%s' deve ser um %s" % (campo, rotulo))


def valida_vocabulario(rel, arquivo, reg):
    if reg.get("status") not in comum.STATUS_VALIDOS:
        rel.erro(arquivo, "status invalido: '%s'" % reg.get("status"))
    if reg.get("esfera") not in comum.ESFERAS_VALIDAS:
        rel.erro(arquivo, "esfera invalida: '%s'" % reg.get("esfera"))
    if reg.get("tipo") not in comum.TIPOS_VALIDOS:
        rel.erro(arquivo, "tipo invalido: '%s'" % reg.get("tipo"))
    if reg.get("regime") not in comum.REGIMES_VALIDOS:
        rel.erro(arquivo, "regime invalido: '%s'" % reg.get("regime"))

    if not RE_ID.match(reg.get("id", "")):
        rel.erro(
            arquivo,
            "id '%s' fora do padrao <tipo>-<orgao>-<recorte>-<ano>" % reg.get("id"),
        )

    esperado = reg.get("id", "") + ".json"
    if os.path.basename(arquivo) != esperado:
        rel.erro(
            arquivo,
            "nome do arquivo difere do id: esperado '%s'" % esperado,
        )

    prefixo = "concurso-" if reg.get("tipo") == "concurso_publico" else "ps-"
    if reg.get("id", "") and not reg["id"].startswith(prefixo):
        rel.erro(
            arquivo,
            "id deveria comecar com '%s' para tipo '%s'" % (prefixo, reg.get("tipo")),
        )


def valida_escopo(rel, arquivo, reg):
    """O repositorio cobre exclusivamente o Espirito Santo."""
    if reg.get("uf") != "ES":
        rel.erro(arquivo, "fora de escopo: uf='%s' (esperado 'ES')" % reg.get("uf"))
    if not reg.get("municipio") or reg.get("municipio") == comum.AUSENTE:
        rel.aviso(arquivo, "municipio nao informado — confirmar a lotacao no ES")


def valida_diretorio(rel, arquivo, reg):
    subdir = os.path.dirname(arquivo)
    permitidos = comum.DIRETORIOS.get(subdir)
    if permitidos is None:
        rel.erro(arquivo, "diretorio desconhecido: '%s'" % subdir)
        return
    if reg.get("status") not in permitidos:
        rel.erro(
            arquivo,
            "status '%s' nao pertence a '%s' (aceitos: %s)"
            % (reg.get("status"), subdir, ", ".join(sorted(permitidos))),
        )

    familia = "concursos" if reg.get("tipo") == "concurso_publico" else "processos-seletivos"
    if not subdir.startswith(familia):
        rel.erro(
            arquivo,
            "tipo '%s' deveria estar sob '%s/', nao '%s'"
            % (reg.get("tipo"), familia, subdir),
        )


def valida_datas(rel, arquivo, reg):
    hoje = comum.hoje()

    verificacao = _valida_data(rel, arquivo, "ultima_verificacao", reg.get("ultima_verificacao"), True)
    atualizacao = _valida_data(rel, arquivo, "ultima_atualizacao", reg.get("ultima_atualizacao"), True)
    publicacao = _valida_data(rel, arquivo, "publicacao", reg.get("publicacao"))

    insc = reg.get("inscricoes") or {}
    inicio = _valida_data(rel, arquivo, "inscricoes.inicio", insc.get("inicio"))
    fim = _valida_data(rel, arquivo, "inscricoes.fim", insc.get("fim"))

    prova = reg.get("prova") or {}
    objetiva = _valida_data(rel, arquivo, "prova.objetiva", prova.get("objetiva"))

    if verificacao and verificacao > hoje:
        rel.erro(arquivo, "ultima_verificacao esta no futuro")
    if atualizacao and verificacao and atualizacao > verificacao:
        rel.erro(arquivo, "ultima_atualizacao e posterior a ultima_verificacao")

    if inicio and fim and inicio > fim:
        rel.erro(arquivo, "inscricoes.inicio e posterior a inscricoes.fim")
    if publicacao and inicio and publicacao > inicio:
        rel.aviso(arquivo, "publicacao posterior ao inicio das inscricoes — confirmar")
    if fim and objetiva and objetiva < fim:
        rel.aviso(arquivo, "prova.objetiva anterior ao fim das inscricoes — confirmar")

    # Coerencia entre o prazo e o status declarado.
    if reg.get("status") == "inscricoes_abertas" and fim and fim < hoje:
        rel.erro(
            arquivo,
            "status 'inscricoes_abertas' mas o prazo terminou em %s — mover para "
            "'encerrados' e atualizar o status" % fim.isoformat(),
        )
    if reg.get("status") == "inscricoes_encerradas" and fim and fim > hoje:
        rel.erro(
            arquivo,
            "status 'inscricoes_encerradas' mas o prazo vai ate %s" % fim.isoformat(),
        )

    for i, entrada in enumerate(reg.get("historico_status") or []):
        if not isinstance(entrada, dict):
            rel.erro(arquivo, "historico_status[%d] deve ser um objeto" % i)
            continue
        _valida_data(rel, arquivo, "historico_status[%d].data" % i, entrada.get("data"), True)
        if entrada.get("status") not in comum.STATUS_VALIDOS:
            rel.erro(
                arquivo,
                "historico_status[%d].status invalido: '%s'" % (i, entrada.get("status")),
            )
        if "observacao" not in entrada:
            rel.aviso(arquivo, "historico_status[%d] sem 'observacao'" % i)


def valida_historico(rel, arquivo, reg):
    """O historico deve ser cronologico e terminar no status atual."""
    historico = [h for h in (reg.get("historico_status") or []) if isinstance(h, dict)]
    if not historico:
        rel.erro(arquivo, "historico_status esta vazio — todo registro precisa de trilha")
        return

    datas = [comum.data_ou_none(h.get("data")) for h in historico]
    if all(d is not None for d in datas) and datas != sorted(datas):
        rel.erro(arquivo, "historico_status nao esta em ordem cronologica")

    if historico[-1].get("status") != reg.get("status"):
        rel.erro(
            arquivo,
            "ultima entrada do historico ('%s') difere do status atual ('%s')"
            % (historico[-1].get("status"), reg.get("status")),
        )

    indices = [
        comum.ORDEM_STATUS.index(h["status"])
        for h in historico
        if h.get("status") in comum.ORDEM_STATUS
    ]
    if indices and indices != sorted(indices):
        rel.aviso(
            arquivo,
            "historico_status regride no ciclo de vida — confirmar se houve "
            "retificacao, suspensao ou reabertura de prazo",
        )


def valida_fontes(rel, arquivo, reg):
    fontes = [f for f in (reg.get("fontes") or []) if isinstance(f, dict)]
    if not fontes:
        rel.erro(arquivo, "sem fontes: todo registro precisa de fonte e link rastreavel")
        return

    for i, fonte in enumerate(fontes):
        for campo in ("titulo", "url", "tipo", "consultado_em"):
            if not fonte.get(campo):
                rel.erro(arquivo, "fontes[%d] sem o campo '%s'" % (i, campo))
        if fonte.get("tipo") and fonte["tipo"] not in comum.TIPOS_FONTE_VALIDOS:
            rel.erro(arquivo, "fontes[%d].tipo invalido: '%s'" % (i, fonte["tipo"]))
        url = fonte.get("url") or ""
        if url and not url.startswith("https://"):
            rel.aviso(arquivo, "fontes[%d].url nao usa HTTPS: %s" % (i, url))
        _valida_data(rel, arquivo, "fontes[%d].consultado_em" % i, fonte.get("consultado_em"))

    prioritarias = {"oficial", "diario_oficial", "banca"}
    if not any(f.get("tipo") in prioritarias for f in fontes):
        rel.aviso(
            arquivo,
            "nenhuma fonte oficial, de diario oficial ou de banca — dados "
            "sustentados apenas por imprensa/portais; validar antes de divulgar",
        )


def valida_coerencia_vagas(rel, arquivo, reg):
    total = reg.get("vagas_imediatas_total")
    if total is None:
        return
    por_cargo = [
        c.get("vagas_imediatas")
        for c in reg.get("cargos", [])
        if isinstance(c, dict)
    ]
    if any(v is None for v in por_cargo):
        return
    soma = sum(por_cargo)
    if soma != total:
        rel.aviso(
            arquivo,
            "soma das vagas por cargo (%d) difere de vagas_imediatas_total (%d)"
            % (soma, total),
        )


def valida_duplicidade(rel, registros):
    """Detecta ids repetidos e possiveis duplicatas por orgao+edital e por link."""
    por_id = defaultdict(list)
    por_chave = defaultdict(list)
    por_edital_url = defaultdict(list)

    for arquivo, reg in registros:
        por_id[reg.get("id")].append(arquivo)

        chave = (
            (reg.get("orgao") or "").strip().lower(),
            (reg.get("edital_numero") or "").strip().lower(),
        )
        if chave[0] and chave[1] and chave[1] != comum.AUSENTE:
            por_chave[chave].append(arquivo)

        url = (reg.get("links") or {}).get("edital")
        if url and url != comum.AUSENTE and url.startswith("http"):
            por_edital_url[url].append(arquivo)

    for identificador, arquivos in por_id.items():
        if len(arquivos) > 1:
            rel.erro(arquivos[0], "id duplicado '%s' em: %s" % (identificador, ", ".join(arquivos)))

    for (orgao, edital), arquivos in por_chave.items():
        if len(arquivos) > 1:
            rel.erro(
                arquivos[0],
                "possivel duplicata: mesmo orgao ('%s') e edital ('%s') em: %s"
                % (orgao, edital, ", ".join(arquivos)),
            )

    for url, arquivos in por_edital_url.items():
        if len(arquivos) > 1:
            rel.aviso(
                arquivos[0],
                "mesmo links.edital em varios registros (%s): confirmar se sao "
                "certames distintos ou duplicata — %s" % (url, ", ".join(arquivos)),
            )


CAMINHO_DESCOBERTAS = os.path.join(comum.RAIZ, "descobertas", "descobertas.json")

CAMPOS_DESCOBERTA = [
    "chave",
    "fonte_id",
    "orgao",
    "titulo",
    "url",
    "primeira_deteccao",
    "ultima_deteccao",
    "no_repositorio",
]


def valida_descobertas(rel):
    """Confere a saida de ferramentas/coletar.py.

    A coleta grava sem revisao humana, entao o pipeline precisa reprovar se ela
    produzir lixo: chave repetida, campo faltando, data invalida, tipo de fonte
    fora do vocabulario ou referencia a um registro de dados/ inexistente.
    O arquivo e opcional — a coleta pode nunca ter rodado.
    """
    if not os.path.exists(CAMINHO_DESCOBERTAS):
        return 0

    rotulo = os.path.relpath(CAMINHO_DESCOBERTAS, comum.RAIZ)
    try:
        with open(CAMINHO_DESCOBERTAS, encoding="utf-8") as fh:
            dados = json.load(fh)
    except ValueError as exc:
        rel.erro(rotulo, "JSON invalido: %s" % exc)
        return 0

    if not isinstance(dados, dict):
        rel.erro(rotulo, "raiz deve ser um objeto")
        return 0

    _valida_data(rel, rotulo, "gerado_em", dados.get("gerado_em"), obrigatorio=True)

    achados = dados.get("achados")
    if not isinstance(achados, list):
        rel.erro(rotulo, "campo 'achados' ausente ou nao e lista")
        return 0

    ids_validos = {reg.get("id") for _, reg in comum.carregar_registros()}
    vistas = set()

    for achado in achados:
        if not isinstance(achado, dict):
            rel.erro(rotulo, "achado que nao e objeto: %r" % (achado,))
            continue

        chave = achado.get("chave")
        alvo = "%s[%s]" % (rotulo, chave or "sem-chave")

        for campo in CAMPOS_DESCOBERTA:
            if campo not in achado:
                rel.erro(alvo, "campo obrigatorio ausente: '%s'" % campo)

        if chave:
            if chave in vistas:
                rel.erro(alvo, "chave repetida entre achados")
            vistas.add(chave)

        for rotulo_data in ("primeira_deteccao", "ultima_deteccao"):
            _valida_data(rel, alvo, rotulo_data, achado.get(rotulo_data))
        inscricoes = achado.get("inscricoes") or {}
        _valida_data(rel, alvo, "inscricoes.inicio", inscricoes.get("inicio"))
        _valida_data(rel, alvo, "inscricoes.fim", inscricoes.get("fim"))

        tipo_fonte = achado.get("fonte_tipo")
        if tipo_fonte and tipo_fonte != comum.AUSENTE:
            if tipo_fonte not in comum.TIPOS_FONTE_VALIDOS:
                rel.erro(alvo, "fonte_tipo invalido: %r" % tipo_fonte)

        estimado = achado.get("status_estimado")
        if estimado and estimado not in comum.STATUS_VALIDOS:
            rel.erro(alvo, "status_estimado fora do vocabulario: %r" % estimado)

        url = achado.get("url") or ""
        if url and not url.startswith(("http://", "https://")):
            rel.erro(alvo, "url deve ser absoluta: %r" % url)

        registro = achado.get("registro_repositorio")
        if achado.get("no_repositorio"):
            if not registro:
                rel.erro(alvo, "no_repositorio=true sem registro_repositorio")
            elif registro not in ids_validos:
                rel.erro(
                    alvo,
                    "registro_repositorio aponta para id inexistente: %r" % registro,
                )
        elif registro:
            rel.erro(alvo, "registro_repositorio preenchido com no_repositorio=false")

    for fonte in dados.get("fontes_consultadas") or []:
        if fonte.get("status") == "erro":
            rel.aviso(
                rotulo,
                "fonte %s falhou na ultima coleta: %s"
                % (fonte.get("id"), fonte.get("erro")),
            )
        elif fonte.get("suspeita_extracao_vazia"):
            rel.aviso(
                rotulo,
                "fonte %s respondeu sem erro mas nao devolveu nenhum item; "
                "possivel mudanca de layout — conferir ferramentas/coletar.py"
                % fonte.get("id"),
            )

    return len(achados)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida os dados de concursos do ES.")
    parser.add_argument("--json", action="store_true", help="saida em JSON")
    args = parser.parse_args()

    rel = Relatorio()
    try:
        registros = comum.carregar_registros()
    except ValueError as exc:
        print("ERRO FATAL: %s" % exc, file=sys.stderr)
        return 1

    if not registros:
        print("ERRO FATAL: nenhum registro encontrado em dados/", file=sys.stderr)
        return 1

    for arquivo, reg in registros:
        valida_estrutura(rel, arquivo, reg)
        valida_vocabulario(rel, arquivo, reg)
        valida_escopo(rel, arquivo, reg)
        valida_diretorio(rel, arquivo, reg)
        valida_datas(rel, arquivo, reg)
        valida_historico(rel, arquivo, reg)
        valida_fontes(rel, arquivo, reg)
        valida_coerencia_vagas(rel, arquivo, reg)

    valida_duplicidade(rel, registros)
    total_descobertas = valida_descobertas(rel)

    if args.json:
        print(
            json.dumps(
                {
                    "registros": len(registros),
                    "descobertas": total_descobertas,
                    "erros": rel.erros,
                    "avisos": rel.avisos,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("Registros analisados: %d" % len(registros))
        print("Descobertas analisadas: %d" % total_descobertas)
        print("Erros: %d | Avisos: %d" % (len(rel.erros), len(rel.avisos)))
        if rel.erros:
            print("\n--- ERROS (reprovam a validacao) ---")
            for item in rel.erros:
                print("  [ERRO] %s: %s" % (item["arquivo"], item["mensagem"]))
        if rel.avisos:
            print("\n--- AVISOS (revisar, nao reprovam) ---")
            for item in rel.avisos:
                print("  [aviso] %s: %s" % (item["arquivo"], item["mensagem"]))
        if not rel.erros:
            print("\nValidacao aprovada.")

    return 1 if rel.erros else 0


if __name__ == "__main__":
    sys.exit(main())
