"""API interna usada pelas páginas do site. Pode mudar sem aviso: integrações devem usar /api/v1."""
from ...dominio.enderecos import ALUNO, CIDADE, ESCOLA
from .api_v1 import Rota


def _perfil(tipo: str):
    """Perfil pelo id (?id=) ou pelo endereço da página (?endereco=maria-souza-lima-al). A resposta traz o
    endereço oficial, que o site põe na barra de endereço."""
    def rota(sessao, pedido):
        params, enderecos = pedido.params, sessao.enderecos()
        achado = enderecos.resolver(tipo, params["endereco"]) if params.get("endereco") else None
        ident = achado[0] if achado else params.get("id", "")
        perfil = {ALUNO: sessao.perfil_aluno, ESCOLA: sessao.perfil_escola, CIDADE: sessao.perfil_cidade}[tipo]
        dados = perfil(ident, params)
        if "erro" not in dados:
            dados["endereco"] = f"/{tipo}/{enderecos.de(tipo, ident)}"
        return dados
    return rota

ROTAS = {
    "/api/busca": Rota(lambda s, pedido: s.busca(pedido.params), "site"),
    # lista curta enquanto a pessoa digita: igual para todos até a próxima publicação, o CDN guarda
    "/api/sugestoes": Rota(lambda s, pedido: s.sugestoes(pedido.params), "site", cache_cdn=86400),
    "/api/ranking": Rota(lambda s, pedido: s.ranking(pedido.params), "site"),
    "/api/aluno": Rota(_perfil(ALUNO), "site"),
    "/api/escola": Rota(_perfil(ESCOLA), "site"),
    "/api/cidade": Rota(_perfil(CIDADE), "site"),
    # a página inicial inteira vem daqui e só muda com a base: o CDN responde, sem acordar o Cloud Run
    "/api/overview": Rota(lambda s, pedido: s.visao_geral(pedido.params), "site", cache_cdn=86400),
}
