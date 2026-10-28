from test_pos import env,good,req
from test_pos_roles import staff
from test_pos_activation_panel import activate
from app.pos.models import Account,Business,Membership,ConnectLink,Order
from app.pos.provision_zenit import provision
from sqlalchemy import select,func


def test_ceo_retires_legacy_employee_juan_without_blocking_employer(env):
    user,headers=staff(env,'cashier',email='juan@hotmail.com')
    path=f"/pos-api/admin/accounts/{user['id']}/subscription"
    assert env[0].delete(path,headers=headers).status_code==403
    good(env[0].delete(path,headers=env[1]()))
    with env[2]() as db:
        assert db.get(Account,user['id']).archived
        assert db.get(Business,1).active and db.get(Business,2).active
        assert db.scalar(select(Membership).where(Membership.account_id==user['id'])).role=='cashier'
    assert env[0].get('/pos-api/business/1/state',headers=headers).status_code==401
    good(env[0].put(path,headers=env[1](),json={'active':True}))
    with env[2]() as db: assert not db.get(Account,user['id']).archived


def test_ceo_suspends_mixed_role_client_only_own_businesses(env):
    user,_=staff(env,'admin',bid=1,email='mixed@example.com')
    with env[2].begin() as db:
        db.add(Membership(account_id=user['id'],business_id=2,role='owner'))
    path=f"/pos-api/admin/accounts/{user['id']}/subscription"
    good(env[0].put(path,headers=env[1](),json={'active':False}))
    with env[2]() as db:
        assert db.get(Business,1).active
        assert not db.get(Business,2).active
    good(env[0].put(path,headers=env[1](),json={'active':True}))
    with env[2]() as db: assert db.get(Business,2).active


def test_connected_zenit_is_retired_and_restored_as_one_client_without_losing_connection(env):
    with env[2].begin() as db:provision(db,True)
    with env[2]() as db:
        uid=db.scalar(select(Account.id).where(Account.email=='eeacordero7@gmail.com'))
        bid=db.scalar(select(Membership.business_id).where(Membership.account_id==uid))
        original_count=db.scalar(select(func.count()).select_from(Business))
    path=f'/pos-api/admin/accounts/{uid}/subscription'
    good(env[0].delete(path,headers=env[1]()))
    with env[2]() as db:
        assert db.get(Account,uid).archived and not db.get(Business,bid).active
        assert db.get(ConnectLink,bid).provider=='zenit'
    result=good(activate(env,'eeacordero7@gmail.com'))
    assert result['account_id']==uid and result['business_id']==bid
    with env[2]() as db:
        assert not db.get(Account,uid).archived and db.get(Business,bid).active
        assert db.get(ConnectLink,bid).provider=='zenit'
        assert db.scalar(select(func.count()).select_from(Business))==original_count


def test_multiple_businesses_remain_one_client_with_one_action(env):
    with env[2].begin() as db:
        third=Business(name='Sucursal',mode='salon',active=True,tables=0);db.add(third);db.flush()
        tid=third.id;db.add(Membership(account_id=2,business_id=tid,role='owner'))
    good(env[0].delete('/pos-api/admin/accounts/2/subscription',headers=env[1]()))
    with env[2]() as db:
        assert db.get(Account,2).archived
        assert not db.get(Business,2).active and not db.get(Business,tid).active
        assert db.get(Business,1).active
    good(env[0].put('/pos-api/admin/accounts/2/subscription',headers=env[1](),json={'active':True}))
    assert req(env,'/state',who=2,bid=tid).status_code==200
