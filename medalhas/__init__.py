"""Medalhas: base de pesquisa dos medalhistas brasileiros em olimpíadas científicas.

Organização (arquitetura hexagonal, de dentro para fora):

    dominio/      regras de negócio puras: olimpíadas, pontuação, identidade de alunos e escolas,
                  ranking e gamificação. Não faz I/O e não importa nada das outras camadas.
    aplicacao/    casos de uso e portas (interfaces) que eles exigem do mundo externo.
    adaptadores/  implementações das portas: coletores (sites oficiais), SQLite e HTTP.

As dependências apontam sempre para dentro: adaptadores -> aplicacao -> dominio.
Os pontos de entrada (`build_db.py` e `server.py`, na raiz) montam as peças.
"""
