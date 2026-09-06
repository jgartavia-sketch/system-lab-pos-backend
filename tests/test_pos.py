import os
os.environ.setdefault('DATABASE_URL','sqlite://')
import secrets
import pytest
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base, get_db
from app.pos.routes import router
from app.pos.models import Account, Business, Membership, Product, SigningKey
from app.pos.security import hash_password

@pytest.fixture()
def env():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,autoflush=False)
    with Session.begin() as db:
        db.add(SigningKey(id=1,secret=secrets.token_urlsafe(64)))
        for i in (1,2):
            db.add(Account(id=i,email=f'user{i}@example.com',name=f'User {i}',password_hash=hash_password('test-password'),ceo=i==1,active=True,version=1))
            db.add(Business(id=i,name=f'Business {i}',mode='restaurante',active=True,tables=5))
            db.add(Membership(account_id=i,business_id=i))
    app=FastAPI();app.include_router(router)
    def database():
        with Session() as db: yield db
    app.dependency_overrides[get_db]=database
    client=TestClient(app)
    def headers(i=1):
        r=client.post('/pos-api/auth/login',json={'email':f'user{i}@example.com','password':'test-password'})
        assert r.status_code==200,r.text
        return {'Authorization':'Bearer '+r.json()['token']}
    return client,headers,Session

def req(env,path='',method='get',payload=None,who=1,bid=None):
    c,h,_=env
    return getattr(c,method)(f'/pos-api/business/{bid or who}'+path,headers=h(who),**({'json':payload} if payload is not None else {}))
def good(r):
    assert r.status_code==200,r.text
    return r.json()
def product(env,who=1,stock=20,price=100,tax=13):
    p=good(req(env,'/products','post',{'name':'Café','sku':'CAFE','price':price,'cost':30,'tax_rate':tax},who))
    good(req(env,f"/products/{p['id']}/stock",'post',{'kind':'entry','quantity':stock,'reason':'Carga inicial'},who))
    return p

def setup_sale(env,who=1,price=100,tax=13):
    p=product(env,who,price=price,tax=tax)
    good(req(env,'/register/open','post',{'amount':1000},who))
    return p

def order(env,p,who=1,**kwargs):
    return good(req(env,'/orders','post',{'items':[{'product_id':p['id'],'quantity':2}],**kwargs},who))

def test_no_session(env):
    assert env[0].get('/pos-api/business/1/state').status_code==401

def test_wrong_password(env):
    assert env[0].post('/pos-api/auth/login',json={'email':'user1@example.com','password':'wrong'}).status_code==401

def test_lockout(env):
    for _ in range(5): env[0].post('/pos-api/auth/login',json={'email':'user1@example.com','password':'wrong'})
    assert env[0].post('/pos-api/auth/login',json={'email':'user1@example.com','password':'test-password'}).status_code==429

def test_tenant_isolation_and_ceo_no_bypass(env):
    p=product(env,2)
    assert req(env,'/state',who=1,bid=2).status_code==403
    assert req(env,f"/products/{p['id']}/stock",'post',{'kind':'entry','quantity':1,'reason':'bad'}).status_code==404

def test_ceo_only_and_no_public_registration(env):
    assert env[0].get('/pos-api/admin',headers=env[1](2)).status_code==403
    assert env[0].post('/pos-api/auth/register',json={}).status_code==404

def test_cash_lifecycle_and_idempotency(env):
    p=setup_sale(env);o=order(env,p)
    assert float(o['total'])==226
    paid=good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'cash','received':500}))
    assert float(paid['change'])==274
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'cash','received':500}))
    s=good(req(env,'/state'));assert float(s['products'][0]['stock'])==18
    assert float(s['register']['expected'])==1226
    closed=good(req(env,'/register/close','post',{'amount':1226}));assert float(closed['difference'])==0

def test_non_cash_not_in_till(env):
    p=setup_sale(env);o=order(env,p)
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'sinpe'}))
    assert float(good(req(env,'/state'))['register']['expected'])==1000

def test_cash_movements_signs(env):
    setup_sale(env)
    good(req(env,'/cash','post',{'kind':'expense','amount':100,'reason':'Compra'}))
    good(req(env,'/cash','post',{'kind':'income','amount':50,'reason':'Fondo'}))
    assert float(good(req(env,'/state'))['register']['expected'])==950
    assert req(env,'/cash','post',{'kind':'expense','amount':10000,'reason':'Compra'}).status_code==400

def test_checkout_revalidates_stock(env):
    p=setup_sale(env);o=order(env,p)
    good(req(env,f"/products/{p['id']}/stock",'post',{'kind':'adjustment','quantity':0,'reason':'Conteo'}))
    assert req(env,f"/orders/{o['id']}/pay",'post',{'method':'card'}).status_code==400
    assert good(req(env,'/state'))['orders'][0]['status']=='open'

def test_invalid_foreign_customer(env):
    p=setup_sale(env)
    c=good(req(env,'/customers','post',{'name':'Other'},2))
    assert req(env,'/orders','post',{'customer_id':c['id'],'items':[{'product_id':p['id'],'quantity':1}]}).status_code==404

def test_kitchen_and_tables(env):
    p=setup_sale(env);o=order(env,p,table_number=1)
    assert req(env,'/orders','post',{'table_number':1,'items':[{'product_id':p['id'],'quantity':1}]}).status_code==409
    for status in ('queued','preparing','ready'):
        good(req(env,f"/orders/{o['id']}/status",'post',{'status':status}))
    assert req(env,f"/orders/{o['id']}",'put',{'items':[{'product_id':p['id'],'quantity':1}]}).status_code==400
    good(req(env,f"/orders/{o['id']}/status",'post',{'status':'cancelled'}))
    order(env,p,table_number=1)

def test_cannot_close_pending_or_double_open(env):
    p=setup_sale(env);order(env,p)
    assert req(env,'/register/open','post',{'amount':0}).status_code==409
    assert req(env,'/register/close','post',{'amount':1000}).status_code==400

def test_refund_once_same_register(env):
    p=setup_sale(env);o=order(env,p)
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'cash','received':226}))
    good(req(env,f"/orders/{o['id']}/refund",'post',{'reason':'Producto devuelto'}))
    assert req(env,f"/orders/{o['id']}/refund",'post',{'reason':'Producto devuelto'}).status_code==409
    s=good(req(env,'/state'));assert float(s['products'][0]['stock'])==20;assert float(s['register']['expected'])==1000

def test_refund_previous_register(env):
    p=setup_sale(env);o=order(env,p)
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'cash','received':226}))
    good(req(env,'/register/close','post',{'amount':1226}))
    good(req(env,'/register/open','post',{'amount':500}))
    good(req(env,f"/orders/{o['id']}/refund",'post',{'reason':'Producto devuelto'}))
    s=good(req(env,'/state'));assert float(s['register']['expected'])==274
    assert float(s['registers'][1]['expected'])==1226

def test_discount_and_report(env):
    p=setup_sale(env);o=order(env,p,discount=20)
    assert float(o['total'])==203.4
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'card'}))
    today=datetime.now(timezone.utc).date();r=good(req(env,f'/reports?start={today-timedelta(days=1)}&end={today}'))
    assert r['tickets']==1;assert float(r['sales'])==203.4;assert float(r['cost'])==60

def test_no_stock_for_service(env):
    p=good(req(env,'/products','post',{'name':'Corte','sku':'CORTE','price':5000,'track_stock':False}))
    good(req(env,'/register/open','post',{'amount':0}));o=order(env,p)
    good(req(env,f"/orders/{o['id']}/pay",'post',{'method':'card'}))
    assert float(good(req(env,'/state'))['products'][0]['stock'])==0

def test_password_revokes_token(env):
    c,h,_=env;old=h()
    r=good(c.post('/pos-api/auth/password',headers=old,json={'current':'test-password','password':'new-password'}))
    assert c.get('/pos-api/auth/me',headers=old).status_code==401
    assert c.get('/pos-api/auth/me',headers={'Authorization':'Bearer '+r['token']}).status_code==200

def test_ceo_create_and_suspend(env):
    c,h,_=env;admin=h()
    b=good(c.post('/pos-api/admin/businesses',headers=admin,json={'name':'Heladería','mode':'heladeria'}))
    u=good(c.post('/pos-api/admin/accounts',headers=admin,json={'name':'Nuevo','email':'new@example.com','password':'new-password','business_ids':[b['id']]}))
    token=good(c.post('/pos-api/auth/login',json={'email':'new@example.com','password':'new-password'}))['token']
    hdr={'Authorization':'Bearer '+token}
    assert c.get(f"/pos-api/business/{b['id']}/state",headers=hdr).status_code==200
    good(c.put(f"/pos-api/admin/accounts/{u['id']}",headers=admin,json={'active':False,'business_ids':[b['id']]}))
    assert c.get(f"/pos-api/business/{b['id']}/state",headers=hdr).status_code==401

def test_appointments_isolated(env):
    c=good(req(env,'/customers','post',{'name':'Cliente'}))
    appointment=good(req(env,'/appointments','post',{'customer_id':c['id'],'title':'Revisión','at':datetime.now(timezone.utc).isoformat()}))
    assert good(req(env,'/state',who=2))['appointments']==[]
    assert req(env,f"/appointments/{appointment['id']}",'put',{'customer_id':c['id'],'title':'Ajena','at':datetime.now(timezone.utc).isoformat()},who=2).status_code==404

def test_bootstrap_migration(env):
    import importlib.util
    spec=importlib.util.spec_from_file_location('migration','alembic/versions/e260906pos01_isolated_pos.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    from app.pos.security import verify_password
    assert m.BOOTSTRAP_HASH.startswith('scrypt$')
    assert len(m.BOOTSTRAP_HASH.split('$')[1])==32

@pytest.mark.parametrize('payload',[{'amount':-1},{'amount':'NaN'},{'amount':'Infinity'}])
def test_invalid_amount(env,payload):
    assert req(env,'/register/open','post',payload).status_code==422


def test_order_create_idempotent(env):
    from uuid import uuid4
    p=setup_sale(env)
    body={'request_key':str(uuid4()),'items':[{'product_id':p['id'],'quantity':1}]}
    one=good(req(env,'/orders','post',body));two=good(req(env,'/orders','post',body))
    assert one['id']==two['id']
    body['items'][0]['quantity']=2
    assert req(env,'/orders','post',body).status_code==409

def test_ceo_reset_password(env):
    c,h,_=env; old=h(2)
    good(c.post('/pos-api/admin/accounts/2/password',headers=h(),json={'password':'changed-password'}))
    assert c.get('/pos-api/auth/me',headers=old).status_code==401
    assert c.post('/pos-api/auth/login',json={'email':'user2@example.com','password':'changed-password'}).status_code==200


def test_full_application_registry_and_legacy_routes(env):
    from app.main import app
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    client=TestClient(app)
    for url in ('/users/','/sales/','/products/','/cash-registers/active'):
        assert client.get(url).status_code==410
    assert client.get('/health').status_code==200
    assert client.get('/pos-api/auth/me').status_code==401
