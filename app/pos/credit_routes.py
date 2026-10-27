"""Common credit ledger. Parent business lock serializes payment, void and drawer close."""
from datetime import date
from uuid import UUID
from pydantic import Field, model_validator
from .routes import (router, Strict, Depends, get_db, tenant, current, select, money, fail,
                     row, find, commit, Order, OPEN, Product, Movement, Decimal, active_register,
                     datetime, timezone, audit, Reason, expected_cash, TZ)
from .models import Receivable, CreditPayment, Customer
from . import zenit_bridge as zb

class Installment(Strict):
    due: date
    amount: Decimal = Field(gt=0,le=999999999,decimal_places=2)
class CreditIn(Strict):
    invoice_number: str = Field(default="",max_length=100)
    installments: list[Installment] = Field(min_length=1,max_length=120)
    @model_validator(mode='after')
    def ordered(self):
        if [i.due for i in self.installments]!=sorted(set(i.due for i in self.installments)):
            raise ValueError('Vencimientos únicos en orden ascendente.')
        return self
class CreditPayIn(Strict):
    request_key: UUID
    amount: Decimal = Field(gt=0,le=999999999,decimal_places=2)
    method: str = Field(pattern='^(cash|card|sinpe|transfer)$')
    reference: str = Field(default='',max_length=100)

def payments(db,obj):
    return list(db.scalars(select(CreditPayment).where(CreditPayment.receivable_id==obj.id,CreditPayment.business_id==obj.business_id).order_by(CreditPayment.id)))
def summary(db,obj):
    history=payments(db,obj); paid=money(sum((p.amount for p in history if not p.voided_at),Decimal(0)))
    allocation=paid; installments=[]
    for item in obj.schedule:
        amount=money(item['amount']); applied=min(allocation,amount); allocation-=applied
        installments.append({**item,'paid':applied,'balance':amount-applied})
    balance=money(obj.original-paid)
    overdue=any(i['balance']>0 and date.fromisoformat(i['due'])<datetime.now(TZ).date() for i in installments)
    status='voided' if obj.voided_at else 'paid' if balance==0 else 'overdue' if overdue else 'partial' if paid else 'pending'
    return {**row(obj),'paid':paid,'balance':Decimal(0) if obj.voided_at else balance,'status':status,'installments':installments,'payments':[row(p) for p in history]}

@router.post('/business/{bid}/orders/{ident}/credit')
def sell_credit(ident:int,p:CreditIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    schedule=[{'due':i.due.isoformat(),'amount':str(money(i.amount))} for i in p.installments]
    existing=db.scalar(select(Receivable).where(Receivable.order_id==ident,Receivable.business_id==b.id))
    if existing:
        if existing.schedule!=schedule: fail('La venta ya tiene otro plan de crédito.',409)
        return summary(db,existing)
    if obj.status not in OPEN or not obj.customer_id or obj.total<=0: fail('Crédito requiere pedido abierto, cliente y total positivo.',409)
    find(db,Customer,obj.customer_id,b.id)
    if money(sum((i.amount for i in p.installments),Decimal(0)))!=obj.total: fail('Las cuotas deben sumar exactamente el total.')
    if p.installments[0].due<datetime.now(TZ).date(): fail('El vencimiento inicial no puede estar en el pasado.')
    linked=zb.is_zenit(db,b.id)
    if obj.external_id and not linked: fail('Crédito de pedidos externos requiere integración transaccional verificada.',409)
    if linked:
        reg=active_register(db,b.id)
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
    obj.status='paid';obj.payment_method='credit';obj.received=0;obj.change=0;obj.paid_at=datetime.now(timezone.utc);obj.revision+=1
    credit=Receivable(business_id=b.id,order_id=obj.id,customer_id=obj.customer_id,original=obj.total,schedule=schedule)
    db.add(credit);db.flush();audit(db,b,a,'credit_sale',{'receivable_id':credit.id},order=obj.id)
    commit(db);return summary(db,credit)

@router.get('/business/{bid}/receivables')
def list_credit(b=Depends(tenant),db=Depends(get_db)):
    rows=[summary(db,r) for r in db.scalars(select(Receivable).where(Receivable.business_id==b.id).order_by(Receivable.id.desc()))]
    return {'accounts':rows,'balance':sum((r['balance'] for r in rows),Decimal(0)),'overdue':sum((r['balance'] for r in rows if r['status']=='overdue'),Decimal(0))}

@router.post('/business/{bid}/receivables/{ident}/payments')
def pay_credit(ident:int,p:CreditPayIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    import hashlib,json
    obj=find(db,Receivable,ident,b.id)
    digest=hashlib.sha256(json.dumps({'id':ident,**p.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
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
    payment=CreditPayment(business_id=b.id,receivable_id=obj.id,account_id=a.id,register_id=reg.id,request_key=str(p.request_key),request_digest=digest,amount=p.amount,method=p.method,reference=p.reference)
    db.add(payment);db.flush()
    movement=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,order_id=obj.order_id,kind='income' if p.method=='cash' else 'credit_payment',amount=p.amount,reason=f'Abono CXC #{obj.id} / comprobante #{payment.id}')
    db.add(movement);db.flush();payment.cash_movement_id=movement.id
    audit(db,b,a,'credit_payment',{'payment_id':payment.id,'amount':str(p.amount),'method':p.method})
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
