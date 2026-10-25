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

Quando o envio falha, a mensagem diz em que fase da conversa SMTP ela parou e
reproduz a resposta do servidor, sem usuario, senha, servidor nem enderecos de
e-mail: o log de execucao deste repositorio e publico.

Uso local:
    export SMTP_SERVIDOR=smtp.exemplo.com SMTP_USUARIO=... SMTP_SENHA=...
    export EMAIL_DESTINATARIO=voce@exemplo.com
    python3 ferramentas/enviar_email.py
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import comum  # noqa: E402

OBRIGATORIAS = ("SMTP_SERVIDOR", "SMTP_USUARIO", "SMTP_SENHA", "EMAIL_DESTINATARIO")

# Mesma ordem de preferencia do smtplib.login(), de proposito: trocar login()
# por autenticar() nao muda o mecanismo usado com provedor nenhum (o Brevo, por
# exemplo, anuncia CRAM-MD5 ao lado de PLAIN e LOGIN). Muda so o que acontece
# quando o servidor recusa.
MECANISMOS_AUTH = ("CRAM-MD5", "PLAIN", "LOGIN")

DICA_CREDENCIAIS = (
    "Confira os secrets SMTP_USUARIO e SMTP_SENHA. Com Gmail, a senha de "
    "aplicativo deixa de valer quando a senha da conta Google e trocada, quando "
    "a verificacao em duas etapas e desligada ou quando ela e excluida: gere "
    "outra em https://myaccount.google.com/apppasswords e grave-a em SMTP_SENHA."
)

_ENDERECO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# AUTH PLAIN e AUTH LOGIN mandam usuario e senha em base64. Servidor que ecoa o
# argumento recusado ("cannot decode ...") devolveria a credencial codificada,
# que o mascaramento do GitHub nao reconhece quando vem concatenada.
_BASE64_LONGO = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


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


def autenticar(smtp, usuario: str, senha: str) -> None:
    """Equivalente a smtp.login() que nao esconde a recusa do servidor.

    smtplib.login() tenta cada mecanismo anunciado e, quando um e recusado,
    passa ao seguinte. O Gmail responde a credencial invalida com 535 e FECHA a
    conexao: a tentativa seguinte cai num socket fechado e o que sobe e
    SMTPServerDisconnected — a recusa, que era a informacao util, se perde.
    Medido contra smtp.gmail.com com credencial invalida: a versao anterior
    deste script imprimia o mesmo "SMTPServerDisconnected" das execucoes de
    15/10 a 23/10/2026, e o ramo de falha de autenticacao nunca disparava. Aqui
    a primeira recusa fica guardada e e ela que sobe quando a conexao cai.
    """
    smtp.ehlo_or_helo_if_needed()
    anunciados = (smtp.esmtp_features.get("auth") or "").upper().split()
    mecanismos = [m for m in MECANISMOS_AUTH if m in anunciados]
    if not mecanismos:
        # Servidor que so anuncia XOAUTH2 e o sinal de que desligou a
        # autenticacao por senha: a lista anunciada vai na mensagem por isso.
        raise smtplib.SMTPNotSupportedError(
            "nenhum mecanismo de AUTH utilizavel; o servidor anuncia: %s"
            % (" ".join(anunciados) or "nenhum")
        )
    smtp.user, smtp.password = usuario, senha
    recusa = None
    for mecanismo in mecanismos:
        try:
            metodo = getattr(smtp, "auth_" + mecanismo.lower().replace("-", "_"))
            smtp.auth(mecanismo, metodo)
            return
        except smtplib.SMTPAuthenticationError as exc:
            recusa = recusa or exc
        except smtplib.SMTPServerDisconnected:
            if recusa is None:
                raise
            raise recusa from None
    raise recusa


def sanitizar(texto: str, sensiveis) -> str:
    """Tira credenciais e enderecos de um texto que vai para o log publico.

    O GitHub mascara os secrets, mas so na forma EXATA: EMAIL_DESTINATARIO com
    dois enderecos e mascarado inteiro, nao cada endereco, e uma resposta do
    servidor que citasse um deles sairia em claro.
    """
    for valor in sorted({v for v in sensiveis if v}, key=len, reverse=True):
        texto = re.sub(re.escape(valor), "***", texto, flags=re.IGNORECASE)
    texto = _ENDERECO.sub("<endereco>", texto)
    texto = _BASE64_LONGO.sub("<omitido>", texto)
    texto = " | ".join(p.strip() for p in texto.splitlines() if p.strip())
    return texto[:500] or "(sem detalhe)"


def _texto(resposta) -> str:
    if isinstance(resposta, bytes):
        return resposta.decode("utf-8", "replace")
    return str(resposta)


def _respostas_por_destinatario(recusados) -> str:
    """Respostas a RCPT sem os enderecos, que sao a chave do dicionario."""
    respostas = ["%s %s" % (codigo, _texto(msg)) for codigo, msg in recusados.values()]
    return "; ".join(dict.fromkeys(respostas))


def descrever_falha(exc, sensiveis) -> str:
    """Codigo e resposta do servidor, ou a mensagem da excecao, sem dado sensivel."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        texto = _respostas_por_destinatario(exc.recipients)
    elif isinstance(exc, smtplib.SMTPResponseException):
        texto = "%s %s" % (exc.smtp_code, _texto(exc.smtp_error))
    else:
        texto = str(exc)
    return sanitizar(texto, sensiveis)


def anotar(nivel: str, mensagem: str) -> None:
    """Mensagem no stderr; no GitHub Actions, como anotacao ::error::/::warning::.

    A anotacao aparece no resumo da execucao e no e-mail de falha que o proprio
    GitHub envia. Sem ela, o unico motivo visivel era "Process completed with
    exit code 1", e a causa so aparecia abrindo o log do passo.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        dados = mensagem.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::%s::%s" % (nivel, dados), file=sys.stderr)
    else:
        rotulo = "ERRO" if nivel == "error" else "AVISO"
        print("%s: %s" % (rotulo, mensagem), file=sys.stderr)


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
    sensiveis = [servidor, usuario, senha, remetente, *destinatarios]

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
    # 'fase' diz ate onde a conversa chegou: "conexao recusada", "TLS falhou" e
    # "credencial recusada" pedem correcoes diferentes, e o tipo da excecao
    # sozinho nao separa os tres.
    fase = "conexao"
    recusados = {}
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(servidor, porta, context=contexto, timeout=30) as smtp:
                fase = "autenticacao"
                autenticar(smtp, usuario, senha)
                fase = "envio"
                recusados = smtp.send_message(mensagem)
                fase = "encerramento"
        else:
            with smtplib.SMTP(servidor, porta, timeout=30) as smtp:
                fase = "starttls"
                smtp.ehlo()
                smtp.starttls(context=contexto)
                smtp.ehlo()
                fase = "autenticacao"
                autenticar(smtp, usuario, senha)
                fase = "envio"
                recusados = smtp.send_message(mensagem)
                fase = "encerramento"
    except smtplib.SMTPAuthenticationError as exc:
        anotar(
            "error",
            "o servidor SMTP recusou as credenciais (%s). %s"
            % (descrever_falha(exc, sensiveis), DICA_CREDENCIAIS),
        )
        return 1
    except (smtplib.SMTPException, OSError) as exc:
        if fase != "encerramento":
            anotar(
                "error",
                "envio de e-mail falhou na fase '%s': %s: %s"
                % (fase, type(exc).__name__, descrever_falha(exc, sensiveis)),
            )
            return 1
        # O servidor ja aceitou a mensagem; so o QUIT falhou. Reprovar aqui
        # acusaria erro num envio que aconteceu.
        anotar(
            "warning",
            "mensagem aceita pelo servidor, mas a conexao nao fechou de forma "
            "limpa: %s: %s" % (type(exc).__name__, descrever_falha(exc, sensiveis)),
        )

    if recusados:
        # send_message so levanta excecao quando TODOS os destinatarios sao
        # recusados; recusa parcial volta no retorno e passaria em silencio.
        anotar(
            "warning",
            "%d de %d destinatario(s) recusado(s) pelo servidor: %s"
            % (
                len(recusados),
                len(destinatarios),
                sanitizar(_respostas_por_destinatario(recusados), sensiveis),
            ),
        )

    print(
        "Resumo enviado para %d destinatario(s). Assunto: %s"
        % (len(destinatarios) - len(recusados), mensagem["Subject"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
