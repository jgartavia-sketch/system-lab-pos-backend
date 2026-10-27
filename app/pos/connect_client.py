"""Server-only, fixed-provider bridge. No URL or credential is accepted from a tenant."""
import json, os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from fastapi import HTTPException

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def connect_request(provider, path, method='GET', body=None):
    if provider=='zenit':
        return zenit_request(path,method,body)
    if provider!='shirleys': raise HTTPException(503,'Integración no disponible.')
    key=os.environ.get('SHIRLEYS_CONNECT_KEY','')
    if len(key)<32: raise HTTPException(503,'System Lab debe configurar la conexión privada de Shirley’s.')
    request=Request('https://shirleys-backend.onrender.com/api/pos-connect'+path,
                    data=json.dumps(body).encode() if body is not None else None,method=method,
                    headers={'X-SystemLab-Key':key,'Content-Type':'application/json','Accept':'application/json'})
    try:
        with build_opener(NoRedirect()).open(request,timeout=18) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise HTTPException(502,'La respuesta del sitio excede el límite permitido.')
            return json.loads(raw)
    except HTTPError as error:
        status=error.code if error.code in (400,404,409,422,429) else 502
        try: message=json.loads(error.read(2048)).get('detail')
        except (ValueError,AttributeError): message=None
        if error.code in (401,403,503): message='System Lab debe revisar la conexión privada con Shirley’s.'
        raise HTTPException(status,message if isinstance(message,str) else 'El sitio no pudo completar la consulta.') from None
    except (URLError,TimeoutError,ValueError):
        raise HTTPException(502,'No se pudo conectar con Shirley’s. Reintentá en unos segundos.') from None


def zenit_request(path,method='GET',body=None):
    from urllib.parse import urlsplit, parse_qs
    from datetime import date
    parsed=urlsplit(path)
    import re
    allowed=(method=='GET' and (parsed.path in ('/catalog','/appointments','/customers','/orders') or re.fullmatch(r'/orders/[a-f0-9-]{36}',parsed.path))) or (method=='POST' and parsed.path in ('/sales','/sales/settle','/sales/reopen','/sales/void','/inventory','/catalog/update','/appointments','/appointments/update','/orders/cancel'))
    if not allowed or parsed.fragment or parsed.scheme or parsed.netloc: raise HTTPException(400,'Ruta privada no disponible.')
    key=os.environ.get('ZENIT_CONNECT_KEY','')
    base=os.environ.get('ZENIT_CONNECT_BASE_URL','').rstrip('/')
    url=urlsplit(base)
    # Deployment operator must verify this server-only origin; tenants cannot supply URLs.
    if len(key)<32 or url.scheme!='https' or not url.hostname or url.username or url.password or url.path not in ('','/') or url.query or url.fragment or url.port not in (None,443):
        raise HTTPException(503,'System Lab debe verificar y configurar el origen privado de Zénit.')
    request=Request(base+'/api/pos-connect'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'X-SystemLab-Key':key,'Accept':'application/json','Content-Type':'application/json'})
    try:
        with build_opener(NoRedirect()).open(request,timeout=18) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise ValueError()
            data=json.loads(raw)
            if not isinstance(data,dict) or data.get('provider')!='zenit': raise ValueError()
            return data
    except HTTPError as error:
        status=error.code if error.code in (400,404,409,422,429) else 502
        try: message=json.loads(error.read(2048)).get('error')
        except (ValueError,AttributeError): message=None
        raise HTTPException(status,message if isinstance(message,str) and status<500 else 'No se pudo completar la conexión privada con Zénit. Reintentá la operación pendiente.') from None
    except (URLError,TimeoutError,ValueError):
        raise HTTPException(502,'No se pudo conectar con Zénit. Reintentá la operación pendiente.') from None
