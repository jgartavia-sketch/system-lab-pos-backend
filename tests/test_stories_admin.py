import os
os.environ.setdefault('DATABASE_URL','sqlite://')
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.routes.stories import router
from app.db.database import get_db
from app.models.stories import StoriesReader
from app.pos.models import Account, SigningKey
from app.pos.security import issue
from app.core.security import create_access_token

@pytest.fixture()
def env():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    for model in [StoriesReader,Account,SigningKey]:model.__table__.create(engine)
    db=Session(engine)
    db.add(SigningKey(id=1,secret='test-key-for-stories-admin-only'))
    db.add_all([Account(id=1,name='Admin',email='admin@example.com',password_hash='unused',ceo=True), Account(id=2,name='Cliente',email='client@example.com',password_hash='unused',ceo=False)])
    now=datetime.now(timezone.utc)
    for i in range(1,32):
        db.add(StoriesReader(id=i,full_name=f'Lector {i}',email=f'reader{i}@example.com',phone=f'8888{i:04}',password_hash='private-hash',referral_code=f'CODE{i}',is_active=i!=1,created_at=now+timedelta(seconds=i)))
    db.commit()
    app=FastAPI(); app.include_router(router); app.dependency_overrides[get_db]=lambda:db
    def headers(i=1):return {'Authorization':'Bearer '+issue(db.get(Account,i),db)}
    with TestClient(app) as c:yield c,db,headers
    db.close();engine.dispose()

def test_private_to_ceo(env):
    c,_,h=env
    assert c.get('/stories/admin/readers').status_code==401
    assert c.get('/stories/admin/readers',headers=h(2)).status_code==403
    assert c.get('/stories/admin/readers',headers={'Authorization':'Bearer '+create_access_token('stories:1')}).status_code==401
    assert c.get('/stories/admin/readers',headers=h()).status_code==200

def test_totals_order_pagination_and_safe_fields(env):
    c,_,h=env
    page=c.get('/stories/admin/readers',headers=h()).json()
    assert page['total']==31 and page['filtered_total']==31 and len(page['items'])==25
    assert page['items'][0]['id']==31
    assert set(page['items'][0])=={'id','full_name','email','phone','is_active','created_at','last_login_at'}
    second=c.get('/stories/admin/readers?offset=25',headers=h()).json()
    assert len(second['items'])==6 and second['items'][-1]['is_active'] is False
    assert not {r['id'] for r in page['items']} & {r['id'] for r in second['items']}

@pytest.mark.parametrize('q,expected',[('LECTOR 31',1),('reader1@example.com',1),('88880002',1),('inexistente',0),('%',0),('_',0),('  ',31)])
def test_search_preserves_total(env,q,expected):
    c,_,h=env
    r=c.get('/stories/admin/readers',headers=h(),params={'q':q}).json()
    assert r['total']==31 and r['filtered_total']==expected

@pytest.mark.parametrize('query',['offset=-1','limit=0','limit=101','q='+('x'*181)])
def test_query_limits(env,query):
    c,_,h=env
    assert c.get('/stories/admin/readers?'+query,headers=h()).status_code==422

def test_inactive_or_revoked_admin(env):
    c,db,h=env
    headers=h(); db.get(Account,1).version+=1;db.commit()
    assert c.get('/stories/admin/readers',headers=headers).status_code==401
    db.get(Account,1).active=False;db.commit()
    assert c.get('/stories/admin/readers',headers=h()).status_code==401
