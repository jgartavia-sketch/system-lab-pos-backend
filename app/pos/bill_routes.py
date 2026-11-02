"""Billing operations reuse order snapshots and the common tenant transaction lock."""
import hashlib
import json
from uuid import uuid4
from pydantic import Field
from .routes import (router, Depends, tenant, current, get_db, select, find, fail,
                     commit, row, Order, Customer, audit, Strict)
from .models import BillSplit
from .bill_allocation import SplitIn, allocate
from . import loyalty


def validate_mode(business):
    if business.mode not in ('restaurante', 'heladeria'):
        fail('Esta operación corresponde a cuentas de restaurante o heladería.', 409)


@router.post('/business/{bid}/orders/{ident}/split/preview')
def preview_split(ident: int, payload: SplitIn, b=Depends(tenant), db=Depends(get_db)):
    validate_mode(b)
    order = find(db, Order, ident, b.id)
    accounts = allocate(order, payload)
    for account in accounts:
        account['items'] = [{k: v for k, v in item.items() if k != 'cost'} for item in account['items']]
    return {'order_id': ident, 'revision': order.revision, 'accounts': accounts, 'total': order.total}


@router.post('/business/{bid}/orders/{ident}/split')
def split_bill(ident: int, payload: SplitIn, b=Depends(tenant), a=Depends(current), db=Depends(get_db)):
    validate_mode(b)
    order = find(db, Order, ident, b.id)
    digest = hashlib.sha256(json.dumps({'order_id': ident, **payload.model_dump(mode='json')}, sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(BillSplit).where(BillSplit.business_id == b.id, BillSplit.request_key == str(payload.request_key)))
    if previous:
        if previous.request_digest != digest:
            fail('Este intento ya corresponde a otra distribución.', 409)
        return {'accounts': [row(find(db, Order, child, b.id)) for child in previous.child_ids], 'replayed': True}
    parts = allocate(order, payload)
    if not order.table_session:
        order.table_session = str(uuid4())
    children = []
    for account, part in zip(payload.accounts, parts):
        child = Order(business_id=b.id, account_id=a.id, request_key=str(uuid4()), request_digest=digest,
                      table_number=order.table_number, table_session=order.table_session,
                      split_parent_id=order.id, preparation_order_id=order.preparation_order_id or order.id,
                      source_channel=order.source_channel, fulfillment=order.fulfillment,
                      notes=order.notes, status='open', **part)
        db.add(child)
        loyalty.choose_customer(db, b, child, account.customer_id, account.loyalty_code)
        db.flush()
        children.append(child)
    order.status = 'split'
    order.revision += 1
    # Preparation remains attached to the original order, independently of billing.
    db.add(BillSplit(business_id=b.id, order_id=order.id, request_key=str(payload.request_key),
                    request_digest=digest, child_ids=[c.id for c in children]))
    audit(db, b, a, 'bill_split', {'children': [c.id for c in children], 'reason': 'Cuentas separadas de la misma mesa'}, order=order.id)
    commit(db)
    return {'accounts': [row(c) for c in children], 'replayed': False}


@router.get('/business/{bid}/loyalty/customers')
def loyalty_customers(q: str = '', b=Depends(tenant), db=Depends(get_db)):
    from urllib.parse import urlencode
    if not loyalty.enabled(db, b.id):
        fail('Este negocio no tiene esta integración de fidelización.', 404)
    if not 2 <= len(q.strip()) <= 160:
        fail('Escribí al menos dos caracteres para buscar al cliente.', 422)
    return loyalty.connect_request('shirleys', '/customers?' + urlencode({'q': q.strip(), 'limit': 25}))


class LoyaltyRetry(Strict):
    order_id: int = Field(gt=0)


@router.post('/business/{bid}/loyalty/retry')
def retry_loyalty(payload: LoyaltyRetry, b=Depends(tenant), db=Depends(get_db)):
    order = find(db, Order, payload.order_id, b.id)
    if not loyalty.enabled(db, b.id):
        fail('Fidelización no disponible.', 404)
    loyalty.sync_order(db, b, order)
    return row(order)
