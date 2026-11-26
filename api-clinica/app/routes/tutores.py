"""CRUD de TUTOR.

Particularidade deste módulo: criar ou editar um tutor também grava o
ENDERECO dele (o frontend manda os dois num só formulário). Como são
duas tabelas que precisam ser gravadas juntas, usamos uma TRANSAÇÃO:
se a segunda gravação falhar, a primeira é desfeita (rollback), evitando
um endereço "órfão" no banco.
"""
import pymysql
import re
from flask import Blueprint, jsonify, request

from app.auth import login_required
from app.db import get_conn
from app.validacoes import campos_faltando, cpf_valido

bp = Blueprint("tutores", __name__, url_prefix="/tutores")

CAMPOS_TUTOR = "t.id_tutor, t.nome_completo, t.cpf, t.dt_nasc, t.email, t.telefone, t.data_cadastro, t.ativo"
CAMPOS_ENDERECO = "t.id_endereco, e.cep, e.logradouro, e.numero, e.complemento, e.bairro, e.cidade, e.uf, e.codigo_ibge"


def _select_base():
    return f"""SELECT {CAMPOS_TUTOR}, {CAMPOS_ENDERECO}
               FROM tutor t JOIN endereco e ON e.id_endereco = t.id_endereco"""


@bp.get("/")
@login_required
def listar():
    sql = _select_base() + " WHERE 1=1"
    parametros = []
    if request.args.get("q"):
        sql += " AND (t.nome_completo LIKE %s OR t.cpf LIKE %s)"
        termo = f"%{request.args['q']}%"
        parametros += [termo, termo]
    if request.args.get("todos") != "1":
        sql += " AND t.ativo = 1"
    sql += " ORDER BY t.nome_completo"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, parametros)
        return jsonify(cur.fetchall())


@bp.get("/<int:id_tutor>")
@login_required
def buscar(id_tutor):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(_select_base() + " WHERE t.id_tutor = %s", (id_tutor,))
        linha = cur.fetchone()
    if not linha:
        return jsonify({"erro": "tutor não encontrado"}), 404
    return jsonify(linha)


def _validar(dados):
    faltando = campos_faltando(dados, ["nome_completo", "cpf"])
    endereco = dados.get("endereco") or {}
    faltando += [
        f"endereco.{c}"
        for c in campos_faltando(endereco, ["cep", "logradouro", "numero", "bairro", "cidade", "uf"])
    ]
    if faltando:
        return f"campos obrigatórios: {', '.join(faltando)}"
    codigo = endereco.get("codigo_ibge")
    if codigo not in (None, "") and (not isinstance(codigo, str) or not re.fullmatch(r"[0-9]{7}", codigo)):
        return "Código IBGE deve ter 7 dígitos"
    if not cpf_valido(dados["cpf"]):
        return "CPF inválido"
    return None


@bp.post("/")
@login_required
def criar():
    dados = request.get_json(silent=True) or {}
    erro = _validar(dados)
    if erro:
        return jsonify({"erro": erro}), 400
    endereco = dados["endereco"]

    conn = get_conn(autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO endereco (cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    endereco["cep"], endereco["logradouro"], endereco["numero"],
                    endereco.get("complemento"), endereco["bairro"], endereco["cidade"],
                    endereco["uf"].upper(), endereco.get("codigo_ibge") or None,
                ),
            )
            id_endereco = cur.lastrowid
            cur.execute(
                """INSERT INTO tutor (nome_completo, cpf, dt_nasc, email, telefone, id_endereco)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    dados["nome_completo"].strip(), dados["cpf"], dados.get("dt_nasc"),
                    dados.get("email"), dados.get("telefone"), id_endereco,
                ),
            )
            id_tutor = cur.lastrowid
        conn.commit()
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({"erro": "já existe um tutor com este CPF"}), 409
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({"id_tutor": id_tutor}), 201


@bp.put("/<int:id_tutor>")
@login_required
def atualizar(id_tutor):
    dados = request.get_json(silent=True) or {}
    erro = _validar(dados)
    if erro:
        return jsonify({"erro": erro}), 400
    endereco = dados["endereco"]

    conn = get_conn(autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id_endereco FROM tutor WHERE id_tutor = %s", (id_tutor,))
            atual = cur.fetchone()
            if not atual:
                conn.rollback()
                return jsonify({"erro": "tutor não encontrado"}), 404

            cur.execute(
                """UPDATE endereco SET codigo_ibge=CASE WHEN %s THEN %s WHEN cep=%s AND cidade=%s AND uf=%s THEN codigo_ibge ELSE NULL END,
                   cep=%s, logradouro=%s, numero=%s, complemento=%s, bairro=%s, cidade=%s, uf=%s WHERE id_endereco = %s""",
                (
                    "codigo_ibge" in endereco, endereco.get("codigo_ibge") or None, endereco["cep"], endereco["cidade"], endereco["uf"].upper(),
                    endereco["cep"], endereco["logradouro"], endereco["numero"],
                    endereco.get("complemento"), endereco["bairro"], endereco["cidade"],
                    endereco["uf"].upper(), atual["id_endereco"],
                ),
            )
            cur.execute(
                """UPDATE tutor SET nome_completo=%s, cpf=%s, dt_nasc=%s, email=%s, telefone=%s
                   WHERE id_tutor = %s""",
                (
                    dados["nome_completo"].strip(), dados["cpf"], dados.get("dt_nasc"),
                    dados.get("email"), dados.get("telefone"), id_tutor,
                ),
            )
        conn.commit()
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({"erro": "já existe um tutor com este CPF"}), 409
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({"mensagem": "atualizado"})


@bp.delete("/<int:id_tutor>")
@login_required
def inativar(id_tutor):
    # Inativação lógica: preserva o tutor e os animais/histórico ligados a ele.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE tutor SET ativo = 0 WHERE id_tutor = %s", (id_tutor,))
        if cur.rowcount == 0:
            return jsonify({"erro": "tutor não encontrado"}), 404
    return jsonify({"mensagem": "inativado"})
