from sqlalchemy import select,func
from test_pos import env,good,req
from app.pos.models import Account,Business,Membership,Activation,ConnectLink
from app.pos.provision_zenit import provision


def activate(env,email='new@example.com',password='new-password-123',confirmation=None,who=1):
    return env[0].post('/pos-api/admin/activate-pos',headers=env[1](who),json={'email':email,'password':password,'confirmation':password if confirmation is None else confirmation})


def test_one_click_creates_active_owner_and_private_workspace_once(env):
    result=good(activate(env));uid=result['account_id'];bid=result['business_id']
    again=good(activate(env,'NEW@example.com'));assert again['account_id']==uid and again['business_id']==bid
    token=good(env[0].post('/pos-api/auth/login',json={'email':'new@example.com','password':'new-password-123'}))['token'];headers={'Authorization':'Bearer '+token}
    me=good(env[0].get('/pos-api/auth/me',headers=headers));assert len(me['businesses'])==1
    assert not me['account']['ceo'];assert me['businesses'][0]['setup_complete'] is False
    assert env[0].get('/pos-api/business/1/state',headers=headers).status_code==403
    assert env[0].post(f'/pos-api/business/{bid}/register/open',headers=headers,json={'amount':0}).status_code==409
    result=good(env[0].put(f'/pos-api/business/{bid}/settings',headers=headers,json={'name':'Salón propio','mode':'salon','tables':15}))
    assert result['tables']==0 and result['setup_complete']
    assert env[0].put(f'/pos-api/business/{bid}/settings',headers=headers,json={'name':'Otro','mode':'restaurante','tables':3}).status_code==409
    with env[2]() as db:assert len(list(db.scalars(select(Membership).where(Membership.account_id==uid))))==1


def test_ceo_and_confirmation_validation(env):
    assert activate(env,who=2).status_code==403
    assert activate(env,confirmation='different-pass').status_code==422
    assert activate(env,'user1@example.com').status_code==403
    with env[2]() as db:assert db.scalar(select(func.count()).select_from(Account))==2


def test_zenit_existing_account_activated_without_duplicate_or_lost_link(env):
    with env[2].begin() as db:token=provision(db,True)
    with env[2]() as db:
        uid=db.scalar(select(Account.id).where(Account.email=='eeacordero7@gmail.com'))
        bid=db.scalar(select(Membership.business_id).where(Membership.account_id==uid))
        before=db.scalar(select(func.count()).select_from(Business))
    r=good(activate(env,'eeacordero7@gmail.com'));assert r['account_id']==uid and r['business_id']==bid
    with env[2]() as db:
        assert db.get(ConnectLink,bid).provider=='zenit';assert db.get(Business,bid).mode=='salon'
        assert db.scalar(select(func.count()).select_from(Business))==before
        assert db.get(Activation,uid) is None
    assert env[0].post('/pos-api/auth/activate',json={'token':token,'password':'old-link-password'}).status_code==400
    good(env[0].post('/pos-api/auth/login',json={'email':'eeacordero7@gmail.com','password':'new-password-123'}))


def test_panel_reset_or_suspend_revokes_pending_link(env):
    with env[2].begin() as db:token=provision(db,True)
    with env[2]() as db:
        uid=db.scalar(select(Account.id).where(Account.email=='eeacordero7@gmail.com'))
        ids=list(db.scalars(select(Membership.business_id).where(Membership.account_id==uid)))
    good(env[0].post(f'/pos-api/admin/accounts/{uid}/password',headers=env[1](),json={'password':'admin-chosen-pass'}))
    assert env[0].post('/pos-api/auth/activate',json={'token':token,'password':'old-link-password'}).status_code==400
    with env[2].begin() as db:
        from datetime import datetime,timedelta,timezone
        import hashlib
        token='x'*48
        db.add(Activation(account_id=uid,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
    good(env[0].put(f'/pos-api/admin/accounts/{uid}',headers=env[1](),json={'active':False,'business_ids':ids}))
    assert env[0].post('/pos-api/auth/activate',json={'token':token,'password':'old-link-password'}).status_code==400


def test_staff_cannot_configure_owner_business_and_tables_are_owner_controlled(env):
    from test_pos_roles import staff
    _,headers=staff(env,'admin')
    assert env[0].put('/pos-api/business/1/settings',headers=headers,json={'name':'No','mode':'restaurante','tables':3}).status_code==403
    assert req(env,'/settings','put',{'name':'Nombre','mode':'restaurante','tables':4}).status_code==200


def test_ceo_can_enable_employee_as_private_client_without_taking_employers_business(env):
    from test_pos_roles import staff
    user,_=staff(env,'cashier',email='employee@example.com')
    result=good(activate(env,'employee@example.com'))
    assert result['account_id']==user['id'] and result['business_id']!=1
    with env[2]() as db:
        roles=list(db.scalars(select(Membership).where(Membership.account_id==user['id'])))
        assert any(m.business_id==1 and m.role=='cashier' for m in roles)
        assert any(m.business_id==result['business_id'] and m.role=='owner' for m in roles)


def test_table_reduction_preserves_open_orders(env):
    from test_pos import setup_sale,order
    p=setup_sale(env);order(env,p,table_number=5)
    assert req(env,'/settings','put',{'name':'Mi restaurante','mode':'restaurante','tables':2}).status_code==409


def test_existing_suspended_business_is_enabled_with_its_owner(env):
    with env[2].begin() as db: db.get(Business,2).active=False
    good(activate(env,'user2@example.com'))
    with env[2]() as db: assert db.get(Business,2).active is True


def test_subscription_freezes_owner_and_staff_then_restores_same_password(env):
    from test_pos_roles import staff
    _,employee_headers=staff(env,'cashier',bid=2,who=2)
    owner_headers=env[1](2)
    path='/pos-api/admin/accounts/2/subscription'
    assert env[0].put(path,headers=owner_headers,json={'active':False}).status_code==403
    good(env[0].put(path,headers=env[1](),json={'active':False}))
    assert env[0].get('/pos-api/business/2/state',headers=owner_headers).status_code==401
    assert env[0].get('/pos-api/business/2/state',headers=employee_headers).status_code==403
    # Unrelated businesses remain available.
    assert req(env,'/state').status_code==200
    good(env[0].put(path,headers=env[1](),json={'active':True}))
    assert req(env,'/state',who=2).status_code==200
    assert env[0].get('/pos-api/business/2/state',headers=employee_headers).status_code==200
    assert env[0].put('/pos-api/admin/accounts/1/subscription',headers=env[1](),json={'active':False}).status_code==403


def test_retire_preserves_history_and_can_restore_without_duplicates(env):
    from test_pos import setup_sale,order
    p=setup_sale(env,who=2);sale=order(env,p,who=2)
    account_id=2
    # Register both routers and verify retirement never physically deletes history.
    before_headers=env[1](2)
    good(env[0].delete(f'/pos-api/admin/accounts/{account_id}/subscription',headers=env[1]()))
    with env[2]() as db:
        assert db.get(Account,2).archived and not db.get(Account,2).active
        assert not db.get(Business,2).active
        from app.pos.models import Order
        assert db.get(Order,sale['id'])
    assert env[0].get('/pos-api/business/2/state',headers=before_headers).status_code==401
    restored=good(activate(env,'user2@example.com'));assert restored['account_id']==2 and restored['business_id']==2
    with env[2]() as db:assert not db.get(Account,2).archived
    token=good(env[0].post('/pos-api/auth/login',json={'email':'user2@example.com','password':'new-password-123'}))['token']
    state=good(env[0].get('/pos-api/business/2/state',headers={'Authorization':'Bearer '+token}))
    assert state['orders'][0]['id']==sale['id']
