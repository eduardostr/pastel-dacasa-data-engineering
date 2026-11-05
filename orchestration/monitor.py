"""Consulta local de histórico/alertas; sem mensagens externas ou gravação."""
import argparse
from datetime import datetime,timezone,timedelta
import json
import requests

from orchestration.operations import api_url,specification


def summarize(run,tasks):
    return {"flow_run_id":run["id"],"name":run.get("name"),"state":run.get("state_type"),
            "auto_scheduled":run.get("auto_scheduled"),
            "expected_start_time":run.get("expected_start_time"),
            "deployment_id":run.get("deployment_id"),"infrastructure_pid":run.get("infrastructure_pid"),
            "start_time":run.get("start_time"),"end_time":run.get("end_time"),
            "seconds":run.get("total_run_time"),"run_count":run.get("run_count"),
            "logical_run_id":run.get("parameters",{}).get("run_id"),
            "tasks":[{"name":t.get("name"),"state":t.get("state_type"),
                      "attempts":t.get("run_count"),"seconds":t.get("total_run_time"),
                      "error":"Consultar logs privados da task" if t.get("state_type") in ("FAILED","CRASHED") else None}
                     for t in tasks]}


def collect(alerts=False,limit=25):
    if not 1<=limit<=100:raise ValueError("Limite entre 1 e 100.")
    api=api_url();spec=specification()
    def post(endpoint,body):
        r=requests.post(api+"/"+endpoint,json=body,timeout=15);r.raise_for_status();return r.json()
    body={"flows":{"name":{"any_":["pastel-da-casa-data-pipeline"]}},"limit":limit,
          "sort":"START_TIME_DESC"}
    if alerts:body["flow_runs"]={"state":{"type":{"any_":["FAILED","CRASHED","CANCELLED"]}}}
    runs=post("flow_runs/filter",body)
    history=[]
    for run in runs:
        tasks=post("task_runs/filter",{"flow_runs":{"id":{"any_":[run["id"]]}},"limit":100})
        history.append(summarize(run,tasks))
    pools=post("work_pools/filter",{})
    selected=[p for p in pools if p["name"]==spec["pool"]]
    workers=post("work_pools/"+spec["pool"]+"/workers/filter",{}) if selected else []
    deployments=post("deployments/filter",{"limit":100})
    return {"checked_at":datetime.now(timezone.utc).isoformat(),"alerts_only":alerts,
            "pool":[{"name":p["name"],"type":p["type"],"is_paused":p["is_paused"],
                     "concurrency_limit":p.get("concurrency_limit")} for p in selected],
            "workers":[{k:w.get(k) for k in ("name","status","last_heartbeat_time")} for w in workers],
            "deployments":[{k:d.get(k) for k in ("id","name","paused","schedules","work_pool_name")}
                           for d in deployments if d["name"]==spec["name"]],
            "runs":history}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alerts",action="store_true");p.add_argument("--limit",type=int,default=25)
    args=p.parse_args()
    print(json.dumps(collect(args.alerts,args.limit),indent=2,ensure_ascii=False))


if __name__=="__main__":main()
