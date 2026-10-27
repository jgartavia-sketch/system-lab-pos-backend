"""Run in Render shell; dry-run by default, never sends email or resets a password."""
import argparse, hashlib, secrets, os, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select
from app.db.database import SessionLocal
from .models import Account, Business, Membership, ConnectLink, Activation
from .security import hash_password

def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.lower()) if not unicodedata.combining(c)).strip()

def provision(db, apply=False, renew=False, supplied_token=None):
    # Transaction advisory lock prevents concurrent first-time duplicate provisioning.
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy import text
        db.execute(text('SELECT pg_advisory_xact_lock(26102701)'))
    matches=list(db.scalars(select(Account).where(Account.email.ilike('eeacordero7@gmail.com')).with_for_update()))
    if len(matches)>1: raise ValueError('Cuentas ambiguas por mayúsculas/minúsculas; resolver manualmente.')
    account=matches[0] if matches else None
    link=db.scalar(select(ConnectLink).where(ConnectLink.provider=='zenit'))
    candidates=[b for b in db.scalars(select(Business)) if 'zenit' in normalized(b.name)]
    if link:
        business=db.get(Business,link.business_id)
        if any(b.id!=business.id for b in candidates): raise ValueError('Negocios Zenit ambiguos; resolver antes de continuar.')
    elif len(candidates)>1: raise ValueError('Más de un negocio Zenit; resolver manualmente.')
    else: business=candidates[0] if candidates else None
    if business and (business.mode!='salon' or not business.active): raise ValueError('Negocio existente incompatible o inactivo.')
    if account:
        links=list(db.scalars(select(Membership).where(Membership.account_id==account.id)))
        if account.ceo or any(not business or m.business_id!=business.id for m in links): raise ValueError('Cuenta con permisos incompatibles; no fue modificada.')
        if any(m.role!='owner' for m in links): raise ValueError('Rol existente distinto de owner; revisar manualmente.')
        if not links: raise ValueError('Cuenta existente sin asociación verificada; revisar manualmente.')
    print('Cuenta existente:',bool(account),'Negocio existente:',bool(business))
    if not apply: return None
    if not business:
        business=Business(name='Zénit Salón',mode='salon',tables=0,service_rate=0);db.add(business);db.flush()
    if not link: db.add(ConnectLink(business_id=business.id,provider='zenit'))
    if account:
        if not renew: return None  # Preserve all existing credentials and activation state.
        if account.active: raise ValueError('No se renueva activación de una cuenta activa.')
        activation=db.get(Activation,account.id)
        if not activation or activation.used_at: raise ValueError('Cuenta sin activación pendiente verificada.')
        token=supplied_token or secrets.token_urlsafe(48)
        activation.token_hash=hashlib.sha256(token.encode()).hexdigest()
        activation.expires_at=datetime.now(timezone.utc)+timedelta(hours=24)
        return token
    account=Account(name='Propietaria Zénit',email='eeacordero7@gmail.com',password_hash=hash_password(secrets.token_urlsafe(64)),active=False,ceo=False)
    db.add(account);db.flush()
    db.add(Membership(account_id=account.id,business_id=business.id,role='owner',can_pay=True))
    token=supplied_token or secrets.token_urlsafe(48)
    db.add(Activation(account_id=account.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(hours=24)))
    return token

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--activation-file');parser.add_argument('--renew-activation',action='store_true');parser.add_argument('--token-env');parser.add_argument('--check-connect',action='store_true')
    args=parser.parse_args()
    if args.check_connect:
        from .connect_client import connect_request
        catalog=connect_request('zenit','/catalog')
        if catalog.get('contractVersion')!=2:parser.error('El backend Zénit todavía no tiene el contrato 2 desplegado.')
        print('Conexión privada verificada:',{'contractVersion':2,'products':len(catalog['products']),'services':len(catalog['services'])})
    supplied=os.environ.get(args.token_env,'') if args.token_env else None
    if args.token_env:
        import re
        if not supplied or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',supplied):parser.error('La variable de activación debe contener un token aleatorio válido de al menos 43 caracteres.')
    if args.apply and not args.activation_file and not args.token_env:parser.error('Usá --token-env o --activation-file para una activación privada.')
    path=Path(args.activation_file) if args.activation_file else None
    if path and path.exists(): parser.error('El archivo ya existe; no se sobrescribe.')
    with SessionLocal.begin() as db:
        token=provision(db,args.apply,args.renew_activation,supplied)
        if token and path:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write('https://systemlabcr.com/pos/salon#activate='+token+'\n')
    with SessionLocal() as db:
        account=db.scalar(select(Account).where(Account.email.ilike('eeacordero7@gmail.com')))
        if account:
            members=list(db.scalars(select(Membership).where(Membership.account_id==account.id)))
            print('Estado verificado:', {'account_id':account.id,'active':account.active,'ceo':account.ceo,
                'memberships':[{'business_id':m.business_id,'role':m.role} for m in members]})
    print('Verificación completada.'  if not args.apply else 'Transacción confirmada. No se enviaron correos.')
if __name__=='__main__': main()
