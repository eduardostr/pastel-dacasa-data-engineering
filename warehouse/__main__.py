import argparse
import json
from pathlib import Path

from warehouse.config import Settings
from warehouse.loader import Warehouse


def main():
    parser = argparse.ArgumentParser(description="DW Pastel da Casa, exclusivamente Silver publicada.")
    parser.add_argument("--mode", choices=["full", "incremental"], required=True)
    parser.add_argument("--silver-root", type=Path, default=Settings().silver_root)
    parser.add_argument("--database", type=Path, default=Settings().database)
    parser.add_argument("--run-id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-persistent", action="store_true", help="Confirmação técnica; requer autorização do usuário.")
    args = parser.parse_args()
    settings = Settings(args.silver_root, args.database)
    if not args.execute:
        print(json.dumps({"mode": args.mode, "silver_root": str(settings.silver_root),
                          "database": str(settings.database), "state": "PLAN_ONLY_NO_LOAD"}, indent=2))
        return 0
    if not args.allow_persistent:
        parser.error("Carga persistente requer autorização e --allow-persistent")
    result = Warehouse(settings).run(args.mode, args.run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
