"""Pruebas aisladas: nunca conectan a la base de producción."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")
import importlib.util
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.api.routes.stories import router, get_db
from app.models.stories import StoriesReader, StoriesComment
from app.core.security import create_access_token

@pytest.fixture()
def env():
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    StoriesReader.__table__.create(engine)
    spec = importlib.util.spec_from_file_location('migration', Path(__file__).parents[1] / 'alembic/versions/f261019com01_stories_comments.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    db = Session(engine)
    for i, email in enumerate(['reader@example.com', 'other@example.com', 'jgartavia@gmail.com'], 1):
        db.add(StoriesReader(id=i, full_name=f'Lector {i}', email=email, phone='12345678', password_hash='unused',referral_code=f'TEST{i}'))
    db.commit()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client, db
    db.close(); engine.dispose()

def headers(i=1):
    return {'Authorization':f'Bearer {create_access_token(subject=f"stories:{i}")}'}

def post(c, **data):
    return c.post('/stories/comments', json=data, headers=headers())

def test_public_read_and_login_required(env):
    c,_ = env
    assert c.get('/stories/comments').json() == []
    assert c.post('/stories/comments',json={'body':'Hola','rating':5}).status_code == 401

def test_anonymous_privacy_and_shared_persistence(env):
    c,db=env
    r=post(c,body='Me encantó',rating=5,anonymous=True)
    assert r.status_code == 201
    row=r.json(); assert row['author_name']=='Anónimo'
    assert not {'reader_id','email','phone','full_name'} & row.keys()
    assert c.get('/stories/comments').json()[0] == row
    assert db.get(StoriesComment,row['id']).reader_id==1

def test_named_opinion(env):
    c,_=env
    assert post(c,body='Una gran historia',rating=4).json()['author_name']=='Lector 1'

@pytest.mark.parametrize('data',[
    {'body':'  ','rating':5},{'body':'a'*2001,'rating':4},
    {'body':'Hola','rating':0},{'body':'Hola','rating':6},
    {'body':'Hola','rating':2.5},{'body':'Hola'},
    {'body':'Hola','rating':True},{'body':'Hola','rating':5,'reader_id':3}])
def test_validation(env,data):
    c,_=env
    assert post(c,**data).status_code == 422

def test_replies_and_nested_conversations(env):
    c,_=env
    root=post(c,body='Primera',rating=3).json()
    reply=c.post('/stories/comments',headers=headers(2),json={'body':'Estoy de acuerdo','parent_id':root['id']}).json()
    assert reply['rating'] is None and reply['author_name']=='Lector 2'
    nested=post(c,body='Gracias',parent_id=reply['id'],anonymous=True)
    assert nested.status_code==201
    assert len(c.get('/stories/comments').json())==1
    assert c.get('/stories/comments',params={'parent_id':root['id']}).json()==[reply]
    assert post(c,body='Mal',parent_id=root['id'],rating=5).status_code==422
    assert post(c,body='No existe',parent_id=999).status_code==404

def test_character_authorization(env):
    c,_=env
    root=post(c,body='Buena',rating=5).json()
    data={'body':'Bienvenido a bordo','parent_id':root['id'],'character':'Andrew'}
    assert c.post('/stories/comments',headers=headers(),json=data).status_code==403
    assert c.get('/stories/comments/capabilities',headers=headers()).json()['characters']==[]
    assert 'Andrew' in c.get('/stories/comments/capabilities',headers=headers(3)).json()['characters']
    response=c.post('/stories/comments',headers=headers(3),json=data)
    assert response.status_code==201 and response.json()['author_name']=='Andrew'
    assert c.post('/stories/comments',headers=headers(3),json={**data,'character':'Inventado'}).status_code==403
    assert c.post('/stories/comments',headers=headers(3),json={**data,'anonymous':True}).status_code==422

def test_pagination_and_inactive_account(env):
    c,db=env
    for i in range(23): assert post(c,body=str(i),rating=1).status_code==201
    first=c.get('/stories/comments').json(); rest=c.get('/stories/comments?offset=20').json()
    assert len(first)==20 and len(rest)==3 and not {r['id'] for r in first}&{r['id'] for r in rest}
    db.get(StoriesReader,1).is_active=False; db.commit()
    assert post(c,body='No',rating=2).status_code==401
