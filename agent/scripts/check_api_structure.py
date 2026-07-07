#!/usr/bin/env python3
"""Decision gate for Alpha Foundry API/UI incremental compatibility."""

from __future__ import annotations

from pathlib import Path


def check_api_structure(root: Path | None = None) -> tuple[str, list[str]]:
    repo = root or Path(__file__).resolve().parents[2]
    required = {
        "api_server": repo / "agent" / "api_server.py",
        "api_routes_dir": repo / "agent" / "src" / "api",
        "frontend_package": repo / "frontend" / "package.json",
        "run_detail": repo / "frontend" / "src" / "pages" / "RunDetail.tsx",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        return "not_compatible", missing
    api_server_text = required["api_server"].read_text(encoding="utf-8", errors="replace")
    if "register_alpha_routes(app)" not in api_server_text:
        return "not_compatible", ["api_server_missing_modular_route_registration"]
    return "incremental_compatible", []


def main() -> int:
    status, _reasons = check_api_structure()
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
