from datetime import datetime, timezone, timedelta, date, time
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
import hashlib, json
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from .models import Account, Business, Membership, Product, Customer, Register, Order, Movement, Appointment, Audit, FinancialEntry, ConnectLink, SigningKey
from .permissions import membership, permissions, enforce
from .security import current, ceo, hash_password, verify_password, issue
from .schemas import *
from .financial_reports import build_report
from .connect_client import connect_request

router = APIRouter(prefix='/pos-api', tags=['POS'])
OPEN = ('open','queued','preparing','ready')
TZ = ZoneInfo('America/Costa_Rica')
def money(v): return Decimal(str(v)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
def fail(message, code=400): raise HTTPException(code, message)
def row(obj):
    result = {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in ('password_hash','failed','locked_until','pin_hash','pin_failed','pin_locked_until')}
    if isinstance(obj, Order): result['items']=[{k:v for k,v in i.items() if k!='cost'} for i in obj.items]
    return result
def commit(db):
    try: db.commit()
    except IntegrityError:
        db.rollback(); fail('El registro ya existe o tiene una referencia inválida.',409)
def find(db, cls, ident, bid):
    obj = db.get(cls, ident)
    if not obj or obj.business_id != bid: fail('Registro no encontrado en este negocio.',404)
    return obj

def tenant(bid: int, request: Request, account=Depends(current), db=Depends(get_db)):
    # Serializes write operations per business: stock, table occupancy, payment and close.
    business = db.scalar(select(Business).where(Business.id==bid).with_for_update())
    if not business or not business.active: fail('Negocio no disponible.',403)
    m=membership(db,account.id,bid)
    if not m: fail('Tu cuenta no tiene acceso a este negocio.',403)
    enforce(request,m)
    return business

def active_register(db,bid):
    reg=db.scalar(select(Register).where(Register.business_id==bid,Register.closed_at.is_(None)))
    if not reg: fail('Primero abrí la caja.')
    return reg

def expected_cash(db,reg):
    sales=db.scalar(select(func.coalesce(func.sum(Order.total),0)).where(Order.register_id==reg.id,Order.status=='paid',Order.payment_method=='cash'))
    movements=db.scalar(select(func.coalesce(func.sum(Movement.amount),0)).where(Movement.register_id==reg.id,Movement.kind.in_(['income','expense','refund'])))
    # A refund of a sale made during this register is removed from sales automatically.
    return money(reg.opening + sales + movements)

@router.post('/auth/login')
def login(p: Login, db=Depends(get_db)):
    a=db.scalar(select(Account).where(Account.email==str(p.email).lower()).with_for_update())
    now=datetime.now(timezone.utc)
    if a and a.locked_until:
        locked=a.locked_until.replace(tzinfo=timezone.utc) if a.locked_until.tzinfo is None else a.locked_until
        if locked>now: fail('Demasiados intentos. Esperá 15 minutos.',429)
    if not a or not a.active or not verify_password(p.password,a.password_hash):
        if a:
            a.failed+=1
            if a.failed>=5: a.locked_until=now+timedelta(minutes=15); a.failed=0
            commit(db)
        fail('Correo o contraseña incorrectos.',401)
    token=issue(a,db)
    a.failed=0; a.locked_until=None; commit(db)
    return {'token':token,'account':row(a)}

@router.get('/auth/me')
def me(a=Depends(current),db=Depends(get_db)):
    businesses=db.scalars(select(Business).join(Membership,Membership.business_id==Business.id).where(Membership.account_id==a.id,Business.active==True)).all()
    return {'account':row(a),'businesses':[{**row(b),**permissions(membership(db,a.id,b.id))} for b in businesses]}

@router.post('/auth/password')
def password(p:Password,a=Depends(current),db=Depends(get_db)):
    if not verify_password(p.current,a.password_hash): fail('La contraseña actual no coincide.',403)
    a.password_hash=hash_password(p.password); a.version+=1; commit(db)
    return {'token':issue(a,db)}

@router.post('/auth/logout')
def logout(a=Depends(current),db=Depends(get_db)):
    a.version+=1; commit(db); return {'ok':True}

@router.get('/admin')
def admin(a=Depends(ceo),db=Depends(get_db)):
    return {'businesses':[row(b) for b in db.scalars(select(Business).order_by(Business.id))],
            'accounts':[{**row(u),'business_ids':list(db.scalars(select(Membership.business_id).where(Membership.account_id==u.id,Membership.role=='owner')))} for u in db.scalars(select(Account).order_by(Account.id))]}

@router.post('/admin/businesses')
def new_business(p:BusinessIn,a=Depends(ceo),db=Depends(get_db)):
    b=Business(**p.model_dump()); db.add(b); commit(db); return row(b)

@router.post('/admin/accounts/{ident}/businesses')
def new_account_business(ident:int,p:BusinessIn,a=Depends(ceo),db=Depends(get_db)):
    """Create and assign a new local atomically, preserving every existing access."""
    owner=db.get(Account,ident)
    if not owner: fail('Cuenta no encontrada.',404)
    b=Business(**p.model_dump()); db.add(b); db.flush()
    db.add(Membership(account_id=owner.id,business_id=b.id,role='owner'))
    commit(db); return row(b)

@router.put('/admin/businesses/{ident}')
def edit_business(ident:int,p:BusinessIn,a=Depends(ceo),db=Depends(get_db)):
    b=db.get(Business,ident)
    if not b: fail('Negocio no encontrado.',404)
    if p.mode!=b.mode: fail('La modalidad de un negocio existente no se cambia.')
    for k,v in p.model_dump().items(): setattr(b,k,v)
    commit(db); return row(b)

def memberships(db,a,ids):
    ids=set(ids)
    if len(list(db.scalars(select(Business.id).where(Business.id.in_(ids))))) != len(ids): fail('Negocio inválido.')
    for old in db.scalars(select(Membership).where(Membership.account_id==a.id,Membership.role=='owner')):
        if old.business_id not in ids: db.delete(old)
    db.flush()
    for bid in ids:
        old=membership(db,a.id,bid)
        if old: old.role='owner'
        else: db.add(Membership(account_id=a.id,business_id=bid,role='owner'))

@router.post('/admin/accounts')
def new_account(p:AccountIn,a=Depends(ceo),db=Depends(get_db)):
    if db.scalar(select(Account.id).where(Account.email==str(p.email).lower())): fail('Ese correo ya está registrado.',409)
    u=Account(name=p.name,email=str(p.email).lower(),password_hash=hash_password(p.password),ceo=False)
    db.add(u); db.flush(); memberships(db,u,p.business_ids); commit(db); return row(u)

@router.put('/admin/accounts/{ident}')
def edit_access(ident:int,p:AccessIn,a=Depends(ceo),db=Depends(get_db)):
    u=db.get(Account,ident)
    if not u: fail('Cuenta no encontrada.',404)
    if u.id==a.id and not p.active: fail('No podés suspender tu propia cuenta CEO.')
    u.active=p.active; u.version+=1; memberships(db,u,p.business_ids); commit(db); return row(u)

@router.get('/business/{bid}/state')
def state(b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    def allrows(cls):
        query=select(cls).where(cls.business_id==b.id).order_by(cls.id.desc())
        if cls in (Register,Movement): query=query.limit(1000)
        if cls is Order:
            recent=select(Order.id).where(Order.business_id==b.id).order_by(Order.id.desc()).limit(1000)
            query=query.where((Order.status.in_(OPEN)) | (Order.kitchen_status.in_(['queued','preparing','ready'])) | (Order.id.in_(recent)))
        return [row(x) for x in db.scalars(query)]
    reg=db.scalar(select(Register).where(Register.business_id==b.id,Register.closed_at.is_(None)))
    result = {'business':row(b),'products':allrows(Product),'customers':allrows(Customer),'orders':allrows(Order),
            'registers':allrows(Register),'movements':allrows(Movement),'appointments':allrows(Appointment),
            'register':{**row(reg),'expected':expected_cash(db,reg)} if reg else None}
    rights=permissions(membership(db,a.id,b.id)); result['permissions']=rights
    link=db.get(ConnectLink,b.id)
    result['connect']={'provider':link.provider,'site':'https://www.shirleyscr.com'} if link and rights['manage'] else None
    if rights['manage']:
        revision=db.execute(select(func.max(FinancialEntry.id),func.max(FinancialEntry.voided_at)).where(FinancialEntry.business_id==b.id)).first()
        result['finance_revision']=':'.join(str(value or '') for value in revision)
    if not rights['manage']:
        for product in result['products']: product.pop('cost',None)
    if not rights['cash']:
        result['registers']=[]; result['movements']=[]
        result['register']={'id':reg.id} if reg else None
        result['orders']=[o for o in result['orders'] if o['status'] in OPEN or o['kitchen_status'] in ('queued','preparing','ready') or (o['account_id']==a.id and rights['sell'])]
    if not rights['sell']:
        result['customers']=[]; result['appointments']=[]
        result['orders']=[o for o in result['orders'] if o['kitchen_status'] in ('queued','preparing','ready')]
    return result

@router.post('/business/{bid}/products')
def new_product(p:ProductIn,b=Depends(tenant),db=Depends(get_db)):
    obj=Product(business_id=b.id,**p.model_dump()); db.add(obj); commit(db); return row(obj)

@router.put('/business/{bid}/products/{ident}')
def edit_product(ident:int,p:ProductIn,b=Depends(tenant),db=Depends(get_db)):
    obj=find(db,Product,ident,b.id)
    for k,v in p.model_dump().items(): setattr(obj,k,v)
    commit(db); return row(obj)

@router.post('/business/{bid}/products/{ident}/stock')
def stock(ident:int,p:StockIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Product,ident,b.id)
    delta=p.quantity if p.kind=='entry' else -p.quantity if p.kind=='exit' else p.quantity-obj.stock
    if obj.stock+delta<0: fail('Existencias insuficientes.')
    obj.stock+=delta
    db.add(Movement(business_id=b.id,account_id=a.id,product_id=obj.id,kind='stock',amount=delta,reason=p.reason))
    commit(db); return row(obj)

@router.post('/business/{bid}/customers')
def new_customer(p:CustomerIn,b=Depends(tenant),db=Depends(get_db)):
    obj=Customer(business_id=b.id,**p.model_dump()); db.add(obj); commit(db); return row(obj)

@router.put('/business/{bid}/customers/{ident}')
def edit_customer(ident:int,p:CustomerIn,b=Depends(tenant),db=Depends(get_db)):
    obj=find(db,Customer,ident,b.id)
    for k,v in p.model_dump().items():setattr(obj,k,v)
    commit(db); return row(obj)

@router.post('/business/{bid}/register/open')
def open_register(p:Amount,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    if db.scalar(select(Register.id).where(Register.business_id==b.id,Register.closed_at.is_(None))): fail('Ya hay una caja abierta.',409)
    obj=Register(business_id=b.id,opened_by=a.id,opening=p.amount); db.add(obj); commit(db); return row(obj)

@router.post('/business/{bid}/register/close')
def close_register(p:Amount,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    reg=active_register(db,b.id)
    if db.scalar(select(Order.id).where(Order.business_id==b.id,Order.status.in_(OPEN))): fail('Cobrá o cancelá los pedidos pendientes antes de cerrar.')
    reg.expected=expected_cash(db,reg); reg.closing=p.amount; reg.difference=money(p.amount-reg.expected)
    reg.closed_at=datetime.now(timezone.utc); reg.closed_by=a.id; commit(db); return row(reg)

@router.post('/business/{bid}/cash')
def cash(p:CashIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    reg=active_register(db,b.id)
    amount=p.amount if p.kind=='income' else -p.amount
    if expected_cash(db,reg)+amount<0: fail('El egreso supera el efectivo disponible.')
    obj=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,kind=p.kind,amount=amount,reason=p.reason)
    db.add(obj); commit(db); return row(obj)

def populate(db,obj,p,b,a):
    if p.customer_id: find(db,Customer,p.customer_id,b.id)
    if p.table_number and p.fulfillment!='dine_in': fail('La mesa solo aplica para consumo en el local.')
    if p.source_channel=='website' and not obj.external_id: fail('Importá el pedido desde SL Connect para conservar su referencia.')
    if p.table_number:
        if b.mode not in ('restaurante','heladeria') or p.table_number>b.tables: fail('Mesa inválida.')
        occupied=db.scalar(select(Order.id).where(Order.business_id==b.id,Order.table_number==p.table_number,Order.status.in_(OPEN),Order.id!=obj.id))
        if occupied: fail('La mesa ya tiene un pedido abierto.',409)
    quantities={}; prices={}
    for i in p.items:
        if i.product_id in prices and prices[i.product_id]!=i.unit_price: fail('Un producto no puede tener precios distintos en el mismo pedido.')
        quantities[i.product_id]=quantities.get(i.product_id,Decimal(0))+i.quantity
        prices[i.product_id]=i.unit_price
    items=[]; subtotal=Decimal(0); changes=[]
    for pid,qty in quantities.items():
        product=find(db,Product,pid,b.id)
        if not product.active: fail('Producto inactivo.')
        if product.track_stock and qty>product.stock: fail(f'Stock insuficiente: {product.name}.')
        unit=product.price if prices[pid] is None else prices[pid]
        if unit!=product.price: changes.append({'product_id':pid,'catalog_price':str(product.price),'authorized_price':str(unit),'quantity':str(qty)})
        line=money(unit*qty); subtotal+=line
        items.append({'product_id':pid,'name':product.name,'quantity':str(qty),'price':str(unit),'cost':str(product.cost),'tax_rate':str(product.tax_rate),'subtotal':str(line),'track_stock':product.track_stock,'cost_known':product.cost_known,'packaging_fee':str(product.packaging_fee)})
    if p.discount>subtotal: fail('El descuento supera el subtotal.')
    tax=Decimal(0); remaining=p.discount
    for idx,item in enumerate(items):
        part=remaining if idx==len(items)-1 else (money(p.discount*Decimal(item['subtotal'])/subtotal) if subtotal else Decimal(0))
        part=min(part,remaining,Decimal(item['subtotal'])); remaining-=part
        line_tax=money((Decimal(item['subtotal'])-part)*Decimal(item['tax_rate'])/100)
        item['discount']=str(part); item['tax']=str(line_tax); tax+=line_tax
    if subtotal+tax>Decimal('999999999999.99'): fail('El total excede el límite de la venta.')
    if changes or p.discount:
        approve_adjustment(db,b,a,p,obj,changes)
    if obj.external_id and p.source_channel!='website': fail('El origen del pedido del sitio web se conserva.')
    obj.source_channel=p.source_channel; obj.fulfillment=p.fulfillment
    obj.packaging_total=money(sum((Decimal(item['packaging_fee'])*Decimal(item['quantity']) for item in items),Decimal(0))) if p.fulfillment in ('pickup','express') else Decimal(0)
    obj.service_total=money((subtotal-p.discount)*b.service_rate/100) if p.fulfillment=='dine_in' else Decimal(0)
    obj.items=items; obj.subtotal=subtotal; obj.discount=p.discount; obj.tax=tax; obj.total=money(subtotal-p.discount+tax+obj.packaging_total+obj.service_total)
    if obj.total>Decimal('999999999999.99'): fail('El total excede el límite de la venta.')
    obj.label=p.label; obj.table_number=p.table_number; obj.notes=p.notes; obj.customer_id=p.customer_id

@router.post('/business/{bid}/orders')
def new_order(p:OrderIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    if p.source_channel=='website': fail('Importá los pedidos del sitio desde SL Connect para evitar duplicarlos.')
    key=str(p.request_key or uuid4())
    digest=hashlib.sha256(json.dumps(p.model_dump(exclude={'request_key','approval'}),sort_keys=True,default=str).encode()).hexdigest()
    existing=db.scalar(select(Order).where(Order.business_id==b.id,Order.request_key==key))
    if existing:
        if existing.request_digest!=digest: fail('Ese intento ya guardó un pedido distinto. Revisá Pedidos antes de reintentar.',409)
        return row(existing)
    active_register(db,b.id)
    obj=Order(business_id=b.id,account_id=a.id,items=[],request_key=key,request_digest=digest); db.add(obj); db.flush()
    populate(db,obj,p,b,a)
    if p.send_to_kitchen:
        if b.mode not in ('restaurante','heladeria'): fail('Esta modalidad no utiliza cocina.')
        obj.status='queued'; obj.kitchen_status='queued'
    commit(db); return row(obj)

@router.put('/business/{bid}/orders/{ident}')
def edit_order(ident:int,p:OrderIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    if obj.status not in ('open','queued'): fail('Solo se editan pedidos antes de preparación.')
    if p.expected_revision!=obj.revision: fail('El pedido cambió en otro dispositivo. Abrilo de nuevo antes de editar.',409)
    obj.revision+=1
    populate(db,obj,p,b,a)
    if p.send_to_kitchen:
        if b.mode not in ('restaurante','heladeria'): fail('Esta modalidad no utiliza cocina.')
        obj.status='queued'; obj.kitchen_status='queued'
    commit(db); return row(obj)

@router.post('/business/{bid}/orders/{ident}/status')
def order_state(ident:int,p:StateIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    rights=permissions(membership(db,a.id,b.id))
    if p.status in ('preparing','ready') and not rights['prepare']: fail('Solo cocina o administración cambia la preparación.',403)
    if p.status=='served' and not (rights['sell'] or rights['prepare']): fail('No podés entregar pedidos.',403)
    if p.status=='queued' and not rights['sell']: fail('No podés enviar pedidos.',403)
    if p.status=='cancelled' and not rights['manage'] and (obj.account_id!=a.id or obj.status!='open'): fail('Solo administración cancela pedidos enviados o de otro usuario.',403)
    if p.status=='cancelled':
        if obj.status not in OPEN: fail('El pedido no se puede cancelar.',409)
        obj.status='cancelled'; obj.kitchen_status='cancelled'
    else:
        if obj.status in ('cancelled','refunded'): fail('Pedido cancelado o devuelto.',409)
        previous=obj.kitchen_status or 'open'
        allowed={'open':('queued',),'queued':('preparing',),'preparing':('ready',),'ready':('served',)}
        if p.status not in allowed.get(previous,()): fail('Transición de cocina inválida.',409)
        if b.mode not in ('restaurante','heladeria'): fail('Esta modalidad no utiliza cocina.')
        obj.kitchen_status=p.status
        if obj.status!='paid' and p.status!='served': obj.status=p.status
    obj.revision+=1; commit(db); return row(obj)

@router.post('/business/{bid}/orders/{ident}/pay')
def pay(ident:int,p:PayIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    # Persisted order ID is the idempotency boundary; retry never charges twice.
    if obj.status=='paid': return row(obj)
    if obj.status not in OPEN: fail('El pedido no se puede cobrar.',409)
    reg=active_register(db,b.id)
    if p.method=='cash' and p.received<obj.total: fail('El efectivo recibido no cubre el total.')
    for item in obj.items:
        product=find(db,Product,item['product_id'],b.id); qty=Decimal(item['quantity'])
        if not product.active: fail(f'Producto inactivo: {product.name}.')
        if item['track_stock']:
            if product.stock<qty: fail(f'Stock insuficiente: {product.name}.')
            product.stock-=qty
            db.add(Movement(business_id=b.id,account_id=a.id,product_id=product.id,order_id=obj.id,kind='stock',amount=-qty,reason=f'Venta #{obj.id}'))
    obj.revision+=1
    obj.status='paid'; obj.register_id=reg.id; obj.payment_method=p.method; obj.received=p.received if p.method=='cash' else obj.total
    obj.change=money(obj.received-obj.total); obj.paid_at=datetime.now(timezone.utc)
    commit(db); return row(obj)

@router.post('/business/{bid}/orders/{ident}/refund')
def refund(ident:int,p:Reason,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    obj=find(db,Order,ident,b.id)
    if obj.status!='paid': fail('Solo se devuelve una venta pagada, una vez.',409)
    reg=active_register(db,b.id)
    if obj.payment_method=='cash' and expected_cash(db,reg)<obj.total: fail('Efectivo insuficiente para la devolución.')
    for item in obj.items:
        if item['track_stock']:
            product=find(db,Product,item['product_id'],b.id); qty=Decimal(item['quantity']); product.stock+=qty
            db.add(Movement(business_id=b.id,account_id=a.id,product_id=product.id,order_id=obj.id,kind='stock',amount=qty,reason='Devolución: '+p.reason))
    # Same-register refunds already disappear from paid cash sales; older-register refunds need an outflow.
    delta=-obj.total if obj.payment_method=='cash' and reg.id!=obj.register_id else Decimal(0)
    db.add(Movement(business_id=b.id,account_id=a.id,register_id=reg.id,order_id=obj.id,kind='refund',amount=delta,reason=p.reason))
    obj.status='refunded'; obj.kitchen_status='cancelled'; obj.revision+=1; commit(db); return row(obj)

@router.get('/business/{bid}/reports')
def reports(start:date,end:date,b=Depends(tenant),db=Depends(get_db)):
    if end<start or (end-start).days>366: fail('Seleccioná un rango de hasta 366 días.')
    return build_report(db,b.id,start,end,row)

@router.post('/business/{bid}/appointments')
def appointment(p:AppointmentIn,b=Depends(tenant),db=Depends(get_db)):
    find(db,Customer,p.customer_id,b.id)
    if p.at.tzinfo is None: fail('La cita debe incluir zona horaria.')
    obj=Appointment(business_id=b.id,**p.model_dump()); db.add(obj); commit(db); return row(obj)

@router.put('/business/{bid}/appointments/{ident}')
def edit_appointment(ident:int,p:AppointmentIn,b=Depends(tenant),db=Depends(get_db)):
    obj=find(db,Appointment,ident,b.id); find(db,Customer,p.customer_id,b.id)
    if p.at.tzinfo is None: fail('La cita debe incluir zona horaria.')
    for k,v in p.model_dump().items(): setattr(obj,k,v)
    commit(db); return row(obj)

@router.post('/admin/accounts/{ident}/password')
def reset_password(ident:int,p:ResetPassword,a=Depends(ceo),db=Depends(get_db)):
    u=db.get(Account,ident)
    if not u: fail('Cuenta no encontrada.',404)
    u.password_hash=hash_password(p.password); u.version+=1; u.failed=0; u.locked_until=None
    commit(db); return {'ok':True}


def audit(db,b,a,action,detail,approver=None,order=None):
    db.add(Audit(business_id=b.id,actor_id=a.id,approver_id=approver,order_id=order,action=action,detail=detail))


def check_pin_lock(m):
    if m and m.pin_locked_until:
        until=m.pin_locked_until
        if until.tzinfo is None: until=until.replace(tzinfo=timezone.utc)
        if until>datetime.now(timezone.utc): fail('Código bloqueado temporalmente. Esperá 15 minutos.',429)


def bad_pin(db,m):
    # Discard the pending sale before committing only the failed-attempt counter.
    ident=m.id if m else None
    db.rollback()
    if ident:
        m=db.scalar(select(Membership).where(Membership.id==ident).with_for_update())
        if m:
            m.pin_failed+=1
            if m.pin_failed>=5:
                m.pin_locked_until=datetime.now(timezone.utc)+timedelta(minutes=15); m.pin_failed=0
            commit(db)
    fail('Autorización incorrecta o no disponible para este local.',403)


def approve_adjustment(db,b,a,p,obj,changes):
    own=membership(db,a.id,b.id)
    approver=a.id
    if not permissions(own)['manage']:
        if not p.approval: fail('El cambio de precio o descuento requiere el código del dueño o administrador.',403)
        person=db.scalar(select(Account).where(Account.email==str(p.approval.email).lower(),Account.active==True))
        m=membership(db,person.id,b.id) if person else None
        check_pin_lock(m)
        if not m or m.role not in ('owner','admin') or not m.pin_hash or not verify_password(p.approval.pin,m.pin_hash): bad_pin(db,m)
        m.pin_failed=0; m.pin_locked_until=None; approver=person.id
    if len(p.adjustment_reason.strip())<3: fail('Indicá el motivo del cambio de precio o descuento.')
    audit(db,b,a,'price_approval',{'reason':p.adjustment_reason,'prices':changes,'discount':str(p.discount),
        'previous_discount':str(obj.discount or 0),'previous_items':[{k:v for k,v in i.items() if k!='cost'} for i in (obj.items or [])]},approver,obj.id)


@router.post('/business/{bid}/pin')
def set_pin(p:PinIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    m=membership(db,a.id,b.id); check_pin_lock(m)
    if not verify_password(p.current_password,a.password_hash): bad_pin(db,m)
    m.pin_hash=hash_password(p.pin); m.pin_failed=0; m.pin_locked_until=None
    audit(db,b,a,'pin_changed',{'account_id':a.id}); commit(db); return {'ok':True}


def owned_ids(db,a):
    return list(db.scalars(select(Membership.business_id).where(Membership.account_id==a.id,Membership.role=='owner')))


def safe_staff(db,a,ident):
    u=db.get(Account,ident)
    if not u or u.ceo or u.id==a.id: fail('Cuenta no administrable desde este local.',403)
    if db.scalar(select(Membership.id).where(Membership.account_id==u.id,Membership.role=='owner')):
        fail('Las cuentas de dueños las administra System Lab.',403)
    return u


@router.get('/business/{bid}/team')
def team(b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    links=db.execute(select(Membership,Account).join(Account,Account.id==Membership.account_id).where(Membership.business_id==b.id)).all()
    candidates=db.scalars(select(Account).join(Membership,Membership.account_id==Account.id).where(Membership.business_id.in_(owned_ids(db,a)),Membership.role!='owner',Account.ceo==False).distinct()).all()
    return {'members':[{'id':u.id,'name':u.name,'email':u.email,'active':u.active,'role':m.role,'can_pay':m.can_pay,'pin_configured':bool(m.pin_hash)} for m,u in links],
        'candidates':[{'id':u.id,'name':u.name,'email':u.email} for u in candidates if not any(u.id==existing.id for _,existing in links)]}


@router.post('/business/{bid}/team')
def create_staff(p:StaffIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    if db.scalar(select(Account.id).where(Account.email==str(p.email).lower())):
        fail('Ese correo ya existe. Usá Vincular empleado si pertenece a tu equipo; de lo contrario contactá a System Lab.',409)
    u=Account(name=p.name,email=str(p.email).lower(),password_hash=hash_password(p.password),ceo=False)
    db.add(u); db.flush()
    db.add(Membership(account_id=u.id,business_id=b.id,role=p.role,can_pay=p.can_pay))
    audit(db,b,a,'staff_created',{'account_id':u.id,'role':p.role,'can_pay':p.can_pay})
    commit(db); return {'id':u.id,'name':u.name,'email':u.email}


@router.put('/business/{bid}/team/{ident}')
def assign_staff(ident:int,p:StaffAccess,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    u=safe_staff(db,a,ident)
    if not db.scalar(select(Membership.id).where(Membership.account_id==u.id,Membership.business_id.in_(owned_ids(db,a)))):
        fail('Esa cuenta no pertenece a tu equipo.',403)
    m=membership(db,u.id,b.id)
    previous=m.role if m else None
    if not m:
        m=Membership(account_id=u.id,business_id=b.id); db.add(m)
    if previous!=p.role: m.pin_hash=None; m.pin_failed=0; m.pin_locked_until=None
    m.role=p.role; m.can_pay=p.can_pay
    audit(db,b,a,'staff_access',{'account_id':u.id,'previous_role':previous,'role':p.role,'can_pay':p.can_pay})
    commit(db); return {'ok':True}


@router.delete('/business/{bid}/team/{ident}')
def remove_staff(ident:int,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    u=safe_staff(db,a,ident); m=membership(db,u.id,b.id)
    if not m: fail('No pertenece a este local.',404)
    audit(db,b,a,'staff_removed',{'account_id':u.id,'role':m.role}); db.delete(m)
    commit(db); return {'ok':True}


@router.post('/business/{bid}/team/{ident}/password')
def staff_password(ident:int,p:ResetPassword,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    u=safe_staff(db,a,ident)
    links=list(db.scalars(select(Membership.business_id).where(Membership.account_id==u.id)))
    if b.id not in links or not set(links).issubset(set(owned_ids(db,a))):
        fail('Esta cuenta tiene accesos fuera de tus locales. El restablecimiento corresponde a System Lab.',403)
    u.password_hash=hash_password(p.password); u.version+=1; u.failed=0; u.locked_until=None
    for m in db.scalars(select(Membership).where(Membership.account_id==u.id)): m.pin_hash=None
    audit(db,b,a,'staff_password_reset',{'account_id':u.id}); commit(db); return {'ok':True}


@router.get('/business/{bid}/audit')
def audit_log(b=Depends(tenant),db=Depends(get_db)):
    records=db.scalars(select(Audit).where(Audit.business_id==b.id).order_by(Audit.id.desc()).limit(200)).all()
    ids={r.actor_id for r in records}|{r.approver_id for r in records if r.approver_id}
    names={u.id:u.name for u in db.scalars(select(Account).where(Account.id.in_(ids)))}
    return [{**row(r),'actor_name':names.get(r.actor_id),'approver_name':names.get(r.approver_id)} for r in records]

# Financial entries are immutable; corrections keep an auditable reversal.
@router.get('/business/{bid}/finances')
def finances(start:date,end:date,b=Depends(tenant),db=Depends(get_db)):
    if end<start or (end-start).days>366: fail('Seleccioná un rango de hasta 366 días.')
    lo=datetime.combine(start,time.min,TZ).astimezone(timezone.utc); hi=datetime.combine(end+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
    entries=db.scalars(select(FinancialEntry).where(FinancialEntry.business_id==b.id,FinancialEntry.occurred_at>=lo,FinancialEntry.occurred_at<hi).order_by(FinancialEntry.occurred_at.desc(),FinancialEntry.id.desc()).limit(1000)).all()
    return {'entries':[row(entry) for entry in entries],'limit':1000}

@router.post('/business/{bid}/finances')
def save_finance(p:FinancialIn,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    if p.occurred_at.tzinfo is None: fail('La fecha debe incluir zona horaria.')
    if p.occurred_at>datetime.now(timezone.utc)+timedelta(minutes=5): fail('Registrá un movimiento realizado, no una fecha futura.')
    digest=hashlib.sha256(json.dumps(p.model_dump(),sort_keys=True,default=str).encode()).hexdigest()
    previous=db.scalar(select(FinancialEntry).where(FinancialEntry.business_id==b.id,FinancialEntry.request_key==str(p.request_key)))
    if previous:
        if previous.request_digest!=digest: fail('Este intento ya corresponde a otro movimiento.',409)
        return row(previous)
    data=p.model_dump(exclude={'from_register','request_key'})
    entry=FinancialEntry(business_id=b.id,account_id=a.id,request_key=str(p.request_key),request_digest=digest,**data)
    if p.from_register:
        if p.method!='cash': fail('Solo el efectivo puede salir o entrar en la caja.')
        if p.occurred_at.astimezone(TZ).date()!=datetime.now(TZ).date(): fail('Los movimientos de caja se registran con la fecha de hoy.')
        reg=active_register(db,b.id)
        delta=p.amount if p.kind in ('other_income','capital_in') else -p.amount
        if expected_cash(db,reg)+delta<0: fail('El egreso supera el efectivo disponible.')
        movement=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,kind='income' if delta>0 else 'expense',amount=delta,reason=p.reason)
        db.add(movement); db.flush(); entry.cash_movement_id=movement.id
    db.add(entry); db.flush()
    db.add(Audit(business_id=b.id,actor_id=a.id,action='financial_entry',detail={'entry_id':entry.id,'kind':p.kind,'amount':str(p.amount),'reason':p.reason}))
    commit(db); return row(entry)

@router.post('/business/{bid}/finances/{ident}/void')
def void_finance(ident:int,p:Reason,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    entry=find(db,FinancialEntry,ident,b.id)
    if entry.voided_at: return row(entry)
    if entry.cash_movement_id:
        original=db.get(Movement,entry.cash_movement_id); reg=db.get(Register,original.register_id)
        if reg.closed_at: fail('La caja ya cerró. Conservá este registro y registrá el ajuste en la caja actual.',409)
        if expected_cash(db,reg)-original.amount<0: fail('La anulación supera el efectivo disponible.')
        reversal=Movement(business_id=b.id,account_id=a.id,register_id=reg.id,kind=original.kind,amount=-original.amount,reason='Anulación: '+p.reason)
        db.add(reversal); db.flush(); entry.void_movement_id=reversal.id
    entry.voided_at=datetime.now(timezone.utc); entry.void_reason=p.reason
    db.add(Audit(business_id=b.id,actor_id=a.id,action='financial_void',detail={'entry_id':entry.id,'reason':p.reason}))
    commit(db); return row(entry)

@router.post('/admin/shirleys')
def setup_shirleys(p:ShirleysSetup,a=Depends(ceo),db=Depends(get_db)):
    from pathlib import Path
    # Serializes onboarding across tenants before checking the unique provider/account.
    db.scalar(select(SigningKey).where(SigningKey.id==1).with_for_update())
    existing=db.scalar(select(ConnectLink).where(ConnectLink.provider=='shirleys'))
    email=str(p.email).lower()
    if existing:
        owner=db.scalar(select(Account).join(Membership,Membership.account_id==Account.id).where(Membership.business_id==existing.business_id,Membership.role=='owner',Account.email==email))
        if not owner: fail('Shirley’s ya está vinculado a otra cuenta. Revisá sus accesos.',409)
        return {'created':False,'business':row(db.get(Business,existing.business_id)),'account':row(owner),'products':db.scalar(select(func.count()).select_from(Product).where(Product.business_id==existing.business_id))}
    if db.scalar(select(Account.id).where(Account.email==email)): fail('El correo ya existe. No se cambió su contraseña ni sus locales.',409)
    catalog=json.loads((Path(__file__).parent/'catalogs/shirleys.json').read_text())
    owner=Account(name=p.name,email=email,password_hash=hash_password(p.password),ceo=False)
    business=Business(name=p.business_name,mode='restaurante',tables=p.tables,active=True,service_rate=Decimal(str(catalog['service_rate'])))
    db.add_all([owner,business]); db.flush()
    db.add(Membership(account_id=owner.id,business_id=business.id,role='owner'))
    db.add(ConnectLink(business_id=business.id,provider='shirleys'))
    for item in catalog['products']:
        db.add(Product(business_id=business.id,**item,cost=0,cost_known=False,tax_rate=0,track_stock=False,stock=0,minimum=0,active=True))
    db.add(Audit(business_id=business.id,actor_id=a.id,action='shirleys_setup',detail={'source_commit':catalog['source_commit'],'products':len(catalog['products'])}))
    commit(db)
    return {'created':True,'business':row(business),'account':row(owner),'products':len(catalog['products'])}

def connected(db,bid):
    link=db.get(ConnectLink,bid)
    if not link: fail('Este local no tiene un sitio autorizado en SL Connect.',404)
    return link

@router.get('/business/{bid}/connect/customers')
def connect_customers(q:str='',offset:int=0,limit:int=25,b=Depends(tenant),db=Depends(get_db)):
    from urllib.parse import urlencode
    if len(q)>160 or offset<0 or not 1<=limit<=100: fail('Consulta de clientes inválida.')
    link=connected(db,b.id)
    return connect_request(link.provider,'/customers?'+urlencode({'q':q,'offset':offset,'limit':limit}))

@router.post('/business/{bid}/connect/customers/{code}/points')
def connect_points(code:str,p:PointsAdjustment,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    from urllib.parse import quote
    if p.delta==0: fail('Indicá una cantidad de puntos distinta de cero.')
    if len(code)>100: fail('Código de cliente inválido.')
    link=connected(db,b.id)
    result=connect_request(link.provider,'/customers/'+quote(code,safe='')+'/points','POST',{
        **p.model_dump(mode='json'),'actor':f'POS local {b.id} · {a.name} (#{a.id})'})
    # The remote ledger owns the idempotency key and the authoritative balance.
    if not db.scalar(select(Audit.id).where(Audit.business_id==b.id,Audit.action=='connect_points',Audit.detail['request_key'].as_string()==str(p.request_key))):
        db.add(Audit(business_id=b.id,actor_id=a.id,action='connect_points',detail={'request_key':str(p.request_key),'customer_code':code,'delta':p.delta,'reason':p.reason})); commit(db)
    return result

@router.get('/business/{bid}/connect/summary')
def connect_summary(start:date,end:date,b=Depends(tenant),db=Depends(get_db)):
    from urllib.parse import urlencode
    if end<start or (end-start).days>366: fail('Seleccioná un rango de hasta 366 días.')
    link=connected(db,b.id)
    result=connect_request(link.provider,'/summary?'+urlencode({'start':start.isoformat(),'end':end.isoformat()}))
    lo=datetime.combine(start,time.min,TZ).astimezone(timezone.utc); hi=datetime.combine(end+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
    direct=db.scalars(select(Order).where(Order.business_id==b.id,Order.source_channel=='whatsapp',Order.created_at>=lo,Order.created_at<hi)).all()
    result['direct_whatsapp']={'orders':len(direct),'paid':sum(o.status=='paid' for o in direct),'paid_total':sum((o.total for o in direct if o.status=='paid'),Decimal(0))}
    recent_ids=[order['id'] for order in result.get('recent_orders',[])]
    result['imported_ids']=list(db.scalars(select(Order.external_id).where(Order.business_id==b.id,Order.external_id.in_(recent_ids))))
    direct_daily={}
    for order in direct:
        stamp=order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)
        day=stamp.astimezone(TZ).date().isoformat();direct_daily[day]=direct_daily.get(day,0)+1
    for day in result.get('daily',[]): day['whatsapp']=direct_daily.get(day['date'],0)
    return result

@router.post('/business/{bid}/connect/orders/{ident}/import')
def import_connect_order(ident:str,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    from uuid import UUID
    try: ident=str(UUID(ident))
    except ValueError: fail('Identificador de pedido inválido.')
    link=connected(db,b.id)
    prior=db.scalar(select(Order).where(Order.business_id==b.id,Order.external_id==ident))
    if prior: return row(prior)
    remote=connect_request(link.provider,'/orders/'+ident)
    if remote['status']=='cancelled': fail('El pedido del sitio está cancelado.',409)
    if remote.get('source_channel') not in ('website','legacy'): fail('Origen externo no compatible.')
    active_register(db,b.id)
    items=[]
    for item in remote['items']:
        product=db.scalar(select(Product).where(Product.business_id==b.id,Product.name==item['name'],Product.sku.like('SHR-%')))
        if not product: fail('Falta un producto del catálogo: '+item['name'])
        items.append(ItemIn(product_id=product.id,quantity=item['quantity'],unit_price=item['price']))
    payload=OrderIn(label='Sitio web · '+ident[:8],items=items,source_channel='website',fulfillment=remote['order_type'],
                    notes=' · '.join(str(value) for value in (remote.get('customer_name'),remote.get('customer_phone'),remote.get('location_text')) if value)[:2000],adjustment_reason='Precio del pedido recibido en el sitio web')
    order=Order(business_id=b.id,account_id=a.id,request_key=str(uuid4()),request_digest=hashlib.sha256(ident.encode()).hexdigest(),external_id=ident,items=[])
    db.add(order); db.flush(); populate(db,order,payload,b,a)
    # Never silently charge a different amount if the site/catalog were changed separately.
    if order.total!=money(remote['total']): fail('El total del sitio no coincide con el catálogo actual. Revisá precios, empaques e impuestos antes de importar.',409)
    commit(db); return row(order)
