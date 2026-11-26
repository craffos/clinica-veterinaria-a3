
"""Autenticação e autorização utilizando tokens JWT.

A cada requisição protegida, a API valida:

1. Presença do token.
2. Assinatura e expiração do JWT.
3. Identificador único do token (jti).
4. Existência do veterinário.
5. Situação cadastral do veterinário.
6. Confirmação de e-mail.
7. Revogação do token.

Somente veterinários ativos, confirmados e com tokens
válidos e não revogados podem acessar as rotas protegidas.
"""

from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import UUID, uuid4

import jwt
from flask import current_app, g, jsonify, request

from app.db import get_conn


# Tempo de validade do token JWT
VALIDADE_TOKEN = timedelta(hours=8)


def gerar_token(id_veterinario, nome_completo):
    """Gera um token JWT assinado e com identificador único."""

    agora = datetime.now(timezone.utc)

    payload = {
        "id_veterinario": id_veterinario,
        "nome_completo": nome_completo,
        "jti": str(uuid4()),
        "iat": agora,
        "exp": agora + VALIDADE_TOKEN,
    }

    return jwt.encode(
        payload,
        current_app.config["SECRET_KEY"],
        algorithm="HS256"
    )


def login_required(funcao):
    """Protege rotas que exigem autenticação e autorização."""

    @wraps(funcao)
    def decorada(*args, **kwargs):

        # 1. Verifica a presença do token
        cabecalho = request.headers.get("Authorization", "")

        if not cabecalho.startswith("Bearer "):
            return jsonify({
                "erro": "faça login: token ausente"
            }), 401

        token = cabecalho.split(" ", 1)[1].strip()

        # 2. Valida assinatura, expiração e campos obrigatórios
        try:
            payload = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"],
                options={
                    "require": [
                        "exp",
                        "iat",
                        "id_veterinario",
                        "jti"
                    ]
                }
            )

        except jwt.ExpiredSignatureError:
            return jsonify({
                "erro": "sessão expirada, faça login de novo"
            }), 401

        except jwt.InvalidTokenError:
            return jsonify({
                "erro": "token inválido"
            }), 401

        # 3. Valida o identificador do veterinário
        id_veterinario = payload.get("id_veterinario")

        if type(id_veterinario) is not int or id_veterinario <= 0:
            return jsonify({
                "erro": "token inválido"
            }), 401

        # 4. Valida o identificador único do JWT
        jti = payload.get("jti")

        try:
            if not isinstance(jti, str):
                raise ValueError("jti inválido")

            if str(UUID(jti)) != jti:
                raise ValueError("jti inválido")

        except (ValueError, TypeError):
            return jsonify({
                "erro": "token inválido"
            }), 401

        # 5. Consulta o veterinário e a revogação do token
        with get_conn() as conn, conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id_veterinario,
                    nome_completo,
                    email,
                    ativo,
                    email_confirmado
                FROM veterinario
                WHERE id_veterinario = %s
                """,
                (id_veterinario,)
            )

            veterinario = cur.fetchone()

            cur.execute(
                """
                SELECT jti
                FROM token_revogado
                WHERE jti = %s
                """,
                (jti,)
            )

            token_revogado = cur.fetchone()

        # 6. Bloqueia tokens revogados
        if token_revogado:
            return jsonify({
                "erro": "sessão encerrada. Faça login novamente."
            }), 401

        # 7. Verifica se o veterinário existe
        if not veterinario:
            return jsonify({
                "erro": "veterinário não encontrado"
            }), 401

        # 8. Bloqueia veterinários inativos
        if not veterinario["ativo"]:
            return jsonify({
                "erro": "cadastro inativo. Acesso não autorizado."
            }), 403

        # 9. Bloqueia cadastros não confirmados
        if not veterinario["email_confirmado"]:
            return jsonify({
                "erro": "confirme seu cadastro antes de acessar o sistema"
            }), 403

        # 10. Disponibiliza os dados atualizados do veterinário
        g.veterinario = {
            "id_veterinario": veterinario["id_veterinario"],
            "nome_completo": veterinario["nome_completo"],
            "email": veterinario["email"],
            "exp": payload["exp"]
        }

        # 11. Disponibiliza os dados da sessão para o logout
        g.jwt_payload = payload

        # 12. Autoriza a execução da rota
        return funcao(*args, **kwargs)

    return decorada
