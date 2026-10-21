# Panel de agentes

Acceso: `/agente/{token_uuid}`. Usa `agentes.token_uuid`, no el token de una oportunidad. No concede acceso al CRUD administrativo.

Swagger agrupa las rutas bajo **Agentes**. Las APIs `/api/agentes/contexto` y `/api/agentes/visitas` requieren `X-Agent-Token`. Cada consulta valida nuevamente el token y filtra en Supabase por igualdad exacta de `agentes.especialidad` con `propiedades.tipo_inmueble` (nombre utilizado por el esquema y el código actual). No filtra por `propiedades.agente_id`: varios agentes pueden compartir especialidad.

Se muestran visitas cuyo estado coincide con `INITIAL_VISIT_STATE`, de oportunidades sin resultado ni fecha de cierre. Incluye nombre y teléfono del lead, inmueble, dirección, distrito, operación y fechas de coordinación. Pagina de 20 en 20, con máximo 60 por petición. No devuelve tokens, user_id ni otros datos del lead.

Requisitos existentes: `agentes.especialidad text`, `agentes.token_uuid uuid`, FK de visitas a oportunidades y propiedades. Si tu columna física de propiedades se llama `tipo` en lugar de `tipo_inmueble`, hay que ajustar el esquema o las consultas; no se crea otra columna automáticamente. Sin especialidad o con token duplicado se deniega el acceso.

No se aplicaron cambios en producción ni se modificó n8n. El enlace del agente permite consultar datos de contacto: compartirlo solo con su agente y rotar `agentes.token_uuid` si se divulga.

## Contacto de solicitudes

Se consultaron los estados remotos (solo lectura): solicitada, confirmada, reprogramacion_propuesta, cancelada y realizada. Ninguno representa haber contactado al cliente. Aplicar manualmente `sql/05_agentes_contactadas.sql` para añadir `contactada` y el RPC transaccional. No se aplicó remotamente.

GET `/api/agentes/visitas?estado=pendientes|contactadas` conserva el listado como array. GET `/api/agentes/visitas/conteos` proporciona totales exactos por especialidad. POST `/api/agentes/visitas/{visit_id}/contactar` exige X-Agent-Token y valida también dentro del RPC el token, especialidad y transición pendiente. Bloquea la visita para serializar dos agentes; el segundo recibe 409. Solo cambia estado_id y visitas.updated_at. Las contactadas siguen visibles incluso si luego se cierra la oportunidad. No modifica fechas, resultado ni cierre.

Los botones Llamar y WhatsApp solo abren enlaces externos. Móviles peruanos locales de nueve dígitos que empiezan con 9 reciben 51; prefijos internacionales + y 00 se respetan. Números locales ambiguos se deshabilitan; no se inventa un código de país. El mensaje de WhatsApp se precarga y el agente decide enviarlo.
