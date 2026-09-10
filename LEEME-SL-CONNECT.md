Repositorio de este ZIP: **system-lab-pos-backend**

Base GitHub comprobada: `ff12bddf435e40a4e4749bd40f370344a9215eb3`.

# POS, finanzas y Shirley’s SL Connect — 9 de septiembre de 2026

Esta actualización se entrega en cuatro ZIPs. Cada uno contiene archivos completos nuevos o modificados para su repositorio actual. Extraé cada ZIP en la raíz del repositorio indicado, conservando las carpetas app/, src/ y alembic/ según corresponda. No sustituyas el repositorio por el ZIP: los archivos que no cambiaron no están incluidos. No incluye bases de datos, contraseñas reales, archivos .env, node_modules ni dist.

## Orden de publicación y configuración

1. En Render, configurá `SHIRLEYS_CONNECT_KEY` con el MISMO valor aleatorio de al menos 32 caracteres en **shirleys-backend** y **system-lab-pos-backend**. Es una clave exclusiva de servidor a servidor: nunca debe ir en Vercel, código Angular, GitHub ni archivos públicos. Podés generar una en tu equipo con:

   `python -c "import secrets; print(secrets.token_urlsafe(48))"`

2. En **shirleys-backend**, configurá también `SHIRLEYS_ADMIN_PASSWORD` (al menos 8 caracteres). `SHIRLEYS_ADMIN_EMAIL` es opcional; su valor predeterminado es `admin@shirleyscr.com`. Esta es la cuenta administrativa del sitio de Shirley’s, independiente de la cuenta del POS. Se eliminó la validación simulada del navegador: el acceso y los cambios de puntos ahora se autorizan en el servidor. La firma de la sesión deriva de la clave privada anterior; opcionalmente podés configurar `SHIRLEYS_ADMIN_SECRET` con otra clave de al menos 32 caracteres. Cambiar contraseña o clave invalida las sesiones administrativas anteriores. El acceso de staff y las cuentas de clientes del sitio conservan sus rutas.

3. Publicá **shirleys-backend** y **system-lab-pos-backend**, cada uno desde su propia terminal. Esperá la finalización de ambos despliegues.

4. En **system-lab-pos-backend**, conservá la DATABASE_URL actual y el Start Command que ejecuta la migración antes de iniciar:

   `python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`

   La nueva revisión es `e260909pos03`, después de `e260907pos02`. Agrega columnas y tablas; no recrea la base ni restablece cuentas. No ejecutes downgrade para actualizar. En **shirleys-backend** no hay Alembic: su inicio agrega columnas/tablas si faltan y conserva los pedidos y clientes existentes. Ambos utilizan sus dependencias actuales de Python.

5. Publicá **shirleys-frontend** y **system-lab-pos-frontend**. La primera publicación de frontend corrige el empaque de Pizza Birria y usa el nuevo acceso administrativo. Recargá las pestañas después del despliegue. Durante la actualización, un frontend antiguo de Shirley’s puede recibir rechazo del precio de empaque o pedir iniciar sesión de nuevo hasta actualizarse.

## Crear la cuenta solicitada y cargar el catálogo

La cuenta real todavía NO fue creada desde esta entrega: requiere los nuevos endpoints desplegados y tu sesión CEO.

- Entrá en `https://systemlabcr.com/admin/clientes` con tu acceso de System Lab y, en **Usuarios y locales del POS**, ingresá con la cuenta CEO del POS si se solicita.
- Abrí **Configurar Shirley’s · POS + SL Connect**.
- Indicá el nombre del dueño, el correo solicitado en la conversación, su contraseña inicial y el número real de mesas. La contraseña no está prellenada ni incluida en estos archivos.
- Presioná **Crear Shirley’s con su catálogo**. Es una operación única que crea cuenta, local, membresía de dueño, enlace privado y 68 productos. Si repetís el mismo alta, no duplica registros ni restablece la contraseña.
- Si el correo ya existe sin este enlace, el servidor avisa y conserva su cuenta; no reemplaza sus locales automáticamente.
- El dueño puede entrar al POS restaurante. Sus empleados se crean desde Mi equipo. El dueño no puede crear nuevos locales ni asignarse otros sitios.

## Catálogo y precios

Se extrajeron del menú de `jgartavia-sketch/shirleys-frontend`, commit `bd95e74ee1659d5c94f3819fa11aaede0c66842d`, archivo `src/app/pages/menu/menu.html`.

- **68 productos / 8 categorías** con sus nombres y precios publicados.
- Para llevar y express: ₡200 de empaque por unidad; **Orden familiar (20 tacos)** y **Pizza Birria (8 slices)** usan ₡400 por unidad. Se corrigió la comparación del nombre de pizza, que antes no reconocía su sufijo.
- Consumo en el local: sin empaque, con el 10% de servicio indicado en el menú. El POS muestra el servicio separado y no lo presenta como utilidad del negocio.
- Se mantienen los precios visibles del menú con impuesto adicional configurado en 0. Esto conserva los importes publicados; no representa una validación fiscal. Revisá la configuración del negocio antes de usarlo para tu operación fiscal.
- El sitio no tiene una tarifa de reparto en su cálculo actual. No se inventa ni se agrega una tarifa automática de express; se conserva el flujo de coordinación por WhatsApp.
- El menú no publica costos de producción ni existencias. Los productos se cargan **con costo pendiente de revisar** y **sin seguimiento de existencias**, evitando inventar márgenes o stock. Completá los costos en Productos antes de vender; activá seguimiento y cargá existencias en Inventario cuando corresponda.
- Los costos se guardan con cada pedido. Cambiar el costo de un producto afecta próximos pedidos y no reescribe ventas históricas. El panel avisa si las ventas del período contienen costos sin revisar.
- El alta es una carga inicial, no una sincronización que sobreescribe el catálogo. Si cambiás precios, nombres o empaques en el sitio, actualizá también sus catálogos de servidor y el POS. Los snapshots están en `app/catalogs/shirleys.json` (Shirley’s) y `app/pos/catalogs/shirleys.json` (System Lab).

## Ingresos, gastos y utilidad

El menú del dueño y administrador incluye **Ingresos y gastos**; el gráfico del panel tiene tres líneas: ingresos operativos, salidas por costos/gastos y utilidad estimada.

- Se pueden registrar gastos operativos, compras de inventario/insumos, otros ingresos operativos, aportes/financiamiento y retiros del dueño.
- Campos: monto, categoría, fecha/hora de Costa Rica, medio de pago, proveedor/beneficiario, referencia y descripción.
- Los movimientos fuera de caja funcionan aunque la caja esté cerrada. Si pagás en efectivo desde la caja abierta, marcá la casilla correspondiente; se comprueba el saldo y el registro se enlaza una sola vez al efectivo.
- Compras de inventario son salidas de dinero; la utilidad reconoce el costo al vender. No se descuentan la compra y el costo de venta dos veces. Las cantidades de inventario se siguen registrando desde Inventario; no se agrega un sistema de recetas.
- Ingresos operativos = ventas cobradas sin impuestos ni servicio + otros ingresos operativos. Costos y gastos = costo histórico de lo vendido + gastos operativos. Utilidad estimada = ingresos operativos − costos y gastos.
- El **flujo de dinero** muestra entradas/salidas reales registradas por todos los medios, incluidas compras, aportes y retiros. Es distinto de la utilidad y no representa un saldo bancario conciliado.
- No registres de nuevo como “otro ingreso” una venta que ya cobraste en POS. Los movimientos antiguos de Caja se conservan; sus egresos mantienen el tratamiento previo como gastos operativos.
- Las anulaciones conservan registro, motivo y auditoría. Un movimiento ligado a una caja cerrada no se anula cambiando el cierre histórico: la interfaz indica registrar un ajuste en la caja actual.
- Las devoluciones completas mantienen el criterio anterior: excluyen la venta de su fecha original. No se cambió su flujo de reintegro.

## Clientes, puntos y pedidos del sitio

En el Panel administrativo del local Shirley’s aparece **SL Connect** con:

- Clientes registrados, nuevos del período y saldo total de puntos.
- Búsqueda por nombre, correo, teléfono o código, con paginación.
- Sumar/restar puntos con motivo y saldo previsto. Se guarda quién hizo el ajuste, saldo anterior y saldo posterior. Un reintento de la misma operación no se suma dos veces; no se permite saldo negativo. Los datos siguen siendo los del sitio, no una copia independiente en el POS.
- Gráfica de cantidad de pedidos por origen: web, WhatsApp directo e historial sin clasificar; detalle por día de Costa Rica.
- Pedidos confirmados, pendientes/modificados, cancelados, para recoger y express; montos solicitados/confirmados, WhatsApp cobrado y ajustes manuales de puntos.
- Últimos 100 pedidos web del período, con importación al POS. Abrí caja, importá, revisá el pedido y luego enviá a cocina o cobrá. La importación conserva una referencia única y se puede reintentar sin duplicar la venta. Se copian cantidades, precios y datos de entrega disponibles. No se registra un cobro automático.

**Origen del pedido:** un pedido armado en la web y enviado por WhatsApp cuenta una sola vez como web. Un pedido recibido por chat directo se carga en Nueva venta eligiendo **WhatsApp directo**. No hay acceso automático a conversaciones de WhatsApp. Los pedidos históricos del sitio sin campo de origen se muestran sin clasificar, sin inventar atribuciones.

El monto confirmado en el sitio no equivale a ingreso cobrado. La confirmación/cancelación web y la operación del POS se conservan separadas; la importación no modifica el estado del sitio ni sincroniza automáticamente cambios posteriores. Revisá ambos estados cuando se cancele o modifique una orden ya importada.

Si un pedido antiguo tiene un total distinto al catálogo (por ejemplo, una pizza guardada antes de corregir su empaque), se rechaza la importación para evitar cobrar silenciosamente otro monto. El pedido original se conserva para revisión.

El acceso a finanzas, clientes del sitio y puntos requiere dueño/administrador de ese local. Los otros locales y empleados sin ese permiso no acceden a esos datos. La conexión está fijada a Shirley’s en el servidor y solo el CEO autoriza su alta.

## Comandos push

El archivo `ENTREGA-SL-CONNECT.json` contiene la lista exacta de esta entrega, su repositorio y mensaje de commit. El script `PUSH-SL-CONNECT.ps1` valida la carpeta/rama, verifica el código, agrega y confirma solamente esos archivos y ejecuta `git push origin main`. No hace force push.

Podés ejecutar `./PUSH-SL-CONNECT.ps1` desde la terminal del repositorio o copiar este bloque completo en PowerShell. Ejecutalo **una vez por repositorio**, en el orden de publicación anterior:

```powershell
$ErrorActionPreference = "Stop"
$entrega = Get-Content .\ENTREGA-SL-CONNECT.json -Raw | ConvertFrom-Json
$archivos = @($entrega.archivos)
$origen = git remote get-url origin
if ($LASTEXITCODE -ne 0) { throw "Abri la terminal del repositorio correspondiente." }
$esperado = [regex]::Escape("jgartavia-sketch/$($entrega.repositorio)")
if ($origen -notmatch "$esperado(\.git)?$") { throw "Este ZIP corresponde a $($entrega.repositorio)." }
if ((git branch --show-current) -ne "main") { throw "Selecciona main antes de publicar." }
if ($entrega.tipo -eq "frontend") {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de dependencias." }
    npm run build
} else {
    $python = @($archivos | Where-Object { $_.EndsWith(".py") })
    python -m compileall -q -- $python
}
if ($LASTEXITCODE -ne 0) { throw "La verificacion fallo; no se hizo commit ni push." }
git add -- $archivos
if ($LASTEXITCODE -ne 0) { throw "No se pudieron preparar los archivos." }
$cambios = git diff --cached --name-only -- $archivos
if ($LASTEXITCODE -ne 0) { throw "No se pudo revisar el cambio." }
if ($cambios) {
    git commit -m $entrega.mensaje -- $archivos
    if ($LASTEXITCODE -ne 0) { throw "El commit fallo; no se hizo push." }
}
git push origin main
if ($LASTEXITCODE -ne 0) { throw "El push fallo. Conserva tu commit y revisa el mensaje de Git." }
```

Los frontends ejecutan `npm ci` y `npm run build`; los backends verifican sintaxis Python. Las migraciones se ejecutan en el despliegue, no en el comando local de push. Si Git rechaza un push porque main avanzó, conservá el commit y revisá las diferencias antes de integrar; el script no sobrescribe el remoto.

## Validación de esta entrega

- System Lab backend: 48 pruebas existentes y 13 nuevas de finanzas, permisos, catálogo, importación y origen de pedidos, aprobadas.
- Shirley’s backend: 11 pruebas de autenticación, SQL, catálogo, precios, búsqueda, puntos, auditoría, reintentos y conservación de datos, aprobadas. Las pruebas SQL se ejecutaron en PostgreSQL WebAssembly (PGlite) aislado, con datos ficticios.
- System Lab frontend: 15 pruebas de las vistas POS, incluidas cantidades, fechas, datos atrasados, empaque/servicio y reintentos, aprobadas.
- Shirley’s frontend: 3 pruebas del nuevo flujo de pedidos, empaques y reintentos, aprobadas.
- Ambos frontends compilan en producción. Permanecen advertencias no bloqueantes de tamaño de bundles/estilos; no se relajaron los presupuestos para ocultarlas.
- Cadena de migraciones POS e instalación incremental `e260907pos02 → e260909pos03` ejecutadas en PostgreSQL aislado. Se verificó conservación de productos y una venta preexistente, valores predeterminados y nuevas tablas.
- Los 68 nombres/precios del snapshot coinciden con los del HTML del menú, y ambos catálogos de servidor son idénticos.
- No se hicieron cambios en las bases de producción, ni se publicó código, ni se ejecutaron pruebas de carga o de navegador sobre los sitios reales.

Para repetir pruebas de backend en un entorno local de pruebas, instalá `pytest` y `httpx` además de las dependencias existentes. En System Lab: `python -m pytest -q tests/test_pos.py tests/test_pos_roles.py tests/test_pos_dashboard.py tests/test_pos_connect_finances.py`. En Shirley’s: `python -m pytest -q tests`; configurá `TEST_DATABASE_URL` hacia una base PostgreSQL exclusiva de pruebas para ejecutar las pruebas SQL. Crean y eliminan un esquema aleatorio propio. Sin esa variable o `TEST_PGLITE_MODULE`, las pruebas SQL se omiten explícitamente. PGlite es opcional y solo para pruebas; no es una dependencia de producción.
