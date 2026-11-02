from decimal import Decimal as D
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from test_pos import env, req, good, setup_sale, order
from test_pos_roles import staff, call
from app.pos.models import Business, Order, Product, Customer, BillSplit, ConnectLink, LoyaltyOperation
from app.pos import loyalty


def split_payload(source, quantities=None, **extra):
    quantities = quantities or [[1], [1]]
    return {'request_key': str(uuid4()), 'expected_revision': source['revision'],
            'accounts': [{'label': f'Cuenta {n+1}', 'items': [{'item_index': i, 'quantity': q} for i, q in enumerate(qs) if q]}
                         for n, qs in enumerate(quantities)], **extra}


def divide(env, source, payload=None):
    return good(req(env, f"/orders/{source['id']}/split", 'post', payload or split_payload(source)))


def test_table_keeps_other_bills_and_new_visit_gets_new_session(env):
    product = setup_sale(env)
    first = order(env, product, table_number=2)
    second = order(env, product, table_number=2, label='Otra persona')
    assert first['table_session'] == second['table_session']
    good(req(env, f"/orders/{first['id']}/pay", 'post', {'method': 'card'}))
    state = good(req(env, '/state'))
    assert [o['id'] for o in state['orders'] if o['status'] == 'open'] == [second['id']]
    good(req(env, f"/orders/{second['id']}/pay", 'post', {'method': 'sinpe'}))
    third = order(env, product, table_number=2)
    assert third['table_session'] != first['table_session']
    assert req(env, '/orders', 'post', {'table_number':2, 'table_session':first['table_session'], 'items':[{'product_id':product['id'],'quantity':1}]}).status_code == 409


@pytest.mark.parametrize('preparation', ['open', 'queued', 'preparing', 'ready', 'served'])
def test_split_during_preparation_preserves_one_kitchen_order_and_money(env, preparation):
    product = setup_sale(env, price='713.37', tax=13)
    with env[2].begin() as db:
        db.get(Business, 1).service_rate = 10
    source = order(env, product, table_number=1, discount='3.11', adjustment_reason='Promoción')
    if preparation != 'open':
        for status in ('queued', 'preparing', 'ready', 'served'):
            source = good(req(env, f"/orders/{source['id']}/status", 'post', {'status':status}))
            if status == preparation: break
    # Billing must retain the original sale, even after catalog prices/costs change.
    with env[2].begin() as db:
        db.get(Product, product['id']).price = 999
        db.get(Product, product['id']).cost = 100
    payload = split_payload(source, [[D('.667')], [D('.666')], [D('.667')]])
    # JSON-compatible exact decimal strings.
    for account in payload['accounts']:
        for item in account['items']: item['quantity'] = str(item['quantity'])
    preview = good(req(env, f"/orders/{source['id']}/split/preview", 'post', payload))
    assert all('cost' not in item for a in preview['accounts'] for item in a['items'])
    result = divide(env, source, payload)
    children = result['accounts']
    for field in ('subtotal', 'discount', 'tax', 'service_total', 'packaging_total', 'total'):
        assert sum(D(str(c[field])) for c in children) == D(str(source[field]))
    assert all(c['preparation_order_id'] == source['id'] and c['kitchen_status'] is None for c in children)
    assert len({c['table_session'] for c in children}) == 1
    assert req(env, f"/orders/{source['id']}/pay", 'post', {'method':'card'}).status_code == 409
    for i, child in enumerate(children):
        body = {'method':['cash', 'card', 'sinpe'][i], 'received':child['total'], 'expected_revision':child['revision']}
        good(req(env, f"/orders/{child['id']}/pay", 'post', body))
        good(req(env, f"/orders/{child['id']}/pay", 'post', body))
    state = good(req(env, '/state'))
    assert D(str(state['products'][0]['stock'])) == 18
    assert D(str(state['register']['expected'])) == 1000 + D(str(children[0]['total']))
    original = next(o for o in state['orders'] if o['id'] == source['id'])
    assert original['status'] == 'split' and original['kitchen_status'] == source['kitchen_status']
    from app.pos.routes import TZ
    from datetime import datetime
    day = datetime.now(TZ).date().isoformat()
    report = good(req(env, f'/reports?start={day}&end={day}'))
    assert D(str(report['sales'])) == D(str(source['total']))
    assert report['tickets'] == 3 and D(str(report['cost'])) == 60
    assert sum(c['orders'] for c in report['channels']) == 3


@pytest.mark.parametrize('discount', [0, '1.01', '2.02'])
def test_allocation_of_small_and_fully_discounted_shared_items(env, discount):
    product = setup_sale(env, price='1.01', tax=13)
    source = order(env, product, table_number=1, discount=discount, adjustment_reason='Promoción')
    children = divide(env, source, split_payload(source, [['.667'], ['.667'], ['.666']]))['accounts']
    assert sum(D(str(o['total'])) for o in children) == D(str(source['total']))
    assert all(D(str(o['discount'])) <= D(str(o['subtotal'])) for o in children)


def test_split_replay_conflict_stale_revision_and_immutable_children(env):
    product = setup_sale(env)
    source = order(env, product, table_number=1)
    payload = split_payload(source)
    first = divide(env, source, payload)
    repeated = divide(env, source, payload)
    assert repeated['replayed'] and [c['id'] for c in first['accounts']] == [c['id'] for c in repeated['accounts']]
    changed = {**payload, 'accounts': [{**payload['accounts'][0], 'label':'Otro'}, payload['accounts'][1]]}
    assert req(env, f"/orders/{source['id']}/split", 'post', changed).status_code == 409
    child = first['accounts'][0]
    assert req(env, f"/orders/{child['id']}", 'put', {'expected_revision':child['revision'], 'items':[{'product_id':product['id'],'quantity':1}]}).status_code == 409
    assert req(env, f"/orders/{child['id']}/status", 'post', {'status':'queued'}).status_code == 409
    # An unsent source may still be sent once after its financial split.
    original = good(req(env, f"/orders/{source['id']}/status", 'post', {'status':'queued'}))
    assert original['status'] == 'split' and original['kitchen_status'] == 'queued'
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(BillSplit)) == 1
    second_source = order(env, product, table_number=2)
    stale = split_payload(second_source)
    good(req(env, f"/orders/{second_source['id']}/status", 'post', {'status':'queued'}))
    assert req(env, f"/orders/{second_source['id']}/split", 'post', stale).status_code == 409


@pytest.mark.parametrize('quantities', [[[1],[D('.5')]], [[2],[1]], [[0],[2]]])
def test_incomplete_overallocated_or_empty_account_is_rejected(env, quantities):
    product=setup_sale(env);source=order(env, product, table_number=1)
    body=split_payload(source, [[str(q) for q in group] for group in quantities])
    response=req(env,f"/orders/{source['id']}/split",'post',body)
    assert response.status_code == 422
    assert good(req(env,'/state'))['orders'][0]['status'] == 'open'


def test_split_requires_a_table_scopes_clients_and_rolls_back_all_children(env):
    product=setup_sale(env);source=order(env, product)
    assert req(env,f"/orders/{source['id']}/split",'post',split_payload(source)).status_code==409
    source=order(env,product,table_number=1)
    foreign=good(req(env,'/customers','post',{'name':'Otro negocio'},who=2))
    body=split_payload(source);body['accounts'][1]['customer_id']=foreign['id']
    assert req(env,f"/orders/{source['id']}/split",'post',body).status_code==404
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 2
        assert db.get(Order, source['id']).status == 'open'
    _,kitchen=staff(env,role='kitchen')
    assert call(env,kitchen,f"/orders/{source['id']}/split",body).status_code==403


def connect(env, monkeypatch, fail_sales=False):
    with env[2].begin() as db: db.add(ConnectLink(business_id=1,provider='shirleys'))
    calls=[];remote_sales={};remote_voids=set()
    def remote(provider,path,method='GET',body=None):
        calls.append((provider,path,body))
        if path.startswith('/customers'):
            return {'customers':[{'code':'A01','name':'Ana del sitio','email':'ana@example.com','whatsapp':'88888888','points':20}], 'total':1}
        if fail_sales: raise HTTPException(502,'Conexión temporalmente no disponible')
        if path=='/sales':
            remote_sales.setdefault(body['sale_key'], body)
            return {'provider':'shirleys','sale_key':body['sale_key'],'points_earned':3,'points':23}
        if path=='/sales/void':
            assert body['sale_key'] in remote_sales
            remote_voids.add(body['sale_key'])
            return {'provider':'shirleys','sale_key':body['sale_key'],'points_earned':3,'points':20,'voided':True}
        raise AssertionError(path)
    monkeypatch.setattr(loyalty,'connect_request',remote)
    return calls,remote_sales,remote_voids,remote


def test_checkout_identifies_prepared_customer_and_delivers_purchase_once(env,monkeypatch):
    product=setup_sale(env,price=3000,tax=0);source=order(env,product,table_number=1)
    for status in ('queued','preparing'): source=good(req(env,f"/orders/{source['id']}/status",'post',{'status':status}))
    calls,sales,voids,_=connect(env,monkeypatch)
    body={'method':'sinpe','loyalty_code':'A01','customer_id':None,'expected_revision':source['revision']}
    paid=good(req(env,f"/orders/{source['id']}/pay",'post',body))
    assert paid['loyalty_status']=='credited' and paid['loyalty_points']==3 and paid['loyalty_name']=='Ana del sitio'
    assert paid['customer_id'] and len(sales)==1
    good(req(env,f"/orders/{source['id']}/pay",'post',body))
    assert len([c for c in calls if c[1]=='/sales'])==1
    assert req(env,f"/orders/{source['id']}/pay",'post',{**body,'loyalty_code':'WRONG'}).status_code==409
    refunded=good(req(env,f"/orders/{source['id']}/refund",'post',{'reason':'Consumo devuelto'}))
    assert refunded['loyalty_status']=='reversed' and len(voids)==1
    with env[2]() as db:
        customer=db.get(Customer,paid['customer_id'])
        assert customer.business_id==1 and customer.remote_id=='A01'
        assert db.scalar(select(func.count()).select_from(LoyaltyOperation))==2


def test_lost_loyalty_response_keeps_payment_and_retry_never_moves_stock_twice(env,monkeypatch):
    product=setup_sale(env,price=3000,tax=0);source=order(env,product,table_number=1)
    _,_,_,_=connect(env,monkeypatch,fail_sales=True)
    body={'method':'cash','received':6000,'loyalty_code':'A01','expected_revision':source['revision']}
    paid=good(req(env,f"/orders/{source['id']}/pay",'post',body))
    assert paid['status']=='paid' and paid['loyalty_status']=='pending'
    state=good(req(env,'/state'));assert D(str(state['products'][0]['stock']))==18
    assert D(str(state['register']['expected']))==7000
    monkeypatch.setattr(loyalty,'connect_request',lambda *args,**kwargs:[])
    malformed=good(req(env,f"/orders/{source['id']}/pay",'post',body))
    assert malformed['status']=='paid' and malformed['loyalty_status']=='pending'
    def restored(provider,path,method='GET',body=None):
        assert path=='/sales'
        return {'provider':'shirleys','sale_key':body['sale_key'],'points_earned':3,'points':23}
    monkeypatch.setattr(loyalty,'connect_request',restored)
    repeated=good(req(env,f"/orders/{source['id']}/pay",'post',body))
    assert repeated['loyalty_status']=='credited'
    state=good(req(env,'/state'));assert D(str(state['products'][0]['stock']))==18
    assert D(str(state['register']['expected']))==7000
    with env[2]() as db:
        job=db.scalar(select(LoyaltyOperation));assert job.attempts==3 and job.state=='done'


def test_refund_while_points_are_pending_preserves_both_intents(env,monkeypatch):
    product=setup_sale(env,price=3000,tax=0);source=order(env,product,table_number=1)
    connect(env,monkeypatch,fail_sales=True)
    good(req(env,f"/orders/{source['id']}/pay",'post',{'method':'card','loyalty_code':'A01'}))
    refunded=good(req(env,f"/orders/{source['id']}/refund",'post',{'reason':'Devolución total'}))
    assert refunded['status']=='refunded' and refunded['loyalty_status']=='void_pending'
    paths=[]
    def restored(provider,path,method='GET',body=None):
        paths.append(path)
        return {'provider':'shirleys','sale_key':body['sale_key'],'points_earned':3,'points':20,'voided':path.endswith('/void')}
    monkeypatch.setattr(loyalty,'connect_request',restored)
    synced=good(req(env,'/loyalty/retry','post',{'order_id':source['id']}))
    assert paths==['/sales','/sales/void'] and synced['loyalty_status']=='reversed'


def test_guest_no_points_and_minimal_staff_loyalty_permissions(env,monkeypatch):
    product=setup_sale(env);source=order(env,product,table_number=1)
    calls,_,_,_=connect(env,monkeypatch)
    good(req(env,f"/orders/{source['id']}/pay",'post',{'method':'card'}))
    assert calls==[]
    _,waiter=staff(env,pay=False)
    assert call(env,waiter,'/loyalty/customers?q=A01',method='get').status_code==200
    assert call(env,waiter,'/connect/customers/A01/points',{'delta':999,'reason':'No autorizado','request_key':str(uuid4())}).status_code==403
    assert call(env,waiter,'/loyalty/retry',{'order_id':source['id']}).status_code==403
    assert req(env,'/loyalty/customers?q=A01',who=2,bid=1).status_code==403


def test_stale_checkout_cannot_pay_the_old_amount(env):
    product=setup_sale(env);source=order(env,product,table_number=1)
    good(req(env,f"/orders/{source['id']}",'put',{'expected_revision':source['revision'],'table_number':1,'items':[{'product_id':product['id'],'quantity':3}]}))
    assert req(env,f"/orders/{source['id']}/pay",'post',{'method':'card','expected_revision':source['revision']}).status_code==409


def test_waiter_cannot_cancel_a_prepared_consumption_by_splitting_it(env):
    product=setup_sale(env)
    _,waiter=staff(env)
    source=good(call(env,waiter,'/orders',{'table_number':1,'send_to_kitchen':True,'items':[{'product_id':product['id'],'quantity':2}]}))
    good(req(env,f"/orders/{source['id']}/status",'post',{'status':'preparing'}))
    source=next(o for o in good(req(env,'/state'))['orders'] if o['id']==source['id'])
    child=good(call(env,waiter,f"/orders/{source['id']}/split",split_payload(source)))['accounts'][0]
    assert call(env,waiter,f"/orders/{child['id']}/status",{'status':'cancelled'}).status_code==403
