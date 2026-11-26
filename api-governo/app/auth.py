
"""Autenticação da API governamental por API Key."""

import hmac
from functools import wraps

from flask import current_app, jsonify, request


def api_key_required(func):
    """Protege endpoints governamentais com uma chave compartilhada."""

    @wraps(func)
    def wrapper(*args, **kwargs):

        chave_configurada = current_app.config.get(
            "GOVERNO_API_KEY", ""
        )

        if not chave_configurada:
            current_app.logger.error(
                "GOVERNO_API_KEY não configurada"
            )

            return jsonify({
                "erro": "serviço de autenticação indisponível"
            }), 503

        chave_recebida = request.headers.get("X-API-Key", "")

        if not chave_recebida:
            return jsonify({
                "erro": "API Key ausente"
            }), 401

        if not hmac.compare_digest(
            chave_recebida.encode("utf-8"),
            chave_configurada.encode("utf-8")
        ):
            return jsonify({
                "erro": "API Key inválida"
            }), 401

        return func(*args, **kwargs)

    return wrapper
