from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from test_pos import env,good,req,setup_sale,order
from app.pos import zenit_bridge as bridge
from app.pos.models import ConnectLink,BridgeOperation,Product

def linked(env):
    product=setup_sale(env,price=100,tax=0)
    with env[2].begin() as db:
        db.add(ConnectLink(business_id=1,provider='zenit'))
        p=db.get(Product,product['id']);p.remote_id=str(uuid4());p.remote_kind='product'
    return product

def test_lost_remote_response_recovers_and_blocks_drawer_close(env,monkeypatch):
    product=linked(env);saved=order(env,product);calls=[];applied={}
    def remote(provider,path,method='GET',body=None):
        calls.append(body['operationKey'])
        result=applied.setdefault(body['operationKey'],{'provider':'zenit','invoiceNumber':body['invoiceNumber'],'status':'PAID'})
        if len(calls)==1:raise HTTPException(502,'Lost response')
        return result
    monkeypatch.setattr(bridge,'connect_request',remote)
    assert req(env,f"/orders/{saved['id']}/pay",'post',{'method':'card'}).status_code==502
    op=good(req(env,'/state'))['bridge_pending'][0]
    assert req(env,'/register/close','post',{'amount':1000}).status_code==409
    assert req(env,f"/connect/zenit/retry/{op['id']}",'post',{},who=2).status_code==404
    good(req(env,f"/connect/zenit/retry/{op['id']}",'post',{}))
    assert len(set(calls))==1 and len(applied)==1
    assert not good(req(env,'/state'))['bridge_pending']
    assert good(req(env,'/state'))['orders'][0]['status']=='paid'

def test_stock_request_replays_after_local_commit(env,monkeypatch):
    product=linked(env);calls=[]
    def remote(*args):calls.append(args);return {'provider':'zenit','stock':25,'delta':5}
    monkeypatch.setattr(bridge,'connect_request',remote)
    body={'request_key':str(uuid4()),'kind':'entry','quantity':5,'reason':'Stock delivery'}
    path=f"/products/{product['id']}/stock"
    assert float(good(req(env,path,'post',body))['stock'])==25
    assert float(good(req(env,path,'post',body))['stock'])==25
    assert len(calls)==1
    assert req(env,path,'post',{**body,'quantity':6}).status_code==409

def test_definite_remote_rejection_keeps_sale_open(env,monkeypatch):
    product=linked(env);saved=order(env,product)
    def reject(*args):raise HTTPException(409,'No stock')
    monkeypatch.setattr(bridge,'connect_request',reject)
    assert req(env,f"/orders/{saved['id']}/pay",'post',{'method':'card'}).status_code==409
    state=good(req(env,'/state'));assert not state['bridge_pending'] and state['orders'][0]['status']=='open'
    with env[2]() as db:assert db.scalar(select(BridgeOperation.state))=='rejected'

def test_unmapped_new_product_is_not_duplicated(env):
    linked(env)
    assert req(env,'/products','post',{'name':'Duplicate','sku':'NEW','price':100}).status_code==409

def test_pos_forwards_current_booking_reply_and_proposal(env,monkeypatch):
    linked(env)
    appointment=str(uuid4());request_key=str(uuid4());calls=[]
    def execute(db,b,a,local_path,local_body,remote_path,remote_body,**kwargs):
        calls.append(remote_body)
        assert remote_body['responseMessage']=='Cambio de horario'
        assert remote_body['proposedDate']=='2027-01-10'
        assert remote_body['proposedTime']=='11:00'
        return {'provider':'zenit','appointment':{'id':appointment,'status':'CANCELLED'}},False
    monkeypatch.setattr(bridge,'execute',execute)
    path=f'/connect/zenit/appointments/{appointment}'
    body={'requestKey':request_key,'status':'CANCELLED','responseMessage':'Cambio de horario','proposedDate':'2027-01-10','proposedTime':'11:00'}
    good(req(env,path,'post',body))
    assert req(env,path,'post',body,who=2,bid=1).status_code==403
    assert len(calls)==1
