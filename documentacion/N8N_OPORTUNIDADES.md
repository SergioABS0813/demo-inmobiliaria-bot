# Revisión de inmobiliaria-bot-simple (7).json

Solo recomendaciones. No se ha modificado, generado, importado ni activado un workflow n8n.

## Orden de ejecución de EXPLORAR INMUEBLES

En el archivo recibido la rama llega a `enviar-link` **antes** de `registrar-oportunidad`. Por eso `$json.token_uuid` se evalúa sobre un lead, donde ese campo ya no existe.

Orden recomendado:

```text
clasificador-primer-menu [Explorar]
  → Buscar lead por user_id
  → ¿Existe el lead?-1
      sí → lead existente ─┐
      no → crear-lead ─────┤
                          → registrar-oportunidad [crear o reutilizar]
                          → enviar-link
```

Ambas ramas deben entregar el lead seleccionado como item actual, con `id`. No usar una referencia fija a la salida vacía de `Buscar lead por user_id` cuando el lead acaba de crearse.

## Ajustes por nodo

| Nodo exacto | Problema | Cambio recomendado |
| --- | --- | --- |
| `registrar-oportunidad` | Actualmente está después del envío. Inserta siempre, usa `estado_id=1` y toma el ID de `Buscar lead por user_id` incluso para leads nuevos. | Colocarlo antes de `enviar-link`. Sustituir el INSERT directo por la RPC `ru_obtener_o_crear_oportunidad` de `02_oportunidades.sql`, con el ID del item lead actual. La RPC devuelve `token_uuid`, busca `nuevo` por nombre, bloquea el lead y reutiliza su oportunidad abierta. |
| `enviar-link` | Recibe una fila de `leads`, sin token. | Conectarlo a la salida de `registrar-oportunidad`. Conservar el mensaje inmobiliario y URL `https://raizurbana.bestsolperu.com/inmuebles/{{ $json.token_uuid }}`. Verificar que el token sea no vacío antes de enviar. |
| `crear-lead` | Envía `estado_id`, que ya no existe en leads, y no envía `telefono`, obligatorio y único. | Quitar `estado_id`. Registrar `user_id` y un teléfono real disponible en el flujo. No usar un BSUID como si fuera un teléfono ni inventar un número para superar NOT NULL. Si WhatsApp no entrega teléfono, resolverlo explícitamente en la conversación antes de crear el lead. |
| `crear-lead-1` | Solo registra `user_id`, pero `telefono` es obligatorio. | Aplicar la misma regla de teléfono real y reutilización del lead. Este nodo no debe crear una oportunidad al saludar: solo se crea al explorar. |
| `Buscar lead por user_id` | La búsqueda sigue siendo válida, pero los reintentos pueden intentar crear dos leads si ambos no encuentran registro. | Mantener búsqueda por `user_id`. Ante conflicto UNIQUE en creación, recuperar el lead existente; no sobrescribir su historial ni actualizar una fila perteneciente a otra identidad. |
| `Visitas del lead` | Filtra por `visitas.lead_id`, columna eliminada. | Consultar `visitas` con join `oportunidades!inner(lead_id)` y filtrar `oportunidades.lead_id`, o resolver primero IDs de oportunidades del lead y filtrar por `oportunidad_id`. No filtrar por estado comercial como sustituto del cierre. |
| `¿Tiene visitas vigentes?` | Recibe la consulta del modelo viejo. | Evaluar la nueva salida; distinguir visita solicitada/fecha coordinada de oportunidad abierta/cerrada. No considerar `visita_solicitada` un cierre comercial. |
| `clasificador-primer-menu` | La referencia al trigger ya es `trigger_whatsapp` en esta versión. Su salida MIS VISITAS aún conduce a nodos heredados de pedidos. | Conservar el clasificador. Revisar la rama de visitas para utilizar las oportunidades del lead; no consultar tablas de pedidos. |
| `actualizar-sesion-ver-pedidos` | Nombre/rama heredados del restaurante. | Adaptar la transición de sesión a las consultas de visitas del lead; no reutilizar IDs de estado del restaurante. |
| `Obtener el úlitmo pedido` | Sigue consultando la tabla `pedido`. | Sustituir esa consulta por visitas relacionadas con las oportunidades del lead, sin crear una oportunidad solo por consultar historial. |
| `Mensaje - No tiene pedido activo` | Mensaje del restaurante. | Indicar que no hay solicitudes de visita, o pedir EXPLORAR INMUEBLES si se necesita iniciar una oportunidad abierta para acceder a la web. |
| `enviar-mensaje-link-ver-pedidos` | Construye enlaces del flujo de pedidos. | Resolver una oportunidad abierta existente y enlazar `/inmuebles/{token_uuid}/mis-visitas`. No usar tokens de lead o pedido. Si no hay una abierta, pedir al usuario iniciar EXPLORAR INMUEBLES; no crear una intención comercial al consultar historial. |

Los nodos de horario, mensajes informativos y otras ramas no se modifican en el backend.

## Cuerpo de la RPC para registrar-oportunidad

Usar un HTTP Request autenticado con la credencial Supabase del servidor, apuntando a `/rest/v1/rpc/ru_obtener_o_crear_oportunidad` del proyecto inmobiliario:

```json
{
  "p_lead_id": "{{ $json.id }}"
}
```

Configurar la expresión como número si el nodo no convierte el string al tipo bigint. Ese ID proviene del lead resuelto por el flujo, no de un mensaje proporcionado libremente por el cliente. No colocar credenciales en la web.

Respuesta:

```text
id, token_uuid, estado_id, reutilizada
```

No insertar ni actualizar `resultado`, `fecha_cierre` o `motivo_perdida` al explorar. Abierta significa que `resultado IS NULL AND fecha_cierre IS NULL`. `visita_solicitada` sigue abierta: se reutiliza y la web permite consultar la primera visita, sin crear otra. Al cerrar comercialmente la oportunidad, una nueva exploración crea otra fila conservando toda la anterior.

## Comprobar después de aplicar SQL

1. Lead existente sin oportunidad: crear una y enviar su token.
2. Lead nuevo: resolver primero el teléfono obligatorio, crear lead, crear oportunidad, enviar token.
3. Dos ejecuciones/reintentos simultáneos: una oportunidad abierta y el mismo token.
4. Oportunidad con visita: reutilizar token y mostrar solicitud existente.
5. Oportunidad cerrada: crear otra con otro token sin sobrescribir la anterior.
6. MIS VISITAS: consultar únicamente oportunidades del lead identificado por WhatsApp.
