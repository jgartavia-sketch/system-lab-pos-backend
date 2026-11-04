"""Common credit ledger. Parent business lock serializes payment, void and drawer close."""
from datetime import date
from uuid import UUID, uuid5, NAMESPACE_URL
import hashlib
import json
from pydantic import Field, model_validator
from .routes import (router, Strict, Depends, get_db, tenant, current, select, money, fail,
                     row, find, commit, Order, OPEN, Product, Movement, Decimal, active_register,
                     datetime, timezone, audit, Reason, expected_cash, TZ)
from .models import Receivable, CreditPayment, Customer
from . import zenit_bridge as zb

class Installment(Strict):
    due: date
    amount: Decimal = Field(gt=0,le=999999999,decimal_places=2)
class InitialPayment(Strict):
    amount: Decimal = Field(default=Decimal(0),ge=0,le=999999999,decimal_places=2)
    method: str = Field(default='cash',pattern='^(cash|card|sinpe|transfer)$')
    reference: str = Field(default='',max_length=100)
class CreditIn(Strict):
    request_key: UUID | None = None
    expected_revision: int | None = Field(default=None,ge=1)
    customer_id: int | None = Field(default=None,gt=0)
    invoice_number: str = Field(default="",max_length=100)
    installments: list[Installment] = Field(default_factory=list,max_length=120)
    due_date: date | None = None
    initial_payment: InitialPayment | None = None
    @model_validator(mode='after')
    def ordered(self):
        if [i.due for i in self.installments]!=sorted(set(i.due for i in self.installments)):
            raise ValueError('Vencimientos únicos en orden ascendente.')
        if self.installments and self.due_date:
            raise ValueError('Usá fecha de pago o cuotas, no ambas.')
        if self.initial_payment and self.initial_payment.amount and not self.request_key:
            raise ValueError('El abono inicial requiere una clave de operación.')
        return self
class CreditPayIn(Strict):
    request_key: UUID
    amount: Decimal = Field(gt=0,le=999999999,decimal_places=2)
    method: str = Field(pattern='^(cash|card|sinpe|transfer)$')
    reference: str = Field(default='',max_length=100)

def payments(db,obj):
    return list(db.scalars(select(CreditPayment).where(CreditPayment.receivable_id==obj.id,CreditPayment.business_id==obj.business_id).order_by(CreditPayment.id)))
def summary(db,obj,history=None):
    history=payments(db,obj) if history is None else history
    paid=money(sum((p.amount for p in history if not p.voided_at),Decimal(0)))
    allocation=paid; installments=[]
    for item in obj.schedule:
        amount=money(item['amount']); applied=min(allocation,amount); allocation-=applied
        installments.append({**item,'paid':applied,'balance':amount-applied})
    balance=money(obj.original-paid)
    overdue=any(i['balance']>0 and i.get('due') and date.fromisoformat(i['due'])<datetime.now(TZ).date() for i in installments)
    status='voided' if obj.voided_at else 'paid' if balance==0 else 'overdue' if overdue else 'partial' if paid else 'pending'
    order=db.get(Order,obj.order_id)
    customer=db.get(Customer,obj.customer_id)
    data={key:value for key,value in row(obj).items() if key not in ('checkout_key','checkout_digest')}
    return {**data,'paid':paid,'balance':Decimal(0) if obj.voided_at else balance,'status':status,
            'customer_name':customer.name if customer else '', 'invoice_number':order.invoice_number if order else '',
            'order_label':order.label if order else '', 'installments':installments,'payments':[row(p) for p in history]}

def payment_digest(ident,p):
    return hashlib.sha256(json.dumps({'id':ident,**p.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()

def record_payment(db,b,a,obj,reg,p):
    """Caller owns the transaction, including the initial credit payment."""
    payment=CreditPayment(business_id=b.id,receivable_id=obj.id,account_id=a.id,register_id=reg.id,
                          request_key=str(p.request_key),request_digest=payment_digest(obj.id,p),
                          amount=p.amount,method=p.method,reference=p.reference)
    db.add(payment);db.flush()
    movement=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,order_id=obj.order_id,
                      kind='income' if p.method=='cash' else 'credit_payment',amount=p.amount,
                      reason=f'Abono CXC #{obj.id} / comprobante #{payment.id}')
    db.add(movement);db.flush();payment.cash_movement_id=movement.id
    audit(db,b,a,'credit_payment',{'payment_id':payment.id,'amount':str(p.amount),'method':p.method})
    return payment

def attach_order_credit(db,bid,orders):
    """Prefetch payment histories so refreshed receipts show their current balance."""
    ids=[o['id'] for o in orders if o['payment_method']=='credit']
    if not ids:return
    credits=list(db.scalars(select(Receivable).where(Receivable.business_id==bid,Receivable.order_id.in_(ids))))
    if not credits:return
    histories={c.id:[] for c in credits}
    for payment in db.scalars(select(CreditPayment).where(CreditPayment.business_id==bid,CreditPayment.receivable_id.in_(histories)).order_by(CreditPayment.id)):
        histories[payment.receivable_id].append(payment)
    by_order={c.order_id:summary(db,c,histories[c.id]) for c in credits}
    for order in orders:
        if order['id'] in by_order:
            detail=by_order[order['id']]
            order['credit']={key:detail[key] for key in ('id','original','paid','balance','status')}

@router.post('/business/{bid}/orders/{ident}/credit')
def sell_credit(ident:int,p:CreditIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    schedule=[{'due':i.due.isoformat(),'amount':str(money(i.amount))} for i in p.installments] if p.installments else [{'due':p.due_date.isoformat() if p.due_date else None,'amount':str(money(obj.total))}]
    digest=hashlib.sha256(json.dumps({'order_id':ident,**p.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
    if p.request_key:
        previous=db.scalar(select(Receivable).where(Receivable.business_id==b.id,Receivable.checkout_key==str(p.request_key)))
        if previous and (previous.order_id!=ident or previous.checkout_digest!=digest):
            fail('Clave de crédito reutilizada con otros datos.',409)
    existing=db.scalar(select(Receivable).where(Receivable.order_id==ident,Receivable.business_id==b.id))
    if existing:
        if existing.checkout_digest:
            if existing.checkout_digest!=digest:fail('La venta ya tiene un crédito registrado. Consultá su saldo en Cuentas por cobrar.',409)
        elif existing.schedule!=schedule or (p.initial_payment and p.initial_payment.amount):
            fail('La venta ya tiene otro plan de crédito.',409)
        return summary(db,existing)
    customer_id=p.customer_id if p.customer_id is not None else obj.customer_id
    if obj.status not in OPEN or not customer_id or obj.total<=0: fail('Crédito requiere una venta abierta, un cliente y un total positivo.',409)
    if p.expected_revision is not None and p.expected_revision!=obj.revision:
        fail('La cuenta cambió en otro dispositivo. Abrila de nuevo antes de cobrar.',409)
    find(db,Customer,customer_id,b.id)
    if obj.external_id and customer_id!=obj.customer_id:fail('El pedido web debe conservar su cliente original.',409)
    if p.installments and money(sum((i.amount for i in p.installments),Decimal(0)))!=obj.total: fail('Las cuotas deben sumar exactamente el total.')
    first_due=p.installments[0].due if p.installments else p.due_date
    if first_due and first_due<datetime.now(TZ).date(): fail('La fecha de pago no puede estar en el pasado.')
    initial=p.initial_payment.amount if p.initial_payment else Decimal(0)
    if initial>=obj.total:fail('El abono inicial debe ser menor que el total. Para pagarlo completo, elegí el método de pago normal.')
    reg=active_register(db,b.id)
    linked=zb.is_zenit(db,b.id)
    if obj.external_id and not linked: fail('Crédito de pedidos externos requiere integración transaccional verificada.',409)
    obj.customer_id=customer_id
    if linked:
        result,replay=zb.execute(db,b,a,f'/orders/{ident}/credit',p.model_dump(mode='json'),'/sales',zb.sale_payload(db,b,a,obj,credit=True,invoice_number=p.invoice_number),order=obj,register=reg)
        if replay:
            return summary(db,db.scalar(select(Receivable).where(Receivable.order_id==ident,Receivable.business_id==b.id)))
        obj.invoice_number=result['invoiceNumber']
    for item in ([] if linked else obj.items):
        product=find(db,Product,item['product_id'],b.id);qty=Decimal(item['quantity'])
        if not product.active: fail('Producto inactivo.')
        if item['track_stock']:
            if product.stock<qty: fail('Stock insuficiente.')
            product.stock-=qty
            db.add(Movement(business_id=b.id,account_id=a.id,product_id=product.id,order_id=obj.id,kind='stock',amount=-qty,reason='Venta a crédito'))
    obj.status='paid';obj.payment_method='credit';obj.register_id=reg.id;obj.received=initial;obj.change=0;obj.paid_at=datetime.now(timezone.utc);obj.revision+=1
    if not linked:obj.invoice_number=p.invoice_number.strip().upper() or obj.invoice_number or f'POS-{b.id}-{obj.id}'
    credit=Receivable(business_id=b.id,order_id=obj.id,customer_id=obj.customer_id,original=obj.total,schedule=schedule,
                      checkout_key=str(p.request_key) if p.request_key else None,checkout_digest=digest)
    db.add(credit);db.flush();audit(db,b,a,'credit_sale',{'receivable_id':credit.id},order=obj.id)
    if initial:
        key=uuid5(NAMESPACE_URL,f'pos-credit-initial:{b.id}:{p.request_key}')
        record_payment(db,b,a,credit,reg,CreditPayIn(request_key=key,**p.initial_payment.model_dump()))
    commit(db);return summary(db,credit)

@router.get('/business/{bid}/receivables')
def list_credit(b=Depends(tenant),db=Depends(get_db)):
    rows=[summary(db,r) for r in db.scalars(select(Receivable).where(Receivable.business_id==b.id).order_by(Receivable.id.desc()))]
    return {'accounts':rows,'balance':sum((r['balance'] for r in rows),Decimal(0)),'overdue':sum((r['balance'] for r in rows if r['status']=='overdue'),Decimal(0))}

@router.post('/business/{bid}/receivables/{ident}/payments')
def pay_credit(ident:int,p:CreditPayIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Receivable,ident,b.id)
    digest=payment_digest(ident,p)
    previous=db.scalar(select(CreditPayment).where(CreditPayment.business_id==b.id,CreditPayment.request_key==str(p.request_key)))
    if previous:
        if previous.request_digest!=digest: fail('Clave de cobro reutilizada con otros datos.',409)
        return row(previous)
    if obj.voided_at: fail('Crédito anulado.',409)
    if p.amount>summary(db,obj)['balance']: fail('El abono excede el saldo.',409)
    reg=active_register(db,b.id)
    if zb.is_zenit(db,b.id) and p.amount==summary(db,obj)['balance']:
        result,replay=zb.execute(db,b,a,f'/receivables/{ident}/payments',p.model_dump(mode='json'),'/sales/settle',{'saleKey':zb.sale_key(b.id,obj.order_id),'actor':zb.actor(a,b),'reason':'Liquidación completa del crédito'},order=find(db,Order,obj.order_id,b.id),register=reg)
        if replay:return row(db.scalar(select(CreditPayment).where(CreditPayment.business_id==b.id,CreditPayment.request_key==str(p.request_key))))
    payment=record_payment(db,b,a,obj,reg,p)
    commit(db);return row(payment)

@router.post('/business/{bid}/receivables/{ident}/payments/{payment_id}/void')
def void_credit_payment(ident:int,payment_id:int,p:Reason,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Receivable,ident,b.id);payment=find(db,CreditPayment,payment_id,b.id)
    if payment.receivable_id!=obj.id: fail('Comprobante no encontrado.',404)
    if payment.voided_at: return row(payment)
    reg=active_register(db,b.id)
    if payment.method=='cash' and expected_cash(db,reg)<payment.amount: fail('Efectivo insuficiente.')
    if zb.is_zenit(db,b.id) and summary(db,obj)['balance']==0:
        result,replay=zb.execute(db,b,a,f'/receivables/{ident}/payments/{payment_id}/void',p.model_dump(mode='json'),'/sales/reopen',{'saleKey':zb.sale_key(b.id,obj.order_id),'actor':zb.actor(a,b),'reason':p.reason},order=find(db,Order,obj.order_id,b.id),register=reg)
        if replay:return row(payment)
    payment.voided_at=datetime.now(timezone.utc);payment.void_reason=p.reason
    movement=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,order_id=obj.order_id,kind='expense' if payment.method=='cash' else 'credit_payment',amount=-payment.amount,reason=f'Anulación abono #{payment.id}: '+p.reason)
    db.add(movement);db.flush();payment.void_movement_id=movement.id
    audit(db,b,a,'credit_payment_void',{'payment_id':payment.id,'reason':p.reason,'original_register_id':payment.register_id,'reversal_register_id':reg.id})
    commit(db);return row(payment)

@router.post('/business/{bid}/receivables/{ident}/void')
def void_credit(ident:int,p:Reason,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Receivable,ident,b.id)
    if obj.voided_at: return summary(db,obj)
    if any(not x.voided_at for x in payments(db,obj)): fail('Primero anulá los abonos; se conserva el historial.',409)
    order=find(db,Order,obj.order_id,b.id)
    linked=zb.is_zenit(db,b.id)
    if linked:
        result,replay=zb.execute(db,b,a,f'/receivables/{ident}/void',p.model_dump(mode='json'),'/sales/void',{'saleKey':zb.sale_key(b.id,order.id),'actor':zb.actor(a,b),'reason':p.reason},order=order)
        if replay:return summary(db,obj)
    for item in ([] if linked else order.items):
        if item['track_stock']:
            product=find(db,Product,item['product_id'],b.id);qty=Decimal(item['quantity']);product.stock+=qty
            db.add(Movement(business_id=b.id,account_id=a.id,product_id=product.id,order_id=order.id,kind='stock',amount=qty,reason='Anulación crédito: '+p.reason))
    order.status='refunded';order.revision+=1;order.kitchen_status='cancelled'
    obj.voided_at=datetime.now(timezone.utc);obj.void_reason=p.reason
    audit(db,b,a,'credit_void',{'receivable_id':obj.id,'reason':p.reason},order=order.id)
    commit(db);return summary(db,obj)
