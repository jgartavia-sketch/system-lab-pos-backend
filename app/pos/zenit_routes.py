from datetime import date as Date
from decimal import Decimal
from uuid import UUID,uuid4
from pydantic import Field
from .routes import router,Strict,Depends,tenant,current,get_db,select,fail,find,commit,row,Order,Product,Customer,Account,OPEN
from . import zenit_bridge as zb
from .connect_client import connect_request

def require_zenit(db,b):
    if not zb.is_zenit(db,b.id):fail('Esta conexión no corresponde al negocio.',404)

@router.post('/business/{bid}/connect/zenit/sync')
def sync_zenit(b=Depends(tenant),db=Depends(get_db)):
    require_zenit(db,b);zb.sync(db,b.id);commit(db)
    return {'synced':True}

@router.get('/business/{bid}/connect/zenit/orders')
def orders_zenit(offset:int=0,b=Depends(tenant),db=Depends(get_db)):
    require_zenit(db,b)
    if offset<0 or offset>1000000:fail('Página inválida.')
    data=connect_request('zenit',f'/orders?offset={offset}')
    data['imported']={o.external_id:o.id for o in db.scalars(select(Order).where(Order.business_id==b.id,Order.external_id.is_not(None)))}
    return data

@router.post('/business/{bid}/connect/zenit/orders/{ident}/import')
def import_zenit(ident:UUID,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    require_zenit(db,b);ident=str(ident)
    existing=db.scalar(select(Order).where(Order.business_id==b.id,Order.external_id==ident))
    if existing:return row(existing)
    remote=connect_request('zenit','/orders/'+ident)['order']
    if remote['status']!='PENDING':fail('Solo se importan pedidos pendientes; los cerrados conservan su historial en Zénit.',409)
    zb.sync(db,b.id);db.flush()
    customer=db.scalar(select(Customer).where(Customer.business_id==b.id,Customer.remote_id==remote['customerId']))
    if not customer:fail('El cliente del pedido no está activo.',409)
    items=[]
    for i in remote['items']:
        product=db.scalar(select(Product).where(Product.business_id==b.id,Product.remote_id==i['productId'],Product.remote_kind=='product'))
        if not product:fail('El producto original no está disponible; revisar el pedido en Zénit.',409)
        items.append({'product_id':product.id,'name':i['name'],'quantity':str(i['quantity']),'price':str(i['price']),'cost':str(product.cost),'tax_rate':'0','subtotal':str(i['subtotal']),'track_stock':bool(i['tracked']),'cost_known':product.cost_known,'packaging_fee':'0','print_station':'none','discount':'0','tax':'0'})
    if sum(Decimal(i['subtotal']) for i in items)!=Decimal(remote['total']):fail('El total del pedido no coincide.',409)
    key=str(uuid4())
    obj=Order(business_id=b.id,account_id=a.id,customer_id=customer.id,request_key=key,request_digest=key,source_channel='website',fulfillment='pickup',external_id=ident,label='Tienda Zénit',notes='Pedido web '+ident,items=items,subtotal=remote['total'],discount=0,tax=0,total=remote['total'],packaging_total=0,service_total=0)
    db.add(obj);commit(db);return row(obj)

class ZenitAppointment(Strict):
    requestKey:UUID
    date:Date
    time:str=Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    durationMinutes:int=Field(ge=15,le=720)
    customerName:str=Field(min_length=2,max_length=100)
    phone:str=Field(default='',max_length=30)
    customerId:UUID|None=None
    serviceSlug:str|None=Field(default=None,max_length=100)
    notes:str=Field(default='',max_length=1000)
    blocked:bool=False
class ZenitAppointmentUpdate(Strict):
    responseMessage:str|None=Field(default=None,max_length=1000)
    proposedDate:Date|None=None
    proposedTime:str|None=Field(default=None,pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    requestKey:UUID
    status:str|None=Field(default=None,pattern='^(CONFIRMED|COMPLETED|CANCELLED)$')
    date:Date|None=None
    time:str|None=Field(default=None,pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    durationMinutes:int|None=Field(default=None,ge=15,le=720)

@router.post('/business/{bid}/connect/zenit/appointments')
def create_zenit_appointment(p:ZenitAppointment,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    require_zenit(db,b)
    body=p.model_dump(mode='json',exclude_none=True)
    result,replay=zb.execute(db,b,a,'/connect/zenit/appointments',p.model_dump(mode='json'),'/appointments',{'actor':zb.actor(a,b),**body})
    commit(db);return result

@router.post('/business/{bid}/connect/zenit/appointments/{ident}')
def update_zenit_appointment(ident:UUID,p:ZenitAppointmentUpdate,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    require_zenit(db,b)
    body=p.model_dump(mode='json',exclude_none=True,exclude={'requestKey'})
    result,replay=zb.execute(db,b,a,f'/connect/zenit/appointments/{ident}',p.model_dump(mode='json'),'/appointments/update',{'actor':zb.actor(a,b),'id':str(ident),**body})
    commit(db);return result

@router.post('/business/{bid}/connect/zenit/retry/{ident}')
def retry_zenit(ident:int,b=Depends(tenant),a=Depends(current),db=Depends(get_db)):
    import re
    from . import routes as r
    from . import credit_routes as c
    require_zenit(db,b);op=find(db,zb.BridgeOperation,ident,b.id)
    if op.state!='pending':return {'finished':True}
    # Never accept a caller-provided target or payload for recovery.
    path=op.local_path;body=op.local_body
    match=re.fullmatch(r'/orders/(\d+)/(pay|credit|refund|status)',path)
    if match:
        oid=int(match[1]);action=match[2]
        if action=='pay':return r.pay(oid,r.PayIn(**body),b,a,db)
        if action=='status':return r.order_state(oid,r.StateIn(**body),b,a,db)
        if action=='credit':return c.sell_credit(oid,c.CreditIn(**body),b,a,db)
        return r.refund(oid,r.Reason(**body),b,a,db)
    match=re.fullmatch(r'/receivables/(\d+)/payments(?:/(\d+)/void)?',path)
    if match:
        if match[2]:return c.void_credit_payment(int(match[1]),int(match[2]),r.Reason(**body),b,a,db)
        return c.pay_credit(int(match[1]),c.CreditPayIn(**body),b,a,db)
    match=re.fullmatch(r'/receivables/(\d+)/void',path)
    if match:return c.void_credit(int(match[1]),r.Reason(**body),b,a,db)
    match=re.fullmatch(r'/products/(\d+)(/stock)?',path)
    if match:
        if match[2]:return r.stock(int(match[1]),r.StockIn(**body),b,a,db)
        return r.edit_product(int(match[1]),r.ProductIn(**body),b,a,db)
    if path=='/connect/zenit/appointments':return create_zenit_appointment(ZenitAppointment(**body),b,a,db)
    match=re.fullmatch(r'/connect/zenit/appointments/([a-f0-9-]{36})',path)
    if match:return update_zenit_appointment(UUID(match[1]),ZenitAppointmentUpdate(**body),b,a,db)
    fail('Operación pendiente no reconocida; no se cambió el historial.',409)
