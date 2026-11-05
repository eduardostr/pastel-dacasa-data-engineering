import json
import logging
from time import perf_counter
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.pedidos import PedidoEntrada
from app.services import pedidos

from .config import parse_date
from .generation import plan
from .persistence import catalog, context, counts, provision
from .validation import validate


def generate(engine, config, run_id=None, logger=None):
    run_id = config.resolve_run_id(run_id)
    logger = logger or logging.getLogger("synthetic")
    attempt_id = str(uuid4())
    start_time = perf_counter()
    logger.info("inicio run_id=%s attempt_id=%s config=%s", run_id, attempt_id, config.identity())
    orders = list(plan(config))
    with engine.connect() as connection:
        locked = connection.execute(text("SELECT pg_try_advisory_lock(hashtextextended(:run,0))"), {"run": run_id}).scalar_one()
        connection.commit()
        if not locked:
            raise RuntimeError("Outra execução com o mesmo run_id está em andamento")
        db = Session(bind=connection)
        try:
            before = counts(db, run_id)
            previous = db.execute(text("SELECT config, status FROM synthetic_runs WHERE run_id=:run"), {"run": run_id}).mappings().first()
            if previous and previous["config"] != config.identity():
                raise ValueError("run_id já usado com configuração diferente")
            if previous and previous["status"] == "COMPLETED":
                result = validate(db, config, run_id)
                result.update({"run_id": run_id, "attempt_id": attempt_id, "created": {},
                               "ignored": sum(before.values()), "counts": before})
                logger.info("fim_idempotente %s tempo=%.3f", result, perf_counter()-start_time)
                return result
            db.execute(text("""INSERT INTO synthetic_runs(run_id, config, status)
                VALUES (:run, CAST(:config AS JSONB), 'RUNNING')
                ON CONFLICT (run_id) DO UPDATE SET status='RUNNING', error=NULL, finished_at=NULL"""),
                {"run": run_id, "config": json.dumps(config.identity())})
            db.commit()
            ids, ignored = catalog(db, config, run_id, logger)
            provision(db, config, run_id, ids, orders)
            done = set(db.execute(text("SELECT ordinal FROM synthetic_objects WHERE run_id=:run AND kind='pedidos'"),
                                  {"run": run_id}).scalars())
            ignored += len(done)
            progress = len(done)
            for order in orders:
                if order.ordinal in done:
                    continue
                context(db, run_id, order.created)
                data = PedidoEntrada(id_cliente=ids["clientes"][order.cliente],
                    id_vendedor=ids["vendedores"][order.vendedor],
                    itens=[{"id_produto": ids["produtos"][p], "quantidade": q} for p, q in order.itens])
                created = pedidos.criar(db, data)
                id = created["id_pedido"]
                if order.status != "PENDENTE":
                    context(db, run_id, order.finished)
                    (pedidos.faturar if order.status == "FATURADO" else pedidos.cancelar)(db, id)
                db.execute(text("INSERT INTO synthetic_objects(run_id, kind, ordinal, record_id) VALUES (:run,'pedidos',:ordinal,:id)"),
                           {"run": run_id, "ordinal": order.ordinal, "id": id})
                progress += 1
                if progress % config.batch_size == 0:
                    checkpoint(db, run_id, progress)
                    logger.info("lote run_id=%s pedidos=%s/%s", run_id, progress, config.pedidos)
            checkpoint(db, run_id, progress)
            result = validate(db, config, run_id)
            after = counts(db, run_id)
            result.update({"run_id": run_id, "attempt_id": attempt_id, "created":
                          {table: total-before.get(table,0) for table,total in after.items()},
                          "ignored": ignored, "counts": after})
            db.execute(text("UPDATE synthetic_runs SET status='COMPLETED', finished_at=NOW(), report=CAST(:report AS JSONB) WHERE run_id=:run"),
                       {"run": run_id, "report": json.dumps(result)})
            db.commit()
            logger.info("fim run_id=%s resultado=%s tempo=%.3f", run_id, result, perf_counter()-start_time)
            return result
        except Exception as error:
            db.rollback()
            # Nunca alterar o registro de outra configuração que reutilizou um ID.
            db.execute(text("""UPDATE synthetic_runs SET status='FAILED', error=:error, finished_at=NOW()
                WHERE run_id=:run AND config=CAST(:config AS JSONB) AND status<>'COMPLETED'"""),
                {"run": run_id, "error": str(error)[:4000], "config": json.dumps(config.identity())})
            db.commit()
            logger.exception("erro run_id=%s tempo=%.3f", run_id, perf_counter()-start_time)
            raise
        finally:
            db.close()
            if connection.in_transaction():
                connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(hashtextextended(:run,0))"), {"run": run_id})
            connection.commit()


def checkpoint(db, run_id, progress):
    db.execute(text("UPDATE synthetic_runs SET progress=:progress WHERE run_id=:run"),
               {"progress": progress, "run": run_id})
    db.commit()
