from datetime import datetime, timedelta
import os
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import inspect, text

from etl.config.schema import COLUMNS, KEYS, SCHEMAS
from etl.load.files import atomic_json, digest, inventory


def extract(engine, settings, run_id, mode, parent, signature):
    root = settings.data_dir
    extraction_id = uuid4().hex
    staging = root / ".staging" / extraction_id / "bronze"
    staging.mkdir(parents=True)
    stats, fingerprints, deleted = {}, {}, {}
    previous = {}
    if parent:
        import json
        previous = json.loads((root / parent["fingerprints"]).read_text(encoding="utf-8"))
    with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
        with connection.begin():
            # Primeiro SELECT fixa o snapshot de todas as tabelas.
            fence = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
            if not connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on":
                raise RuntimeError("Conexão de origem não está somente leitura")
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            inspector = inspect(connection)
            for table, columns in COLUMNS.items():
                actual = inspector.get_columns(table, schema=settings.schema)
                if {c["name"] for c in actual} != {name for name, _ in columns}:
                    raise RuntimeError("Schema drift: colunas divergentes em " + table)
                for col in actual:
                    expected = dict(columns)[col["name"]]
                    python_type = col["type"].python_type
                    correct = ((pa.types.is_integer(expected) and python_type is int and str(col["type"]).upper() == ("BIGINT" if expected.bit_width == 64 else "INTEGER")) or
                        (pa.types.is_decimal(expected) and getattr(col["type"], "precision", None) == 12 and getattr(col["type"], "scale", None) == 2) or
                        (pa.types.is_timestamp(expected) and python_type is datetime and getattr(col["type"], "timezone", False)) or
                        (pa.types.is_string(expected) and python_type is str) or
                        (pa.types.is_boolean(expected) and python_type is bool))
                    if not correct:
                        raise RuntimeError("Schema drift: tipo divergente em " + table + "." + col["name"])
                watermark = parent["watermarks"].get(table) if parent else None
                lower = datetime.fromisoformat(watermark) - timedelta(seconds=settings.lookback_seconds) if watermark else None
                fingerprints[table] = {}
                selected = scanned = changed = 0
                path = staging / (table + ".parquet")
                names = ", ".join('"' + name + '"' for name, _ in columns)
                query = text(f'SELECT {names} FROM "{settings.schema}"."{table}" ORDER BY "{KEYS[table]}"')
                result = connection.execution_options(stream_results=True, max_row_buffer=settings.batch_size).execute(query)
                with pq.ParquetWriter(path, SCHEMAS[table], compression="zstd") as writer:
                    while True:
                        batch = result.mappings().fetchmany(settings.batch_size)
                        if not batch:
                            break
                        rows = []
                        for mapping in batch:
                            row = dict(mapping)
                            scanned += 1
                            key = str(row[KEYS[table]])
                            hashed = digest(row)
                            fingerprints[table][key] = hashed
                            differs = previous.get(table, {}).get(key) != hashed
                            if differs:
                                changed += 1
                            # Hash reconciliation covers backdated records and commits
                            # older than the overlap. updated_at is inclusive, never > alone.
                            overlap = lower is not None and row.get("updated_at") is not None and row["updated_at"] >= lower
                            if mode == "full" or differs or overlap:
                                rows.append({**row, "_run_id": run_id, "_extracted_at": fence,
                                             "_source": signature["origin"] + "." + table, "_record_hash": hashed})
                        if rows:
                            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[table]))
                            selected += len(rows)
                with path.open("r+b") as stream:
                    os.fsync(stream.fileno())
                result.close()
                connection.execution_options(stream_results=False)
                deleted[table] = sorted(set(previous.get(table, {})) - set(fingerprints[table])) if mode == "incremental" else []
                stats[table] = {"scanned": scanned, "extracted": selected, "source_changed": changed,
                                "deleted_keys": len(deleted[table]), "window_start": lower.isoformat() if lower else None}
    atomic_json(staging / "fingerprints.json", fingerprints)
    atomic_json(staging / "deleted_keys.json", deleted)
    target = root / "bronze" / run_id / extraction_id
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, target)
    files = inventory(root, [target])
    checkpoint = {"run_id": run_id, "mode": mode, "source": signature, "bronze": str(target.relative_to(root)),
        "files": files, "snapshot_at": fence.isoformat(), "watermarks": {table: fence.isoformat() for table in COLUMNS},
        "stats": stats, "parent": parent, "fingerprints": str((target / "fingerprints.json").relative_to(root)),
        "deleted_keys": str((target / "deleted_keys.json").relative_to(root))}
    return checkpoint
