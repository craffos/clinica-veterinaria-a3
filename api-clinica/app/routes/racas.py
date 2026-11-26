"""CRUD de RACA. Mesma ideia de app/routes/especies.py, mas toda raça
pertence a uma espécie (id_especie é obrigatório)."""
import pymysql
from flask import Blueprint, jsonify, request

from app.db import get_conn

bp = Blueprint("racas", __name__, url_prefix="/racas")

CAMPOS = "id_raca, nome, id_especie, descricao, ativo"


@bp.get("/")
def listar():
    # ?id_especie=2 filtra as raças de uma espécie (usado no formulário do animal)
    # ?todas=1 inclui as inativas
    sql = f"SELECT {CAMPOS} FROM raca WHERE 1=1"
    parametros = []
    if request.args.get("id_especie"):
        sql += " AND id_especie = %s"
        parametros.append(request.args["id_especie"])
    if request.args.get("todas") != "1":
        sql += " AND ativo = 1"
    sql += " ORDER BY nome"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, parametros)
        return jsonify(cur.fetchall())


@bp.get("/<int:id_raca>")
def buscar(id_raca):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {CAMPOS} FROM raca WHERE id_raca = %s", (id_raca,))
        linha = cur.fetchone()
    if not linha:
        return jsonify({"erro": "raça não encontrada"}), 404
    return jsonify(linha)


@bp.post("/")
def criar():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    id_especie = dados.get("id_especie")
    if not nome or not id_especie:
        return jsonify({"erro": "nome e id_especie são obrigatórios"}), 400
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raca (nome, id_especie, descricao) VALUES (%s, %s, %s)",
                (nome, id_especie, dados.get("descricao")),
            )
            return jsonify({"id_raca": cur.lastrowid}), 201
    except pymysql.err.IntegrityError as e:
        if "fk_raca_especie" in str(e):
            return jsonify({"erro": "espécie não encontrada"}), 400
        return jsonify({"erro": "já existe uma raça com este nome para esta espécie"}), 409


@bp.put("/<int:id_raca>")
def atualizar(id_raca):
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "nome é obrigatório"}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE raca SET nome = %s, descricao = %s WHERE id_raca = %s",
            (nome, dados.get("descricao"), id_raca),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "raça não encontrada"}), 404
    return jsonify({"mensagem": "atualizada"})


@bp.delete("/<int:id_raca>")
def inativar(id_raca):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE raca SET ativo = 0 WHERE id_raca = %s", (id_raca,))
        if cur.rowcount == 0:
            return jsonify({"erro": "raça não encontrada"}), 404
    return jsonify({"mensagem": "inativada"})
