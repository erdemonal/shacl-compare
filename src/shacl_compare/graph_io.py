from __future__ import annotations

from pathlib import Path

from rdflib import Graph
from rdflib.term import BNode


def load_graph(path: Path) -> Graph:
    if not path.is_file():
        raise FileNotFoundError(f"Missing graph file: {path}")
    g = Graph()
    g.parse(path)
    return g


def graph_contains_blank_nodes(g: Graph) -> bool:
    for s, p, o in g:
        if isinstance(s, BNode) or isinstance(p, BNode) or isinstance(o, BNode):
            return True
    return False
