"""Durable transaction intent + idempotent remote operation. No fire-and-forget sync."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from .models import Business,Product,Customer,ConnectLink,BridgeOperation
from .connect_client import connect_request

def is_zenit(db,bid):
    link=db.get(ConnectLink,bid)
    return bool(link and link.provider=='zenit')
def actor(a,b): return f'POS:{b.id}:{a.id}'
def sale_key(bid,oid): return f'POS:{bid}:{oid}'
def pending(db,bid):
    return db.scalar(select(BridgeOperation).where(BridgeOperation.business_id==bid,BridgeOperation.state=='pending').order_by(BridgeOperation.id))
def execute(db,b,a,local_path,local_body,remote_path,remote_body,order=None,register=None):
    request_key=local_body.get('request_key') or local_body.get('requestKey')
    if request_key:
        previous=db.scalar(select(BridgeOperation).where(BridgeOperation.business_id==b.id,BridgeOperation.state=='done',
            (BridgeOperation.local_body['request_key'].as_string()==request_key)|(BridgeOperation.local_body['requestKey'].as_string()==request_key)))
        if previous:
            if previous.local_path!=local_path or previous.local_body!=local_body: raise HTTPException(409,'Clave de operación reutilizada con otros datos.')
            return previous.result,True
    op=pending(db,b.id)
    if op and (op.local_path!=local_path or op.local_body!=local_body):
        raise HTTPException(409,'Hay una operación pendiente. Reintentala desde Resumen antes de continuar.')
    if not op:
        key=str(uuid4())
        op=BridgeOperation(business_id=b.id,actor_id=a.id,order_id=order.id if order else None,register_id=register.id if register else None,
            key=key,local_path=local_path,local_body=local_body,remote_path=remote_path,remote_body={**remote_body,'operationKey':key},state='pending')
        db.add(op);db.commit() # Intent survives lost responses and a failed local final commit.
        db.scalar(select(Business).where(Business.id==b.id).with_for_update())
        db.refresh(op)
        if op.state=='done': return op.result,True
    try:
        result=connect_request('zenit',op.remote_path,'POST',op.remote_body)
    except HTTPException as error:
        # 4xx here proves remote transaction rejected; 5xx/timeouts remain pending.
        if error.status_code in (400,404,409,422):
            op.state='rejected';op.result={'detail':str(error.detail)};db.commit()
        raise
    if not isinstance(result,dict) or result.get('provider')!='zenit':
        raise HTTPException(502,'Respuesta privada inválida. Reintentá la operación pendiente.')
    op.state='done';op.result=result
    return result,False

def sale_payload(db,b,a,obj,credit=False,invoice_number=''):
    customer=db.get(Customer,obj.customer_id) if obj.customer_id else None
    if customer and customer.business_id!=b.id: raise HTTPException(404,'Cliente de otro negocio.')
    items=[]
    for i in obj.items:
        product=db.get(Product,i['product_id'])
        if not product or product.business_id!=b.id or not product.remote_id:
            raise HTTPException(409,'Actualizá el catálogo Zénit: este artículo no tiene correspondencia en el sitio.')
        items.append({'id':product.remote_id,'kind':product.remote_kind,'quantity':str(i['quantity']),'unitPriceCents':int(Decimal(str(i['price']))*100)})
    invoice=(invoice_number or obj.invoice_number or (f'ZENIT-{obj.external_id}' if obj.external_id else f'POS-{b.id}-{obj.id}')).strip().upper()
    return {'saleKey':sale_key(b.id,obj.id),'actor':actor(a,b),'shopOrderId':obj.external_id,
            'customerId':customer.remote_id if customer else None,'invoiceNumber':invoice,'totalCents':int(obj.total*100),'credit':credit,'items':items}

def sync(db,bid):
    catalog=connect_request('zenit','/catalog')
    seen=set()
    for kind,rows in [('product',catalog['products']),('service',catalog['services'])]:
        for remote in rows:
            rid=remote['id'];seen.add((kind,rid))
            obj=db.scalar(select(Product).where(Product.business_id==bid,Product.remote_kind==kind,Product.remote_id==rid))
            if not obj:
                obj=Product(business_id=bid,remote_kind=kind,remote_id=rid,sku=f'ZENIT-{kind[0]}-{rid}',cost=0,cost_known=False,tax_rate=0,packaging_fee=0,print_station='none',minimum=0)
                db.add(obj)
            obj.name=remote['name'];obj.category=remote.get('category',{}).get('name') or ('Productos' if kind=='product' else 'Servicios')
            obj.price=Decimal(remote['price'] or 0)
            obj.active=bool(remote['active'] and remote.get('category',{}).get('active',True) and (remote.get('available',True) if kind=='product' else True))
            obj.track_stock=kind=='product' and remote.get('stock') is not None
            obj.stock=Decimal(remote.get('stock') or 0);obj.duration_minutes=remote.get('durationMinutes')
    for obj in db.scalars(select(Product).where(Product.business_id==bid,Product.remote_id.is_not(None))):
        if (obj.remote_kind,obj.remote_id) not in seen:obj.active=False
    offset=0
    while offset is not None:
        data=connect_request('zenit',f'/customers?offset={offset}&limit=200')
        for remote in data['customers']:
            obj=db.scalar(select(Customer).where(Customer.business_id==bid,Customer.remote_id==remote['id']))
            if not obj:
                candidates=list(db.scalars(select(Customer).where(Customer.business_id==bid,Customer.email==remote['email'])))
                if len(candidates)>1: raise HTTPException(409,'Clientes locales duplicados con el mismo correo; resolver antes de sincronizar.')
                obj=candidates[0] if candidates else Customer(business_id=bid)
                db.add(obj);obj.remote_id=remote['id']
            obj.name=remote['name'];obj.phone=remote['phone'];obj.email=remote['email']
        offset=data.get('nextOffset')
        if offset is not None and offset>100000:raise HTTPException(502,'El catálogo de clientes excede el límite de sincronización.')
    db.get(ConnectLink,bid).synced_at=datetime.now(timezone.utc)
