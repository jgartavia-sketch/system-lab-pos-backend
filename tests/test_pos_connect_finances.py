from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import json

import pytest
from sqlalchemy import func, select
from fastapi import HTTPException
from test_pos import env, good, req, order, setup_sale
from test_pos_roles import staff, call
from app.pos import routes
from app.pos.models import Account, Audit, Business, ConnectLink, FinancialEntry, Movement, Order, Product


def entry(**values):
    return {'request_key':str(uuid4()),'kind':'expense','amount':100,'category':'Servicios','method':'sinpe','reason':'Pago electricidad','occurred_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),**values}


def report_today(env):
    day=datetime.now(routes.TZ).date().isoformat()
    return good(req(env,f'/reports?start={day}&end={day}'))


def test_finances_cash_once_and_void_preserves_history(env):
    setup_sale(env)
    body=entry(method='cash',from_register=True)
    saved=good(req(env,'/finances','post',body))
    assert good(req(env,'/finances','post',body))['id']==saved['id']
    assert req(env,'/finances','post',{**body,'amount':101}).status_code==409
    assert float(good(req(env,'/state'))['register']['expected'])==900
    report=report_today(env)
    assert float(report['outflows'])==float(report['operating_expenses'])==100
    assert float(report['profit'])==-100
    voided=good(req(env,f"/finances/{saved['id']}/void",'post',{'reason':'Registro duplicado'}))
    assert voided['voided_at'] and voided['void_movement_id']
    good(req(env,f"/finances/{saved['id']}/void",'post',{'reason':'Registro duplicado'}))
    assert float(good(req(env,'/state'))['register']['expected'])==1000
    assert float(report_today(env)['outflows'])==0
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(FinancialEntry))==1
        assert db.scalar(select(func.count()).select_from(Movement).where(Movement.kind=='expense'))==2
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='financial_void'))==1


def test_inventory_spending_does_not_double_subtract_cost(env):
    product=setup_sale(env,price=100,tax=0)
    saved=order(env,product)
    good(req(env,f"/orders/{saved['id']}/pay",'post',{'method':'card'}))
    for kind,amount in [('purchase',500),('expense',20),('other_income',40),('capital_in',1000),('withdrawal',100)]:
        good(req(env,'/finances','post',entry(kind=kind,amount=amount)))
    report=report_today(env)
    assert float(report['income'])==240
    assert float(report['outflows'])==80  # 2 sold units at cost 30 + expense 20
    assert float(report['profit'])==160
    assert float(report['money_in'])==1240
    assert float(report['money_out'])==620
    assert float(report['cash_flow'])==620
    assert float(report['inventory_purchases'])==500
    assert float(good(req(env,'/state'))['register']['expected'])==1000


def test_finances_work_without_cash_register_and_validate_date(env):
    good(req(env,'/finances','post',entry(method='transfer')))
    assert req(env,'/finances','post',entry(method='cash',from_register=True)).status_code==400
    assert req(env,'/finances','post',entry(occurred_at='2026-09-01T12:00:00')).status_code==400
    assert req(env,'/finances','post',entry(occurred_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())).status_code==400
    assert req(env,'/finances','post',entry(amount=-1)).status_code==422


def test_cannot_void_closed_drawer_or_overdraw(env):
    setup_sale(env)
    assert req(env,'/finances','post',entry(method='cash',from_register=True,amount=1001)).status_code==400
    saved=good(req(env,'/finances','post',entry(method='cash',from_register=True)))
    good(req(env,'/register/close','post',{'amount':900}))
    assert req(env,f"/finances/{saved['id']}/void",'post',{'reason':'Corrección posterior'}).status_code==409
    assert float(report_today(env)['operating_expenses'])==100


def test_finance_period_uses_costa_rica_midnight(env):
    for stamp in ['2026-09-01T05:59:59Z','2026-09-01T06:00:00Z']:
        good(req(env,'/finances','post',entry(occurred_at=stamp)))
    report=good(req(env,'/reports?start=2026-08-31&end=2026-09-01'))
    assert [float(day['operating_expenses']) for day in report['daily']]==[100,100]
    history=good(req(env,'/finances?start=2026-09-01&end=2026-09-01'))
    assert len(history['entries'])==1
    assert req(env,'/finances?start=2026-09-02&end=2026-09-01').status_code==400


def test_tenant_and_employee_cannot_access_finances_or_connected_customers(env,monkeypatch):
    def unexpected(*args,**kwargs): raise AssertionError('Remote API must not run for unauthorized tenants')
    monkeypatch.setattr(routes,'connect_request',unexpected)
    _,waiter=staff(env)
    for path in ['/finances?start=2026-09-01&end=2026-09-02','/connect/customers']:
        assert call(env,waiter,path,method='get').status_code==403
        assert req(env,path,who=2,bid=1).status_code==403
    assert call(env,waiter,'/finances',entry()).status_code==403
    assert req(env,'/connect/customers').status_code==404
    assert req(env,'/connect/customers',who=2).status_code==404


def setup_catalog(env):
    body={'name':'Shirleys owner','email':'catalog-owner@example.com','password':'test-only-password','tables':10}
    result=good(env[0].post('/pos-api/admin/shirleys',headers=env[1](),json=body))
    token=good(env[0].post('/pos-api/auth/login',json={'email':body['email'],'password':body['password']}))['token']
    return result,body,{'Authorization':'Bearer '+token}


def test_catalog_onboarding_exact_and_repeat_does_not_reset(env):
    result,body,h=setup_catalog(env)
    assert result['created'] and result['products']==68
    bid=result['business']['id']
    assert not result['account']['ceo'] and 'password_hash' not in result['account']
    assert float(result['business']['service_rate'])==10
    catalog=json.loads((Path(__file__).parents[1]/'app/pos/catalogs/shirleys.json').read_text())['products']
    state=good(call(env,h,'/state',method='get',bid=bid))
    assert {(p['name'],p['category'],float(p['price']),float(p['packaging_fee'])) for p in state['products']}=={(p['name'],p['category'],p['price'],p['packaging_fee']) for p in catalog}
    assert len({p['category'] for p in state['products']})==8
    assert all(not p['track_stock'] and not p['cost_known'] and float(p['tax_rate'])==0 for p in state['products'])
    assert state['connect']['provider']=='shirleys'
    repeated=good(env[0].post('/pos-api/admin/shirleys',headers=env[1](),json={**body,'password':'different-password'}))
    assert not repeated['created'] and repeated['business']['id']==bid
    assert env[0].post('/pos-api/auth/login',json={'email':body['email'],'password':body['password']}).status_code==200
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Product).where(Product.business_id==bid))==68
        assert db.scalar(select(func.count()).select_from(ConnectLink))==1


def test_onboarding_ceo_only_and_existing_account_untouched(env):
    body={'name':'Existing','email':'user2@example.com','password':'different-password'}
    assert env[0].post('/pos-api/admin/shirleys',headers=env[1](2),json=body).status_code==403
    assert env[0].post('/pos-api/admin/shirleys',headers=env[1](),json=body).status_code==409
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Business))==2
        assert db.scalar(select(func.count()).select_from(ConnectLink))==0


def test_packaging_and_service_by_fulfillment_and_profit(env):
    result,_,h=setup_catalog(env);bid=result['business']['id']
    good(call(env,h,'/register/open',{'amount':0},bid=bid))
    products=good(call(env,h,'/state',method='get',bid=bid))['products']
    pizza=next(p for p in products if p['name']=='Pizza Birria (8 slices)')
    for delivery in ['pickup','express','dine_in']:
        saved=good(call(env,h,'/orders',{'items':[{'product_id':pizza['id'],'quantity':2}],'fulfillment':delivery,'source_channel':'whatsapp'},bid=bid))
        assert float(saved['packaging_total'])==(800 if delivery!='dine_in' else 0)
        assert float(saved['service_total'])==(0 if delivery!='dine_in' else float(pizza['price'])*.2)
        assert float(saved['total'])==2*float(pizza['price'])+float(saved['packaging_total'])+float(saved['service_total'])
        good(call(env,h,f"/orders/{saved['id']}/pay",{'method':'card'},bid=bid))
    day=datetime.now(routes.TZ).date().isoformat()
    report=good(call(env,h,f'/reports?start={day}&end={day}',method='get',bid=bid))
    assert report['missing_cost_lines']==3
    assert float(report['income'])==float(report['sales'])-float(report['service_total'])
    assert next(c for c in report['channels'] if c['channel']=='whatsapp')['orders']==3
    assert call(env,h,'/orders',{'items':[{'product_id':pizza['id'],'quantity':1}],'source_channel':'website'},bid=bid).status_code==400
    assert call(env,h,'/orders',{'items':[{'product_id':pizza['id'],'quantity':1}],'fulfillment':'express','table_number':1},bid=bid).status_code==400


def test_import_remote_order_once_and_mismatch_rolls_back(env,monkeypatch):
    result,_,h=setup_catalog(env);bid=result['business']['id']
    good(call(env,h,'/register/open',{'amount':0},bid=bid))
    remote_id=str(uuid4())
    products=good(call(env,h,'/state',method='get',bid=bid))['products']
    pizza=next(p for p in products if p['name']=='Pizza Birria (8 slices)')
    remote={'id':remote_id,'source_channel':'website','status':'pending_confirmation','order_type':'express','customer_name':'Cliente web','customer_phone':'88888888','location_text':'Dirección de prueba','items':[{'name':pizza['name'],'quantity':1,'price':float(pizza['price'])}],'total':float(pizza['price'])+400}
    calls=[]
    def bridge(provider,path,*args):
        calls.append((provider,path));return remote.copy()
    monkeypatch.setattr(routes,'connect_request',bridge)
    path=f'/connect/orders/{remote_id}/import'
    saved=good(call(env,h,path,{},bid=bid))
    assert saved['status']=='open' and saved['source_channel']=='website' and saved['external_id']==remote_id
    assert 'Cliente web' in saved['notes']
    assert good(call(env,h,path,{},bid=bid))['id']==saved['id'] and len(calls)==1
    assert float(saved['total'])==remote['total']
    remote['total']+=1
    assert call(env,h,f'/connect/orders/{uuid4()}/import',{},bid=bid).status_code==409
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Order).where(Order.business_id==bid))==1


def test_remote_point_retry_audits_once_and_actor_cannot_be_forged(env,monkeypatch):
    with env[2].begin() as db: db.add(ConnectLink(business_id=1,provider='shirleys'))
    calls=[]
    def bridge(provider,path,method='GET',body=None):
        calls.append((provider,path,method,body));return {'points':20}
    monkeypatch.setattr(routes,'connect_request',bridge)
    data={'request_key':str(uuid4()),'delta':5,'reason':'Recompensa autorizada'}
    good(req(env,'/connect/customers/ABC/points','post',data))
    good(req(env,'/connect/customers/ABC/points','post',data))
    assert calls[0][3]['actor']=='POS local 1 · User 1 (#1)'
    assert req(env,'/connect/customers/ABC/points','post',{**data,'actor':'forged'}).status_code==422
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='connect_points'))==1
    good(req(env,'/connect/customers?q=Mar%C3%ADa%20%26&limit=25'))
    assert 'q=Mar%C3%ADa+%26' in calls[-1][1]


def test_connect_fails_closed_without_server_key(monkeypatch):
    from app.pos.connect_client import connect_request
    monkeypatch.delenv('SHIRLEYS_CONNECT_KEY',raising=False)
    with pytest.raises(HTTPException) as error: connect_request('shirleys','/customers')
    assert error.value.status_code==503


def test_origin_summary_counts_direct_chat_once_and_limits_imported_ids(env,monkeypatch):
    product=setup_sale(env)
    direct=order(env,product,source_channel='whatsapp')
    good(req(env,f"/orders/{direct['id']}/pay",'post',{'method':'card'}))
    remote_id=str(uuid4())
    imported=order(env,product)
    with env[2].begin() as db:
        db.add(ConnectLink(business_id=1,provider='shirleys'))
        saved=db.get(Order,imported['id']);saved.source_channel='website';saved.external_id=remote_id
    day=datetime.now(routes.TZ).date().isoformat()
    monkeypatch.setattr(routes,'connect_request',lambda *args: {'orders':{'website':1},'recent_orders':[{'id':remote_id}],'daily':[{'date':day,'website':1,'legacy':0}]})
    result=good(req(env,f'/connect/summary?start={day}&end={day}'))
    assert result['direct_whatsapp']['orders']==1 and result['direct_whatsapp']['paid']==1
    assert result['orders']['website']==1
    assert result['imported_ids']==[remote_id]
    assert result['daily'][0]['whatsapp']==1
