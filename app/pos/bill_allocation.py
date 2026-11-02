"""Allocate saved money, never reprice or resend an existing preparation order."""
from decimal import Decimal, ROUND_FLOOR
from uuid import UUID
from fastapi import HTTPException
from pydantic import Field
from .schemas import Strict

D = Decimal
ZERO = D(0)
OPEN = ('open', 'queued', 'preparing', 'ready')


class SplitItem(Strict):
    item_index: int = Field(ge=0, le=199)
    quantity: Decimal = Field(gt=0, le=999999, decimal_places=3)


class SplitAccount(Strict):
    label: str = Field(min_length=1, max_length=160)
    customer_id: int | None = None
    loyalty_code: str | None = Field(default=None, min_length=1, max_length=100)
    items: list[SplitItem] = Field(min_length=1, max_length=200)


class SplitIn(Strict):
    request_key: UUID
    expected_revision: int = Field(ge=1)
    accounts: list[SplitAccount] = Field(min_length=2, max_length=20)


def apportion(value, weights, capacities=None):
    """Largest remainder in cents, including deterministic tie and cap handling."""
    total = int(D(str(value)) * 100)
    weights = [D(str(w)) for w in weights]
    denominator = sum(weights, ZERO)
    if total == 0:
        return [ZERO for _ in weights]
    if denominator <= 0 or total < 0:
        raise HTTPException(409, 'El pedido tiene importes que requieren revisión antes de separar.')
    exact = [D(total) * w / denominator for w in weights]
    caps = [int(D(str(c)) * 100) for c in capacities] if capacities is not None else [total] * len(weights)
    amounts = [min(int(v.to_integral_value(rounding=ROUND_FLOOR)), cap) for v, cap in zip(exact, caps)]
    ranking = sorted(range(len(weights)), key=lambda i: (-(exact[i] - int(exact[i])), i))
    remaining = total - sum(amounts)
    while remaining:
        available = [i for i in ranking if weights[i] > 0 and amounts[i] < caps[i]]
        if not available:
            raise HTTPException(409, 'No se pudieron distribuir los importes del pedido.')
        for i in available:
            if not remaining:
                break
            amounts[i] += 1
            remaining -= 1
    return [D(c) / 100 for c in amounts]


def allocate(order, payload):
    if order.status not in OPEN or order.external_id or not order.table_number:
        raise HTTPException(409, 'Separá una cuenta de mesa abierta creada en el POS.')
    if order.revision != payload.expected_revision:
        raise HTTPException(409, 'La cuenta cambió en otro dispositivo. Abrila de nuevo antes de separar.')
    shares = [[ZERO for _ in payload.accounts] for _ in order.items]
    for account_index, account in enumerate(payload.accounts):
        seen = set()
        for part in account.items:
            if part.item_index >= len(order.items) or part.item_index in seen:
                raise HTTPException(422, 'Hay artículos repetidos o inexistentes en la distribución.')
            seen.add(part.item_index)
            shares[part.item_index][account_index] = part.quantity
    for item, quantities in zip(order.items, shares):
        if sum(quantities, ZERO) != D(str(item['quantity'])):
            raise HTTPException(422, 'Distribuí exactamente toda la cantidad de cada artículo.')
    result = [dict(label=a.label, items=[], subtotal=ZERO, discount=ZERO, tax=ZERO) for a in payload.accounts]
    for index, (item, weights) in enumerate(zip(order.items, shares)):
        subtotals = apportion(item['subtotal'], weights)
        discounts = apportion(item.get('discount', '0'), weights, subtotals)
        net = [s - d for s, d in zip(subtotals, discounts)]
        taxes = apportion(item.get('tax', '0'), net)
        for j, quantity in enumerate(weights):
            if quantity == 0:
                continue
            child_item = {**item, 'quantity': str(quantity), 'subtotal': str(subtotals[j]),
                          'discount': str(discounts[j]), 'tax': str(taxes[j]), 'source_item_index': index}
            result[j]['items'].append(child_item)
            result[j]['subtotal'] += subtotals[j]
            result[j]['discount'] += discounts[j]
            result[j]['tax'] += taxes[j]
    net = [a['subtotal'] - a['discount'] for a in result]
    service = apportion(order.service_total, net)
    packaging = apportion(order.packaging_total, [sum((D(i.get('packaging_fee', '0')) * D(i['quantity']) for i in a['items']), ZERO) for a in result])
    for j, account in enumerate(result):
        account['service_total'] = service[j]
        account['packaging_total'] = packaging[j]
        account['total'] = net[j] + account['tax'] + service[j] + packaging[j]
    for field in ('subtotal', 'discount', 'tax', 'service_total', 'packaging_total', 'total'):
        if sum((a[field] for a in result), ZERO) != D(str(getattr(order, field))):
            raise HTTPException(409, 'El pedido original requiere revisión: sus importes no coinciden.')
    return result
