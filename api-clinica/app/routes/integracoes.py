
"""Gerenciamento das integrações governamentais.

Permite consultar o histórico das operações, acompanhar
os status e realizar o reenvio de integrações pendentes
ou com falha.

Os reenvios preservam o payload original e a chave
de idempotência da operação.

Integrações confirmadas não são processadas novamente.
Integrações interrompidas durante o envio podem ser
recuperadas após dois minutos.
"""

from flask import Blueprint, jsonify, request, current_app

from app.auth import login_required
from app.db import get_conn
from app.services import governo_service


bp = Blueprint(
    "integracoes",
    __name__,
    url_prefix="/integracoes"
)


STATUS_VALIDOS = (
    "PENDENTE",
    "ENVIADO",
    "CONFIRMADO",
    "FALHA"
)


CAMPOS = """
    i.id_integracao,
    i.id_animal,
    a.nome AS nome_animal,
    i.id_vacina,
    i.tipo_operacao,
    i.status,
    i.protocolo,
    i.tentativas,
    i.data_criacao,
    i.ultima_tentativa,
    i.data_confirmacao,
    i.mensagem_erro,
    CASE
        WHEN i.status IN ('PENDENTE', 'FALHA')
            THEN 1
        WHEN i.status = 'ENVIADO'
            AND i.ultima_tentativa <=
                DATE_SUB(NOW(), INTERVAL 2 MINUTE)
            THEN 1
        ELSE 0
    END AS pode_reenviar
"""


def _select_base():
    """Consulta base das integrações governamentais."""

    return f"""
        SELECT {CAMPOS}
        FROM integracao_governo i
        JOIN animal a
            ON a.id_animal = i.id_animal
    """


def _buscar_integracao(id_integracao):
    """Consulta uma integração pelo identificador."""

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            _select_base() + """
                WHERE i.id_integracao = %s
            """,
            (id_integracao,)
        )

        return cur.fetchone()


@bp.get("/")
@login_required
def listar():
    """Lista as integrações governamentais."""

    sql = _select_base() + " WHERE 1=1"

    parametros = []

    status = request.args.get("status")

    if status:

        status = status.strip().upper()

        if status not in STATUS_VALIDOS:

            return jsonify({
                "erro": "status de integração inválido",
                "status_validos": list(STATUS_VALIDOS)
            }), 400

        sql += " AND i.status = %s"

        parametros.append(status)

    id_animal = request.args.get("id_animal")

    if id_animal is not None:

        if (
            not id_animal.isascii()
            or not id_animal.isdigit()
        ):

            return jsonify({
                "erro": "id_animal inválido"
            }), 400

        try:

            id_animal = int(id_animal)

        except ValueError:

            return jsonify({
                "erro": "id_animal inválido"
            }), 400

        if id_animal <= 0 or id_animal > 2147483647:

            return jsonify({
                "erro": "id_animal inválido"
            }), 400

        sql += " AND i.id_animal = %s"

        parametros.append(id_animal)

    sql += """
        ORDER BY i.data_criacao DESC,
                 i.id_integracao DESC
    """

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(sql, parametros)

        return jsonify(cur.fetchall())


@bp.get("/<int:id_integracao>")
@login_required
def buscar(id_integracao):
    """Consulta os detalhes de uma integração."""

    integracao = _buscar_integracao(
        id_integracao
    )

    if not integracao:

        return jsonify({
            "erro": "integração não encontrada"
        }), 404

    return jsonify(integracao), 200


@bp.post("/<int:id_integracao>/reenviar")
@login_required
def reenviar(id_integracao):
    """Realiza uma nova tentativa de comunicação."""

    try:

        # Consulta o estado atual da integração.
        integracao = _buscar_integracao(
            id_integracao
        )

        if not integracao:

            return jsonify({
                "erro": "integração não encontrada"
            }), 404

        # Integrações confirmadas não precisam
        # ser enviadas novamente.
        if integracao["status"] == "CONFIRMADO":

            return jsonify({
                "erro": "integração já confirmada",
                "id_integracao": id_integracao,
                "status": "CONFIRMADO",
                "protocolo": integracao["protocolo"]
            }), 409

        # Impede reenvio enquanto uma tentativa
        # recente ainda estiver em processamento.
        if not integracao["pode_reenviar"]:

            return jsonify({
                "erro": (
                    "integração em processamento; "
                    "aguarde antes de tentar novamente"
                ),
                "id_integracao": id_integracao,
                "status": integracao["status"]
            }), 409

        # O serviço controla atomicamente a tentativa,
        # preservando a chave de idempotência e o payload.
        processado = governo_service.reenviar(
            id_integracao
        )

        # Consulta novamente para retornar
        # o resultado real da tentativa.
        resultado = _buscar_integracao(
            id_integracao
        )

        if not resultado:

            return jsonify({
                "erro": "integração não encontrada"
            }), 404

        if not processado:

            if resultado["status"] == "CONFIRMADO":

                return jsonify({
                    "erro": "integração já confirmada",
                    "id_integracao": id_integracao,
                    "status": resultado["status"],
                    "protocolo": resultado["protocolo"]
                }), 409

            if (
                resultado["status"] == "ENVIADO"
                and not resultado["pode_reenviar"]
            ):

                return jsonify({
                    "erro": (
                        "integração em processamento "
                        "ou aguardando recuperação"
                    ),
                    "id_integracao": id_integracao,
                    "status": resultado["status"]
                }), 409

            return jsonify({
                "erro": (
                    "não foi possível processar "
                    "o reenvio da integração"
                ),
                "id_integracao": id_integracao,
                "status": resultado["status"]
            }), 503

        # HTTP 200 significa que a tentativa foi
        # processada, não necessariamente confirmada.
        #
        # O resultado efetivo está no campo status.
        return jsonify(resultado), 200

    except Exception:

        current_app.logger.exception(
            "Erro ao reenviar integração %s",
            id_integracao
        )

        return jsonify({
            "erro": "não foi possível reenviar a integração"
        }), 500
