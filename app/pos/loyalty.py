"""A paid bill and its durable loyalty intent commit together; delivery is retryable."""
from urllib.parse import urlencode
from fastapi import HTTPException
from sqlalchemy import select
from .models import Business, ConnectLink, Customer, LoyaltyOperation
from .connect_client import connect_request


def enabled(db, business_id):
    link = db.get(ConnectLink, business_id)
    return bool(link and link.provider == 'shirleys')


def choose_customer(db, business, order, customer_id=None, code=None):
    customer = db.get(Customer, customer_id) if customer_id else None
    if customer_id and (not customer or customer.business_id != business.id):
        raise HTTPException(404, 'Cliente no encontrado en este negocio.')
    if not code and customer and enabled(db, business.id):
        code = customer.remote_id
    if code:
        if not enabled(db, business.id):
            raise HTTPException(409, 'Este negocio no tiene esta integración de fidelización.')
        data = connect_request('shirleys', '/customers?' + urlencode({'q': code, 'limit': 100}))
        remote = next((c for c in data.get('customers', []) if c['code'] == code), None)
        if not remote:
            raise HTTPException(404, 'No encontramos ese cliente registrado en el sitio del negocio.')
        if customer and customer.remote_id != code:
            raise HTTPException(409, 'El cliente local y el cliente de fidelización no coinciden.')
        if not customer:
            customer = db.scalar(select(Customer).where(Customer.business_id == business.id, Customer.remote_id == code))
        if not customer:
            customer = Customer(business_id=business.id, remote_id=code)
            db.add(customer)
        customer.name = remote['name']
        customer.email = remote.get('email', '')
        customer.phone = remote.get('whatsapp', '')
        db.flush()
        order.loyalty_code = code
        order.loyalty_name = remote['name']
    else:
        order.loyalty_code = None
        order.loyalty_name = None
    order.customer_id = customer.id if customer else None


def enqueue(db, business, order, actor, kind='purchase', reason=''):
    if not enabled(db, business.id) or not order.loyalty_code:
        return
    previous = db.scalar(select(LoyaltyOperation).where(LoyaltyOperation.business_id == business.id,
                         LoyaltyOperation.order_id == order.id, LoyaltyOperation.kind == kind))
    if previous:
        return
    payload = {'sale_key': f'SLPOS:{business.id}:{order.id}', 'actor': f'POS:{business.id}:{actor.id}'}
    if kind == 'purchase':
        payload.update(customer_code=order.loyalty_code, amount=str(order.total),
                       invoice_number=f'SLPOS-{business.id}-{order.id}')
        if order.total <= 0:
            return
    else:
        # Never manufacture a reversal for a bill that did not earn purchase points.
        sale = db.scalar(select(LoyaltyOperation.id).where(LoyaltyOperation.business_id == business.id,
                         LoyaltyOperation.order_id == order.id, LoyaltyOperation.kind == 'purchase'))
        if not sale:
            return
        payload['reason'] = reason
    db.add(LoyaltyOperation(business_id=business.id, order_id=order.id, kind=kind, payload=payload))
    order.loyalty_status = 'pending' if kind == 'purchase' else 'void_pending'


def sync_order(db, business, order):
    """Remote timeout leaves the already paid/refunded bill and pending intent intact."""
    db.scalar(select(Business).where(Business.id == business.id).with_for_update())
    db.refresh(order)
    jobs = list(db.scalars(select(LoyaltyOperation).where(LoyaltyOperation.business_id == business.id,
                           LoyaltyOperation.order_id == order.id).order_by(LoyaltyOperation.id)))
    for job in jobs:
        if job.state == 'done':
            continue
        job.attempts += 1
        try:
            result = connect_request('shirleys', '/sales' if job.kind == 'purchase' else '/sales/void', 'POST', job.payload)
            if not isinstance(result, dict) or result.get('provider') != 'shirleys' or result.get('sale_key') != job.payload['sale_key']:
                raise HTTPException(502, 'Respuesta de fidelización inválida; reintentá la sincronización.')
            if not isinstance(result.get('points_earned'), int) or result['points_earned'] < 0:
                raise HTTPException(502, 'No se pudo verificar la acreditación; reintentá la sincronización.')
        except HTTPException as error:
            job.last_error = str(error.detail)[:500]
            order.loyalty_status = 'void_pending' if any(j.kind == 'void' and j.state != 'done' for j in jobs) else 'pending'
            db.commit()
            return
        job.state = 'done'
        job.last_error = None
        job.result = result
        if job.kind == 'purchase':
            order.loyalty_points = result['points_earned']
            order.loyalty_status = 'credited'
        else:
            order.loyalty_status = 'reversed'
    if any(j.kind == 'void' and j.state != 'done' for j in jobs):
        order.loyalty_status = 'void_pending'
    db.commit()
