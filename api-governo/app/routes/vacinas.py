"""Recebimento de notificações de vacinação antirrábica.

Implementa:
- Autenticação por API Key.
- Idempotência com SHA-256.
- Prevenção de duplicidade de vacinação.
- Persistência transacional.
- Recebimento de vacinas independentemente do cadastro
  governamental prévio do animal.
"""

import hashlib
import json

from datetime import date

import pymysql

from flask import Blueprint, jsonify, request, current_app

from app.auth import api_key_required
from app.db import get_conn
from app.utils import gerar_protocolo


bp = Blueprint(
    "vacinas",
    __name__,
    url_prefix="/vacinas"
)


def _validar(dados):
    """Valida os dados recebidos da API da clínica."""

    if not isinstance(dados, dict):
        return "corpo da requisição JSON inválido"

    chave = dados.get("chave_idempotencia")

    if (
        not isinstance(chave, str)
        or not chave.strip()
        or len(chave) > 100
    ):
        return "chave de idempotência inválida"

    for campo in (
        "id_animal_clinica",
        "id_vacina_clinica"
    ):

        valor = dados.get(campo)

        if (
            type(valor) is not int
            or valor <= 0
            or valor > 2147483647
        ):
            return f"{campo} inválido"

    data_aplicacao = dados.get("data_aplicacao")

    if not isinstance(data_aplicacao, str):
        return "data_aplicacao inválida"

    try:

        data_convertida = date.fromisoformat(
            data_aplicacao
        )

        if data_convertida.isoformat() != data_aplicacao:

            return "data_aplicacao deve utilizar YYYY-MM-DD"

        if data_convertida > date.today():

            return "data de aplicação não pode ser futura"

    except ValueError:

        return "data_aplicacao deve utilizar YYYY-MM-DD"

    lote = dados.get("lote")

    if lote is not None:

        if not isinstance(lote, str) or len(lote) > 50:

            return "lote inválido"

    for campo, limite in {'numero_microchip': 15, 'nome_animal': 80, 'nome_vacina': 100, 'fabricante': 100, 'nome_veterinario': 150, 'crmv': 20, 'uf_crmv': 2}.items():
        valor = dados.get(campo)
        if valor is not None and (not isinstance(valor, str) or len(valor) > limite):
            return f"{campo} inválido"
    vet = dados.get("id_veterinario_clinica")
    if vet is not None and (type(vet) is not int or not 0 < vet <= 2147483647):
        return "id_veterinario_clinica inválido"
    chip = dados.get("numero_microchip")
    if chip is not None and (len(chip) != 15 or not chip.isascii() or not chip.isdigit()):
        return "numero_microchip inválido"
    return None


CAMPOS_EXTRAS = ('numero_microchip', 'nome_animal', 'nome_vacina', 'fabricante', 'id_veterinario_clinica', 'nome_veterinario', 'crmv', 'uf_crmv')

def _gerar_payload_hash(dados):
    """Gera um hash SHA-256 determinístico da operação."""

    payload = {
        "tipo_operacao": "VACINA_ANTIRRABICA",
        "id_animal_clinica": dados["id_animal_clinica"],
        "id_vacina_clinica": dados["id_vacina_clinica"],
        "data_aplicacao": dados["data_aplicacao"],
        "lote": dados.get("lote")
    }

    payload.update({c: dados[c] for c in CAMPOS_EXTRAS if c in dados})
    payload_canonico = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":")
    )

    return hashlib.sha256(
        payload_canonico.encode("utf-8")
    ).hexdigest()


def _mesma_vacina(
    vacina,
    id_animal,
    id_vacina,
    data_aplicacao,
    lote, dados
):
    """Compara os dados de uma vacinação já registrada."""

    return (
        vacina is not None
        and vacina["id_animal_clinica"] == id_animal
        and vacina["id_vacina_clinica"] == id_vacina
        and str(vacina["data_aplicacao"]) == data_aplicacao
        and vacina["lote"] == lote
        and all(vacina[c] == dados.get(c) for c in CAMPOS_EXTRAS)
    )


@bp.post("/")
@api_key_required
def registrar():
    """Registra uma vacinação antirrábica no governo."""

    dados = request.get_json(silent=True)

    erro = _validar(dados)

    if erro:

        return jsonify({"erro": erro}), 400

    # Permite testar a indisponibilidade governamental.
    if request.args.get("simular_falha") == "1":

        return jsonify({
            "erro": "serviço indisponível (falha simulada)"
        }), 503

    chave = dados["chave_idempotencia"]

    id_animal = dados["id_animal_clinica"]

    id_vacina = dados["id_vacina_clinica"]

    data_aplicacao = dados["data_aplicacao"]

    lote = dados.get("lote")

    payload_hash = _gerar_payload_hash(dados)

    protocolo = gerar_protocolo("VC")

    conn = get_conn()

    try:

        conn.begin()

        with conn.cursor() as cur:

            # Registra a chave e o hash da operação.
            try:

                cur.execute(
                    """
                    INSERT INTO operacao_recebida (
                        chave_idempotencia,
                        payload_hash,
                        protocolo
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (
                        chave,
                        payload_hash,
                        protocolo
                    )
                )

            except pymysql.err.IntegrityError as erro:

                conn.rollback()

                if erro.args[0] != 1062:

                    raise

                # A chave já foi processada anteriormente.
                cur.execute(
                    """
                    SELECT protocolo, payload_hash
                    FROM operacao_recebida
                    WHERE chave_idempotencia = %s
                    """,
                    (chave,)
                )

                existente = cur.fetchone()

                if not existente:

                    return jsonify({
                        "erro": "conflito de idempotência"
                    }), 409

                protocolo_existente = existente["protocolo"]

                # Impede reutilização de uma chave
                # pertencente a outro tipo de operação.
                if not protocolo_existente.startswith("VC-"):

                    return jsonify({
                        "erro": (
                            "chave de idempotência utilizada "
                            "em outra operação"
                        )
                    }), 409

                hash_existente = existente["payload_hash"]

                # Detecta reutilização da chave com
                # conteúdo diferente.
                if (
                    hash_existente is not None
                    and hash_existente != payload_hash
                ):

                    return jsonify({
                        "erro": (
                            "chave de idempotência utilizada "
                            "com dados diferentes"
                        )
                    }), 409

                # Confere também o registro persistido.
                # Mantém compatibilidade com registros
                # antigos que ainda não possuam hash.
                cur.execute(
                    """
                    SELECT
                        id_animal_clinica,
                        id_vacina_clinica,
                        data_aplicacao,
                        lote, numero_microchip, nome_animal, nome_vacina, fabricante, id_veterinario_clinica, nome_veterinario, crmv, uf_crmv
                    FROM vacina_antirrabica_registrada
                    WHERE protocolo = %s
                    """,
                    (protocolo_existente,)
                )

                vacina = cur.fetchone()

                if not _mesma_vacina(
                    vacina,
                    id_animal,
                    id_vacina,
                    data_aplicacao,
                    lote, dados
                ):

                    return jsonify({
                        "erro": (
                            "chave de idempotência utilizada "
                            "com dados diferentes"
                        )
                    }), 409

                # Preenche o hash de operações antigas,
                # caso existam.
                if hash_existente is None:

                    cur.execute(
                        """
                        UPDATE operacao_recebida
                        SET payload_hash = %s
                        WHERE chave_idempotencia = %s
                          AND payload_hash IS NULL
                        """,
                        (payload_hash, chave)
                    )

                return jsonify({
                    "protocolo": protocolo_existente,
                    "repetido": True
                }), 200

            # Verifica se o animal já está registrado.
            cur.execute(
                """
                SELECT id_registro
                FROM animal_registrado
                WHERE id_animal_clinica = %s
                FOR UPDATE
                """,
                (id_animal,)
            )

            animal = cur.fetchone()

            # A ausência de cadastro governamental
            # não impede o registro da vacinação.
            id_registro = (
                animal["id_registro"]
                if animal
                else None
            )

            # Verifica se a vacinação já foi registrada,
            # mesmo utilizando outra chave de idempotência.
            cur.execute(
                """
                SELECT
                    id_animal_clinica,
                    id_vacina_clinica,
                    data_aplicacao,
                    lote,
                    numero_microchip, nome_animal, nome_vacina, fabricante, id_veterinario_clinica, nome_veterinario, crmv, uf_crmv,
                    protocolo
                FROM vacina_antirrabica_registrada
                WHERE id_vacina_clinica = %s
                FOR UPDATE
                """,
                (id_vacina,)
            )

            existente = cur.fetchone()

            if existente:

                if not _mesma_vacina(
                    existente,
                    id_animal,
                    id_vacina,
                    data_aplicacao,
                    lote, dados
                ):

                    conn.rollback()

                    return jsonify({
                        "erro": (
                            "vacina já registrada "
                            "com dados diferentes"
                        )
                    }), 409

                # Preserva o protocolo original.
                protocolo = existente["protocolo"]

                cur.execute(
                    """
                    UPDATE operacao_recebida
                    SET protocolo = %s
                    WHERE chave_idempotencia = %s
                    """,
                    (protocolo, chave)
                )

                conn.commit()

                return jsonify({
                    "protocolo": protocolo,
                    "repetido": True
                }), 200

            # Persiste a vacinação antirrábica.
            cur.execute(
                """
                INSERT INTO vacina_antirrabica_registrada (
                    id_registro,
                    id_animal_clinica,
                    id_vacina_clinica,
                    data_aplicacao,
                    lote,
                    numero_microchip, nome_animal, nome_vacina, fabricante, id_veterinario_clinica, nome_veterinario, crmv, uf_crmv,
                    protocolo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_registro,
                    id_animal,
                    id_vacina,
                    data_aplicacao,
                    lote,
                    dados.get('numero_microchip'), dados.get('nome_animal'), dados.get('nome_vacina'), dados.get('fabricante'), dados.get('id_veterinario_clinica'), dados.get('nome_veterinario'), dados.get('crmv'), dados.get('uf_crmv'),
                    protocolo
                )
            )

            id_registro_vacina = cur.lastrowid

        # Confirma a vacinação e o registro da
        # operação idempotente na mesma transação.
        conn.commit()

        return jsonify({
            "mensagem": "vacinação antirrábica registrada",
            "id_registro_vacina": id_registro_vacina,
            "protocolo": protocolo,
            "animal_cadastrado": animal is not None,
            "repetido": False
        }), 201

    except pymysql.err.IntegrityError:

        conn.rollback()

        return jsonify({
            "erro": "conflito no registro da vacinação"
        }), 409

    except Exception:

        conn.rollback()

        current_app.logger.exception(
            "Erro no registro governamental da vacinação"
        )

        return jsonify({
            "erro": "não foi possível registrar a vacinação"
        }), 500

    finally:

        conn.close()
