"""Server-side permissions; every request rechecks the current local membership."""
from fastapi import HTTPException
from sqlalchemy import select
from .models import Membership

def membership(db, account_id, bid):
    return db.scalar(select(Membership).where(Membership.account_id==account_id, Membership.business_id==bid))

def permissions(m):
    manager=m.role in ('owner','admin')
    return dict(role=m.role, team=m.role=='owner', manage=manager,
                sell=m.role in ('owner','admin','cashier','waiter'),
                pay=manager or (m.role in ('cashier','waiter') and m.can_pay),
                cash=manager or m.role=='cashier', kitchen=True,
                prepare=manager or m.role=='kitchen', pin=manager,
                pin_configured=bool(m.pin_hash))

def enforce(request, m):
    p=permissions(m)
    tail=request.url.path.split('/business/',1)[1].split('/',1)[1]
    area=tail.split('/')[0]
    allowed=False
    if area=='state': allowed=request.method=='GET'
    elif area=='team': allowed=p['team']
    elif area in ('audit','reports','products','finances','connect'): allowed=p['manage']
    elif area=='pin': allowed=p['pin']
    elif area in ('cash','register'): allowed=p['cash']
    elif area in ('customers','appointments'): allowed=p['sell']
    elif area=='orders':
        if tail.endswith('/pay'): allowed=p['pay']
        elif tail.endswith('/refund'): allowed=p['manage']
        elif tail.endswith('/status'): allowed=p['sell'] or p['prepare']
        else: allowed=p['sell']
    if not allowed: raise HTTPException(403, 'Tu rol no permite esta operación en este local.')
