"""CRUD de ESPECIE. Use este arquivo como MODELO para os outros módulos
(raca, tutor, animal...): copie, troque os nomes e os campos."""
from flask import Blueprint, jsonify, request

from app.db import get_conn

bp = Blueprint("especies", __name__, url_prefix="/especies")

CAMPOS = "id_especie, nome, descricao, ativo"


@bp.get("/")
def listar():
    # ?todas=1 inclui as inativas
    sql = f"SELECT {CAMPOS} FROM especie"
    if request.args.get("todas") != "1":
        sql += " WHERE ativo = 1"
    sql += " ORDER BY nome"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return jsonify(cur.fetchall())


@bp.get("/<int:id_especie>")
def buscar(id_especie):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {CAMPOS} FROM especie WHERE id_especie = %s", (id_especie,))
        linha = cur.fetchone()
    if not linha:
        return jsonify({"erro": "espécie não encontrada"}), 404
    return jsonify(linha)


@bp.post("/")
def criar():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "nome é obrigatório"}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO especie (nome, descricao) VALUES (%s, %s)",
            (nome, dados.get("descricao")),
        )
        return jsonify({"id_especie": cur.lastrowid}), 201


@bp.put("/<int:id_especie>")
def atualizar(id_especie):
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "nome é obrigatório"}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE especie SET nome = %s, descricao = %s WHERE id_especie = %s",
            (nome, dados.get("descricao"), id_especie),
        )
        if cur.rowcount == 0:
            return jsonify({"erro": "espécie não encontrada"}), 404
    return jsonify({"mensagem": "atualizada"})


@bp.delete("/<int:id_especie>")
def inativar(id_especie):
    # Inativação lógica: não apaga, só marca ativo = 0 (preserva o histórico).
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE especie SET ativo = 0 WHERE id_especie = %s", (id_especie,))
        if cur.rowcount == 0:
            return jsonify({"erro": "espécie não encontrada"}), 404
    return jsonify({"mensagem": "inativada"})
