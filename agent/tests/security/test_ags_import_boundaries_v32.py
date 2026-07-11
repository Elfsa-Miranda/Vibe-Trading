from __future__ import annotations

import ast
from pathlib import Path


_FORBIDDEN_PARTS = {"broker", "live", "order", "execution_router"}


def test_ags_import_graph_has_no_order_broker_or_live_dependencies() -> None:
    repo = Path(__file__).resolve().parents[3]
    files = [
        repo / "agent/src/api/alpha_genesis_routes.py",
        *(repo / "agent/src/alpha_quality/reporting").glob("*.py"),
    ]
    imported: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

    assert not {
        name
        for name in imported
        if _FORBIDDEN_PARTS.intersection(name.lower().replace("-", "_").split("."))
    }
