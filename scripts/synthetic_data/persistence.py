import json
from datetime import timedelta
from sqlalchemy import text

from .config import parse_date
from .generation import customer, fake_for, product, seller


TABLES = {"clientes": "id_cliente", "vendedores": "id_vendedor", "produtos": "id_produto"}


def context(db, run_id, date):
    db.execute(text("SELECT set_config('pasteldacasa.synthetic_run', :run, true), set_config('pasteldacasa.synthetic_clock', :date, true)"),
               {"run": run_id, "date": date.isoformat()})


def catalog(db, config, run_id, logger):
    ids = {}
    skipped = 0
    tag = run_id.replace("-", "")[:16]
    for kind in TABLES:
        previous = dict(db.execute(text("SELECT ordinal, record_id FROM synthetic_objects WHERE run_id = :run AND kind = :kind ORDER BY ordinal"),
                                   {"run": run_id, "kind": kind}).all())
        skipped += len(previous)
        ids[kind] = []
        count = getattr(config, kind)
        for index in range(count):
            if index in previous:
                ids[kind].append(previous[index])
                continue
            context(db, run_id, parse_date(config.start))
            if kind == "clientes":
                values = customer(config, index, tag)
                # Nunca substitui CNPJ já existente, seja real ou de outro lote.
                fake = fake_for(config, f"cnpj:{run_id}:{index}", index)
                while db.execute(text("SELECT 1 FROM clientes WHERE cnpj = :cnpj"), {"cnpj": values["cnpj"]}).first():
                    values["cnpj"] = fake.cnpj().translate(str.maketrans("", "", "./-"))
            elif kind == "vendedores":
                values = seller(config, index, tag)
            else:
                values = product(config, index, tag)
            columns = ", ".join(values)
            params = ", ".join(":" + column for column in values)
            id = db.execute(text(f"INSERT INTO {kind} ({columns}) VALUES ({params}) RETURNING {TABLES[kind]}"), values).scalar_one()
            db.execute(text("INSERT INTO synthetic_objects(run_id, kind, ordinal, record_id) VALUES (:run, :kind, :ordinal, :id)"),
                       {"run": run_id, "kind": kind, "ordinal": index, "id": id})
            ids[kind].append(id)
            if (index + 1) % config.batch_size == 0:
                db.commit()
                logger.info("lote_catalogo tabela=%s criados_ate=%s", kind, index + 1)
        db.commit()
    return ids, skipped


def provision(db, config, run_id, ids, orders):
    # Apenas produtos novos deste run. Entradas antes da primeira venda.
    required = {index: 100 for index in range(config.produtos)}
    for order in orders:
        if order.status == "FATURADO":
            for product_id, quantity in order.itens:
                required[product_id] += quantity
    context(db, run_id, parse_date(config.start))
    for ordinal, product_id in enumerate(ids["produtos"]):
        previous = db.execute(text("SELECT record_id FROM synthetic_objects WHERE run_id = :run AND kind = 'entradas' AND ordinal = :ordinal"),
                              {"run": run_id, "ordinal": ordinal}).scalar_one_or_none()
        if previous is not None:
            continue
        quantity = required[ordinal]
        db.execute(text("UPDATE produtos SET estoque_atual = estoque_atual + :q WHERE id_produto = :id"),
                   {"q": quantity, "id": product_id})
        movement = db.execute(text("""INSERT INTO movimentacoes_estoque(id_produto, tipo, quantidade, observacao)
            VALUES (:id, 'ENTRADA', :q, :obs) RETURNING id_movimentacao"""),
            {"id": product_id, "q": quantity, "obs": f"Estoque inicial sintético da execução {run_id}"}).scalar_one()
        db.execute(text("INSERT INTO synthetic_objects(run_id, kind, ordinal, record_id) VALUES (:run, 'entradas', :ordinal, :id)"),
                   {"run": run_id, "ordinal": ordinal, "id": movement})
    db.commit()


def counts(db, run_id):
    return dict(db.execute(text("SELECT table_name, count(*) FROM synthetic_records WHERE run_id = :run GROUP BY table_name"),
                           {"run": run_id}).all())
