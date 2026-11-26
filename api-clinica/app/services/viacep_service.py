"""Fala com a API pública ViaCEP (https://viacep.com.br). O frontend nunca
chama o ViaCEP direto: ele chama a nossa rota GET /cep/<cep>, que usa
esta função. Assim o tratamento de erro fica num lugar só."""
import requests

TIMEOUT_SEGUNDOS = 5


def buscar_cep(cep):
    """Devolve o dicionário do ViaCEP, ou None se a consulta falhou
    (sem internet, ViaCEP fora do ar, etc.)."""
    try:
        resposta = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
        return resposta.json()
    except requests.RequestException:
        return None
