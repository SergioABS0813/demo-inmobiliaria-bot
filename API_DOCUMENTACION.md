# Documentación de la API

Se habilitan estas rutas sin exigir token para leer la documentación:

- `/docs`: Swagger UI, con formularios para probar endpoints.
- `/redoc`: referencia de lectura de la API.
- `/openapi.json`: contrato OpenAPI generado por FastAPI.

Los endpoints personales exigen `X-Opportunity-Token`. En Swagger, usar **Try it out** y completar ese encabezado con el token de una oportunidad abierta existente. Se acepta `X-Lead-Token` como alias obsoleto, también con token de oportunidad. No completar ambos con valores distintos. No se utiliza la clave secreta de Supabase en Swagger.

La pantalla en blanco se debía a que la CSP del sitio bloqueaba el JavaScript del CDN y el inicializador inline de Swagger. `app/docs.py` registra las interfaces utilizando las utilidades de FastAPI y añade una política exclusiva para esas respuestas: CDN jsDelivr y nonce aleatorio por respuesta para scripts. Los estilos inline de las bibliotecas se permiten solo en esas páginas. El catálogo y las demás rutas conservan su CSP anterior.

`docs_url=None` y `redoc_url=None` deshabilitan únicamente los handlers automáticos, ya que se registran handlers personalizados en esas mismas URLs. `openapi_url='/openapi.json'` queda habilitado. Las páginas HTML del catálogo no se incluyen en OpenAPI; aparecen solo las APIs de datos.

Después de desplegar estos cambios, reconstruir/reiniciar el contenedor de FastAPI. Si el proxy también añade una CSP, ambas políticas se aplican y la del proxy puede seguir bloqueando la documentación. La interfaz necesita acceso a jsDelivr; no es una versión offline.

Validado mediante TestClient: rutas accesibles, esquema con endpoints y modelos, encabezado de token, nonce coherente con HTML/CSP, longitud de respuesta y política original del sitio. No se ejecutó un navegador ni se desplegó en el dominio remoto.

Referencia: https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/
