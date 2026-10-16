"""FalkorDB connection. If the graph is unreachable we fail loudly; there is no silent fallback."""

from functools import lru_cache

from falkordb import FalkorDB, Graph
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeout

from neura1.config import settings


class GraphUnavailable(RuntimeError):
    pass


@lru_cache
def _db() -> FalkorDB:
    return FalkorDB(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        username=settings.falkordb_username,
        password=settings.falkordb_password,
    )


def get_graph(name: str | None = None) -> Graph:
    try:
        return _db().select_graph(name or settings.graph_name)
    except Exception as exc:  # connection errors surface as various redis exceptions
        raise GraphUnavailable(str(exc)) from exc


def rows(graph: Graph, query: str, params: dict | None = None, read_only: bool = True) -> list[dict]:
    """Run a query and return rows as dicts keyed by the RETURN aliases."""
    try:
        res = graph.ro_query(query, params) if read_only else graph.query(query, params)
    except (RedisConnectionError, RedisTimeout) as exc:
        raise GraphUnavailable(str(exc)) from exc
    cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    cols = [c.decode() if isinstance(c, bytes) else c for c in cols]
    return [dict(zip(cols, r)) for r in res.result_set]
