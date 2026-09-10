"""Server-only, fixed-provider bridge. No URL or credential is accepted from a tenant."""
import json, os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from fastapi import HTTPException

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def connect_request(provider, path, method='GET', body=None):
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
