"""CRUD de ENDERECO. Na prática, o frontend cria/edita o endereço junto
com o tutor (veja app/routes/tutores.py); este módulo existe para o CRUD
ficar completo e para permitir corrigir um endereço isoladamente."""
import re
from flask import Blueprint, jsonify, request

from app.db import get_conn
from app.validacoes import campos_faltando

bp = Blueprint("enderecos", __name__, url_prefix="/enderecos")

CAMPOS = "id_endereco, cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge"


@bp.get("/<int:id_endereco>")
def buscar(id_endereco):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {CAMPOS} FROM endereco WHERE id_endereco = %s", (id_endereco,))
        linha = cur.fetchone()
    if not linha:
        return jsonify({"erro": "endereço não encontrado"}), 404
    return jsonify(linha)


@bp.post("/")
def criar():
    dados = request.get_json(silent=True) or {}
    codigo = dados.get("codigo_ibge")
    if codigo not in (None, "") and (not isinstance(codigo, str) or not re.fullmatch(r"[0-9]{7}", codigo)):
        return jsonify({"erro": "Código IBGE deve ter 7 dígitos"}), 400
    faltando = campos_faltando(dados, ["cep", "logradouro", "numero", "bairro", "cidade", "uf"])
    if faltando:
        return jsonify({"erro": f"campos obrigatórios: {', '.join(faltando)}"}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO endereco (cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                dados["cep"],
                dados["logradouro"],
                dados["numero"],
                dados.get("complemento"),
                dados["bairro"],
                dados["cidade"],
                dados["uf"].upper(), dados.get("codigo_ibge") or None,
            ),
        )
        return jsonify({"id_endereco": cur.lastrowid}), 201


@bp.put("/<int:id_endereco>")
def atualizar(id_endereco):
    dados = request.get_json(silent=True) or {}
    codigo = dados.get("codigo_ibge")
    if codigo not in (None, "") and (not isinstance(codigo, str) or not re.fullmatch(r"[0-9]{7}", codigo)):
        return jsonify({"erro": "Código IBGE deve ter 7 dígitos"}), 400
    faltando = campos_faltando(dados, ["cep", "logradouro", "numero", "bairro", "cidade", "uf"])
    if faltando:
        return jsonify({"erro": f"campos obrigatórios: {', '.join(faltando)}"}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE endereco SET codigo_ibge=CASE WHEN %s THEN %s WHEN cep=%s AND cidade=%s AND uf=%s THEN codigo_ibge ELSE NULL END,
               cep=%s, logradouro=%s, numero=%s, complemento=%s, bairro=%s, cidade=%s, uf=%s WHERE id_endereco = %s""",
            (
                    "codigo_ibge" in dados, dados.get("codigo_ibge") or None, dados["cep"], dados["cidade"], dados["uf"].upper(),
                dados["cep"],
                dados["logradouro"],
                dados["numero"],
                dados.get("complemento"),
                dados["bairro"],
                dados["cidade"],
                dados["uf"].upper(),
                id_endereco,
            ),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "endereço não encontrado"}), 404
    return jsonify({"mensagem": "atualizado"})
