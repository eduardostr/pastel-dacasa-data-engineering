import argparse
import json
from pathlib import Path

from etl.config import Settings
from etl.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description="Pastel da Casa: ETL Bronze/Silver. Sem --execute apenas exibe o plano.")
    parser.add_argument("--mode", choices=["full", "incremental"], required=True)
    parser.add_argument("--data-dir", type=Path, default=Settings().data_dir)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--lookback-seconds", type=int, default=900)
    parser.add_argument("--run-id")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-full", action="store_true", help="Confirma FULL; usar apenas após autorização.")
    args = parser.parse_args()
    settings = Settings(args.data_dir, args.schema, args.batch_size, args.lookback_seconds)
    if not args.execute:
        print(json.dumps({"mode": args.mode, "data_dir": str(settings.data_dir), "schema": args.schema,
            "batch_size": args.batch_size, "lookback_seconds": args.lookback_seconds,
            "state": "PLAN_ONLY_NO_EXTRACTION"}, indent=2))
        return 0
    if args.mode == "full" and not args.allow_full:
        parser.error("FULL persistente requer autorização e --allow-full")
    manifest = Pipeline(settings=settings).run(args.mode, args.run_id, args.reprocess)
    print(json.dumps({"run_id": manifest["run_id"], "version": manifest["version"],
        "watermarks": manifest["watermarks"], "metrics": manifest["metrics"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
