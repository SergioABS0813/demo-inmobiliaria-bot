# Panel de propiedades de Raíz Urbana

Ruta: **`/agente/propiedades`**. Herramienta interna para cargar la demo. No se añaden módulos de CRM ni se modifican n8n, leads, oportunidades o visitas.

## Preparación

1. Revisar y ejecutar manualmente `sql/03_admin_propiedades.sql` en el proyecto inmobiliario correcto. Requiere el esquema vigente con FK corregidas. No ejecutar la migración histórica `01_migracion.sql`.
2. Confirmar que el bucket existente **`imagenes-inmobiliaria-demo`** sea público para lectura: el catálogo usa URLs públicas, como antes. No hace falta conceder INSERT/UPDATE/DELETE a `anon` o `authenticated` en Storage. Las escrituras las hace FastAPI con la credencial privilegiada.
3. Configurar en Storage los MIME permitidos `image/jpeg`, `image/png`, `image/webp` y un máximo de 8 MB por archivo, compatible con la validación del backend. No se ha creado ni modificado el bucket automáticamente.
4. Mantener `SUPABASE_URL` y `SUPABASE_SECRET_KEY` del proyecto existente. Añadir a `.env`:

```text
ADMIN_USERNAME=agente
ADMIN_PASSWORD=TU_CONTRASEÑA
```

El valor mostrado es una indicación, no una contraseña para usar. Configurar un secreto propio. `.env` no fue modificado ni se copian credenciales a JavaScript. No se necesita una clave de Storage adicional.

5. Instalar las nuevas dependencias o reconstruir la imagen:

```powershell
pip install -r requirements.txt
# O, si se ejecuta con Docker:
docker compose up --build
```

## Acceso

Abrir `https://raizurbana.bestsolperu.com/agente/propiedades` después de desplegar. Para desarrollo local, `http://localhost:8001/agente/propiedades`.

El navegador solicita usuario y contraseña mediante HTTP Basic. El panel, consultas y escrituras administrativas verifican la credencial en FastAPI. Si faltan el usuario o la contraseña en la configuración, el panel queda deshabilitado (503); si no coinciden las credenciales introducidas, responde 401. Los tokens de agentes/oportunidades no se reutilizan como credenciales administrativas.

Usar HTTPS fuera de localhost. La autenticación Basic permanece en la sesión del navegador; no se implementa un sistema de cuentas o cierre de sesión. Una ventana privada facilita terminar la sesión cerrándola. El HTML del panel está en `app/templates`, fuera del directorio público estático.

Las escrituras requieren `X-RU-Admin: 1` y rechazan orígenes de otros hosts. El JavaScript lo envía automáticamente. En Swagger utilizar Authorize con HTTP Basic y ese encabezado. El resto del sitio conserva su política de acceso por oportunidad. Solo la respuesta HTML del panel permite `blob:` en imágenes para las miniaturas locales.

## Uso

1. Consultar el listado, buscar por título o filtrar por distrito y disponibilidad. Los desactivados se conservan y siguen siendo editables.
2. Pulsar **Nueva propiedad**, completar la información y elegir un agente/distrito de los registros existentes. Los distritos activos aparecen primero; los inactivos siguen disponibles y están identificados. No se aplica a ellos una regla de delivery.
3. Guardar. La respuesta devuelve el ID. Si no se marca disponibilidad, la nueva propiedad queda desactivada por defecto.
4. En **Fotografías y planos**, elegir categoría, seleccionar archivos y pulsar **Subir imágenes**. La categoría pertenece a esa selección; repetir para las demás categorías.
5. Cambiar la secuencia con ↑/↓ y pulsar **Guardar orden**. La primera imagen es la portada del catálogo; se conserva un único orden global, incluidas las imágenes antiguas y los planos.
6. Marcar disponibilidad y guardar cuando se quiera mostrar el inmueble. Aparecerá en el catálogo en su siguiente carga/consulta; no se añade polling ni se invalida una página que ya estuviera abierta.

Editar datos no sustituye imágenes. **Desactivar** actualiza exclusivamente disponibilidad, sin borrar la propiedad ni sus visitas. No existe endpoint para borrar físicamente propiedades.

## Imágenes

Las rutas se generan desde el ID devuelto por la propiedad:

```text
imagenes-inmobiliaria-demo/
  propiedad_123/
    vista_1/UUID-sala.jpg
    vista_2/UUID-dormitorio.webp
    plano/UUID-plano.png
```

Las categorías son hermanas. Storage utiliza prefijos virtuales: no hace falta crear carpetas ni objetos vacíos. Las categorías sin fotografías no necesitan existir.

Cada archivo recibe un UUID y un nombre saneado; se sube con sobrescritura deshabilitada. `propiedad_imagenes.url` conserva la convención existente: **URL pública HTTPS completa**. Cada archivo confirmado genera una fila con propiedad, categoría y orden. El frontend público conserva la secuencia por `orden` y reconoce los planos mediante su etiqueta y texto alternativo.

Formatos: JPEG, PNG, WebP estático. Límites: 8 MB y 24 megapíxeles por archivo; entre 1 y 6 archivos y hasta 24 MB por selección. Pillow comprueba el contenido real, dimensiones, integridad y correspondencia con el MIME declarado. No se admiten SVG, GIF, WebP animado ni archivos renombrados con contenido diferente. El backend valida toda la selección antes de iniciar subidas.

Si una subida de un lote falla, las imágenes que sí se registraron se conservan. Se muestran los fallos por archivo; seleccionar solo los fallidos para reintentar. No hay reintentos automáticos de POST. Ante timeout ambiguo, recargar las imágenes antes de repetir para evitar subir una fotografía dos veces.

### Datos existentes y eliminación

La migración añade `categoria TEXT` con `vista_1`, `vista_2`, `plano` o NULL. Solo infiere una categoría si la URL contiene una ruta conocida; las demás filas quedan **Sin clasificar**, sin alterar su URL u orden. No se trasladan archivos existentes ni se cambia su categoría manualmente al editar otros datos.

PostgreSQL y Storage no comparten una transacción. Para retirar una imagen:

1. Una RPC elimina la fila y encola la ruta del archivo en `propiedad_archivos_pendientes` dentro de la misma transacción.
2. FastAPI intenta eliminar el objeto y, si confirma éxito, retira su entrada de la cola.
3. Si Storage o la confirmación de DB fallan, la cola permanece. El listado muestra **Reintentar limpieza**; cada acción procesa hasta 20 entradas. No hay cron ni servicio adicional.

No se descargan ni eliminan URLs arbitrarias. Solo se eliminan objetos del bucket y host configurados, dentro de una carpeta reconocida de la propiedad seleccionada. Las URLs externas o rutas heredadas no reconocidas se desvinculan de la DB y conservan su archivo.

Si Storage acepta un archivo pero falla el registro en DB, se intenta retirarlo. Si la compensación falla, se encola para limpieza. Si también está caída la base y no puede guardarse la cola, se devuelve la ruta al administrador y se registra en el servidor para revisión manual. No se promete atomicidad distribuida cuando ambos servicios están caídos.

## Migración

`03_admin_propiedades.sql` es aditiva y transaccional. Incluye:

- Columna y restricción de categoría, conservando NULL para imágenes anteriores.
- Tabla técnica de limpieza pendiente con RLS habilitado y acceso solo de `service_role`.
- `ru_admin_registrar_imagen`: asigna el siguiente orden bajo bloqueo de la propiedad.
- `ru_admin_ordenar_imagenes`: comprueba que se envíen todos los IDs actuales, sin duplicados ni imágenes de otra propiedad; actualiza el orden en una transacción.
- `ru_admin_retirar_imagen`: retira la fila y registra la limpieza bajo el mismo bloqueo.

Los cambios de lista por subidas/eliminaciones simultáneas hacen que un orden desactualizado devuelva 409; recargar antes de reordenar. No se modifican ni eliminan relaciones de leads/oportunidades/visitas. No se ejecutó la migración desde esta entrega.

**Aplicar la migración antes de desplegar el backend**, porque la galería pública ahora consulta también `categoria`.

## Endpoints

Todos requieren HTTP Basic. Las mutaciones requieren también `X-RU-Admin: 1`.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/agente/propiedades` | HTML protegido del panel |
| GET | `/api/agente/opciones` | Distritos y agentes sin exponer sus tokens |
| GET | `/api/agente/propiedades` | Listado paginado, `q`, `distrito_id`, `disponible`, `offset`, `limit` |
| POST | `/api/agente/propiedades` | Crear y devolver el ID |
| GET | `/api/agente/propiedades/{id}` | Datos para editar |
| PATCH | `/api/agente/propiedades/{id}` | Actualización parcial de datos |
| PATCH | `/api/agente/propiedades/{id}/disponibilidad` | Activar o desactivar |
| GET | `/api/agente/propiedades/{id}/imagenes` | Fotos, categoría y orden |
| POST | `/api/agente/propiedades/{id}/imagenes` | Multipart: `categoria` y uno o varios `files` |
| PUT | `/api/agente/propiedades/{id}/imagenes/orden` | JSON `{"ids":[3,1,2]}` con toda la secuencia |
| DELETE | `/api/agente/propiedades/{id}/imagenes/{imagen_id}` | Retirar una imagen y limpiar su archivo administrado |
| GET | `/api/agente/archivos-pendientes` | Número de archivos en cola |
| POST | `/api/agente/archivos-pendientes/reintentar` | Reintentar hasta 20 limpiezas |

## Archivos

Backend nuevo: `app/admin.py`, `admin_auth.py`, `admin_schemas.py`, `admin_services.py`, `app/templates/agente_propiedades.html`.

Backend modificado: `app/main.py` registra el router, añade categoría a las consultas públicas y gestiona errores; `app/config.py` incorpora la credencial administrativa. No se modifican los servicios de oportunidades/visitas.

Frontend nuevo: `static/js/admin.js`, `static/css/admin.css`. Frontend modificado: `static/js/detalle.js` reconoce la categoría sin cambiar la secuencia de la galería. No se reemplazan las imágenes, el logo, los estilos ni los HTML públicos.

También se añaden la migración, `tests/test_admin.py`, las dependencias Pillow/python-multipart y la configuración del `.env` existente.

## Verificación

```powershell
python -m unittest discover -s tests -v
```

Pruebas con TestClient y dobles de DB/Storage: acceso y origen, propiedades opcionales, referencias inexistentes, conservación de fotos e historial al editar/desactivar, contenido real de imágenes, rutas únicas, lotes inválidos, compensación de fallos, cola/reintento y contrato de orden. No equivalen a probar transacciones reales de PostgreSQL ni a subir archivos al bucket.

Antes de la demostración, probar con la base y el bucket configurados: crear un inmueble, subir una imagen de cada categoría, cambiar portada, comprobar el catálogo con una oportunidad válida, editar sin perder fotos, eliminar una imagen y desactivar. Verificar que el bucket permita las URLs públicas y que el proxy admita solicitudes multipart de al menos 25 MB y el tiempo necesario de carga.

No se ejecutaron pruebas visuales en navegador, ni escrituras sobre la base/Storage reales, ni despliegue remoto. Se mantiene el límite de alcance: preparación de la demo, sin CRM ni modificaciones de n8n.


La configuración se lee del `.env` existente en la raíz del proyecto, independientemente del directorio desde el que se ejecute Uvicorn. No se requiere `.env.example`. Después de modificar `.env`, reiniciar el proceso; en Docker Compose recrear el contenedor con `docker compose up -d --force-recreate web` (si cambió el código, añadir `--build`).
