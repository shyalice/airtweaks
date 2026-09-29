#!/usr/bin/env python3
"""airtweaks backend dispatcher — PyInstaller bundles this into a single
binary. usage: `airtweaks-backend <feature>`, JSON on stdin, JSONL on stdout.
"""
from __future__ import annotations
import importlib
import json
import sys
from pathlib import Path

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(BASE))


def _feature_entry(name: str) -> int:
    try:
        mod = importlib.import_module(f"features.{name}")
    except ImportError as e:
        sys.stdout.write(json.dumps({"type": "result", "ok": False, "exit_code": 2,
                                     "error": f"unknown feature '{name}': {e}"}) + "\n")
        return 2
    if not hasattr(mod, "run"):
        sys.stdout.write(json.dumps({"type": "result", "ok": False, "exit_code": 2,
                                     "error": f"feature '{name}' has no run()"}) + "\n")
        return 2
    try:
        params = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        sys.stdout.write(json.dumps({"type": "result", "ok": False, "exit_code": 1,
                                     "error": f"bad stdin json: {e}"}) + "\n")
        return 1
    try:
        mod.run(params)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        import traceback
        sys.stdout.write(json.dumps({
            "type": "result", "ok": False, "exit_code": 1,
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc(limit=8),
        }) + "\n")
        return 1


def main() -> int:
    if len(sys.argv) < 2:
        sys.stdout.write(json.dumps({"type": "result", "ok": False, "exit_code": 2,
                                     "error": "usage: airtweaks-backend <feature>"}) + "\n")
        return 2
    return _feature_entry(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
