"""Prepara cron pausado. Só --serve registra no servidor; nunca habilita o cron."""
import argparse
import json
import os


def specification():
    return {"name":"daily-incremental","cron":os.getenv("PASTEL_CRON","10 15 * * *"),
            "timezone":os.getenv("PASTEL_TIMEZONE","America/Sao_Paulo"),
            "paused":True,"active":False,"concurrency_limit":1,
            "parameters":{"mode":"incremental","allow_persistent":True}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--serve",action="store_true",help="Registra deployment PAUSADO e mantém runner local; requer autorização de registro.")
    args=p.parse_args()
    spec=specification()
    if not args.serve:
        print(json.dumps(spec,indent=2))
        return
    from prefect.schedules import Cron
    from orchestration.flows.pipeline import data_pipeline
    data_pipeline.serve(name=spec["name"],paused=True,
        schedules=[Cron(spec["cron"],timezone=spec["timezone"],active=False)],
        parameters=spec["parameters"],global_limit=1,limit=1,pause_on_shutdown=True)


if __name__=="__main__":
    main()
