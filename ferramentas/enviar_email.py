#!/usr/bin/env python3
"""Envia por SMTP o resumo gerado por gerar_email.py.

Toda a configuracao vem de VARIAVEIS DE AMBIENTE. Nenhuma credencial fica no
repositorio — no GitHub Actions elas vem de GitHub Secrets.

Variaveis obrigatorias:
    SMTP_SERVIDOR        host do servidor SMTP
    SMTP_USUARIO         usuario de autenticacao
    SMTP_SENHA           senha ou app password
    EMAIL_DESTINATARIO   destinatario (separar varios por virgula)

Opcionais:
    SMTP_PORTA           porta (padrao 587 para STARTTLS, 465 para SSL)
    EMAIL_REMETENTE      remetente (padrao: SMTP_USUARIO)
    ARQUIVO_RESUMO       caminho do resumo (padrao: email/<hoje>-resumo.md)

Uso local:
    export SMTP_SERVIDOR=smtp.exemplo.com SMTP_USUARIO=... SMTP_SENHA=...
    export EMAIL_DESTINATARIO=voce@exemplo.com
    python3 ferramentas/enviar_email.py
"""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

OBRIGATORIAS = ("SMTP_SERVIDOR", "SMTP_USUARIO", "SMTP_SENHA", "EMAIL_DESTINATARIO")


def extrai_assunto(corpo: str) -> str:
    """Le o assunto sugerido do proprio resumo."""
    for linha in corpo.splitlines():
        if linha.startswith("**Assunto sugerido:**"):
            return linha.split(":", 1)[1].replace("**", "").strip()
    for linha in corpo.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return "Concursos ES — atualizações"


def markdown_para_texto(corpo: str) -> str:
    """Limpeza minima do Markdown para leitura em cliente de texto puro."""
    linhas = []
    for linha in corpo.splitlines():
        limpa = linha.replace("**", "")
        if limpa.startswith("# "):
            limpa = limpa[2:].upper()
        elif limpa.startswith("## "):
            limpa = "\n" + limpa[3:].upper()
        linhas.append(limpa)
    return "\n".join(linhas)


def main() -> int:
    faltando = [nome for nome in OBRIGATORIAS if not os.environ.get(nome)]
    if faltando:
        print(
            "ERRO: variaveis de ambiente ausentes: %s.\n"
            "Configure-as como GitHub Secrets ou no ambiente local. "
            "Nunca grave credenciais no repositorio." % ", ".join(faltando),
            file=sys.stderr,
        )
        return 1

    servidor = os.environ["SMTP_SERVIDOR"]
    porta = int(os.environ.get("SMTP_PORTA") or 587)
    usuario = os.environ["SMTP_USUARIO"]
    senha = os.environ["SMTP_SENHA"]
    remetente = os.environ.get("EMAIL_REMETENTE") or usuario
    destinatarios = [
        d.strip() for d in os.environ["EMAIL_DESTINATARIO"].split(",") if d.strip()
    ]

    caminho = os.environ.get("ARQUIVO_RESUMO") or os.path.join(
        "email", "%s-resumo.md" % comum.hoje().isoformat()
    )
    if not os.path.isabs(caminho):
        caminho = os.path.join(comum.RAIZ, caminho)

    if not os.path.exists(caminho):
        print(
            "ERRO: resumo nao encontrado em %s. Rode ferramentas/gerar_email.py antes."
            % caminho,
            file=sys.stderr,
        )
        return 1

    with open(caminho, encoding="utf-8") as fh:
        corpo = fh.read()

    mensagem = EmailMessage()
    mensagem["Subject"] = extrai_assunto(corpo)
    mensagem["From"] = remetente
    mensagem["To"] = ", ".join(destinatarios)
    mensagem.set_content(markdown_para_texto(corpo))

    contexto = ssl.create_default_context()
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(servidor, porta, context=contexto, timeout=30) as smtp:
                smtp.login(usuario, senha)
                smtp.send_message(mensagem)
        else:
            with smtplib.SMTP(servidor, porta, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=contexto)
                smtp.ehlo()
                smtp.login(usuario, senha)
                smtp.send_message(mensagem)
    except smtplib.SMTPAuthenticationError:
        # Nunca ecoar usuario ou senha no log.
        print("ERRO: falha de autenticacao no SMTP. Verifique os secrets.", file=sys.stderr)
        return 1
    except (smtplib.SMTPException, OSError) as exc:
        print("ERRO ao enviar e-mail: %s" % type(exc).__name__, file=sys.stderr)
        return 1

    print(
        "Resumo enviado para %d destinatario(s). Assunto: %s"
        % (len(destinatarios), mensagem["Subject"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
