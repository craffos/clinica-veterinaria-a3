"""CRUD de consultas. O veterinário responsável é obtido do JWT."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, g, jsonify, request
from app.auth import login_required
from app.db import get_conn

bp = Blueprint('consultas', __name__, url_prefix='/consultas')
STATUS_VALIDOS = ('AGENDADA', 'EM_ATENDIMENTO', 'CONCLUIDA', 'CANCELADA', 'NAO_COMPARECEU')
TEXTOS = ('historico', 'sintomas', 'diagnostico', 'tratamento', 'prescricao', 'observacao')
CAMPOS = '''c.id_consulta, c.id_animal, a.nome AS nome_animal, c.id_veterinario,
 v.nome_completo AS nome_veterinario, c.data_hora, c.motivo, c.historico,
 c.sintomas, c.diagnostico, c.tratamento, c.prescricao, c.peso_consulta,
 c.temperatura, c.observacao, c.status'''


def _select_base():
    return f'''SELECT {CAMPOS} FROM consulta c
        JOIN animal a ON a.id_animal=c.id_animal
        JOIN veterinario v ON v.id_veterinario=c.id_veterinario'''


def _decimal(valor, nome, maximo):
    if valor is None or valor == '':
        return None
    try:
        numero = Decimal(str(valor))
        if not numero.is_finite() or not 0 < numero <= Decimal(maximo) or numero != numero.quantize(Decimal('0.01')):
            raise ValueError
        return numero
    except (InvalidOperation, ValueError):
        raise ValueError(f'{nome} deve ser positivo, até {maximo}, com no máximo duas casas decimais') from None


def _validar(dados, anterior=None):
    if not isinstance(dados, dict):
        raise ValueError('corpo JSON deve ser um objeto')
    motivo = dados.get('motivo')
    if not isinstance(motivo, str) or not motivo.strip() or len(motivo.strip()) > 255:
        raise ValueError('motivo obrigatório, com até 255 caracteres')
    try:
        data = datetime.fromisoformat(dados['data_hora'])
        if data.tzinfo is not None or len(dados['data_hora']) < 16:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError('data_hora inválida; informe data e hora local') from None
    base = anterior or {}
    status = dados.get('status', base.get('status', 'AGENDADA'))
    if status not in STATUS_VALIDOS:
        raise ValueError('status deve ser um de: ' + ', '.join(STATUS_VALIDOS))
    resultado = {'data_hora': data, 'motivo': motivo.strip(), 'status': status}
    for campo in TEXTOS:
        valor = dados.get(campo, base.get(campo))
        if valor is not None and (not isinstance(valor, str) or len(valor.encode('utf-8')) > 65535):
            raise ValueError(f'{campo} deve ser texto válido de até 65535 bytes')
        resultado[campo] = valor
    resultado['peso_consulta'] = _decimal(dados.get('peso_consulta', base.get('peso_consulta')), 'peso da consulta', '9999.99')
    resultado['temperatura'] = _decimal(dados.get('temperatura', base.get('temperatura')), 'temperatura', '99.99')
    return resultado


@bp.get('/')
@login_required
def listar():
    sql = _select_base() + ' WHERE 1=1'
    parametros = []
    for campo in ('id_animal', 'status'):
        if request.args.get(campo):
            sql += f' AND c.{campo} = %s'
            parametros.append(request.args[campo])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql + ' ORDER BY c.data_hora DESC', parametros)
        return jsonify(cur.fetchall())


@bp.get('/<int:id_consulta>')
@login_required
def buscar(id_consulta):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(_select_base() + ' WHERE c.id_consulta=%s', (id_consulta,))
        linha = cur.fetchone()
    if not linha:
        return jsonify({'erro': 'consulta não encontrada'}), 404
    return jsonify(linha)


@bp.post('/')
@login_required
def criar():
    dados = request.get_json(silent=True)
    try:
        valores = _validar(dados)
        id_animal = dados.get('id_animal')
        if isinstance(id_animal, bool) or not isinstance(id_animal, int) or id_animal <= 0:
            raise ValueError('id_animal deve ser um inteiro positivo')
    except ValueError as erro:
        return jsonify({'erro': str(erro)}), 400
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('SELECT id_animal FROM animal WHERE id_animal=%s AND ativo=1', (id_animal,))
        if not cur.fetchone():
            return jsonify({'erro': 'animal ativo não encontrado'}), 404
        valores = {'id_animal': id_animal, 'id_veterinario': g.veterinario['id_veterinario'], **valores}
        cur.execute('INSERT INTO consulta (' + ', '.join(valores) + ') VALUES (' + ', '.join(['%s'] * len(valores)) + ')', tuple(valores.values()))
        return jsonify({'id_consulta': cur.lastrowid}), 201


@bp.put('/<int:id_consulta>')
@login_required
def atualizar(id_consulta):
    dados = request.get_json(silent=True)
    with get_conn() as conn, conn.cursor() as cur:
        conn.begin()
        try:
            cur.execute('SELECT * FROM consulta WHERE id_consulta=%s FOR UPDATE', (id_consulta,))
            anterior = cur.fetchone()
            if not anterior:
                conn.rollback()
                return jsonify({'erro': 'consulta não encontrada'}), 404
            valores = _validar(dados, anterior)
            cur.execute('UPDATE consulta SET ' + ', '.join(f'{campo}=%s' for campo in valores) + ' WHERE id_consulta=%s', (*valores.values(), id_consulta))
            conn.commit()
        except ValueError as erro:
            conn.rollback()
            return jsonify({'erro': str(erro)}), 400
        except Exception:
            conn.rollback()
            raise
    return jsonify({'mensagem': 'atualizada'})


@bp.delete('/<int:id_consulta>')
@login_required
def cancelar(id_consulta):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('SELECT id_consulta FROM consulta WHERE id_consulta=%s', (id_consulta,))
        if not cur.fetchone():
            return jsonify({'erro': 'consulta não encontrada'}), 404
        cur.execute("UPDATE consulta SET status='CANCELADA' WHERE id_consulta=%s", (id_consulta,))
    return jsonify({'mensagem': 'cancelada'})
