"""Cria apenas um snapshot de testes fora do projeto; não executa cargas."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import duckdb
import requests

ROOT=Path(__file__).resolve().parents[2]


def prepare(destination):
    destination=Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError("Use um diretório novo fora do projeto, preferencialmente temporário.")
    data=ROOT/"data";db=data/"warehouse/pastel_da_casa.duckdb"
    api=os.getenv("PREFECT_API_URL","http://127.0.0.1:4200/api")
    r=requests.post(api.rstrip("/")+"/flow_runs/filter",
        json={"flow_runs":{"state":{"type":{"any_":["RUNNING","PENDING","CANCELLING"]}}},"limit":100},timeout=10)
    r.raise_for_status()
    if r.json():raise RuntimeError("Há flows ativos; snapshot não iniciado.")
    def fingerprint(path):
        with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
    manifest_before=(data/"control/current.json").read_bytes()
    protected={p:fingerprint(p) for layer in ("bronze","silver","quarantine") for p in (data/layer).rglob("*") if p.is_file()}
    c=duckdb.connect(str(db),read_only=True)
    try:
        if Path(str(db)+".wal").exists():raise RuntimeError("WAL pendente; coordenar escritor antes do snapshot.")
        destination.mkdir(parents=True,exist_ok=False)
        shutil.copytree(data,destination/"data",ignore=shutil.ignore_patterns(
            "warehouse","orchestration","*.lock","audit.sqlite","audit.sqlite-wal","audit.sqlite-shm"))
        shutil.copy2(db,destination/"model.duckdb")
        src=sqlite3.connect((data/"control/audit.sqlite").as_uri()+"?mode=ro",uri=True)
        dst=sqlite3.connect(destination/"data/control/audit.sqlite")
        try:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("Auditoria inválida.")
        finally:src.close();dst.close()
        if (data/"control/current.json").read_bytes()!=manifest_before:
            raise RuntimeError("Publicação mudou durante a cópia; snapshot não aprovado.")
        for path,expected in protected.items():
            if fingerprint(path)!=expected or fingerprint(destination/"data"/path.relative_to(data))!=expected:
                raise RuntimeError("Arquivo mudou durante o snapshot.")
        from warehouse.source import load_publication
        publication=load_publication(destination/"data")
        applied=c.execute("SELECT silver_version,silver_fingerprint FROM dw_state").fetchone()
        if applied!=(publication["manifest"]["version"],publication["fingerprint"]):
            raise RuntimeError("Silver e DW não reconciliados; snapshot não aprovado.")
        if fingerprint(db)!=fingerprint(destination/"model.duckdb"):raise RuntimeError("Cópia DW divergente.")
        manifest=publication["manifest"]
        matching=[]
        for report_path in (data/"orchestration/runs").glob("*.json"):
            report=json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("silver_version")==manifest["version"] and report.get("etl_run_id")==manifest["run_id"]:
                matching.append(report)
        metadata={"silver_version":applied[0],"source_files":len(protected),
                  "etl_run_id":manifest["run_id"],
                  "source_schema":manifest["source"]["origin"].rsplit("/",1)[-1]}
        if matching:metadata["logical_run_id"]=matching[-1]["run_id"]
        (destination/"SNAPSHOT_READY.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    finally:c.close()
    return destination


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    print(prepare(args.destination))
