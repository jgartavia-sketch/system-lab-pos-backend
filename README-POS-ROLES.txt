SYSTEM LAB POS — DUEÑOS, EQUIPOS Y COMANDAS MÓVILES
Actualización 7 septiembre 2026. Requiere la entrega anterior del POS ya aplicada.
Base GitHub backend: fe89e0bcbe5a2dfa69cead77973cc1955e73ddea.

INSTALAR PRIMERO BACKEND
Desde PowerShell, dentro de system-lab-pos-backend, guardar el ZIP y ejecutar:
Expand-Archive ".\system-lab-pos-backend-equipos.zip" "." -Force
 git add app/pos/models.py app/pos/schemas.py app/pos/routes.py app/pos/permissions.py alembic/versions/e260907pos02_roles.py tests/test_pos.py tests/test_pos_roles.py README-POS-ROLES.txt
 git commit -m "Agrega roles por local y autorizaciones auditadas al POS"
 git push origin main

Render conserva DATABASE_URL y Start Command:
python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Debe ejecutar la migración e260906pos01 -> e260907pos02 y mostrar Application startup complete.
Después publicar el frontend de esta actualización y recargar las pestañas del POS.
No modifica contraseñas, ventas, existencias ni datos de Stories/client-control.
Las membresías preexistentes otorgadas por System Lab pasan a Dueño. Las nuevas creadas por el equipo tienen un rol explícito.
Si se habían creado empleados con la versión anterior, revisar sus permisos de dueño en Panel System Lab antes de usarlos.

JERARQUÍA
- Panel System Lab (antes Administración CEO): solo cuenta CEO. Crea locales y cuentas de dueños; asigna múltiples locales del mismo tipo o de tipos distintos a una cuenta. Sus checkboxes asignan propiedad, no roles de empleado.
- Dueño: opera sus locales; desde Mi equipo crea, vincula, cambia permisos y retira empleados por local. No crea otros dueños ni locales: eso corresponde a System Lab como proveedor.
- Administrador: productos/precios, inventario, caja, reportes, devoluciones, cocina y códigos de autorización. No gestiona empleados.
- Cajero: pedidos, clientes, agenda y caja. Cobro de ventas activable por el dueño.
- Salonero: mesas, pedidos, clientes, agenda, enviar/entregar comandas; cobro activable por el dueño. Sin catálogo editable, inventario, arqueos, reportes ni devoluciones.
- Cocina: consulta comandas y cambia preparación/listo/entregado. Sin cobros, gestión de empleados o catálogo.
Cada local tiene permisos independientes. El mismo empleado puede ser salonero en uno y cajero en otro.
Un empleado existente solo puede vincularse si ya pertenece al equipo de alguno de los locales del dueño. Correos de cuentas ajenas requieren intervención de System Lab.
Retirar acceso afecta ese local inmediatamente en el servidor, incluso con una sesión ya iniciada. Conserva historial y otros accesos.
Restablecer contraseña revoca sesiones; el dueño solo puede hacerlo si todos los accesos de la cuenta están dentro de sus locales. Si no, corresponde a System Lab.

AUTORIZACIÓN DE PRECIOS
1. Dueño/administrador: Mi cuenta -> Código para autorizar precios. Elegir 6-12 dígitos y confirmar con su contraseña.
2. El salonero puede proponer otro precio unitario o descuento. Para guardar, debe indicar motivo y el responsable debe ingresar correo + código personal.
3. El servidor valida cuenta activa, rol y local. La autorización se procesa con el pedido y queda auditada con solicitante, responsable, pedido, precios, cantidad y motivo.
4. El catálogo no cambia: solo el precio de esa venta. Modificar el catálogo requiere rol dueño/administrador.
5. Un dueño/administrador que ajusta su propia venta registra motivo; la auditoría lo identifica como responsable.
6. Código guardado con hash scrypt; nunca en respuestas o auditoría. Tras cinco fallos se bloquea 15 minutos. Retirar/degradar el rol invalida su autorización.
7. Editar otra vez un pedido con precios especiales exige nueva autorización. El código se limpia del formulario tras cada intento.
Autorizaciones muestra los últimos 200 registros por local. No hay borrado de auditoría desde la aplicación.

COMANDAS Y COBROS
Guardar y enviar a cocina es una sola operación. Cocina consulta cambios cada 5 segundos mientras su panel está abierto y conectado.
Estado de cocina separado del pago: se puede cobrar antes de terminar la preparación; la comanda permanece hasta Marcar entregado.
Ver comanda / Imprimir comanda abre la vista imprimible del navegador. No vuelve a enviar ni duplica pedidos.
La impresión física depende del teléfono, navegador y configuración de impresora; no incluye conexión automática Bluetooth/USB/ESC-POS ni impresión silenciosa.
Los códigos de intento evitan duplicados de creación y el cobro se protege por ID de pedido. Ediciones desactualizadas de otro dispositivo se rechazan.
Se conserva una caja compartida por local. Un salonero puede cobrar si está autorizado, pero no abrir/cerrar caja.
SINPE/tarjeta/transferencia son registros de pagos confirmados externamente, no una pasarela.

PRUEBAS
41 pruebas de backend aprobadas: regresión, múltiples locales, aislamiento, escalada de permisos, cobros, retiro de acceso con sesión activa, autorizaciones correctas/incorrectas, bloqueo PIN, auditoría, costos ocultos, cambios concurrentes obsoletos, cocina de pedido pagado y restablecimiento seguro.
SQL de toda la cadena Alembic ejecutado en PostgreSQL WASM (PGlite); además migración incremental en SQLite para el navegador de pruebas.
Navegador Chromium con API FastAPI local real: dueño con dos restaurantes, creación/vinculación/retiro de empleados, PIN, salonero móvil con precio autorizado, comanda, cobro y cocina después del pago, auditoría.
Pantallas 320, 360, 390, 768 y 1440 px revisadas; no desbordamiento horizontal de página en las vistas probadas.
No se probó una impresora física ni carga concurrente en PostgreSQL nativo ni el despliegue final de Render/Vercel.
Para repetir: python -m pytest -q tests/test_pos.py tests/test_pos_roles.py

Esta entrega agrega los controles descritos. Permanecen fuera de alcance facturación electrónica, offline, recetas/ingredientes, división de cuentas, pagos mixtos, impresión automática y especializaciones avanzadas de cada rubro.
