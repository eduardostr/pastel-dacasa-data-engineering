import argparse
import json
import logging
from pathlib import Path
from uuid import uuid4

from app.database import engine

from .config import Config
from .isolation import isolated_database
from .runner import generate


def main():
    parser = argparse.ArgumentParser(description="Gerador sintético Pastel da Casa; sem --execute apenas mostra o plano.")
    for key, default in (("clientes",1000), ("vendedores",30), ("produtos",50), ("pedidos",20000), ("seed",42), ("batch-size",200)):
        parser.add_argument("--" + key, type=int, default=default)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--execute", action="store_true")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--isolated", action="store_true", help="Schema temporário descartado ao final (padrão).")
    target.add_argument("--development", action="store_true", help="Grava dados sintéticos no banco atual; requer migração 004.")
    parser.add_argument("--allow-large-load", action="store_true", help="Confirma carga acima de 1.000 pedidos.")
    parser.add_argument("--log-dir", default="scripts/synthetic_data/logs")
    args = parser.parse_args()
    try:
        config = Config(**{key: getattr(args,key) for key in
                          ("clientes","vendedores","produtos","pedidos","start","end","seed","batch_size")})
        run_id = config.resolve_run_id(args.run_id)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"run_id": run_id, "config": config.identity(), "batch_size": config.batch_size,
                      "target": "development" if args.development else "isolated"}, ensure_ascii=False, indent=2))
    if not args.execute:
        print("Plano somente. Nada foi criado. Use --execute para executar.")
        return 0
    if config.pedidos > 1000 and not args.allow_large_load:
        parser.error("Carga acima de 1.000 pedidos bloqueada. Requer autorização e --allow-large-load.")
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / f"{run_id}-{uuid4().hex}.log", encoding="utf-8")])
    try:
        if args.development:
            with engine.connect() as connection:
                ready = connection.exec_driver_sql("SELECT to_regclass('synthetic_runs')").scalar_one()
                if not ready:
                    raise RuntimeError("Migração 004 ausente. Execute backend/migrate.py antes da carga de desenvolvimento.")
            result = generate(engine, config, run_id)
        else:
            with isolated_database(engine) as (target_engine, schema):
                logging.info("schema_temporario=%s; será removido ao final", schema)
                result = generate(target_engine, config, run_id)
                # A segunda execução faz parte da validação pequena de idempotência.
                repeated = generate(target_engine, config, run_id)
                if repeated["created"]:
                    raise RuntimeError("Reexecução criou registros indevidos")
                result["idempotent_replay"] = True
                result["isolated_schema"] = schema
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        logging.exception("Geração não concluída; lotes confirmados podem ser retomados com o mesmo run_id")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
