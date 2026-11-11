"""Erros que a API devolve ao cliente (o servidor traduz para HTTP 400 e 404)."""


class ParametroInvalido(ValueError):
    """Parâmetro da URL com valor inválido -> 400, com a mensagem explicando o que corrigir."""


class NaoEncontrado(LookupError):
    """Aluno, escola ou rota inexistente -> 404."""
