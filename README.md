# Raíz Urbana Inmobiliaria

Catálogo inmobiliario y solicitudes de visita desde enlaces personalizados de WhatsApp. FastAPI, Pydantic v2, Supabase PostgreSQL, HTML/CSS/JavaScript vanilla, Uvicorn y Docker. No requiere compilación de frontend.

## Modelo actual

```text
leads → oportunidades → visitas
          token_uuid     UNIQUE(oportunidad_id)
```

El lead identifica al cliente. Una oportunidad representa su intención comercial y contiene el token y estado comercial. Cada oportunidad admite como máximo una primera visita; las adicionales se coordinan con el asesor.

n8n identifica/registra al lead, crea o reutiliza una oportunidad abierta al seleccionar EXPLORAR INMUEBLES y envía `/inmuebles/{token_uuid}`. FastAPI no crea leads ni oportunidades al abrir el enlace. Se preservan oportunidades cerradas e historial.

Una oportunidad está abierta cuando `resultado` y `fecha_cierre` son NULL. `visita_solicitada` sigue abierta. Un enlace inválido o cerrado no permite consultar catálogo ni APIs personales. Un enlace abierto permite consultar también las visitas históricas del mismo lead.

## Preparar Supabase

Se utiliza el esquema actualizado proporcionado por el usuario. No se aplicaron cambios a una base real desde esta entrega.

1. Ejecutar y revisar **`sql/00_diagnostico.sql`**, de solo lectura.
2. Resolver las inconsistencias que señale: tokens duplicados, varias oportunidades abiertas por lead, visitas sin oportunidad o relaciones huérfanas. No se corrigen borrando historial automáticamente.
3. Revisar y ejecutar manualmente **`sql/02_oportunidades.sql`**. **No ejecutar `01_migracion.sql`: corresponde al modelo anterior.**
4. Verificar nombres reales de estados: `nuevo` y `visita_solicitada` en `estado_oportunidad`; configurar el estado inicial real de `estados_visita`.

La migración corrige las FK de imágenes y visitas, asegura un token único por oportunidad, una visita por oportunidad y una oportunidad abierta por lead. Añade únicamente `request_id` y `request_hash` como metadatos de idempotencia y las RPCs necesarias. Ante datos incompatibles, aborta la transacción sin eliminarlos.

La RPC de visita valida de nuevo bajo bloqueo, registra la visita, actualiza el nombre y cambia el estado de la oportunidad en una sola transacción. No llena fechas del asesor/acordada ni cierra comercialmente la oportunidad. Todas las RPCs privilegiadas quedan limitadas a `service_role`.

## Configuración

Crear `.env` a partir de `.env.example`, conservando la credencial de Supabase exclusivamente en el servidor:

```text
SUPABASE_URL=...
SUPABASE_SECRET_KEY=...
INITIAL_VISIT_STATE=Pendiente de coordinación
REQUESTED_OPPORTUNITY_STATE=visita_solicitada
PRIVACY_CONTACT=...
```

`INITIAL_VISIT_STATE` es el nombre exacto del estado inicial **de la visita** en `estados_visita`. `REQUESTED_OPPORTUNITY_STATE` es el nombre exacto del estado **comercial** en `estado_oportunidad`. Se buscan sus IDs en la base; no se fijan números ni se crean estados automáticamente.

El esquema nuevo no guarda consentimiento en leads. El checkbox existente se conserva como aceptación validada de la solicitud; no constituye evidencia persistente de consentimiento en esta base. Ver detalles en la documentación de adaptación.

## Ejecutar

Desde la raíz de este repositorio:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

O, con `.env` preparado:

```powershell
docker compose up --build
```

Abrir `http://localhost:8001/inmuebles/TOKEN_EXISTENTE_DE_OPORTUNIDAD`. Para teléfonos usar HTTPS. `/` solo explica el acceso desde WhatsApp. Las imágenes proceden de las URLs reales registradas en Supabase; no se incorporan propiedades ficticias.

## API y documentación

`/docs`, `/redoc` y `/openapi.json` siguen habilitados. En Swagger completar `X-Opportunity-Token` con un UUID de oportunidad abierta; no introducir credenciales de Supabase. `X-Lead-Token` sigue aceptándose como alias obsoleto, con la misma semántica de oportunidad.

Rutas conservadas: `/api/lead/contexto`, `/api/propiedades`, `/api/propiedades/filtros`, `/api/propiedades/{id}`, `/api/visitas`, `/api/visitas/mias`, `/api/visitas/{id}`. Nueva: `GET /api/visitas/actual`. `/api/health` informa del proceso, no de la conexión a Supabase.

## Verificar

```powershell
python -m unittest discover -s tests -v
```

Las pruebas HTTP usan dobles de Supabase, no escrituras en producción. Verifican acceso por oportunidad, cierre, historial entre oportunidades del mismo lead, aislamiento entre clientes, visita existente, replay y errores de carrera de la RPC. Los tests históricos del generador n8n se omiten si se retiró ese archivo.

La concurrencia y rollback reales requieren PostgreSQL de pruebas; el aspecto móvil y el flujo completo requieren navegador/WhatsApp. No se ha desplegado ni activado un workflow desde esta entrega.

## Documentación de los cambios

- [Adaptación y contratos](documentacion/ADAPTACION_OPORTUNIDADES.md): backend, frontend, endpoints, migración, archivos y límites.
- [Ajustes de n8n por nodo](documentacion/N8N_OPORTUNIDADES.md): orden de creación/reutilización y envío de token, columnas antiguas y teléfono obligatorio.
- [Swagger y CSP](API_DOCUMENTACION.md): carga de documentación sin relajar la CSP del catálogo.

No se genera un workflow de n8n ni se añaden módulos de CRM, autenticación, edición de visitas o notificaciones nuevas.
