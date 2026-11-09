# medalhas

Base de pesquisa dos premiados da **OBMEP** (2005–2025) e da **OBM** (1979–2025), com busca por pessoa ou escola.

## Como usar

Requer apenas Python 3.10+ (sem dependências externas).

```bash
python build_db.py   # baixa as listas oficiais e gera data/medalhas.db (alguns minutos na 1ª vez)
python server.py     # abre a busca em http://localhost:8000
```

- `python build_db.py --refresh` apaga o cache e baixa tudo de novo (use quando sair um ano novo).
- `python server.py --port 9000 --no-browser` para mudar a porta / não abrir o navegador.

## Fontes

| Olimpíada | Origem | Dados disponíveis |
|-----------|--------|-------------------|
| OBMEP | `premiacao.obmep.org.br/<edição>/verRelatorioPremiados{Ouro,Prata,Bronze}[.privada].do.htm` | nome, escola, esfera (E/M/F), município, UF, nível, medalha, rede (pública/privada) |
| OBM | `www.obm.org.br/premiados-obm-<ano>/` | nome, cidade/UF, nível, pontos, prêmio (inclui menções honrosas) |

As edições são descobertas automaticamente a partir de `obmep.org.br/premiados.htm` e
`obm.org.br/quem-somos/premiados-da-obm/`, então anos novos entram sem mudar código.

Observações:
- A OBMEP não teve edição em 2020; escolas privadas só aparecem a partir de 2017.
- A OBM não publica a escola, só cidade/UF.
- Cada resultado tem link para a página oficial (`fonte ↗`) para conferência.

## Como a busca de escolas funciona

- Acentos, pontuação e ordem das palavras são ignorados ("MILITAR DE FORTALEZA, COLEGIO" = "Colégio Militar de Fortaleza").
- Abreviações e siglas são expandidas nos dados **e** no texto digitado (`scraper/escolas.py`):
  `EE` → escola estadual, `EMEF`, `EEEFM`, `ETEC`/`ETE` → escola técnica estadual, `PROFA` → professor,
  `IFAL` → instituto federal de Alagoas (todas as `IF<UF>`, `IFSUL`, `IFBAIANO`, `CEFET`…).
  Assim, "instituto federal de alagoas" traz também as escolas cadastradas como "IFAL".
- Grafias diferentes da mesma escola (mesmo município) são agrupadas em um único cartão.
- Para incluir uma sigla nova, adicione em `SIGLAS` ou `ABREVIACOES` e rode `python build_db.py`.

## Estrutura

```
scraper/common.py   download com cache + normalização de texto
scraper/obmep.py    coleta OBMEP
scraper/obm.py      coleta OBM
build_db.py         gera o SQLite (data/medalhas.db)
server.py           servidor local + API (/api/busca, /api/stats)
web/index.html      interface de busca
```
