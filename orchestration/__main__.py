import argparse
import json
from orchestration.config import plan, identifiers


def main():
    p = argparse.ArgumentParser(description="Orquestração local; cargas exigem autorização explícita.")
    p.add_argument("--mode", choices=["full","incremental"], default="incremental")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--validate-only", action="store_true")
    p.add_argument("--allow-persistent", action="store_true")
    p.add_argument("--allow-full", action="store_true")
    p.add_argument("--run-id")
    args = p.parse_args()
    try:
        spec = plan(args.mode,args.validate_only,args.dry_run,args.allow_persistent,args.allow_full)
        ids = identifiers(args.run_id)
    except ValueError as error:
        p.error(str(error))
    if args.dry_run:
        print(json.dumps({**spec, **ids, "status":"PLAN_ONLY_NO_CONNECTIONS"},indent=2))
        return
    from orchestration.flows.pipeline import data_pipeline
    result = data_pipeline(**vars(args))
    print(json.dumps(result,default=str,indent=2,ensure_ascii=False))


if __name__ == "__main__":
    main()
