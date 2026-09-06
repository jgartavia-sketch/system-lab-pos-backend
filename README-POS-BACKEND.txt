SYSTEM LAB POS — BACKEND INTEGRADO PARA PRUEBAS
Base revisada: main 59190a034d23dcd307c78405335368289fbdcf43.

INSTALACIÓN (primero backend, después frontend)
1. Guardar system-lab-pos-backend-full.zip dentro de la carpeta del repositorio system-lab-pos-backend.
2. Abrir la terminal PowerShell en esa carpeta y ejecutar:

Expand-Archive ".\system-lab-pos-backend-full.zip" "." -Force
git add app/main.py app/pos alembic/env.py alembic/versions/e260906pos01_isolated_pos.py tests/test_pos.py README-POS-BACKEND.txt
git commit -m "Integra POS privado por negocio con caja ventas y cocina"
git push origin main

3. En Render, el Start Command debe ejecutar las migraciones antes del servidor:
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Si ya tiene ese comando, no cambiarlo. Esperar que el despliegue termine antes de subir frontend.
La DATABASE_URL existente se conserva. No requiere nuevas dependencias ni cambiar las cuentas de Stories.
Si CORS_ORIGINS se configuró manualmente en Render, debe incluir https://systemlabcr.com y https://www.systemlabcr.com.

CUENTA INICIAL
La migración crea jgartavia@gmail.com con la contraseña solicitada, guardada únicamente como hash scrypt.
Tiene administración CEO y acceso al negocio "Restaurante de prueba · System Lab" con 10 mesas.
Incluye tres productos DEMO, precios de ejemplo y 20 unidades de cada uno, solo en este negocio de prueba.
No crea ventas ni abre una caja automáticamente. Los ejemplos no representan existencias reales.
Las migraciones posteriores no restablecen la contraseña. Cambiarla desde Mi cuenta.
La firma de las sesiones usa una clave aleatoria generada en la base de datos, independiente de Stories.

CAPACIDADES
- Login, bloqueo temporal por intentos fallidos, cambio/restablecimiento de contraseña y revocación de sesiones.
- Solo CEO crea negocios/cuentas y asigna o suspende permisos. El CEO también necesita membresía para operar un negocio.
- Catálogo, categorías, códigos, precios, costos, impuesto configurable por producto, existencias y servicios sin stock.
- Clientes, mesas, mostrador, notas de pedido, estados de cocina, cobros e impresión de comprobante interno.
- Descuento general, control de stock al cobrar, reintentos idempotentes de pedido y cobro.
- Devolución total con reposición del stock. El reintegro externo al cliente es manual.
- Apertura, ingresos/egresos de efectivo, cierre y diferencia. Tarjeta/SINPE no inflan el efectivo esperado.
- Reportes por fecha de Costa Rica, métodos, productos, ticket promedio, margen estimado y exportación desde frontend.
- Agenda de citas/recepciones para servicios.

DATOS Y COMPATIBILIDAD
El POS privado usa tablas pos_* independientes. Los registros anteriores del POS legado no se transfieren automáticamente.
El sitio, Stories y client-management mantienen sus rutas y tablas.
Las rutas antiguas sin autenticación (/users, /sales, /products, /auth y demás rutas POS legadas) responden 410.
Las nuevas operaciones usan /pos-api y validan negocio, cuenta activa y sesión en el backend.
No usar las rutas antiguas para integrar clientes nuevos.
La caja operativa es una por negocio. Todas las mutaciones de ese negocio se serializan mediante bloqueo de fila en PostgreSQL.

ALCANCE DE ESTA ENTREGA
Es una versión integrada para pruebas de aceptación, con restaurante como primera operación validada.
Las cinco modalidades están disponibles por autorización y comparten el núcleo. La agenda y las referencias/notas cubren el flujo básico de servicios.
No incluye facturación electrónica, pasarela de tarjetas/SINPE, funcionamiento offline, recetas que consuman ingredientes, modificadores de helados, citas por empleado, diagnóstico vehicular estructurado, división de cuenta ni pagos combinados en un mismo pedido.
Un método de pago registrado no transfiere dinero; primero confirmar el cobro externamente.
Las devoluciones son completas y suponen que todos los productos vuelven al inventario. Registrar una salida posterior si corresponde a merma.
Los reportes excluyen ventas devueltas del período original. El margen utiliza costo histórico del pedido y egresos de caja, no contabilidad general.
La vista operativa conserva todos los pedidos abiertos y hasta 1000 pedidos recientes; movimientos y cajas muestran los últimos 1000. Los reportes consultan el rango completo de hasta 366 días.

PRUEBAS EJECUTADAS
- 26 pruebas de backend aprobadas con las dependencias del requirements.txt existente y Python 3.12.
- Cadena SQL completa de Alembic ejecutada en PostgreSQL WASM mediante PGlite, incluida cuenta inicial y secuencias.
- Aplicación FastAPI completa: login y compatibilidad del registro de modelos; rutas legadas bloqueadas.
- Navegador Chromium con API local real: login, producto, stock, mesa, cocina, cobro, comprobante, reporte y cierre con diferencia cero.
- Navegador: creación de cliente/cita y creación de negocio/cuenta desde CEO. Vista móvil revisada sin desbordamiento horizontal.
- No se han ejecutado pruebas contra tu base de Render ni contra la publicación real de Vercel, ni una prueba de carga/concurrencia en un PostgreSQL nativo.

REPETIR PRUEBAS LOCALES (no usa la base de producción)
python -m pip install pytest httpx
python -m pytest -q tests/test_pos.py

El ZIP contiene archivos completos para agregar/reemplazar en el repositorio existente. No sustituye el repositorio entero ni incluye .env.
