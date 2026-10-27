from uuid import uuid4
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func
from test_pos import env,req,good,setup_sale,order
from app.pos.models import Account,Business,Membership,ConnectLink,Activation,CreditPayment,Order,Product
from app.pos.provision_zenit import provision
from app.pos import routes

def credit(env):
    product=setup_sale(env,price=100,tax=0)
    customer=good(req(env,'/customers','post',{'name':'Cliente crédito'}))
    sale=order(env,product,customer_id=customer['id'])
    due=(datetime.now(routes.TZ).date()+timedelta(days=1)).isoformat()
    plan={'installments':[{'due':due,'amount':100},{'due':(datetime.now(routes.TZ).date()+timedelta(days=30)).isoformat(),'amount':100}]}
    saved=good(req(env,f"/orders/{sale['id']}/credit",'post',plan))
    return sale,saved,plan

def test_credit_payments_retry_reports_and_reversals(env):
    sale,c,plan=credit(env)
    assert c['status']=='pending' and float(c['balance'])==200
    assert good(req(env,f"/orders/{sale['id']}/credit",'post',plan))['id']==c['id']
    assert req(env,f"/orders/{sale['id']}/refund",'post',{'reason':'invalid path'}).status_code==409
    payload={'request_key':str(uuid4()),'amount':50,'method':'cash','reference':'Recibo prueba'}
    path=f"/receivables/{c['id']}/payments"
    payment=good(req(env,path,'post',payload));assert good(req(env,path,'post',payload))['id']==payment['id']
    assert req(env,path,'post',{**payload,'amount':51}).status_code==409
    assert req(env,path,'post',{**payload,'request_key':str(uuid4()),'amount':151}).status_code==409
    assert float(good(req(env,'/state'))['register']['expected'])==1050
    current=good(req(env,'/receivables'))['accounts'][0]
    assert current['status']=='partial' and float(current['installments'][0]['balance'])==50
    day=datetime.now(routes.TZ).date().isoformat()
    report=good(req(env,f'/reports?start={day}&end={day}'))
    assert float(report['sales'])==200 and float(report['money_in'])==50 and float(report['operating_expenses'])==0
    good(req(env,f"/receivables/{c['id']}/payments/{payment['id']}/void",'post',{'reason':'Corrección prueba'}))
    assert float(good(req(env,'/state'))['register']['expected'])==1000
    good(req(env,f"/receivables/{c['id']}/void",'post',{'reason':'Venta anulada'}))
    assert good(req(env,'/receivables'))['accounts'][0]['status']=='voided'
    assert float(good(req(env,'/state'))['products'][0]['stock'])==20

def test_credit_validation_tenant_and_final_payment(env):
    sale,c,_=credit(env);path=f"/receivables/{c['id']}/payments"
    for amount in [-1,0,'0.001',201]:
        assert req(env,path,'post',{'request_key':str(uuid4()),'amount':amount,'method':'cash'}).status_code in (409,422)
    assert req(env,path,'post',{'request_key':str(uuid4()),'amount':50,'method':'cash'},who=2).status_code==404
    good(req(env,path,'post',{'request_key':str(uuid4()),'amount':200,'method':'card'}))
    assert good(req(env,'/receivables'))['accounts'][0]['status']=='paid'
    assert float(good(req(env,'/state'))['register']['expected'])==1000
    assert req(env,path,'post',{'request_key':str(uuid4()),'amount':1,'method':'cash'}).status_code==409

def test_zenit_provision_activation_and_repeat(env):
    with env[2].begin() as db: token=provision(db,True)
    assert token
    with env[2].begin() as db:
        assert provision(db,True) is None
        account=db.scalar(select(Account).where(Account.email=='eeacordero7@gmail.com'))
        assert not account.active and not account.ceo
        bid=db.scalar(select(Membership.business_id).where(Membership.account_id==account.id))
    payload={'token':token,'password':'Only-test-password12'}
    good(env[0].post('/pos-api/auth/activate',json=payload))
    assert env[0].post('/pos-api/auth/activate',json=payload).status_code==400
    login=good(env[0].post('/pos-api/auth/login',json={'email':'eeacordero7@gmail.com','password':payload['password']}))
    h={'Authorization':'Bearer '+login['token']}
    assert env[0].get('/pos-api/admin',headers=h).status_code==403
    assert env[0].get('/pos-api/business/1/state',headers=h).status_code==403
    result=good(env[0].get(f'/pos-api/business/{bid}/state',headers=h))
    assert result['permissions']['role']=='owner'
    assert env[0].post(f'/pos-api/business/{bid}/appointments',headers=h,json={'customer_id':1,'title':'Test','at':'2026-12-01T12:00:00Z'}).status_code==409

def test_zenit_refuses_existing_ceo(env):
    with env[2].begin() as db:
        db.get(Account,1).email='eeacordero7@gmail.com'
    with env[2]() as db:
        import pytest
        with pytest.raises(ValueError): provision(db,True)

def test_zenit_bridge_is_readonly_and_isolated(env,monkeypatch):
    with env[2].begin() as db: db.add(ConnectLink(business_id=1,provider='zenit'))
    calls=[]
    monkeypatch.setattr(routes,'connect_request',lambda *args: calls.append(args) or {'provider':'zenit','appointments':[]})
    good(req(env,'/connect/zenit/appointments?date=2026-10-27'))
    assert len(calls)==1
    assert req(env,'/connect/zenit/catalog',who=2).status_code==404
    assert req(env,'/connect/zenit/catalog',who=2,bid=1).status_code==403
    assert len(calls)==1
    from app.pos.connect_client import zenit_request
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException): zenit_request('/orders/x','POST',{})

def test_credit_overdue_expiry_and_permissions(env):
    from app.pos.models import Receivable
    from test_pos_roles import staff,call
    sale,c,_=credit(env)
    with env[2].begin() as db:
        obj=db.get(Receivable,c['id'])
        obj.schedule=[{'due':(datetime.now(routes.TZ).date()-timedelta(days=1)).isoformat(),'amount':'200.00'}]
    assert good(req(env,'/receivables'))['accounts'][0]['status']=='overdue'
    _,waiter=staff(env)
    assert call(env,waiter,'/receivables',method='get').status_code==403
    assert call(env,waiter,f"/orders/{sale['id']}/credit",{'installments':[{'due':'2027-01-01','amount':200}]}).status_code==403
    with env[2].begin() as db:
        token=provision(db,True)
        db.flush()
        activation=db.scalar(select(Activation))
        activation.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    assert env[0].post('/pos-api/auth/activate',json={'token':token,'password':'Only-test-password12'}).status_code==400

def test_credit_void_closed_register_and_exact_cents(env):
    _,c,_=credit(env)
    payload={'request_key':str(uuid4()),'amount':'0.01','method':'cash'}
    p=good(req(env,f"/receivables/{c['id']}/payments",'post',payload))
    assert float(good(req(env,'/receivables'))['balance'])==199.99
    assert req(env,f"/receivables/{c['id']}/void",'post',{'reason':'Con abono activo'}).status_code==409
    good(req(env,'/register/close','post',{'amount':1000.01}))
    good(req(env,'/register/open','post',{'amount':1000.01}))
    good(req(env,f"/receivables/{c['id']}/payments/{p['id']}/void",'post',{'reason':'Corrección en caja actual'}))
    assert float(good(req(env,'/state'))['register']['expected'])==1000
    assert float(good(req(env,'/receivables'))['balance'])==200

def test_activation_renewal_revokes_old_token_without_reset(env):
    with env[2].begin() as db: first=provision(db,True)
    with env[2].begin() as db:
        old_hash=db.scalar(select(Account.password_hash).where(Account.email=='eeacordero7@gmail.com'))
        renewed=provision(db,True,True)
        assert db.scalar(select(Account.password_hash).where(Account.email=='eeacordero7@gmail.com'))==old_hash
    body={'token':first,'password':'Only-test-password12'}
    assert env[0].post('/pos-api/auth/activate',json=body).status_code==400
    good(env[0].post('/pos-api/auth/activate',json={**body,'token':renewed}))
    with env[2]() as db:
        import pytest
        with pytest.raises(ValueError): provision(db,True,True)
