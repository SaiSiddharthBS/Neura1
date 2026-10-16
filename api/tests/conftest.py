import pytest

from neura1.graph import get_graph
from neura1.ingest.structured import load_records
from neura1.ingest.unstructured import load_sources


@pytest.fixture(scope="session")
def graph():
    g = get_graph("voltline_test")
    try:
        g.delete()
    except Exception:
        pass
    g = get_graph("voltline_test")
    load_records(g)
    load_sources(g)
    yield g
    g.delete()


@pytest.fixture
def fresh_graph():
    """A separate, freshly loaded graph for tests that change company state (e.g. applying updates)."""
    g = get_graph("voltline_test_fresh")
    try:
        g.delete()
    except Exception:
        pass
    g = get_graph("voltline_test_fresh")
    load_records(g)
    load_sources(g)
    yield g
    g.delete()
