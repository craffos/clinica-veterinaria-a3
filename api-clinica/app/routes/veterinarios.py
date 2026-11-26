"""Lista simples de veterinários (usada para mostrar 'quem atendeu' nas
telas). Quem realiza cada consulta/vacina/vínculo é sempre o veterinário
logado (pego do token) - veja app/routes/consultas.py e afins."""
from flask import Blueprint, jsonify

from app.auth import login_required
from app.db import get_conn

bp = Blueprint("veterinarios", __name__, url_prefix="/veterinarios")


@bp.get("/")
@login_required
def listar():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id_veterinario, nome_completo, crmv, uf_crmv
               FROM veterinario WHERE ativo = 1 ORDER BY nome_completo"""
        )
        return jsonify(cur.fetchall())
