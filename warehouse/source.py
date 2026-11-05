from datetime import datetime
from hashlib import sha256
import json

import pyarrow.parquet as pq

from etl.config.schema import SCHEMAS, SALES_SCHEMA


def load_publication(root):
    pointer = root / "control/current.json"
    if not pointer.is_file():
        raise RuntimeError("Não há manifesto Silver publicado")
    manifest = json.loads(pointer.read_text(encoding="utf-8"))
    required = ("run_id", "version", "published_at", "snapshot_at", "silver", "files", "source", "metrics")
    if any(k not in manifest for k in required):
        raise RuntimeError("Manifesto Silver incompleto")
    silver = (root / manifest["silver"]).resolve()
    if not silver.is_relative_to(root / "silver") or not silver.is_dir():
        raise RuntimeError("Caminho Silver fora da publicação permitida")
    for field in ("published_at", "snapshot_at"):
        timestamp = datetime.fromisoformat(manifest[field])
        if timestamp.tzinfo is None:
            raise RuntimeError("Timestamp de publicação sem fuso")
    files = {}
    for name, schema in {**SCHEMAS, "vendas_detalhadas": SALES_SCHEMA}.items():
        path = silver / (name + ".parquet")
        relative = str(path.relative_to(root)).replace("\\", "/")
        expected = manifest["files"].get(relative)
        if expected is None or not path.is_file():
            raise RuntimeError("Parquet não consta da publicação: " + name)
        with path.open("rb") as stream:
            actual = sha256(stream.read()).hexdigest()
        if actual != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise RuntimeError("Checksum Silver divergente: " + name)
        parquet = pq.ParquetFile(path)
        if parquet.schema_arrow != schema:
            raise RuntimeError("Contrato Silver divergente: " + name)
        if manifest["metrics"].get(name, {}).get("valid") != parquet.metadata.num_rows:
            raise RuntimeError("Contagem do manifesto divergente: " + name)
        files[name] = {"path": path, "sha256": actual, "bytes": path.stat().st_size}
    identity = {"version": manifest["version"], "run_id": manifest["run_id"],
                "published_at": manifest["published_at"], "snapshot_at": manifest["snapshot_at"],
                "source": manifest["source"],
                "files": {name: {"sha256": value["sha256"], "bytes": value["bytes"]} for name, value in files.items()}}
    fingerprint = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {"manifest": manifest, "files": files, "fingerprint": fingerprint}


def stage(connection, publication):
    # Somente Parquets Silver: não há consulta à Bronze, PostgreSQL ou API.
    for name, info in publication["files"].items():
        literal = "'" + str(info["path"]).replace("'", "''") + "'"
        connection.execute(f"CREATE OR REPLACE TEMP TABLE s_{name} AS SELECT * FROM read_parquet({literal})")


def verify_unchanged(publication):
    for name, info in publication["files"].items():
        with info["path"].open("rb") as stream:
            if sha256(stream.read()).hexdigest() != info["sha256"]:
                raise RuntimeError("Arquivo Silver alterado durante a carga: " + name)
