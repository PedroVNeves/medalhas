"""API interna usada pelas páginas do site. Pode mudar sem aviso: integrações devem usar /api/v1."""
from .api_v1 import Rota

ROTAS = {
    "/api/busca": Rota(lambda s, pedido: s.busca(pedido.params), "site"),
    "/api/ranking": Rota(lambda s, pedido: s.ranking(pedido.params), "site"),
    "/api/aluno": Rota(lambda s, pedido: s.perfil_aluno(pedido.params.get("id", ""), pedido.params), "site"),
    "/api/escola": Rota(lambda s, pedido: s.perfil_escola(pedido.params.get("id", ""), pedido.params), "site"),
    "/api/overview": Rota(lambda s, pedido: s.visao_geral(pedido.params), "site"),
}
