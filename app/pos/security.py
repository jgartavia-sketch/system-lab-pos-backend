import hashlib, hmac, secrets
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings
from app.db.database import get_db
from .models import Account, SigningKey
bearer = HTTPBearer(auto_error=False)

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'
def verify_password(password, encoded):
    try:
        _, salt, expected = encoded.split('$')
        digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError): return False

def signing_key(db):
    key=db.get(SigningKey,1)
    if not key: raise HTTPException(503, 'Ejecutá las migraciones del POS.')
    return key.secret

def issue(account, db):
    return jwt.encode({'sub': str(account.id), 'ver': account.version, 'type': 'pos', 'exp': datetime.now(timezone.utc)+timedelta(hours=8)}, signing_key(db), algorithm='HS256')

def current(credentials: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    try:
        if not credentials: raise ValueError()
        p = jwt.decode(credentials.credentials, signing_key(db), algorithms=['HS256'])
        if p.get('type') != 'pos': raise ValueError()
        account = db.get(Account, int(p['sub']))
        if not account or not account.active or p.get('ver') != account.version: raise ValueError()
        return account
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Sesión vencida o no autorizada.')

def ceo(account=Depends(current)):
    if not account.ceo: raise HTTPException(403, 'Solo el CEO puede administrar accesos.')
    return account
