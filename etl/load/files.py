from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq


def utcnow():
    return datetime.now(timezone.utc)


def serial(value):
    if isinstance(value, (datetime,)):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value).__name__)


def digest(row):
    return sha256(json.dumps(row, sort_keys=True, default=serial, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, default=serial)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path, default=None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default


def write_table(path, table):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", version="2.6")
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def read_table(path):
    return pq.ParquetFile(path).read()


def checksum(path):
    with Path(path).open("rb") as stream:
        return sha256(stream.read()).hexdigest()


def inventory(root, folders):
    result = {}
    for folder in folders:
        for path in sorted(Path(folder).rglob("*")):
            if path.is_file():
                relative = str(path.relative_to(root)).replace("\\", "/")
                result[relative] = {"sha256": checksum(path), "bytes": path.stat().st_size}
    return result


def verify(root, files):
    for relative, expected in files.items():
        path = (Path(root) / relative).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
            raise RuntimeError("Artefato ausente ou fora da raiz: " + relative)
        if checksum(path) != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise RuntimeError("Checksum divergente: " + relative)
        if path.suffix == ".parquet":
            # Leitura integral: não apenas o footer.
            pq.ParquetFile(path).read()


def as_table(rows, schema):
    return pa.Table.from_pylist(rows, schema=schema)


def current_manifest(root, verify_files=True):
    value = read_json(Path(root) / "control/current.json")
    if value and verify_files:
        verify(Path(root), value["files"])
    return value


def dataset(root, name, manifest=None):
    # Fixar um manifesto ao ler múltiplos datasets evita misturar versões.
    manifest = manifest if manifest is not None else current_manifest(root)
    if not manifest:
        raise RuntimeError("Nenhuma publicação disponível")
    return read_table(Path(root) / manifest["silver"] / (name + ".parquet"))
