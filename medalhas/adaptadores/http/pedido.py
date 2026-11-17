"""O que uma rota recebe além da sessão de leitura."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pedido:
    """Dados da requisição que uma rota pode usar, já extraídos pelo servidor (imutável)."""
    params: dict          # parâmetros da URL (um valor por chave)
    base: str             # endereço pelo qual o cliente chegou (ex.: http://localhost:8000), para links
    aceita_gzip: bool     # o cliente aceita resposta compactada
    versao_base: int      # muda a cada base nova (invalida arquivos de exportação)
