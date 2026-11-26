
"""Gerenciamento de vínculos de microchips RFID.

Regras de negócio:
- Um animal pode possuir somente um vínculo ativo.
- O número do microchip deve possuir exatamente 15 dígitos.
- O histórico de vinculação deve ser preservado.
- Somente veterinários autenticados podem realizar operações.
- Vinculações e desvinculações geram atualização governamental.

O vínculo e a integração governamental são registrados
na mesma transação, utilizando Transactional Outbox.

A comunicação HTTP ocorre somente após o commit.
"""

import re

import pymysql

from flask import Blueprint, g, jsonify, request, current_app

from app.auth import login_required
from app.db import get_conn
from app.services import governo_service
from app.validacoes import campos_faltando


bp = Blueprint(
    "microchips",
    __name__,
    url_prefix="/microchips"
)


CAMPOS = """
    m.id_vinculo,
    m.id_animal,
    a.nome AS nome_animal,
    m.id_veterinario,
    v.nome_completo AS nome_veterinario,
    m.numero_microchip,
    m.data_vinculacao,
    m.data_desvinculacao,
    m.ativo,
    m.observacao
"""


def _select_base():
    """Consulta base dos vínculos de microchips."""

    return f"""
        SELECT {CAMPOS}
        FROM vinculo_microchip m
        JOIN animal a
            ON a.id_animal = m.id_animal
        JOIN veterinario v
            ON v.id_veterinario = m.id_veterinario
    """


@bp.get("/")
@login_required
def listar():
    """Lista o histórico de vínculos de microchips."""

    sql = _select_base() + " WHERE 1=1"

    parametros = []

    if request.args.get("id_animal"):

        sql += " AND m.id_animal = %s"

        parametros.append(
            request.args["id_animal"]
        )

    sql += """
        ORDER BY m.data_vinculacao DESC,
                 m.id_vinculo DESC
    """

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(sql, parametros)

        return jsonify(cur.fetchall())


def _validar(dados):
    """Valida os dados da vinculação RFID."""

    if not isinstance(dados, dict):

        return "corpo da requisição JSON inválido"

    faltando = campos_faltando(
        dados,
        [
            "id_animal",
            "numero_microchip"
        ]
    )

    if faltando:

        return f"campos obrigatórios: {', '.join(faltando)}"

    id_animal = dados["id_animal"]

    if isinstance(id_animal, str):

        if (
            not id_animal.isascii()
            or not id_animal.isdigit()
        ):
            return "id_animal inválido"

        try:
            id_animal = int(id_animal)
        except ValueError:
            return "id_animal inválido"

    if (
        type(id_animal) is not int
        or id_animal <= 0
        or id_animal > 2147483647
    ):
        return "id_animal inválido"

    dados["id_animal"] = id_animal

    numero_microchip = dados["numero_microchip"]

    if not isinstance(numero_microchip, str):

        return "número do microchip deve ser uma string"

    numero_microchip = numero_microchip.strip()

    if not re.fullmatch(r"[0-9]{15}", numero_microchip):

        return (
            "número do microchip deve possuir "
            "exatamente 15 dígitos"
        )

    dados["numero_microchip"] = numero_microchip

    observacao = dados.get("observacao")

    if observacao is not None:

        if not isinstance(observacao, str):

            return "observação inválida"

        dados["observacao"] = observacao.strip() or None

    return None


@bp.post("/")
@login_required
def vincular():
    """Vincula um microchip RFID a um animal."""

    dados = request.get_json(silent=True)

    erro = _validar(dados)

    if erro:

        return jsonify({"erro": erro}), 400

    id_animal = dados["id_animal"]

    numero_microchip = dados["numero_microchip"]

    id_veterinario = g.veterinario["id_veterinario"]

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                # Bloqueia o animal durante a operação.
                cur.execute(
                    """
                    SELECT id_animal, ativo
                    FROM animal
                    WHERE id_animal = %s
                    FOR UPDATE
                    """,
                    (id_animal,)
                )

                animal = cur.fetchone()

                if not animal:

                    conn.rollback()

                    return jsonify({
                        "erro": "animal não encontrado"
                    }), 404

                if not animal["ativo"]:

                    conn.rollback()

                    return jsonify({
                        "erro": "animal inativo"
                    }), 409

                # Verifica se o animal já possui
                # um microchip ativo.
                cur.execute(
                    """
                    SELECT id_vinculo
                    FROM vinculo_microchip
                    WHERE id_animal = %s
                      AND ativo = 1
                    FOR UPDATE
                    """,
                    (id_animal,)
                )

                if cur.fetchone():

                    conn.rollback()

                    return jsonify({
                        "erro": (
                            "este animal já possui um "
                            "microchip ativo; desvincule antes"
                        )
                    }), 409

                # Preserva a restrição de unicidade
                # histórica do número do microchip.
                cur.execute(
                    """
                    SELECT id_vinculo, ativo
                    FROM vinculo_microchip
                    WHERE numero_microchip = %s
                    """,
                    (numero_microchip,)
                )

                microchip_existente = cur.fetchone()

                if microchip_existente:

                    conn.rollback()

                    if microchip_existente["ativo"]:

                        return jsonify({
                            "erro": (
                                "este número de microchip "
                                "já está vinculado a um animal"
                            )
                        }), 409

                    return jsonify({
                        "erro": (
                            "este número de microchip "
                            "já consta no histórico de vínculos"
                        )
                    }), 409

                # Registra o vínculo local.
                cur.execute(
                    """
                    INSERT INTO vinculo_microchip (
                        id_animal,
                        id_veterinario,
                        numero_microchip,
                        observacao
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        id_animal,
                        id_veterinario,
                        numero_microchip,
                        dados.get("observacao")
                    )
                )

                id_vinculo = cur.lastrowid

                # Registra a atualização governamental
                # na mesma transação.
                id_integracao = (
                    governo_service.registrar_animal(
                        cur,
                        id_animal,
                        tipo_operacao="ATUALIZACAO_ANIMAL"
                    )
                )

            # Confirma o vínculo e a integração.
            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": "conflito de vínculo de microchip"
        }), 409

    except pymysql.err.DataError:

        return jsonify({
            "erro": "dados do microchip inválidos"
        }), 400

    except Exception:

        current_app.logger.exception(
            "Erro ao vincular microchip ao animal %s",
            id_animal
        )

        return jsonify({
            "erro": "não foi possível vincular o microchip"
        }), 500

    # Comunicação externa somente após o commit.
    governo_service.enviar_integracao(
        id_integracao
    )

    return jsonify({
        "mensagem": "microchip vinculado",
        "id_vinculo": id_vinculo,
        "id_animal": id_animal,
        "numero_microchip": numero_microchip,
        "id_integracao": id_integracao
    }), 201


@bp.post("/<int:id_vinculo>/desvincular")
@login_required
def desvincular(id_vinculo):
    """Desvincula um microchip preservando seu histórico."""

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                # Identifica o animal associado ao vínculo.
                cur.execute(
                    """
                    SELECT id_animal
                    FROM vinculo_microchip
                    WHERE id_vinculo = %s
                    """,
                    (id_vinculo,)
                )

                referencia = cur.fetchone()

                if not referencia:

                    conn.rollback()

                    return jsonify({
                        "erro": "vínculo não encontrado"
                    }), 404

                id_animal = referencia["id_animal"]

                # Bloqueia primeiro o animal, mantendo
                # a ordem de bloqueio das demais rotas.
                cur.execute(
                    """
                    SELECT id_animal
                    FROM animal
                    WHERE id_animal = %s
                    FOR UPDATE
                    """,
                    (id_animal,)
                )

                if not cur.fetchone():

                    conn.rollback()

                    return jsonify({
                        "erro": "animal não encontrado"
                    }), 404

                # Bloqueia o vínculo antes de modificá-lo.
                cur.execute(
                    """
                    SELECT id_vinculo, ativo
                    FROM vinculo_microchip
                    WHERE id_vinculo = %s
                    FOR UPDATE
                    """,
                    (id_vinculo,)
                )

                vinculo = cur.fetchone()

                if not vinculo:

                    conn.rollback()

                    return jsonify({
                        "erro": "vínculo não encontrado"
                    }), 404

                # Desvinculação idempotente.
                if not vinculo["ativo"]:

                    conn.rollback()

                    return jsonify({
                        "mensagem": "microchip já desvinculado",
                        "id_vinculo": id_vinculo
                    }), 200

                # Desativa o vínculo sem apagar o histórico.
                cur.execute(
                    """
                    UPDATE vinculo_microchip
                    SET ativo = 0,
                        data_desvinculacao = NOW()
                    WHERE id_vinculo = %s
                    """,
                    (id_vinculo,)
                )

                # O payload governamental será criado
                # sem o microchip anteriormente ativo.
                id_integracao = (
                    governo_service.registrar_animal(
                        cur,
                        id_animal,
                        tipo_operacao="ATUALIZACAO_ANIMAL"
                    )
                )

            # Confirma a desvinculação e a integração.
            conn.commit()

    except Exception:

        current_app.logger.exception(
            "Erro ao desvincular microchip %s",
            id_vinculo
        )

        return jsonify({
            "erro": "não foi possível desvincular o microchip"
        }), 500

    # Atualiza o governo após a persistência local.
    governo_service.enviar_integracao(
        id_integracao
    )

    return jsonify({
        "mensagem": "desvinculado",
        "id_vinculo": id_vinculo,
        "id_animal": id_animal,
        "id_integracao": id_integracao
    }), 200
