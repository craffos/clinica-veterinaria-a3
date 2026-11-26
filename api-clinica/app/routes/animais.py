"""CRUD de animais da clínica veterinária.

O cadastro e a atualização de animais utilizam o padrão
Transactional Outbox para garantir a persistência dos dados
clínicos e da integração governamental na mesma transação.

A comunicação HTTP com o governo ocorre somente após o commit.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

import pymysql

from flask import Blueprint, jsonify, request, current_app

from app.auth import login_required
from app.db import get_conn
from app.services import governo_service
from app.validacoes import campos_faltando


bp = Blueprint("animais", __name__, url_prefix="/animais")


CAMPOS = """
    a.id_animal,
    a.nome,
    a.id_especie,
    esp.nome AS nome_especie,
    a.id_raca,
    r.nome AS nome_raca,
    a.sexo,
    a.cor,
    a.peso_atual,
    a.idade_estimada,
    a.dt_nasc,
    a.porte,
    a.id_tutor,
    t.nome_completo AS nome_tutor,
    a.observacao,
    a.ativo
"""


def _select_base():
    """Consulta base dos animais."""

    return f"""
        SELECT {CAMPOS}
        FROM animal a
        JOIN especie esp
            ON esp.id_especie = a.id_especie
        JOIN raca r
            ON r.id_raca = a.id_raca
        JOIN tutor t
            ON t.id_tutor = a.id_tutor
    """


@bp.get("/")
@login_required
def listar():
    """Lista os animais cadastrados."""

    sql = _select_base() + " WHERE 1=1"

    parametros = []

    if request.args.get("id_tutor"):
        sql += " AND a.id_tutor = %s"
        parametros.append(request.args["id_tutor"])

    if request.args.get("q"):
        sql += " AND a.nome LIKE %s"
        parametros.append(f"%{request.args['q']}%")

    if request.args.get("todos") != "1":
        sql += " AND a.ativo = 1"

    sql += " ORDER BY a.nome"

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(sql, parametros)

        return jsonify(cur.fetchall())


@bp.get("/<int:id_animal>")
@login_required
def buscar(id_animal):
    """Consulta um animal pelo identificador."""

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            _select_base() + " WHERE a.id_animal = %s",
            (id_animal,)
        )

        linha = cur.fetchone()

    if not linha:
        return jsonify({
            "erro": "animal não encontrado"
        }), 404

    return jsonify(linha)


def _validar(dados):
    """Valida os dados do animal."""

    if not isinstance(dados, dict):
        return "corpo da requisição JSON inválido"

    faltando = campos_faltando(
        dados,
        [
            "nome",
            "id_especie",
            "id_raca",
            "sexo",
            "id_tutor"
        ]
    )

    if faltando:
        return f"campos obrigatórios: {', '.join(faltando)}"

    nome = dados["nome"]

    if (
        not isinstance(nome, str)
        or not nome.strip()
        or len(nome.strip()) > 80
    ):
        return "nome do animal inválido"

    for campo in ("id_especie", "id_raca", "id_tutor"):

        valor = dados[campo]

        if isinstance(valor, str):
            if not valor.isascii() or not valor.isdigit():
                return f"{campo} inválido"

            try:
                valor = int(valor)
            except ValueError:
                return f"{campo} inválido"

        if type(valor) is not int or valor <= 0:
            return f"{campo} inválido"

        if valor > 2147483647:
            return f"{campo} inválido"

        dados[campo] = valor

    if dados["sexo"] not in ("M", "F"):
        return "sexo deve ser 'M' ou 'F'"

    porte = dados.get("porte")

    if porte not in (
        None,
        "",
        "PEQUENO",
        "MEDIO",
        "GRANDE"
    ):
        return "porte deve ser PEQUENO, MEDIO ou GRANDE"

    nascimento = dados.get("dt_nasc")

    if nascimento not in (None, ""):

        if not isinstance(nascimento, str):
            return "data de nascimento inválida"

        try:
            data_nascimento = date.fromisoformat(nascimento)

            if data_nascimento.isoformat() != nascimento:
                return "data de nascimento deve utilizar YYYY-MM-DD"

            if data_nascimento > date.today():
                return "data de nascimento não pode ser futura"

        except ValueError:
            return "data de nascimento inválida"

    cor = dados.get("cor")
    if cor is not None:
        if not isinstance(cor, str) or len(cor.strip()) > 80:
            return "cor inválida"
        dados["cor"] = cor.strip() or None

    peso = dados.get("peso_atual")
    if peso not in (None, ""):
        try:
            if isinstance(peso, bool):
                return "peso atual inválido"
            peso = Decimal(str(peso))
            if not peso.is_finite() or not 0 < peso <= Decimal("9999.99"):
                return "peso atual deve ser positivo e até 9999,99 kg"
            if peso != peso.quantize(Decimal("0.01")):
                return "peso atual deve ter até duas casas decimais"
            dados["peso_atual"] = peso
        except (InvalidOperation, ValueError):
            return "peso atual inválido"
    else:
        dados["peso_atual"] = None

    idade = dados.get("idade_estimada")
    if idade not in (None, ""):
        if isinstance(idade, str) and idade.isascii() and idade.isdigit() and len(idade) <= 5:
            idade = int(idade)
        if type(idade) is not int or not 0 <= idade <= 65535:
            return "idade estimada deve ser um inteiro entre 0 e 65535 meses"
        dados["idade_estimada"] = idade
    else:
        dados["idade_estimada"] = None

    observacao = dados.get("observacao")

    if observacao is not None:
        if not isinstance(observacao, str):
            return "observação inválida"

    return None


def _validar_referencias(cur, dados):
    """Verifica os relacionamentos e registros ativos."""

    cur.execute(
        """
        SELECT id_tutor
        FROM tutor
        WHERE id_tutor = %s
          AND ativo = 1
        FOR UPDATE
        """,
        (dados["id_tutor"],)
    )

    if not cur.fetchone():
        return "tutor inexistente ou inativo"

    cur.execute(
        """
        SELECT id_especie
        FROM especie
        WHERE id_especie = %s
          AND ativo = 1
        FOR UPDATE
        """,
        (dados["id_especie"],)
    )

    if not cur.fetchone():
        return "espécie inexistente ou inativa"

    cur.execute(
        """
        SELECT id_raca
        FROM raca
        WHERE id_raca = %s
          AND id_especie = %s
          AND ativo = 1
        FOR UPDATE
        """,
        (
            dados["id_raca"],
            dados["id_especie"]
        )
    )

    if not cur.fetchone():
        return (
            "raça inexistente, inativa ou "
            "incompatível com a espécie"
        )

    return None


def _valores_animal(dados):
    """Normaliza os valores utilizados no INSERT e UPDATE."""

    return (
        dados["nome"].strip(),
        dados["id_especie"],
        dados["id_raca"],
        dados["sexo"],
        dados.get("dt_nasc") or None,
        dados.get("porte") or None,
        dados["id_tutor"],
        dados.get("observacao") or None,
        dados.get("cor"),
        dados.get("peso_atual"),
        dados.get("idade_estimada")
    )


@bp.post("/")
@login_required
def criar():
    """Cadastra um animal e registra sua integração."""

    dados = request.get_json(silent=True)

    erro = _validar(dados)

    if erro:
        return jsonify({"erro": erro}), 400

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                erro = _validar_referencias(cur, dados)

                if erro:
                    conn.rollback()
                    return jsonify({"erro": erro}), 400

                # Registra o animal na clínica.
                cur.execute(
                    """
                    INSERT INTO animal (
                        nome,
                        id_especie,
                        id_raca,
                        sexo,
                        dt_nasc,
                        porte,
                        id_tutor,
                        observacao,
                        cor,
                        peso_atual,
                        idade_estimada
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    """,
                    _valores_animal(dados)
                )

                id_animal = cur.lastrowid

                # Registra a integração na mesma transação.
                id_integracao = governo_service.registrar_animal(
                    cur,
                    id_animal,
                    tipo_operacao="CADASTRO_ANIMAL"
                )

            # Confirma os dois registros no banco local.
            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": (
                "tutor, espécie ou raça inválidos "
                "ou incompatibilidade entre espécie e raça"
            )
        }), 400

    except Exception:

        current_app.logger.exception(
            "Erro ao cadastrar animal"
        )

        return jsonify({
            "erro": "não foi possível cadastrar o animal"
        }), 500

    # Comunicação governamental somente após o commit.
    # Uma indisponibilidade externa não desfaz o cadastro.
    governo_service.enviar_integracao(id_integracao)

    return jsonify({
        "id_animal": id_animal,
        "id_integracao": id_integracao
    }), 201


@bp.put("/<int:id_animal>")
@login_required
def atualizar(id_animal):
    """Atualiza um animal e registra sua integração."""

    dados = request.get_json(silent=True)

    campos_recebidos = set(dados) if isinstance(dados, dict) else set()
    erro = _validar(dados)

    if erro:
        return jsonify({"erro": erro}), 400

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

                # Bloqueia o registro durante a atualização.
                cur.execute(
                    """
                    SELECT id_animal, ativo, cor, peso_atual, idade_estimada
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

                for campo in ("cor", "peso_atual", "idade_estimada"):
                    if campo not in campos_recebidos:
                        dados[campo] = animal[campo]

                erro = _validar_referencias(cur, dados)

                if erro:
                    conn.rollback()
                    return jsonify({"erro": erro}), 400

                # Atualiza os dados clínicos.
                cur.execute(
                    """
                    UPDATE animal
                    SET nome = %s,
                        id_especie = %s,
                        id_raca = %s,
                        sexo = %s,
                        dt_nasc = %s,
                        porte = %s,
                        id_tutor = %s,
                        observacao = %s,
                        cor = %s,
                        peso_atual = %s,
                        idade_estimada = %s
                    WHERE id_animal = %s
                    """,
                    _valores_animal(dados) + (id_animal,)
                )

                # Registra a atualização governamental
                # dentro da mesma transação.
                id_integracao = governo_service.registrar_animal(
                    cur,
                    id_animal,
                    tipo_operacao="ATUALIZACAO_ANIMAL"
                )

            conn.commit()

    except pymysql.err.IntegrityError:

        return jsonify({
            "erro": (
                "tutor, espécie ou raça inválidos "
                "ou incompatibilidade entre espécie e raça"
            )
        }), 400

    except Exception:

        current_app.logger.exception(
            "Erro ao atualizar animal %s",
            id_animal
        )

        return jsonify({
            "erro": "não foi possível atualizar o animal"
        }), 500

    # Tenta comunicar o governo após a persistência local.
    governo_service.enviar_integracao(id_integracao)

    return jsonify({
        "mensagem": "atualizado",
        "id_animal": id_animal,
        "id_integracao": id_integracao
    }), 200


@bp.delete("/<int:id_animal>")
@login_required
def inativar(id_animal):
    """Realiza a exclusão lógica do animal."""

    try:

        with get_conn(autocommit=False) as conn:

            with conn.cursor() as cur:

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
                        "mensagem": "animal já inativado"
                    }), 200

                cur.execute(
                    """
                    UPDATE animal
                    SET ativo = 0
                    WHERE id_animal = %s
                    """,
                    (id_animal,)
                )

            conn.commit()

    except Exception:

        current_app.logger.exception(
            "Erro ao inativar animal %s",
            id_animal
        )

        return jsonify({
            "erro": "não foi possível inativar o animal"
        }), 500

    return jsonify({
        "mensagem": "inativado"
    }), 200
