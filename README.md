# Raíz Urbana Inmobiliaria

Demo comercial de catálogo y solicitudes de visitas desde enlaces personalizados de WhatsApp. Python/FastAPI + Supabase PostgreSQL + HTML/CSS/JavaScript vanilla. No requiere compilación de frontend.

## Estado real de la entrega

El repositorio de destino contenía únicamente un README. Se implementaron backend, cinco vistas, estilos compartidos, galería, filtros, formulario, confirmación, consulta de visitas y RPCs de persistencia.

**No se proporcionaron credenciales, DDL de Supabase, estados reales ni el archivo `logotipo-inmobiliaria.png`.** Las migraciones están preparadas, no aplicadas. No se afirma que la conexión o la persistencia se hayan verificado contra una base real. El código no utiliza las credenciales del proyecto del restaurante.

No hay propiedades ni leads ficticios incorporados. La portada usa una ilustración arquitectónica en CSS, no una fotografía de inmueble inventado. El catálogo muestra exclusivamente registros de Supabase. Una marca tipográfica provisional reemplaza al logotipo pendiente.

## Arquitectura

```text
app/
  main.py       # Rutas, seguridad HTTP y respuestas sanitizadas
  config.py     # Variables de entorno
  db.py         # Cliente Supabase del servidor
  schemas.py    # Contratos Pydantic
  services.py   # Resolución del lead, normalización y contrato RPC
static/
  catalogo.html
  detalle.html
  solicitar-visita.html
  confirmacion.html
  mis-visitas.html
  inicio.html   # Entrada sin token
  css/          # Base, catálogo y detalle/formulario
  js/           # API, utilidades y comportamiento de cada vista
  img/placeholder.svg
sql/
  00_diagnostico.sql
  01_migracion.sql
tests/test_app.py
```

No se crea ningún lead al abrir la web. n8n debe crearlo previamente y compartir `/inmuebles/{token_uuid}`. El frontend transmite el token mediante `X-Lead-Token` para las APIs. FastAPI lo resuelve contra `leads`; nunca acepta un `lead_id` del navegador.

La visita se crea únicamente al enviar el formulario. La RPC bloquea el lead, resuelve reintentos, valida propiedad y fecha, actualiza nombre/consentimiento e inserta la visita en la misma transacción. No establece fechas del asesor ni fecha acordada.

## Antes de configurar Supabase

Ejecutar **solo** `sql/00_diagnostico.sql` en el SQL Editor del proyecto correcto y revisar el resultado. La consulta incluye tipos, restricciones, estados, duplicados de tokens, imágenes huérfanas, políticas y triggers.

Supuestos que deben verificarse:

1. Las tablas y columnas son las indicadas en el requerimiento. Los IDs son enteros (integer o bigint), no UUID. `visitas.id` tiene identity/secuencia.
2. `leads.token_uuid` es UUID y único. La migración abortará si encuentra tokens duplicados; no elimina datos para resolverlos.
3. `fecha_cliente`, `fecha_agente`, `fecha_acordada` y `consentimiento_at` son `timestamptz`. Las fechas del asesor y acordada permiten NULL y no tienen defaults que confirmen una visita.
4. Existen las FK `propiedades.distrito_id → distritos.id`, `visitas.lead_id → leads.id`, `visitas.propiedad_id → propiedades.id` y `visitas.estado_id → estados_visita.id`. PostgREST debe poder resolver los embeddings sin ambigüedad. No se intenta inventar relaciones alternativas.
5. `nombre` de visitas significa código visible de solicitud. Se genera `VIS-000001`, sin confundirlo con el nombre del lead. Revisar triggers y restricciones si el sistema existente asigna sus propios códigos.
6. El nombre configurado en `INITIAL_VISIT_STATE` corresponde **exactamente a un único estado existente**. No se asume su ID, ni se crean estados automáticamente. Si falta, incorporar el estado mediante una migración consensuada con n8n o configurar el apropiado.
7. El campo `motivo` de visita contiene información apta para el cliente. Si los flujos lo usan para notas internas, no debe exponerse sin adaptar el contrato.
8. Los triggers existentes son compatibles con la actualización del lead y la inserción de visitas. FastAPI no añade notificaciones externas.

Tras revisar, aplicar `sql/01_migracion.sql`. Toda la migración está dentro de una transacción. Corrige la FK descrita erróneamente como `propiedad_imagenes.id → propiedades.id` y agrega `propiedad_id → propiedades.id` si falta. Los huérfanos deben corregirse previamente; no se borran automáticamente. Si el esquema difiere, adaptar la migración antes de ejecutarla.

La migración añade solo `visitas.request_id`, `visitas.request_hash`, índices y funciones. Conserva las entidades del modelo. Las RPCs se revocan para `public`, `anon` y `authenticated` y se conceden a `service_role`; no modifican las políticas RLS existentes. Revisar que las tablas tampoco expongan datos personales mediante otras APIs.

Para imágenes, cargar URLs HTTPS reales de Supabase Storage en `propiedad_imagenes.url` y definir la secuencia con `orden`. No se clasifican fotos mediante atributos inventados. Sin imagen o ante errores aparece un SVG de respaldo. Las miniaturas intentan transformación de Supabase; si el plan no la soporta vuelven al original. En ese caso, usar archivos ya optimizados para evitar descargas grandes.

## Configuración y ejecución local

Desde la raíz de **este** repositorio, con Python 3.14:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Completar `.env` con el proyecto inmobiliario correcto. `SUPABASE_SECRET_KEY` es la credencial privilegiada del servidor, nunca una variable de JavaScript. `PRIVACY_CONTACT` debe completarse antes de usar datos reales.

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Abrir `http://localhost:8001`. La portada explica cómo acceder mediante el enlace de WhatsApp. Para recorrer el flujo real abrir `http://localhost:8001/inmuebles/TOKEN_EXISTENTE_DEL_LEAD`.

La configuración ausente produce errores comprensibles; no sustituye Supabase por almacenamiento temporal. Se usa HTTPS para la demo en teléfonos: el formulario utiliza Web Crypto para su clave de idempotencia y los enlaces son secretos. Localhost permite pruebas de desarrollo.

### Docker

```powershell
docker compose up --build
```

Disponible en `http://localhost:8001`. Compose utiliza el puerto 8001 del host para no interferir con la demo del restaurante en 8000. `.env` se inyecta en ejecución y está excluido del contexto de construcción.

## API

Todas las rutas de datos requieren `X-Lead-Token: UUID` salvo `/api/health`.

| Método y ruta | Uso |
| --- | --- |
| `GET /api/lead/contexto` | Nombre, consentimiento y contacto de privacidad |
| `GET /api/propiedades/filtros` | Opciones reales de filtros mediante DISTINCT en PostgreSQL |
| `GET /api/propiedades` | Propiedades disponibles filtradas y paginadas |
| `GET /api/propiedades/{id}` | Detalle e imágenes ordenadas |
| `POST /api/visitas` | Escritura transaccional e idempotente |
| `GET /api/visitas/mias` | Visitas del lead, orden global y paginación en PostgreSQL |
| `GET /api/visitas/{id}` | Una visita limitada al lead del token |
| `GET /api/health` | Proceso disponible; no comprueba conexión con Supabase |

Filtros: `tipo_operacion`, `tipo_inmueble`, `distrito_id`, `precio_min`, `precio_max`, `dormitorios_min`, `moneda`, `offset`, `limit`. Los rangos de precio requieren moneda para evitar comparar soles y dólares como si fueran equivalentes.

Ejemplo de cuerpo de visita (sustituir ID y fecha por valores válidos):

```json
{
  "propiedad_id": 1,
  "nombre": "Nombre del cliente",
  "fecha_cliente": "2030-01-15T15:00:00-05:00",
  "consentimiento": true,
  "request_id": "4db69d2c-5290-4a2a-b0fa-98ac17d3cad4"
}
```

La fecha debe ser futura y tener offset de Lima `-05:00`. La RPC valida el futuro usando el reloj de PostgreSQL. El reintento de una solicitud ya aceptada se reconoce antes de validar fecha/disponibilidad: puede recuperarse aunque haya pasado la hora o cambiado la propiedad. Reutilizar la misma clave con datos diferentes produce 409.

El navegador guarda en sessionStorage solo el hash de los datos y la clave aleatoria del envío, no nombre, token o fecha. Así un timeout no genera una segunda visita al reintentar el mismo cuerpo en la misma pestaña. No se impide que una persona solicite voluntariamente otra visita con una nueva clave; no existe una regla de exclusividad de horarios.

## Frontend y accesibilidad

- Catálogo de 1/2/3 columnas, filtros combinables y paginación.
- Tokens fuera de query strings de API y fuera del almacenamiento del navegador.
- Textos dinámicos mediante nodos DOM y `textContent`; sin `innerHTML` con contenido de Supabase.
- Consultas cancelables, tiempo máximo de espera y descarte de respuestas antiguas.
- Skeletons y estados de vacío, error y éxito.
- Galería con miniaturas diferidas, navegación táctil, botones, teclado y ampliación con `dialog` nativo.
- Controles de al menos 44 px, modo claro, movimiento reducido y barra móvil con safe area.
- Formulario precargado, consentimiento explícito, zona de Lima y bloqueo del envío mientras está pendiente.
- Mis visitas se actualiza manualmente; no hace polling ni agrega edición/cancelación/reprogramación sin reglas.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas usan dobles de Supabase y TestClient: verifican tokens, aislamiento entre leads, campos extra, consentimiento, zona horaria, filtros, huella idempotente, contrato de la RPC, orden de imágenes y entrega de vistas/cabeceras. **No demuestran ejecución de PostgreSQL, rollback ni concurrencia real de la RPC.**

Verificación manual con Supabase configurado:

1. Token inexistente: no mostrar datos ni aceptar escritura.
2. Token A: solo ver solicitudes de A; consultar una visita de B debe devolver 404.
3. Aplicar filtros combinados y rangos en una moneda; verificar resultados y estado vacío.
4. Abrir fichas con varias imágenes, sin imágenes y con imágenes rotas.
5. Enviar fecha pasada, consentimiento ausente y propiedad que acaba de deshabilitarse: no crear visita.
6. Enviar dos solicitudes concurrentes con la misma clave/cuerpo: verificar una única fila y replay.
7. Reutilizar clave con cuerpo diferente: verificar 409 y ninguna escritura adicional.
8. Comprobar que nombre, consentimiento y visita se confirman juntos; inducir un fallo de restricción y comprobar rollback.
9. Confirmar que `fecha_agente` y `fecha_acordada` siguen NULL y se utiliza el estado real configurado.
10. Probar Android/iPhone dentro de WhatsApp, teclado virtual, 320 px, galería, foco y orientación.

## Límites pendientes

- Conectar el proyecto real y revisar/aplicar SQL; probar persistencia y concurrencia contra PostgreSQL.
- Incorporar el PNG del logotipo y fotografías reales; comprobar el diseño en navegador.
- Configurar contacto/texto de privacidad según el uso efectivo antes de recoger datos reales.
- Deshabilitar o redactar logs de rutas en proxy/hosting/APM: el token está en la URL de navegación. Uvicorn ya arranca con `--no-access-log`, se usa `no-referrer` y respuestas `no-store`.
- Revisar expiración/rotación de tokens si se amplía el uso. El esquema recibido no incluye vencimiento.
- No hay CRM, panel administrativo, pagos, calendario de disponibilidad ni mensajería nueva.

No se publica automáticamente en Sites: el requerimiento fija FastAPI/Uvicorn/Docker y PostgreSQL externo, y el repositorio se entrega para ejecución local. El hosting de Sites utiliza Workers y no ejecuta este servidor Python.
