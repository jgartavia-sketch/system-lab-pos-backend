from test_pos import env, req, good, setup_sale, order
from app.pos.models import Account, Membership, Business, Order, Audit
from app.pos.security import hash_password
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
from uuid import uuid4


def staff(env,role='waiter',pay=True,bid=1,who=1,email='employee@example.com'):
    u=good(req(env,'/team','post',{'name':'Empleado','email':email,'password':'employee-password','role':role,'can_pay':pay},who,bid))
    token=good(env[0].post('/pos-api/auth/login',json={'email':email,'password':'employee-password'}))['token']
    return u,{'Authorization':'Bearer '+token}

def call(env,h,path,body=None,method='post',bid=1):
    return getattr(env[0],method)(f'/pos-api/business/{bid}'+path,headers=h,**({'json':body} if body is not None else {}))

def pin(env,bid=1,who=1):
    good(req(env,'/pin','post',{'current_password':'test-password','pin':'684291'},who,bid))

def discounted(pid,**extra):
    return {'request_key':str(uuid4()),'items':[{'product_id':pid,'quantity':1,'unit_price':80}], 'adjustment_reason':'Atención al cliente',**extra}


def test_owner_multiple_restaurants_same_login(env):
    c,h,_=env
    b=good(c.post('/pos-api/admin/businesses',headers=h(),json={'name':'Segundo restaurante','mode':'restaurante'}))
    good(c.put('/pos-api/admin/accounts/2',headers=h(),json={'active':True,'business_ids':[2,b['id']]}))
    me=good(c.get('/pos-api/auth/me',headers=h(2)))
    assert len(me['businesses'])==2 and all(x['role']=='owner' for x in me['businesses'])
    assert req(env,'/state',who=2,bid=b['id']).status_code==200
    assert req(env,'/state',who=2,bid=1).status_code==403


def test_waiter_server_restrictions_and_hidden_costs(env):
    p=setup_sale(env);u,h=staff(env)
    s=good(call(env,h,'/state',method='get'))
    assert not s['permissions']['manage'] and s['permissions']['pay']
    assert 'cost' not in s['products'][0] and 'expected' not in s['register']
    assert s['movements']==s['registers']==[]
    for path,body,method in [('/products',{'name':'Bad','sku':'BAD','price':0},'post'),
       ('/products/'+str(p['id']),{'name':'Café','sku':'CAFE','price':0},'put'),
       ('/products/'+str(p['id'])+'/stock',{'kind':'entry','quantity':10,'reason':'bad'},'post'),
       ('/register/open',{'amount':0},'post'),('/cash',{'kind':'income','amount':100,'reason':'bad'},'post'),
       ('/reports?start=2026-09-01&end=2026-09-07',None,'get'),('/team',None,'get'),('/audit',None,'get'),
       ('/pin',{'current_password':'employee-password','pin':'111111'},'post')]:
        assert call(env,h,path,body,method).status_code==403,path
    o=good(call(env,h,'/orders',{'items':[{'product_id':p['id'],'quantity':1}]}))
    assert 'cost' not in o['items'][0]
    good(call(env,h,f"/orders/{o['id']}/pay",{'method':'cash','received':113}))
    assert call(env,h,f"/orders/{o['id']}/refund",{'reason':'bad refund'}).status_code==403


def test_cash_permission_and_removal_apply_existing_session(env):
    p=setup_sale(env);u,h=staff(env,pay=False)
    o=good(call(env,h,'/orders',{'items':[{'product_id':p['id'],'quantity':1}]}))
    assert call(env,h,f"/orders/{o['id']}/pay",{'method':'card'}).status_code==403
    good(req(env,f"/team/{u['id']}",'put',{'role':'waiter','can_pay':True}))
    good(call(env,h,f"/orders/{o['id']}/pay",{'method':'card'}))
    good(req(env,f"/team/{u['id']}",'delete'))
    assert call(env,h,'/state',method='get').status_code==403
    with env[2]() as db: assert db.get(Order,o['id']).status=='paid'


def test_link_employee_only_to_owned_local(env):
    c,headers,_=env;u,h=staff(env)
    b=good(c.post('/pos-api/admin/businesses',headers=headers(),json={'name':'Otro local','mode':'restaurante'}))
    good(c.put('/pos-api/admin/accounts/1',headers=headers(),json={'active':True,'business_ids':[1,b['id']]}))
    good(req(env,f"/team/{u['id']}",'put',{'role':'cashier','can_pay':True},bid=b['id']))
    assert call(env,h,'/state',method='get',bid=b['id']).status_code==200
    assert req(env,f"/team/{u['id']}",'put',{'role':'admin'},who=2,bid=2).status_code==403
    good(req(env,f"/team/{u['id']}",'delete',bid=b['id']))
    assert call(env,h,'/state',method='get').status_code==200


def test_staff_cannot_escalate_or_remove_owner(env):
    u,h=staff(env,role='admin')
    assert call(env,h,'/team',{'name':'Bad','email':'bad@example.com','password':'12345678'}).status_code==403
    assert req(env,'/team/1','delete').status_code==403
    assert req(env,f"/team/{u['id']}",'put',{'role':'owner'}).status_code==422
    assert env[0].post('/pos-api/admin/businesses',headers=h,json={'name':'Bad','mode':'restaurante'}).status_code==403


def test_override_requires_local_pin_and_audits_exact_change(env):
    p=setup_sale(env);u,h=staff(env);pin(env)
    body=discounted(p['id'])
    assert call(env,h,'/orders',body).status_code==403
    body['approval']={'email':'user2@example.com','pin':'684291'}
    assert call(env,h,'/orders',body).status_code==403
    body['approval']={'email':'user1@example.com','pin':'684291'}
    o=good(call(env,h,'/orders',body))
    assert float(o['total'])==90.4
    replay=good(call(env,h,'/orders',body));assert replay['id']==o['id']
    entries=good(req(env,'/audit'));entry=next(x for x in entries if x['action']=='price_approval')
    assert entry['actor_id']==u['id'] and entry['approver_id']==1 and entry['order_id']==o['id']
    assert entry['detail']['prices'][0]['authorized_price']=='80'
    assert '684291' not in str(entries)
    assert float(good(req(env,'/state'))['products'][0]['price'])==100
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='price_approval'))==1


def test_discount_bypass_rejected(env):
    p=setup_sale(env);_,h=staff(env)
    assert call(env,h,'/orders',{'items':[{'product_id':p['id'],'quantity':1}],'discount':1}).status_code==403


def test_wrong_pin_does_not_persist_order_and_locks(env):
    p=setup_sale(env);_,h=staff(env);pin(env)
    for _ in range(5):
        assert call(env,h,'/orders',discounted(p['id'],approval={'email':'user1@example.com','pin':'000000'})).status_code==403
    assert call(env,h,'/orders',discounted(p['id'],approval={'email':'user1@example.com','pin':'684291'})).status_code==429
    with env[2]() as db:
        assert db.scalar(select(func.count()).select_from(Order))==0
        m=db.scalar(select(Membership).where(Membership.account_id==1));m.pin_locked_until=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    good(call(env,h,'/orders',discounted(p['id'],approval={'email':'user1@example.com','pin':'684291'})))


def test_revoked_admin_pin_cannot_authorize(env):
    p=setup_sale(env);admin,ah=staff(env,role='admin',email='manager@example.com');_,h=staff(env,email='waiter@example.com')
    good(call(env,ah,'/pin',{'current_password':'employee-password','pin':'954321'}))
    good(req(env,f"/team/{admin['id']}",'put',{'role':'waiter'}))
    assert call(env,h,'/orders',discounted(p['id'],approval={'email':'manager@example.com','pin':'954321'})).status_code==403


def test_paid_comanda_remains_in_kitchen_and_can_be_served(env):
    p=setup_sale(env);_,wh=staff(env);_,kh=staff(env,role='kitchen',email='kitchen@example.com')
    o=good(call(env,wh,'/orders',{'items':[{'product_id':p['id'],'quantity':1}],'send_to_kitchen':True,'table_number':1}))
    good(call(env,wh,f"/orders/{o['id']}/pay",{'method':'card'}))
    kitchen=good(call(env,kh,'/state',method='get'))
    assert kitchen['orders'][0]['status']=='paid' and kitchen['orders'][0]['kitchen_status']=='queued'
    assert call(env,kh,f"/orders/{o['id']}/pay",{'method':'card'}).status_code==403
    assert call(env,wh,f"/orders/{o['id']}/status",{'status':'preparing'}).status_code==403
    for state in ('preparing','ready','served'):
        result=good(call(env,kh,f"/orders/{o['id']}/status",{'status':state}));assert result['status']=='paid'
    assert good(call(env,kh,'/state',method='get'))['orders']==[]
    assert float(good(req(env,'/state'))['products'][0]['stock'])==19


def test_waiter_cannot_cancel_sent_or_other_order(env):
    p=setup_sale(env);_,h=staff(env)
    o=order(env,p)
    assert call(env,h,f"/orders/{o['id']}/status",{'status':'cancelled'}).status_code==403
    o=good(call(env,h,'/orders',{'items':[{'product_id':p['id'],'quantity':1}],'send_to_kitchen':True}))
    assert call(env,h,f"/orders/{o['id']}/status",{'status':'cancelled'}).status_code==403


def test_stale_edit_rejected(env):
    p=setup_sale(env);_,h=staff(env)
    o=good(call(env,h,'/orders',{'items':[{'product_id':p['id'],'quantity':1}]}))
    body={'items':[{'product_id':p['id'],'quantity':2}],'expected_revision':o['revision']}
    good(call(env,h,f"/orders/{o['id']}",body,'put'))
    assert call(env,h,f"/orders/{o['id']}",body,'put').status_code==409


def test_staff_password_reset_revokes_sessions(env):
    u,h=staff(env)
    good(req(env,f"/team/{u['id']}/password",'post',{'password':'changed-password'}))
    assert call(env,h,'/state',method='get').status_code==401


def test_owner_cannot_reset_account_outside_owned_businesses(env):
    u,h=staff(env)
    with env[2].begin() as db: db.add(Membership(account_id=u['id'],business_id=2,role='waiter'))
    assert req(env,f"/team/{u['id']}/password",'post',{'password':'changed-password'}).status_code==403
    assert call(env,h,'/state',method='get',bid=2).status_code==200


def test_pin_hash_and_secrets_not_in_responses(env):
    pin(env)
    assert 'pin_hash' not in str(good(req(env,'/team')))
    assert 'pin_hash' not in str(good(env[0].get('/pos-api/admin',headers=env[1]())))
    with env[2]() as db:
        assert db.scalar(select(Membership).where(Membership.account_id==1)).pin_hash.startswith('scrypt$')
