"""Serviço de integração da clínica com a API governamental.

Implementa uma versão simplificada do padrão Transactional Outbox,
com persistência do payload original, autenticação por API Key,
idempotência e reenvio de operações pendentes.
"""

import json
import uuid

import requests

from flask import current_app

from app.db import get_conn


TIMEOUT_SEGUNDOS = 5


def _criar_integracao(
    cur,
    id_animal,
    id_vacina,
    tipo_operacao,
    payload
):
    """Registra a integração na transação do chamador."""

    chave = str(uuid.uuid4())

    payload = {
        **payload,
        "chave_idempotencia": chave
    }

    payload_json = json.dumps(
        payload,
        ensure_ascii=False
    )

    cur.execute(
        """
        INSERT INTO integracao_governo (
            id_animal,
            id_vacina,
            tipo_operacao,
            status,
            chave_idempotencia,
            payload_original
        )
        VALUES (%s, %s, %s, 'PENDENTE', %s, %s)
        """,
        (
            id_animal,
            id_vacina,
            tipo_operacao,
            chave,
            payload_json
        )
    )

    id_integracao = cur.lastrowid

    # A versão é atribuída antes do commit, na mesma transação.
    if tipo_operacao in ("CADASTRO_ANIMAL", "ATUALIZACAO_ANIMAL"):
        payload["versao_origem"] = id_integracao
        cur.execute(
            """
            UPDATE integracao_governo
            SET payload_original = %s
            WHERE id_integracao = %s
            """,
            (json.dumps(payload, ensure_ascii=False), id_integracao)
        )

    return id_integracao


def registrar_animal(
    cur,
    id_animal,
    tipo_operacao="CADASTRO_ANIMAL"
):
    """Prepara a integração do animal na transação local."""

    if tipo_operacao not in (
        "CADASTRO_ANIMAL",
        "ATUALIZACAO_ANIMAL"
    ):
        raise ValueError("tipo de operação inválido")

    cur.execute(
        """
        SELECT
            a.id_animal,
            a.nome,
            esp.nome AS especie,
            r.nome AS raca,
            m.numero_microchip
        FROM animal a
        JOIN especie esp
            ON esp.id_especie = a.id_especie
        JOIN raca r
            ON r.id_raca = a.id_raca
        LEFT JOIN vinculo_microchip m
            ON m.id_animal = a.id_animal
            AND m.ativo = 1
        WHERE a.id_animal = %s
        FOR UPDATE
        """,
        (id_animal,)
    )

    animal = cur.fetchone()

    if not animal:
        raise ValueError("animal não encontrado")

    payload = {
        "id_animal_clinica": animal["id_animal"],
        "nome": animal["nome"],
        "especie": animal["especie"],
        "raca": animal["raca"],
        "numero_microchip": animal["numero_microchip"]
    }

    return _criar_integracao(
        cur,
        id_animal,
        None,
        tipo_operacao,
        payload
    )


def registrar_vacina(cur, id_vacina, id_animal):
    """Prepara a notificação de vacinação antirrábica."""

    cur.execute(
        """
        SELECT
            v.*, a.nome AS nome_animal, m.numero_microchip,
            vt.nome_completo AS nome_veterinario, vt.crmv, vt.uf_crmv,
            vt.id_veterinario AS id_veterinario_clinica
        FROM vacina v
        JOIN animal a ON a.id_animal = v.id_animal
        JOIN veterinario vt ON vt.id_veterinario = v.id_veterinario
        LEFT JOIN vinculo_microchip m ON m.id_animal = a.id_animal AND m.ativo = 1
        WHERE v.id_vacina = %s AND v.id_animal = %s
        """,
        (id_vacina, id_animal)
    )

    vacina = cur.fetchone()

    if not vacina:
        raise ValueError("vacina não encontrada")

    if not vacina["antirrabica"] or vacina["status"] != "APLICADA":
        raise ValueError(
            "somente vacinas antirrábicas exigem integração"
        )

    payload = {
        "id_vacina_clinica": id_vacina,
        "id_animal_clinica": id_animal,
        "data_aplicacao": str(vacina["data_aplicacao"]),
        "lote": vacina["lote"],
        "numero_microchip": vacina["numero_microchip"],
        "nome_animal": vacina["nome_animal"],
        "nome_vacina": vacina["nome_vacina"],
        "fabricante": vacina["fabricante"],
        "id_veterinario_clinica": vacina["id_veterinario_clinica"],
        "nome_veterinario": vacina["nome_veterinario"],
        "crmv": vacina["crmv"],
        "uf_crmv": vacina["uf_crmv"]
    }

    return _criar_integracao(
        cur,
        id_animal,
        id_vacina,
        "VACINA_ANTIRRABICA",
        payload
    )


def _buscar_integracao(id_integracao):
    """Consulta uma operação de integração."""

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            """
            SELECT *
            FROM integracao_governo
            WHERE id_integracao = %s
            """,
            (id_integracao,)
        )

        return cur.fetchone()


def _iniciar_tentativa(id_integracao):
    """Reserva a operação para uma tentativa de envio."""

    with get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE integracao_governo
                SET status = 'ENVIADO',
                    tentativas = tentativas + 1,
                    ultima_tentativa = NOW(),
                    mensagem_erro = NULL
                WHERE id_integracao = %s
                  AND (
                      status IN ('PENDENTE', 'FALHA')
                      OR (
                          status = 'ENVIADO'
                          AND ultima_tentativa <=
                              DATE_SUB(
                                  NOW(),
                                  INTERVAL 2 MINUTE
                              )
                      )
                  )
                """,
                (id_integracao,)
            )

            if cur.rowcount == 0:
                conn.rollback()
                return None

            cur.execute(
                """
                SELECT *
                FROM integracao_governo
                WHERE id_integracao = %s
                """,
                (id_integracao,)
            )

            integracao = cur.fetchone()

        conn.commit()

        return integracao


def _marcar_resultado(
    id_integracao,
    tentativa,
    status,
    protocolo=None,
    erro=None
):
    """Atualiza o resultado da tentativa atual."""

    with get_conn() as conn, conn.cursor() as cur:

        if status == "CONFIRMADO":

            cur.execute(
                """
                UPDATE integracao_governo
                SET status = 'CONFIRMADO',
                    protocolo = %s,
                    data_confirmacao = NOW(),
                    mensagem_erro = NULL
                WHERE id_integracao = %s
                  AND tentativas = %s
                  AND status = 'ENVIADO'
                """,
                (
                    protocolo,
                    id_integracao,
                    tentativa
                )
            )

        else:

            cur.execute(
                """
                UPDATE integracao_governo
                SET status = %s,
                    mensagem_erro = %s
                WHERE id_integracao = %s
                  AND tentativas = %s
                  AND status = 'ENVIADO'
                """,
                (
                    status,
                    (erro or "")[:500],
                    id_integracao,
                    tentativa
                )
            )


def _enviar(id_integracao, tentativa, caminho, payload):
    """Executa a comunicação HTTP com o governo."""

    url = (
        current_app.config["GOVERNO_URL"].rstrip("/")
        + caminho
    )

    chave_api = current_app.config.get(
        "GOVERNO_API_KEY", ""
    )

    if not chave_api:

        _marcar_resultado(
            id_integracao,
            tentativa,
            "FALHA",
            erro="GOVERNO_API_KEY não configurada"
        )

        return

    headers = {
        "X-API-Key": chave_api,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:

        resposta = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=TIMEOUT_SEGUNDOS,
            allow_redirects=False
        )

    except requests.Timeout:

        _marcar_resultado(
            id_integracao,
            tentativa,
            "PENDENTE",
            erro="tempo limite de comunicação excedido"
        )

        return

    except requests.RequestException:

        _marcar_resultado(
            id_integracao,
            tentativa,
            "PENDENTE",
            erro="não foi possível conectar ao governo"
        )

        return

    if resposta.status_code in (200, 201):

        try:
            dados = resposta.json()
        except ValueError:
            dados = None

        protocolo = (
            dados.get("protocolo")
            if isinstance(dados, dict)
            else None
        )

        if (
            not isinstance(protocolo, str)
            or not protocolo.strip()
            or len(protocolo) > 60
        ):

            _marcar_resultado(
                id_integracao,
                tentativa,
                "PENDENTE",
                erro="resposta governamental sem protocolo válido"
            )

            return

        _marcar_resultado(
            id_integracao,
            tentativa,
            "CONFIRMADO",
            protocolo=protocolo
        )

        return

    if (
        resposta.status_code >= 500
        or resposta.status_code in (408, 429)
    ):

        _marcar_resultado(
            id_integracao,
            tentativa,
            "PENDENTE",
            erro=(
                f"HTTP {resposta.status_code}: "
                "indisponibilidade governamental"
            )
        )

    else:

        _marcar_resultado(
            id_integracao,
            tentativa,
            "FALHA",
            erro=(
                f"HTTP {resposta.status_code}: "
                f"{resposta.text[:300]}"
            )
        )


def enviar_integracao(id_integracao):
    """Envia uma integração já persistida no banco local.

    Deve ser chamado somente depois do commit da transação
    que registrou os dados clínicos e a integração.
    """

    try:

        integracao = _iniciar_tentativa(id_integracao)

        if not integracao:
            return False

        tentativa = integracao["tentativas"]

        try:

            payload = integracao["payload_original"]

            if isinstance(payload, (str, bytes)):
                payload = json.loads(payload)

            if not isinstance(payload, dict):
                raise ValueError("payload inválido")

            if (
                payload.get("chave_idempotencia")
                != integracao["chave_idempotencia"]
            ):
                raise ValueError("chave de idempotência divergente")

        except (ValueError, TypeError):

            _marcar_resultado(
                id_integracao,
                tentativa,
                "FALHA",
                erro="payload original inválido"
            )

            return False

        tipo = integracao["tipo_operacao"]

        if tipo == "VACINA_ANTIRRABICA":

            caminho = "/vacinas/"

        elif tipo in (
            "CADASTRO_ANIMAL",
            "ATUALIZACAO_ANIMAL"
        ):

            caminho = "/animais/"

        else:

            _marcar_resultado(
                id_integracao,
                tentativa,
                "FALHA",
                erro="tipo de operação inválido"
            )

            return False

        _enviar(
            id_integracao,
            tentativa,
            caminho,
            payload
        )

        return True

    except Exception:

        current_app.logger.exception(
            "Erro no envio da integração %s",
            id_integracao
        )

        return False


def reenviar(id_integracao):
    """Reenvia a operação utilizando o payload original."""

    integracao = _buscar_integracao(id_integracao)

    if not integracao:
        return False

    if integracao["status"] == "CONFIRMADO":
        return False

    return enviar_integracao(id_integracao)
