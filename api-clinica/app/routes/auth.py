
"""Cadastro, confirmação, login e logout do veterinário."""

import hashlib
import secrets
import pymysql

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import gerar_token, login_required
from app.db import get_conn
from app.validacoes import campos_faltando, cpf_valido


bp = Blueprint("auth", __name__, url_prefix="/auth")


# ==========================================================
# CADASTRO DO VETERINÁRIO
# ==========================================================

@bp.post("/registrar")
def registrar():

    dados = request.get_json(silent=True) or {}

    faltando = campos_faltando(
        dados,
        ["nome_completo", "cpf", "crmv", "uf_crmv", "email", "senha"]
    )

    if faltando:
        return jsonify({
            "erro": f"campos obrigatórios: {', '.join(faltando)}"
        }), 400

    cpf = "".join(
        caractere for caractere in str(dados["cpf"])
        if caractere in "0123456789"
    )

    if not cpf_valido(cpf):
        return jsonify({"erro": "CPF inválido"}), 400

    if not isinstance(dados["senha"], str) or len(dados["senha"]) < 6:
        return jsonify({
            "erro": "a senha precisa ter pelo menos 6 caracteres"
        }), 400

    # Gera o hash seguro da senha.
    senha_hash = generate_password_hash(dados["senha"])

    # Gera um token criptograficamente seguro.
    token_confirmacao = secrets.token_urlsafe(32)

    # Armazena somente o hash do token no banco.
    token_hash = hashlib.sha256(
        token_confirmacao.encode("utf-8")
    ).hexdigest()

    try:

        with get_conn() as conn, conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO veterinario (
                    nome_completo,
                    cpf,
                    crmv,
                    uf_crmv,
                    email,
                    telefone,
                    senha_hash,
                    email_confirmado,
                    token_confirmacao_hash,
                    token_confirmacao_expira
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    0, %s,
                    DATE_ADD(NOW(), INTERVAL 30 MINUTE)
                )
                """,
                (
                    dados["nome_completo"].strip(),
                    cpf,
                    dados["crmv"].strip(),
                    dados["uf_crmv"].strip().upper(),
                    dados["email"].strip().lower(),
                    dados.get("telefone"),
                    senha_hash,
                    token_hash,
                ),
            )

            id_veterinario = cur.lastrowid

            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": "já existe um veterinário com este CPF, e-mail ou CRMV"
        }), 409

    # Simulação acadêmica do envio de e-mail.
    # O token é exibido no terminal da API, não na resposta HTTP.

    print("\n" + "=" * 65, flush=True)
    print("SIMULAÇÃO DE ENVIO DE E-MAIL", flush=True)
    print(f"Destinatário: {dados['email']}", flush=True)
    print(f"Token de confirmação: {token_confirmacao}", flush=True)
    print("Validade: 30 minutos", flush=True)
    print("=" * 65 + "\n", flush=True)

    return jsonify({
        "id_veterinario": id_veterinario,
        "email_confirmado": False,
        "mensagem": (
            "Cadastro realizado com sucesso. "
            "Confirme seu cadastro antes de realizar o login."
        )
    }), 201


# ==========================================================
# CONFIRMAÇÃO DO CADASTRO
# ==========================================================

@bp.post("/confirmar")
def confirmar():

    dados = request.get_json(silent=True) or {}

    email = (dados.get("email") or "").strip().lower()
    token = (dados.get("token") or "").strip()

    if not email or not token:
        return jsonify({
            "erro": "informe o e-mail e o token de confirmação"
        }), 400

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            """
            UPDATE veterinario
            SET
                email_confirmado = 1,
                data_confirmacao = NOW(),
                token_confirmacao_hash = NULL,
                token_confirmacao_expira = NULL
            WHERE email = %s
              AND token_confirmacao_hash = %s
              AND token_confirmacao_expira > NOW()
              AND email_confirmado = 0
              AND ativo = 1
            """,
            (email, token_hash),
        )

        if cur.rowcount != 1:
            return jsonify({
                "erro": "token inválido, expirado ou cadastro indisponível"
            }), 400

        conn.commit()

    return jsonify({
        "mensagem": "Cadastro confirmado com sucesso.",
        "email_confirmado": True
    }), 200


# ==========================================================
# LOGIN DO VETERINÁRIO
# ==========================================================

@bp.post("/login")
def login():

    dados = request.get_json(silent=True) or {}

    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    if not email or not senha:
        return jsonify({
            "erro": "informe e-mail e senha"
        }), 400

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                id_veterinario,
                nome_completo,
                email,
                senha_hash,
                email_confirmado,
                ativo
            FROM veterinario
            WHERE email = %s
            """,
            (email,),
        )

        veterinario = cur.fetchone()

    # Verifica as credenciais.
    if not veterinario or not check_password_hash(
        veterinario["senha_hash"], senha
    ):
        return jsonify({
            "erro": "e-mail ou senha incorretos"
        }), 401

    # Impede o acesso de veterinários inativos.
    if not veterinario["ativo"]:
        return jsonify({
            "erro": "cadastro inativo. Acesso não autorizado."
        }), 403

    # Impede o acesso antes da confirmação.
    if not veterinario["email_confirmado"]:
        return jsonify({
            "erro": "confirme seu cadastro antes de realizar o login"
        }), 403

    # Registra o último acesso.
    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            """
            UPDATE veterinario
            SET ultimo_acesso = NOW()
            WHERE id_veterinario = %s
            """,
            (veterinario["id_veterinario"],),
        )

        conn.commit()

    # Gera o token JWT de autenticação.
    token = gerar_token(
        veterinario["id_veterinario"],
        veterinario["nome_completo"]
    )

    return jsonify({
        "token": token,
        "veterinario": {
            "id_veterinario": veterinario["id_veterinario"],
            "nome_completo": veterinario["nome_completo"],
            "email": veterinario["email"],
        }
    }), 200


# ==========================================================
# CONSULTA DO VETERINÁRIO AUTENTICADO
# ==========================================================

@bp.get("/me")
@login_required
def me():

    """Confere se o token é válido e retorna o usuário logado."""

    return jsonify(g.veterinario)


# ==========================================================
# LOGOUT DO VETERINÁRIO
# ==========================================================

@bp.post("/logout")
@login_required
def logout():

    """Revoga o token JWT utilizado na sessão atual."""

    # Identifica o token e o veterinário autenticado.
    jti = g.jwt_payload["jti"]
    id_veterinario = g.veterinario["id_veterinario"]

    # Converte a expiração do JWT para DATETIME em UTC.
    data_expiracao = datetime.fromtimestamp(
        g.veterinario["exp"],
        tz=timezone.utc
    ).replace(tzinfo=None)

    # Registra o token na tabela de revogação.
    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO token_revogado (
                jti,
                id_veterinario,
                data_expiracao
            )
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE jti = VALUES(jti)
            """,
            (
                jti,
                id_veterinario,
                data_expiracao
            )
        )

        conn.commit()

    return jsonify({
        "mensagem": "Logout realizado com sucesso."
    }), 200
