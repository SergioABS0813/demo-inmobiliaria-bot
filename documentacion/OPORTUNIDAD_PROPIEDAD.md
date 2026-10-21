# Oportunidad y propiedad

Aplicar manualmente `sql/06_oportunidad_propiedad.sql` despues de 02 y 04; no volver a aplicar 02. No se ejecuto en produccion. La migracion inspecciona duplicados y discordancias y aborta sin reasignar ni cerrar registros si encuentra conflictos. Recupera propiedad_id desde visitas historicas solo cuando la asociacion esta vacia e inequivoca, añade la FK si falta, permite NULL y retira oportunidades_abiertas_propiedad_nn. Conserva el indice abierto lead/propiedad, añade el indice de exploracion y sustituye el antiguo ru_oportunidad_abierta_por_lead_uq.

Al solicitar, el RPC base bloquea primero el lead y luego la oportunidad. Vincula propiedad e inserta visita en la misma transaccion. Una propiedad ya asociada no se sobrescribe; errores RU_PROPERTY_MISMATCH y RU_PROPERTY_ALREADY_OPEN dan HTTP 409. Se conservan request_id, request_hash, replay y UNIQUE(visitas.oportunidad_id), telefono, fechas y estados existentes. No se cambia resultado, fecha_cierre ni motivo_perdida.

POST /api/oportunidades/resolver recibe propiedad_id y X-Opportunity-Token. No acepta lead_id. Bajo bloqueo del lead reutiliza la abierta del inmueble, o reutiliza/crea una exploracion sin propiedad. El formulario cambia el token y la URL antes de mostrar la revision, conserva el formulario si debe resolver un conflicto concurrente y nunca reenvia automaticamente una solicitud. El catalogo conserva todos los inmuebles; Mis visitas consulta las oportunidades del lead.

n8n: reutilizar el RPC ru_obtener_o_crear_oportunidad en registrar-oportunidad, pasando el lead identificado. Ahora solo reutiliza exploraciones abiertas y deja propiedad_id en NULL. Ejecutar enviar-link despues y usar token_uuid del resultado. Un INSERT directo debe manejar el conflicto del indice de exploracion reutilizando la existente. No se generan ni modifican workflows.

Las consultas de diagnostico de indices y restricciones estan al inicio del SQL. Si existen restricciones adicionales no recogidas en este repositorio, revisarlas antes de aplicar. No se eliminan automaticamente oportunidades duplicadas.
