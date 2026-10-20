# Adaptación al esquema de oportunidades

## Arquitectura conservada

Se mantienen FastAPI, servicios, SDK de Supabase, las pantallas HTML/CSS y las utilidades JavaScript. No hay CRM, autenticación adicional ni creación de oportunidades desde FastAPI. n8n sigue iniciando la intención comercial y enviando el enlace.

`leads` identifica a la persona; `oportunidades` controla el acceso y el estado comercial; `visitas` guarda una primera visita por oportunidad.

## Acceso

La URL sigue siendo `/inmuebles/{token_uuid}`. Se busca el UUID en `oportunidades`, con su lead y estado relacionados. Una oportunidad se considera habilitada si tiene lead/estado válidos, `resultado IS NULL` y `fecha_cierre IS NULL`. Si cualquiera de los dos campos de cierre tiene valor, el token deja de habilitar catálogo, detalle y APIs personales. El usuario debe pedir un nuevo enlace por WhatsApp.

Las páginas de catálogo, detalle, formulario, confirmación e historial se validan en FastAPI antes de servirlas. Se entrega `acceso-invalido.html` con 404 para token incorrecto/inexistente y 403 para oportunidad cerrada. Cada endpoint de datos también valida acceso; abrir un HTML estático directamente nunca da acceso a propiedades o visitas.

El frontend usa `X-Opportunity-Token`. Se conserva `X-Lead-Token` como alias de compatibilidad, pero también se interpreta exclusivamente como token de **oportunidad**, nunca de lead. Si ambos encabezados difieren se devuelve 400. No se devuelven UUIDs de otras oportunidades, teléfonos, `user_id` ni credenciales.

## Endpoints

| Ruta | Adaptación |
| --- | --- |
| `GET /api/lead/contexto` | Ruta conservada. Resuelve la oportunidad y devuelve nombre del lead, estado comercial, `visita_id`, `puede_solicitar` y contacto de privacidad. Ya no consulta consentimiento ni token en leads. |
| `GET /api/propiedades` | Conserva filtros, paginación y catálogo completo de disponibles. Exige oportunidad abierta. |
| `GET /api/propiedades/filtros` | Mismas opciones reales; exige oportunidad abierta. |
| `GET /api/propiedades/{id}` | Mismo detalle/galería; exige oportunidad abierta. |
| `POST /api/visitas` | Resuelve oportunidad desde token, verifica duplicados y llama a `ru_solicitar_visita_oportunidad`. |
| `GET /api/visitas/actual` | Nuevo: visita asociada a la oportunidad actual. Devuelve 404 si todavía no existe. |
| `GET /api/visitas/mias` | Conserva historial del cliente mediante `visitas → oportunidades → leads`, con orden global y paginación en RPC. Incluye oportunidades históricas del mismo lead mientras el acceso actual esté abierto. |
| `GET /api/visitas/{id}` | Detalle limitado al lead de la oportunidad del token. Nunca acepta lead_id u oportunidad_id del navegador. |

Swagger/ReDoc/OpenAPI se mantienen. Las APIs usan modelos de respuesta que excluyen metadatos de reintento e información personal innecesaria.

## Solicitar y reintentar

Se conserva el cuerpo de solicitud: propiedad, nombre, fecha con offset de Lima, aceptación y UUID de reintento. No se aceptan `lead_id` ni `oportunidad_id` en el cuerpo.

FastAPI comprueba oportunidad abierta y visita existente. La RPC lo verifica de nuevo bajo bloqueo `FOR UPDATE` de la oportunidad, valida propiedad disponible y fecha futura, actualiza solo `leads.nombre`, inserta la visita con `oportunidad_id` y cambia el estado comercial a `visita_solicitada` en una misma transacción. Las fechas de agente/acordada quedan NULL; no se altera el resultado ni se cierra la oportunidad.

Se mantienen `request_id` y `request_hash` como dos columnas técnicas añadidas por migración. La misma clave y contenido recuperan la visita ya aceptada; una clave distinta para la misma oportunidad produce 409 con `visita_id`. La restricción UNIQUE de oportunidad impide otra visita incluso con claves diferentes o escrituras concurrentes. La interfaz muestra el enlace a la solicitud existente ante ese conflicto.

La fecha futura se comprueba en PostgreSQL después de reconocer un replay válido. Un reintento idéntico de una visita aceptada no se rechaza solo porque haya pasado su hora. Una oportunidad cerrada sí deja de autorizar acceso, incluso para reintentos.

### Consentimiento

El esquema suministrado ya no tiene `leads.consentimiento`, `consentimiento_at` ni `updated_at`. No se consultan ni escriben. Se conserva el checkbox y su validación como aceptación de la solicitud para no cambiar el formulario, pero **no se registra una evidencia persistente de consentimiento en este modelo**. No se añaden columnas comerciales para simular que sí existe. Si se necesita esa evidencia, hay que definir su persistencia aparte.

## Migración manual

1. Respaldar y revisar `sql/00_diagnostico.sql` (solo lectura).
2. Resolver manualmente oportunidades duplicadas abiertas, tokens repetidos, filas incompletas o huérfanas si aparecen. La migración aborta, no los borra ni reasigna.
3. Ejecutar **solo `sql/02_oportunidades.sql`**, no `01_migracion.sql`, que corresponde al modelo anterior. No se ejecutó SQL desde esta entrega.
4. Verificar que `estado_oportunidad` tenga exactamente un registro llamado `nuevo` y otro `visita_solicitada`. No se asumen IDs ni se crean catálogos ficticios.
5. Configurar `INITIAL_VISIT_STATE` con el nombre real del estado inicial de `estados_visita`. `REQUESTED_OPPORTUNITY_STATE` tiene por defecto `visita_solicitada`; es el estado comercial, distinto del estado inicial de la visita.
6. Desplegar backend y JavaScript coordinadamente con las nuevas RPCs.

La migración añade/verifica FK de visitas a oportunidad, las FK de oportunidad a lead/estado si faltan, corrige imágenes, elimina únicamente FK equivalentes redundantes de visita a propiedad y refuerza relaciones obligatorias. Asegura UUID generado y único, una visita por oportunidad y **una oportunidad abierta por lead**. Esta última regla permite reutilización atómica ante reintentos y preserva todas las oportunidades cerradas. Si la base contiene varias abiertas por lead, se detiene para revisión comercial.

RPCs nuevas: `ru_solicitar_visita_oportunidad`, `ru_mis_visitas_oportunidades`, `ru_obtener_o_crear_oportunidad`. También se conserva/define `ru_filtros_propiedades` para no depender de la migración antigua. Acceso exclusivo de `service_role`; revisar RLS de las tablas existentes por separado. El SDK privilegiado solo vive en FastAPI/n8n.

## Frontend

Se conservan estilos, logos, favicon y HTML existentes. Se añade solo la pantalla de acceso inválido. Catálogo y detalle muestran acceso a la visita existente sin restringir la exploración. El formulario bloquea una segunda solicitud y gestiona el 409 que puede llegar si otra pestaña envió primero. Historial/confirmación derivan un rótulo `Solicitud #ID` sin consultar un `visitas.nombre` inexistente y dejan de leer `visitas.motivo`.

## Pruebas y límites

Archivos modificados: `app/main.py`, `app/services.py`, `app/schemas.py`, `app/config.py`; `static/js/api.js`, `utils.js`, `catalogo.js`, `detalle.js`, `solicitar.js`, `visitas.js`; `sql/00_diagnostico.sql`, cabecera de `sql/01_migracion.sql`; `tests/test_app.py`, `tests/test_docs.py`, guardia de tests históricos en `tests/test_n8n.py`; `README.md` y `API_DOCUMENTACION.md`.

Archivos nuevos: `sql/02_oportunidades.sql`, `static/acceso-invalido.html`, `.env.example`, esta guía y `documentacion/N8N_OPORTUNIDADES.md`. No se cambia `.env`, las imágenes, CSS, favicon ni los HTML existentes.

Ejecutar `python -m unittest discover -s tests -v`. Los dobles de Supabase prueban el contrato HTTP y la resolución de relaciones, tokens abiertos/cerrados, aislamiento por lead, duplicados, replay y errores de carrera devueltos por la RPC. No equivalen a ejecutar transacciones concurrentes reales en PostgreSQL.

No se aplicaron migraciones ni se enviaron mensajes de WhatsApp. Debe comprobarse en una base de pruebas: dos envíos simultáneos con claves distintas dejan una visita, fallo de actualización de estado revierte la visita/nombre, dos exploraciones simultáneas reutilizan una oportunidad, cierre comercial permite otra oportunidad y no borra historial. No hay herramientas de compilación de frontend; validar JavaScript y UX en navegador/WhatsApp cuando esté disponible.

Los tests históricos del generador n8n se omiten si ese generador fue retirado. No se vuelve a crear por esta adaptación. Los ajustes del workflow se describen en `documentacion/N8N_OPORTUNIDADES.md` por nombre exacto de nodo.
