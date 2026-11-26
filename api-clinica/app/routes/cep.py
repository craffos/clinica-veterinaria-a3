"""Endpoint que o frontend usa para preencher o endereço a partir do CEP."""
from flask import Blueprint, jsonify

from app.services.viacep_service import buscar_cep
from app.validacoes import cep_valido, somente_digitos

bp = Blueprint("cep", __name__, url_prefix="/cep")


@bp.get("/<cep>")
def consultar(cep):
    if not cep_valido(cep):
        return jsonify({"erro": "CEP deve ter 8 dígitos"}), 400

    dados = buscar_cep(somente_digitos(cep))
    if dados is None:
        return jsonify({"erro": "não foi possível consultar o ViaCEP agora"}), 502
    if dados.get("erro"):
        return jsonify({"erro": "CEP não encontrado"}), 404

    return jsonify(
        {
            "cep": dados.get("cep", "").replace("-", ""),
            "logradouro": dados.get("logradouro", ""),
            "bairro": dados.get("bairro", ""),
            "cidade": dados.get("localidade", ""),
            "uf": dados.get("uf", ""),
            "codigo_ibge": dados.get("ibge") or None,
        }
    )
