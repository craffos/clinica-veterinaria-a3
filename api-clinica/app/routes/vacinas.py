"""CRUD de vacinas da clínica veterinária.

Cada registro representa uma dose agendada, aplicada ou cancelada.

Vacinas antirrábicas são persistidas juntamente com a
integração governamental na mesma transação, utilizando
o padrão Transactional Outbox.

A comunicação com o governo ocorre somente após o commit.
"""

from datetime import date

import pymysql

from flask import Blueprint, g, jsonify, request, current_app

from app.auth import login_required
from app.db import get_conn
from app.services import governo_service
from app.validacoes import campos_faltando


bp = Blueprint("vacinas", __name__, url_prefix="/vacinas")


CAMPOS = """
    vc.id_vacina,
    vc.id_animal,
    a.nome AS nome_animal,
    vc.id_veterinario,
    vt.nome_completo AS nome_veterinario,
    vc.nome_vacina,
    vc.antirrabica,
    vc.fabricante,
    vc.lote,
    vc.data_aplicacao,
    vc.dose,
    vc.via_administracao,
    vc.proxima_dose,
    vc.observacao, vc.tipo_vacina, vc.validade_lote, vc.status
"""


def _select_base():
    """Consulta base das vacinas."""

    return f"""
        SELECT {CAMPOS}
        FROM vacina vc
        JOIN animal a
            ON a.id_animal = vc.id_animal
        JOIN veterinario vt
            ON vt.id_veterinario = vc.id_veterinario
    """


@bp.get("/")
@login_required
def listar():
    """Lista as vacinas registradas."""

    sql = _select_base() + " WHERE 1=1"

    parametros = []

    if request.args.get("id_animal"):

        sql += " AND vc.id_animal = %s"

        parametros.append(
            request.args["id_animal"]
        )

    sql += """
        ORDER BY vc.data_aplicacao DESC,
                 vc.id_vacina DESC
    """

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(sql, parametros)

        return jsonify(cur.fetchall())


@bp.get("/<int:id_vacina>")
@login_required
def buscar(id_vacina):
    """Consulta uma vacinação pelo identificador."""

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            _select_base() + " WHERE vc.id_vacina = %s",
            (id_vacina,)
        )

        linha = cur.fetchone()

    if not linha:

        return jsonify({
            "erro": "vacina não encontrada"
        }), 404

    return jsonify(linha)


def _normalizar_antirrabica(valor):
    """Converte valores válidos para 0 ou 1."""

    if isinstance(valor, bool):
        return int(valor)

    if type(valor) is int and valor in (0, 1):
        return valor

    if isinstance(valor, str):

        valor = valor.strip().lower()

        if valor in ("1", "true"):
            return 1

        if valor in ("0", "false"):
            return 0

    raise ValueError(
        "antirrabica deve ser 0, 1, true ou false"
    )


def _validar_data(valor):
    """Valida uma data no formato YYYY-MM-DD."""

    if not isinstance(valor, str):
        raise ValueError("data inválida")

    data_convertida = date.fromisoformat(valor)

    if data_convertida.isoformat() != valor:
        raise ValueError("formato de data inválido")

    return data_convertida


def _validar(dados, criacao=False):
    """Valida e normaliza os dados da vacinação."""

    if not isinstance(dados, dict):
        return "corpo da requisição JSON inválido"

    obrigatorios = [
        "nome_vacina",
        "data_aplicacao"
    ]

    if criacao:
        obrigatorios.append("id_animal")

    faltando = campos_faltando(
        dados,
        obrigatorios
    )

    if faltando:
        return f"campos obrigatórios: {', '.join(faltando)}"

    if criacao:

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

    nome = dados["nome_vacina"]

    if not isinstance(nome, str) or not nome.strip():
        return "nome da vacina inválido"

    dados["nome_vacina"] = nome.strip()

    try:

        if criacao or "antirrabica" in dados:

            dados["antirrabica"] = _normalizar_antirrabica(
                dados.get("antirrabica", 0)
            )

    except ValueError as erro:
        return str(erro)

    try:

        aplicacao = _validar_data(
            dados["data_aplicacao"]
        )

    except ValueError:

        return "data de aplicação deve utilizar YYYY-MM-DD"

    status = dados.get("status", "APLICADA")
    if status not in ("AGENDADA", "APLICADA", "CANCELADA"):
        return "status inválido"
    dados["status"] = status
    if status == "APLICADA" and aplicacao > date.today():

        return "data de aplicação não pode ser futura"

    proxima_dose = dados.get("proxima_dose")

    if proxima_dose not in (None, ""):

        try:

            proxima = _validar_data(proxima_dose)

        except ValueError:

            return "próxima dose deve utilizar YYYY-MM-DD"

        if proxima <= aplicacao:

            return (
                "próxima dose deve ser posterior "
                "à data de aplicação"
            )

    else:

        dados["proxima_dose"] = None

    validade = dados.get("validade_lote")
    if validade not in (None, ""):
        try:
            if _validar_data(validade) < aplicacao:
                return "validade do lote anterior à data da vacina"
        except ValueError:
            return "validade_lote deve utilizar YYYY-MM-DD"
    else:
        dados["validade_lote"] = None

    campos_opcionais = (
        "tipo_vacina",
        "fabricante",
        "lote",
        "dose",
        "via_administracao",
        "observacao"
    )

    for campo in campos_opcionais:

        valor = dados.get(campo)

        if valor is not None:

            if not isinstance(valor, str):
                return f"{campo} inválido"

            dados[campo] = valor.strip() or None

    for campo, limite in (("nome_vacina", 100), ("tipo_vacina", 80), ("fabricante", 100), ("dose", 30), ("via_administracao", 30)):
        if len(dados.get(campo) or "") > limite:
            return f"{campo} excede {limite} caracteres"
    lote = dados.get("lote")

    if lote is not None and len(lote) > 50:

        return "lote deve conter até 50 caracteres"

    return None


def _valores_vacina(dados):
    """Organiza os valores utilizados no banco."""

    return (
        dados["nome_vacina"],
        dados["antirrabica"],
        dados.get("fabricante"),
        dados.get("lote"),
        dados["data_aplicacao"],
        dados.get("dose"),
        dados.get("via_administracao"),
        dados.get("proxima_dose"),
        dados.get("observacao"), dados.get("tipo_vacina"), dados.get("validade_lote"), dados["status"]
    )


@bp.post("/")
@login_required
def criar():
    """Registra uma dose efetivamente aplicada."""

    dados = request.get_json(silent=True)

    erro = _validar(dados, criacao=True)

    if erro:

        return jsonify({"erro": erro}), 400

    id_animal = dados["id_animal"]

    id_veterinario = g.veterinario["id_veterinario"]

    id_integracao = None

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                # Verifica se o animal existe e está ativo.
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

                # Registra a vacinação local.
                cur.execute(
                    """
                    INSERT INTO vacina (
                        id_animal,
                        id_veterinario,
                        nome_vacina,
                        antirrabica,
                        fabricante,
                        lote,
                        data_aplicacao,
                        dose,
                        via_administracao,
                        proxima_dose,
                        observacao, tipo_vacina, validade_lote, status
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        id_animal,
                        id_veterinario
                    ) + _valores_vacina(dados)
                )

                id_vacina = cur.lastrowid

                # Somente vacinas antirrábicas geram
                # uma integração governamental.
                if dados["antirrabica"] == 1 and dados["status"] == "APLICADA":

                    id_integracao = (
                        governo_service.registrar_vacina(
                            cur,
                            id_vacina,
                            id_animal
                        )
                    )

            # Confirma a vacinação e a integração
            # na mesma transação local.
            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": "dados ou relacionamentos inválidos"
        }), 400

    except pymysql.err.DataError:

        return jsonify({
            "erro": "dados da vacinação inválidos"
        }), 400

    except Exception:

        current_app.logger.exception(
            "Erro ao registrar vacinação"
        )

        return jsonify({
            "erro": "não foi possível registrar a vacinação"
        }), 500

    # A comunicação externa acontece após o commit.
    if id_integracao is not None:

        governo_service.enviar_integracao(
            id_integracao
        )

    return jsonify({
        "id_vacina": id_vacina,
        "antirrabica": dados["antirrabica"],
        "id_integracao": id_integracao
    }), 201


@bp.put("/<int:id_vacina>")
@login_required
def atualizar(id_vacina):
    """Atualiza os dados de uma vacinação registrada."""

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({"erro": "JSON inválido"}), 400

    id_integracao = None

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                # Bloqueia a vacinação durante a atualização.
                cur.execute(
                    """
                    SELECT *
                    FROM vacina
                    WHERE id_vacina = %s
                    FOR UPDATE
                    """,
                    (id_vacina,)
                )

                vacina = cur.fetchone()

                if not vacina:

                    conn.rollback()

                    return jsonify({
                        "erro": "vacina não encontrada"
                    }), 404

                id_animal = vacina["id_animal"]

                anteriores = {k: (v.isoformat() if isinstance(v, date) else v) for k,v in vacina.items()}
                dados = {**anteriores, **dados}
                erro = _validar(dados)
                if erro:
                    conn.rollback()
                    return jsonify({"erro": erro}), 400
                if vacina["status"] == "CANCELADA" and dados["status"] != "CANCELADA":
                    conn.rollback()
                    return jsonify({"erro": "vacina cancelada"}), 409
                if vacina["status"] == "APLICADA" and dados["status"] == "AGENDADA":
                    conn.rollback()
                    return jsonify({"erro": "vacina já aplicada"}), 409

                # Preserva a classificação anterior quando
                # o campo antirrabica não for informado.
                if "antirrabica" not in dados:

                    dados["antirrabica"] = int(
                        vacina["antirrabica"]
                    )

                # Não permite transferir a vacinação
                # para outro animal.
                if "id_animal" in dados:

                    if str(dados["id_animal"]) != str(id_animal):

                        conn.rollback()

                        return jsonify({
                            "erro": (
                                "não é permitido alterar "
                                "o animal da vacinação"
                            )
                        }), 409

                # Verifica se já existe integração
                # governamental para esta vacinação.
                cur.execute(
                    """
                    SELECT id_integracao, status
                    FROM integracao_governo
                    WHERE id_vacina = %s
                      AND tipo_operacao = 'VACINA_ANTIRRABICA'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (id_vacina,)
                )

                integracao_existente = cur.fetchone()

                if integracao_existente:

                    # Os campos enviados ao governo devem
                    # permanecer consistentes com o payload.
                    alterou_classificacao = (
                        dados["antirrabica"]
                        != int(vacina["antirrabica"])
                    )

                    alterou_data = (
                        dados["data_aplicacao"]
                        != str(vacina["data_aplicacao"])
                    )

                    alterou_lote = (
                        dados.get("lote")
                        != vacina["lote"]
                    )

                    if (
                        alterou_classificacao
                        or alterou_data
                        or alterou_lote
                        or any(dados[c] != vacina[c] for c in ("status", "nome_vacina", "fabricante"))
                    ):

                        conn.rollback()

                        return jsonify({
                            "erro": (
                                "não é permitido alterar "
                                "a classificação antirrábica, "
                                "a data, lote, nome, fabricante ou status "
                                "de uma vacina com integração "
                                "governamental registrada"
                            )
                        }), 409

                # Atualiza os dados clínicos permitidos.
                cur.execute(
                    """
                    UPDATE vacina
                    SET nome_vacina = %s,
                        antirrabica = %s,
                        fabricante = %s,
                        lote = %s,
                        data_aplicacao = %s,
                        dose = %s,
                        via_administracao = %s,
                        proxima_dose = %s,
                        observacao = %s, tipo_vacina = %s, validade_lote = %s, status = %s
                    WHERE id_vacina = %s
                    """,
                    _valores_vacina(dados) + (id_vacina,)
                )

                # Se uma vacina comum for corrigida para
                # antirrábica, cria a integração obrigatória.
                #
                # Também recupera registros antirrábicos
                # antigos que não possuam integração.
                if (
                    dados["antirrabica"] == 1
                    and dados["status"] == "APLICADA"
                    and not integracao_existente
                ):

                    id_integracao = (
                        governo_service.registrar_vacina(
                            cur,
                            id_vacina,
                            id_animal
                        )
                    )

            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": "dados ou relacionamentos inválidos"
        }), 400

    except pymysql.err.DataError:

        return jsonify({
            "erro": "dados da vacinação inválidos"
        }), 400

    except Exception:

        current_app.logger.exception(
            "Erro ao atualizar vacinação %s",
            id_vacina
        )

        return jsonify({
            "erro": "não foi possível atualizar a vacinação"
        }), 500

    # Envia somente quando uma nova integração foi criada.
    if id_integracao is not None:

        governo_service.enviar_integracao(
            id_integracao
        )

    return jsonify({
        "mensagem": "atualizada",
        "id_vacina": id_vacina,
        "id_integracao": id_integracao
    }), 200
