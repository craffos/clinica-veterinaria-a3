"""Cadastro, atualização e consulta governamental com versionamento."""
import hashlib
import json
import re

import pymysql
from flask import Blueprint, jsonify, request, current_app
from app.auth import api_key_required
from app.db import get_conn
from app.utils import gerar_protocolo

bp = Blueprint("animais", __name__, url_prefix="/animais")


def _validar(dados):
    if not isinstance(dados, dict):
        return "corpo da requisição JSON inválido"
    chave = dados.get("chave_idempotencia")
    if not isinstance(chave, str) or not chave.strip() or len(chave) > 100:
        return "chave de idempotência inválida"
    identificador = dados.get("id_animal_clinica")
    if type(identificador) is not int or not 0 < identificador <= 2147483647:
        return "id_animal_clinica inválido"
    versao = dados.get("versao_origem")
    if type(versao) is not int or not 0 < versao <= 18446744073709551615:
        return "versao_origem deve ser um inteiro positivo"
    for campo, limite in (("nome", 80), ("especie", 60)):
        valor = dados.get(campo)
        if not isinstance(valor, str) or not valor.strip() or len(valor) > limite:
            return f"{campo} inválido"
    raca = dados.get("raca")
    if raca is not None and (not isinstance(raca, str) or len(raca) > 80):
        return "raça inválida"
    chip = dados.get("numero_microchip")
    if chip is not None and (not isinstance(chip, str) or not re.fullmatch(r"[0-9]{15}", chip)):
        return "microchip deve conter exatamente 15 dígitos"
    return None


def _hash_payload(dados):
    campos = ("id_animal_clinica", "nome", "especie", "raca", "numero_microchip", "versao_origem")
    payload = {campo: dados.get(campo) for campo in campos}
    payload["tipo"] = "ANIMAL"
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@bp.post("/")
@api_key_required
def registrar():
    dados = request.get_json(silent=True)
    erro = _validar(dados)
    if erro:
        return jsonify({"erro": erro}), 400
    if request.args.get("simular_falha") == "1":
        return jsonify({"erro": "serviço indisponível (falha simulada)"}), 503

    chave = dados["chave_idempotencia"]
    id_animal = dados["id_animal_clinica"]
    versao = dados["versao_origem"]
    nome, especie = dados["nome"], dados["especie"]
    raca, microchip = dados.get("raca"), dados.get("numero_microchip")
    payload_hash = _hash_payload(dados)
    protocolo = gerar_protocolo("AN")
    conn = get_conn()
    try:
        conn.begin()
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO operacao_recebida
                        (chave_idempotencia, payload_hash, protocolo)
                    VALUES (%s, %s, %s)
                """, (chave, payload_hash, protocolo))
            except pymysql.err.IntegrityError as exc:
                conn.rollback()
                if exc.args[0] != 1062:
                    raise
                cur.execute("""
                    SELECT protocolo, payload_hash FROM operacao_recebida
                    WHERE chave_idempotencia = %s
                """, (chave,))
                existente = cur.fetchone()
                if (not existente or not existente["protocolo"].startswith("AN-")
                        or existente["payload_hash"] != payload_hash):
                    return jsonify({"erro": "conflito de idempotência: chave já utilizada com outra operação ou conteúdo"}), 409
                return jsonify({"protocolo": existente["protocolo"], "repetido": True}), 200

            cur.execute("""
                SELECT id_registro, versao_origem FROM animal_registrado
                WHERE id_animal_clinica = %s FOR UPDATE
            """, (id_animal,))
            animal = cur.fetchone()

            if animal and versao < animal["versao_origem"]:
                conn.commit()
                return jsonify({
                    "mensagem": "operação antiga recebida sem sobrescrever o cadastro",
                    "id_registro": animal["id_registro"],
                    "id_animal_clinica": id_animal,
                    "versao_origem": versao,
                    "versao_atual": animal["versao_origem"],
                    "protocolo": protocolo,
                    "aplicado": False,
                    "repetido": False
                }), 200
            if animal and versao == animal["versao_origem"]:
                conn.rollback()
                return jsonify({"erro": "versão já utilizada por outra operação"}), 409

            if microchip is not None:
                cur.execute("""
                    SELECT id_animal_clinica FROM animal_registrado
                    WHERE numero_microchip = %s AND id_animal_clinica <> %s
                """, (microchip, id_animal))
                if cur.fetchone():
                    conn.rollback()
                    return jsonify({"erro": "microchip já registrado para outro animal"}), 409

            if animal:
                id_registro = animal["id_registro"]
                cur.execute("""
                    UPDATE animal_registrado SET nome = %s, especie = %s,
                        raca = %s, numero_microchip = %s, versao_origem = %s,
                        data_atualizacao = NOW()
                    WHERE id_registro = %s
                """, (nome, especie, raca, microchip, versao, id_registro))
                mensagem, status_http = "animal atualizado com sucesso", 200
            else:
                cur.execute("""
                    INSERT INTO animal_registrado
                        (id_animal_clinica, nome, especie, raca, numero_microchip, versao_origem, protocolo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (id_animal, nome, especie, raca, microchip, versao, protocolo))
                id_registro = cur.lastrowid
                mensagem, status_http = "animal registrado com sucesso", 201

            cur.execute("""
                UPDATE vacina_antirrabica_registrada SET id_registro = %s
                WHERE id_animal_clinica = %s AND id_registro IS NULL
            """, (id_registro, id_animal))
        conn.commit()
        return jsonify({"mensagem": mensagem, "id_registro": id_registro,
                        "id_animal_clinica": id_animal, "versao_origem": versao,
                        "protocolo": protocolo, "aplicado": True, "repetido": False}), status_http
    except pymysql.err.IntegrityError:
        conn.rollback()
        return jsonify({"erro": "conflito no registro do animal"}), 409
    except Exception:
        conn.rollback()
        current_app.logger.exception("Erro no registro governamental do animal")
        return jsonify({"erro": "não foi possível registrar o animal"}), 500
    finally:
        conn.close()


def _consultar(campo, valor):
    # Campo definido exclusivamente pelas rotas, nunca pelo cliente.
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM animal_registrado WHERE {campo} = %s", (valor,))
            animal = cur.fetchone()
        if not animal:
            return jsonify({"erro": "animal não encontrado"}), 404
        return jsonify(animal), 200
    finally:
        conn.close()


@bp.get("/<int:id_animal_clinica>")
@api_key_required
def consultar(id_animal_clinica):
    return _consultar("id_animal_clinica", id_animal_clinica)


@bp.get("/microchip/<numero_microchip>")
@api_key_required
def consultar_microchip(numero_microchip):
    if not re.fullmatch(r"[0-9]{15}", numero_microchip):
        return jsonify({"erro": "microchip deve conter exatamente 15 dígitos"}), 400
    return _consultar("numero_microchip", numero_microchip)
