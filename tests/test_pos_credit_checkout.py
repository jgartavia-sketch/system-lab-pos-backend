"""Credit is a checkout choice; payments, cash and remote recovery stay consistent."""
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from test_pos import env, good, req, setup_sale, order
from app.pos.models import CreditPayment, Receivable, Movement, ConnectLink, Product, Order
from app.pos import routes, zenit_bridge as bridge


def checkout(env, initial=0, method='cash', **overrides):
    product=setup_sale(env,price=1500,tax=0)
    sale=order(env,product)
    customer=good(req(env,'/customers','post',{'name':'Cliente de prueba'}))
    payload={'request_key':str(uuid4()),'expected_revision':sale['revision'],
             'customer_id':customer['id'],'due_date':None,
             'initial_payment':{'amount':initial,'method':method,'reference':'PRUEBA'},**overrides}
    return product,sale,customer,payload


def ledger(env):
    return good(req(env,'/receivables'))['accounts']


def test_full_credit_at_checkout_no_installments_no_money_received(env):
    _,sale,customer,payload=checkout(env)
    path=f"/orders/{sale['id']}/credit"
    credit=good(req(env,path,'post',payload))
    assert Decimal(credit['original'])==3000 and Decimal(credit['balance'])==3000
    assert credit['customer_id']==customer['id'] and credit['installments'][0]['due'] is None
    assert credit['payments']==[] and credit['status']=='pending'
    assert 'checkout_digest' not in credit
    state=good(req(env,'/state'))
    assert Decimal(state['register']['expected'])==1000
    assert Decimal(state['products'][0]['stock'])==18
    assert state['orders'][0]['payment_method']=='credit'
    assert Decimal(state['orders'][0]['credit']['balance'])==3000
    assert good(req(env,path,'post',payload))['id']==credit['id']
    good(req(env,'/register/close','post',{'amount':1000}))


@pytest.mark.parametrize('method',['cash','card','sinpe','transfer'])
def test_initial_payment_atomic_idempotent_and_reported_as_collection(env,method):
    _,sale,_,payload=checkout(env,initial='1000.25',method=method)
    path=f"/orders/{sale['id']}/credit"
    credit=good(req(env,path,'post',payload))
    assert credit['status']=='partial' and Decimal(credit['paid'])==Decimal('1000.25')
    assert Decimal(credit['balance'])==Decimal('1999.75') and len(credit['payments'])==1
    assert good(req(env,path,'post',payload))['id']==credit['id']
    changed={**payload,'initial_payment':{**payload['initial_payment'],'amount':1100}}
    assert req(env,path,'post',changed).status_code==409
    with env[2]() as db:
        assert db.scalar(select(func.count(CreditPayment.id)))==1
        assert db.scalar(select(func.count(Receivable.id)))==1
    state=good(req(env,'/state'))
    assert Decimal(state['register']['expected'])==(Decimal('2000.25') if method=='cash' else Decimal(1000))
    assert Decimal(state['orders'][0]['credit']['paid'])==Decimal('1000.25')
    day=datetime.now(routes.TZ).date().isoformat()
    report=good(req(env,f'/reports?start={day}&end={day}'))
    assert Decimal(report['sales'])==3000 and Decimal(report['credit_sales'])==3000
    assert Decimal(report['credit_collections'])==Decimal('1000.25')
    assert Decimal(report['money_in'])==Decimal('1000.25')
    assert Decimal(report['collections_by_method'][method])==Decimal('1000.25')
    assert Decimal(report['operating_expenses'])==0


@pytest.mark.parametrize('amount',[-1,3000,3001,'0.001'])
def test_invalid_initial_payment_never_sells_or_changes_stock(env,amount):
    _,sale,_,payload=checkout(env,initial=amount)
    assert req(env,f"/orders/{sale['id']}/credit",'post',payload).status_code in (400,422)
    state=good(req(env,'/state'))
    assert state['orders'][0]['status']=='open'
    assert Decimal(state['products'][0]['stock'])==20
    assert ledger(env)==[]


def test_customer_revision_date_drawer_and_request_key_are_validated(env):
    product,sale,_,payload=checkout(env,initial=500)
    path=f"/orders/{sale['id']}/credit"
    assert req(env,path,'post',{**payload,'customer_id':None}).status_code==409
    foreign=good(req(env,'/customers','post',{'name':'Otro local'},who=2))
    assert req(env,path,'post',{**payload,'customer_id':foreign['id']}).status_code==404
    assert req(env,path,'post',{**payload,'expected_revision':999}).status_code==409
    yesterday=(datetime.now(routes.TZ).date()-timedelta(days=1)).isoformat()
    assert req(env,path,'post',{**payload,'due_date':yesterday}).status_code==400
    good(req(env,path,'post',payload))
    second=order(env,product)
    assert req(env,f"/orders/{second['id']}/credit",'post',{**payload,'expected_revision':second['revision']}).status_code==409
    with env[2].begin() as db:db.get(Order,second['id']).status='cancelled'
    good(req(env,'/register/close','post',{'amount':1500}))
    # A saved open sale can exist before opening the next drawer.
    with env[2].begin() as db:
        obj=db.get(Order,second['id']);obj.status='open'
    assert req(env,f"/orders/{second['id']}/credit",'post',{**payload,'request_key':str(uuid4()),'expected_revision':second['revision']}).status_code==400


def test_later_payments_settle_and_void_without_duplicate_sales(env):
    _,sale,_,payload=checkout(env,initial=1000,method='sinpe')
    credit=good(req(env,f"/orders/{sale['id']}/credit",'post',payload))
    path=f"/receivables/{credit['id']}/payments"
    payment_payload={'request_key':str(uuid4()),'amount':2000,'method':'cash'}
    paid=good(req(env,path,'post',payment_payload))
    assert good(req(env,path,'post',payment_payload))['id']==paid['id']
    assert ledger(env)[0]['status']=='paid'
    assert Decimal(good(req(env,'/state'))['register']['expected'])==3000
    assert req(env,path,'post',{**payment_payload,'request_key':str(uuid4()),'amount':1}).status_code==409
    good(req(env,path+f"/{paid['id']}/void",'post',{'reason':'Corrección de abono'}))
    assert Decimal(ledger(env)[0]['balance'])==2000
    assert Decimal(good(req(env,'/state'))['register']['expected'])==1000
    initial=ledger(env)[0]['payments'][0]
    good(req(env,path+f"/{initial['id']}/void",'post',{'reason':'Corrección del abono inicial'}))
    good(req(env,f"/receivables/{credit['id']}/void",'post',{'reason':'Venta cancelada'}))
    assert ledger(env)[0]['status']=='voided'
    assert Decimal(good(req(env,'/state'))['products'][0]['stock'])==20


def test_zenit_initial_payment_remote_timeout_recovery_and_final_settlement(env,monkeypatch):
    product,sale,customer,payload=checkout(env,initial=1000,method='sinpe')
    with env[2].begin() as db:
        db.add(ConnectLink(business_id=1,provider='zenit'))
        obj=db.get(Product,product['id']);obj.remote_id=str(uuid4());obj.remote_kind='product'
    calls=[];applied={}
    def remote(provider,path,method='GET',body=None):
        calls.append((path,body['operationKey']))
        result=applied.setdefault(body['operationKey'],{'provider':'zenit','invoiceNumber':body.get('invoiceNumber','POS-TEST')})
        if len(calls)==1:raise HTTPException(502,'Respuesta perdida')
        return result
    monkeypatch.setattr(bridge,'connect_request',remote)
    path=f"/orders/{sale['id']}/credit"
    assert req(env,path,'post',payload).status_code==502
    assert ledger(env)==[]
    pending=good(req(env,'/state'))['bridge_pending'][0]
    credit=good(req(env,f"/connect/zenit/retry/{pending['id']}",'post',{}))
    assert len(credit['payments'])==1 and Decimal(credit['balance'])==2000
    assert len(set(key for _,key in calls))==1
    assert not good(req(env,'/state'))['bridge_pending']
    good(req(env,path,'post',payload))
    assert len(calls)==2
    final={'request_key':str(uuid4()),'amount':2000,'method':'card'}
    good(req(env,f"/receivables/{credit['id']}/payments",'post',final))
    assert calls[-1][0]=='/sales/settle'
    assert ledger(env)[0]['status']=='paid'
    assert len(ledger(env)[0]['payments'])==2


def test_credit_validation_rejects_full_initial_payment_before_remote_call(env,monkeypatch):
    product,sale,_,payload=checkout(env,initial=3000)
    with env[2].begin() as db:db.add(ConnectLink(business_id=1,provider='zenit'))
    calls=[]
    monkeypatch.setattr(bridge,'connect_request',lambda *args:calls.append(args))
    assert req(env,f"/orders/{sale['id']}/credit",'post',payload).status_code==400
    assert calls==[] and ledger(env)==[]
