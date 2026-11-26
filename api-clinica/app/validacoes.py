"""Pequenas funções de validação usadas em vários módulos de rotas."""
import re


def somente_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    """Confere os dígitos verificadores do CPF (mesma conta que a Receita usa)."""
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(cpf[n]) * ((i + 1) - n) for n in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


def cep_valido(cep):
    return len(somente_digitos(cep)) == 8


def campos_faltando(dados, obrigatorios):
    """Devolve a lista dos campos obrigatórios que vieram vazios."""
    return [c for c in obrigatorios if not str(dados.get(c) or "").strip()]
