"""Como as datas são guardadas no banco: sem fuso horário (são só
"24/11/2026 14:30", o que o veterinário digitou, sem indicar se é UTC
ou qualquer outro fuso).

O JSON padrão do Flask serializa datetime/date no formato RFC 1123
("Tue, 24 Nov 2026 14:30:00 GMT"), que **afirma** ser UTC. O navegador
acredita nisso e converte para o fuso local do computador do usuário,
deslocando a hora (e, pior, às vezes até o dia, em campos só de data).

Como este projeto é de uma única clínica, sem suporte a fusos
diferentes, a solução correta é NUNCA afirmar que a data é UTC: aqui
devolvemos só "AAAA-MM-DD HH:MM:SS" (datetime) ou "AAAA-MM-DD" (date),
sem indicar fuso nenhum. O frontend (js/nav.js) lê esse texto e monta
a data no fuso local do navegador, sem nenhuma conversão."""
import datetime

from flask.json.provider import DefaultJSONProvider


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, datetime.datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, datetime.date):
            return o.strftime("%Y-%m-%d")
        return DefaultJSONProvider.default(o)
