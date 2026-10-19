import os
os.environ.setdefault('DATABASE_URL','sqlite://')
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse,parse_qs
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base,get_db
from app.api.routes import stories,client_management
from app.models.stories import StoriesReader,StoriesReferral,StoriesReward,StoriesComment,StoriesPasswordReset
from app.models.client_management import ManagedClient,ProjectMilestone,ClientPayment
from app.pos.models import Account,SigningKey
from app.pos.security import issue
from app.core.security import get_password_hash,verify_password,create_access_token

@pytest.fixture()
def env(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk(connection,record):connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    with Session() as db:
        db.add(SigningKey(id=1,secret='isolated-test-key'))
        db.add_all([Account(id=1,email='admin@example.com',name='Admin',password_hash='unused',ceo=True),Account(id=2,email='client@example.com',name='Client',password_hash='unused',ceo=False)])
        db.add_all([StoriesReader(id=i,full_name=f'Lector {i}',email=f'reader{i}@example.com',phone='88888888',password_hash=get_password_hash('OldPassword1'),referral_code=f'CODE{i}') for i in range(1,4)])
        db.add(ManagedClient(id=1,name='Empresa',slug='empresa',is_active=True));db.commit()
        db.add_all([ProjectMilestone(id=1,client_id=1,title='Tarea de prueba',status='pending',priority='medium'),ClientPayment(id=1,client_id=1,product_service='Mensualidad',value=25000,currency='CRC',status='paid')]);db.commit()
    app=FastAPI();app.include_router(stories.router);app.include_router(client_management.router)
    def dependency():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=dependency
    monkeypatch.setattr(client_management,'SessionLocal',Session)
    monkeypatch.setattr(stories,'mail_is_configured',lambda:True)
    sent=[];monkeypatch.setattr(stories,'send_password_reset',lambda email,link:sent.append((email,link)))
    def headers(i=1):
        with Session() as db:return {'Authorization':'Bearer '+issue(db.get(Account,i),db)}
    with TestClient(app) as client:yield client,Session,headers,sent
    engine.dispose()

def request_reset(c,email='reader1@example.com'):
    return c.post('/stories/auth/forgot-password',json={'email':email})

def token(sent):return parse_qs(urlparse(sent[-1][1]).query)['reset'][0]

def test_reset_one_use_password_and_revoked_sessions(env):
    c,Session,h,sent=env
    old=c.post('/stories/auth/login',json={'email':'reader1@example.com','password':'OldPassword1'}).json()['access_token']
    assert request_reset(c).status_code==200
    secret=token(sent)
    with Session() as db:
        reset=db.query(StoriesPasswordReset).one();assert reset.token_hash==hashlib.sha256(secret.encode()).hexdigest() and reset.token_hash!=secret
    r=c.post('/stories/auth/reset-password',json={'token':secret,'password':'NewPassword2'});assert r.status_code==200,r.text
    assert c.post('/stories/auth/reset-password',json={'token':secret,'password':'OtherPassword3'}).status_code==400
    assert c.get('/stories/auth/me',headers={'Authorization':'Bearer '+old}).status_code==401
    legacy=create_access_token('stories:1');assert c.get('/stories/auth/me',headers={'Authorization':'Bearer '+legacy}).status_code==401
    assert c.post('/stories/auth/login',json={'email':'reader1@example.com','password':'OldPassword1'}).status_code==401
    new=c.post('/stories/auth/login',json={'email':'reader1@example.com','password':'NewPassword2'});assert new.status_code==200
    assert c.get('/stories/auth/me',headers={'Authorization':'Bearer '+new.json()['access_token']}).status_code==200

def test_unknown_email_and_throttling(env):
    c,S,h,sent=env
    expected=request_reset(c).json();assert request_reset(c,'unknown@example.com').json()==expected
    assert request_reset(c).json()==expected and len(sent)==1
    with S() as db:
        row=db.query(StoriesPasswordReset).one();row.created_at=datetime.now(timezone.utc)-timedelta(minutes=2);db.commit()
    old=token(sent);request_reset(c);assert len(sent)==2
    assert c.post('/stories/auth/reset-password',json={'token':old,'password':'Password123'}).status_code==400

def test_expired_invalid_and_short_password(env):
    c,S,h,sent=env;request_reset(c);secret=token(sent)
    assert c.post('/stories/auth/reset-password',json={'token':secret,'password':'short'}).status_code==422
    with S() as db:
        row=db.query(StoriesPasswordReset).one();row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert c.post('/stories/auth/reset-password',json={'token':secret,'password':'Password123'}).status_code==400
    assert c.post('/stories/auth/reset-password',json={'token':'x'*43,'password':'Password123'}).status_code==400

def test_mail_not_configured_and_failed_delivery(env,monkeypatch):
    c,S,h,sent=env
    monkeypatch.setattr(stories,'mail_is_configured',lambda:False);assert request_reset(c).status_code==503
    monkeypatch.setattr(stories,'mail_is_configured',lambda:True)
    def fail(*args):raise RuntimeError('provider failure')
    monkeypatch.setattr(stories,'send_password_reset',fail);assert request_reset(c).status_code==200
    with S() as db:assert db.query(StoriesPasswordReset).one().used_at is not None

def test_inactive_reader_cannot_recover(env):
    c,S,h,sent=env
    with S() as db:db.get(StoriesReader,1).is_active=False;db.commit()
    assert request_reset(c).status_code==200 and not sent

@pytest.mark.parametrize('path',['/stories/admin/readers/1','/client-management/milestones/1','/client-management/payments/1'])
def test_deletes_require_ceo(env,path):
    c,S,h,sent=env
    assert c.delete(path).status_code==401
    assert c.delete(path,headers=h(2)).status_code==403
    assert c.delete(path,headers=h()).status_code==204
    assert c.delete(path,headers=h()).status_code==404

def test_reader_delete_cascades_without_other_accounts(env):
    c,S,h,sent=env
    with S() as db:
        db.add_all([StoriesReferral(referrer_id=1,referred_reader_id=2,status='pending'),StoriesReferral(referrer_id=3,referred_reader_id=1,status='pending'),StoriesReward(reader_id=1,reward_number=1)])
        root=StoriesComment(reader_id=1,body='opinión',rating=4,anonymous=True);db.add(root);db.flush();db.add(StoriesComment(reader_id=2,parent_id=root.id,body='respuesta',anonymous=False));db.commit()
    request_reset(c)
    assert c.delete('/stories/admin/readers/1',headers=h()).status_code==204
    with S() as db:
        assert db.get(StoriesReader,1) is None and db.get(StoriesReader,2) is not None
        for model in [StoriesComment,StoriesReferral,StoriesReward,StoriesPasswordReset]:assert db.query(model).count()==0
    assert c.get('/stories/admin/readers',headers=h()).json()['total']==2

def test_cannot_delete_own_reader_account(env):
    c,S,h,sent=env
    with S() as db:db.get(StoriesReader,1).email='admin@example.com';db.commit()
    assert c.delete('/stories/admin/readers/1',headers=h()).status_code==409

def test_complete_task_keeps_payment_unchanged(env):
    c,S,h,sent=env
    r=c.patch('/client-management/milestones/1',json={'status':'completed'});assert r.status_code==200 and r.json()['status']=='completed'
    with S() as db:assert db.get(ClientPayment,1).value==25000

def test_new_migration_preserves_existing_readers():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import text, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    engine=create_engine('sqlite://')
    spec=importlib.util.spec_from_file_location('reset_migration',Path(__file__).parents[1]/'alembic/versions/f261019pwd01_stories_password_reset.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE stories_readers (id INTEGER PRIMARY KEY, full_name VARCHAR(180))'))
        conn.execute(text("INSERT INTO stories_readers VALUES (1,'Lector existente')"))
        with Operations.context(MigrationContext.configure(conn)):migration.upgrade()
        assert conn.execute(text('SELECT full_name,session_version FROM stories_readers')).one()==('Lector existente',0)
        assert 'stories_password_resets' in inspect(conn).get_table_names()
        with Operations.context(MigrationContext.configure(conn)):migration.downgrade()
        assert conn.execute(text('SELECT full_name FROM stories_readers')).scalar()=='Lector existente'
    engine.dispose()

def test_mail_uses_tls_and_configured_sender(monkeypatch):
    from app.core import stories_mail
    sent=[];steps=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def starttls(self,**kwargs):steps.append('tls')
        def login(self,*args):steps.append('login')
        def send_message(self,message):sent.append(message);steps.append('send')
    monkeypatch.setattr(stories_mail.smtplib,'SMTP',FakeSMTP)
    monkeypatch.setattr(stories_mail.settings,'SMTP_HOST','smtp.example.com');monkeypatch.setattr(stories_mail.settings,'SMTP_FROM','info@example.com');monkeypatch.setattr(stories_mail.settings,'SMTP_USERNAME','info@example.com');monkeypatch.setattr(stories_mail.settings,'SMTP_USE_SSL',False)
    stories_mail.send_password_reset('reader@example.com','https://www.systemlabcr.com/stories/mi-cuenta?reset=secret')
    assert steps==['tls','login','send'] and sent[0]['To']=='reader@example.com' and sent[0]['From']=='info@example.com'

def test_mail_api_uses_https_and_key_only_on_server(monkeypatch):
    import json
    from app.core import stories_mail
    requests=[]
    class FakeResponse:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"id":"fake-email-id"}'
    def urlopen(request,**kwargs):requests.append(request);return FakeResponse()
    monkeypatch.setattr(stories_mail,'urlopen',urlopen)
    monkeypatch.setattr(stories_mail.settings,'RESEND_API_KEY','test-only-key')
    monkeypatch.setattr(stories_mail.settings,'STORIES_MAIL_FROM','System Lab <info@example.com>')
    assert stories_mail.mail_is_configured()
    stories_mail.send_password_reset('reader@example.com','https://www.systemlabcr.com/stories/mi-cuenta?reset=opaque-secret')
    assert requests[0].full_url=='https://api.resend.com/emails' and requests[0].get_header('Authorization')=='Bearer test-only-key'
    assert json.loads(requests[0].data)['to']==['reader@example.com']
