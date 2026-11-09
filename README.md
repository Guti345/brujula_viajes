# Brújula Viajes

Sistema de la agencia de viajes Brújula Viajes, un proyecto del curso Ingeniería de Datos. La agencia vende vuelos, noches de hotel, tours y paquetes.

El sistema muestra a los asesores la disponibilidad real, no vende lo que no tiene y produce los reportes de ventas B1 a B3.

**Stack:** FastAPI + PyMongo + MongoDB local + Streamlit.

## Contenido del repositorio

```text
brujula_viajes/
├── back/                                     API en FastAPI
│   ├── main.py                               Punto de entrada de la API y manejo de errores
│   ├── datos_mongo.py                        Datos de inicio (borra y recarga la base)
│   └── app/
│       ├── database.py                       Conexión, validadores e índices de MongoDB
│       ├── schemas.py                        Modelos de entrada y salida
│       ├── cotizacion.py                     Cotización de los ítems de una reserva
│       ├── inventario.py                     Descuento y devolución de inventario
│       ├── utils.py                          Funciones de apoyo
│       └── routers/                          Endpoints, incluidos los reportes
├── front/                                    Aplicación en Streamlit para los asesores
│   ├── app.py                                Inicio e ingreso del asesor
│   ├── estilo.py                             Estilo de marca y navegación
│   ├── api_client.py                         Único puente entre Streamlit y la API
│   ├── pages/                                Buscar y reservar, Reservas, Catálogo y clientes, Reportes
│   ├── assets/                               Logos, íconos e ilustraciones
│   └── .streamlit/config.toml                Tema de la aplicación
├── evidencias_backend/                       Capturas de las pruebas en Swagger y en mongosh
├── evidencias_frontend/                      Capturas de las pruebas en la interfaz
├── Documentación_Brújula_Viajes.pdf          Informe de modelado
├── Reporte_Evidencias_Endpoints_Backend.pdf  Informe de evidencias del backend
├── Reporte_Evidencias_Endpoints_Frontend.pdf Informe de evidencias del frontend
├── Presentación_brujula_viajes.pdf           Presentación del proyecto
├── brujula_1_disponibilidad.mp4              Video de demostración: disponibilidad
├── brujula_2_paquetes.mp4                    Video de demostración: paquetes
├── brujula_3_reportes.mp4                    Video de demostración: reportes
├── requirements.txt                          Dependencias de Python
├── .env.example                              Plantilla de variables de entorno
├── .gitignore
└── README.md
```

## Entregables del proyecto

| Entregable | Ubicación en el repositorio |
|---|---|
| API | `back/` |
| Frontend | `front/` |
| Script de datos de prueba | `back/datos_mongo.py` |
| Validadores e índices | `back/app/database.py` |
| Informe de modelado | `Documentación_Brújula_Viajes.pdf` |
| Evidencias del backend | `evidencias_backend/` y `Reporte_Evidencias_Endpoints_Backend.pdf` |
| Evidencias del frontend | `evidencias_frontend/` y `Reporte_Evidencias_Endpoints_Frontend.pdf` |
| Videos de demostración | `brujula_1_disponibilidad.mp4`, `brujula_2_paquetes.mp4` y `brujula_3_reportes.mp4` |
| Presentación | `Presentación_brujula_viajes.pdf` |

## Requisitos e instalación

### Requisitos

- **Python 3.11 o superior.** `pymongo` 4.19, `streamlit` 1.66.1 y `httpx2` 2.16.0 exigen 3.11 o superior; las uniones `X | Y` del código exigen 3.10 o superior.
- **MongoDB 6 o superior**, corriendo en `localhost:27017`, o una URL de Atlas en `MONGO_URL`.
- **Windows PowerShell.**

### Instalación

Cada bloque de esta guía se copia desde la raíz del repositorio. En cada terminal nueva, activa primero el entorno con la segunda línea de este bloque.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Configuración

Crea el `.env` solo si no existe. Si ya existe, no lo reemplaces, porque conserva tu `MONGO_URL` y tus secretos.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

En `.env.example` todas las líneas están comentadas. Abre tu `.env`, quita el `#` de `MONGO_DB=brujula_viajes` y, si hace falta, el de una de las líneas `MONGO_URL`. Sin esa variable, la API usa el MongoDB local en `localhost:27017`.

En cualquier caso, comprueba que el `.env` tenga la base correcta. Este comando debe mostrar `MONGO_DB=brujula_viajes`:

```powershell
Select-String -Path .env -Pattern '^MONGO_DB='
```

Una variable `MONGO_DB` definida en la terminal tiene prioridad sobre el `.env`. Si te queda alguna de una sesión anterior, quítala:

```powershell
Remove-Item Env:MONGO_DB -ErrorAction SilentlyContinue
```

El `.env` no se sube al repositorio porque ya está en `.gitignore`.

## Preparación inicial de MongoDB (una sola vez)

Estos dos pasos se hacen una sola vez al montar el proyecto, o cuando se quiera reconstruir la base. En el uso normal se omiten y se pasa directamente a [Arranque y acceso](#arranque-y-acceso). MongoDB debe estar corriendo.

### Paso 1: validadores e índices

Crea las colecciones con sus validadores e índices. Se puede repetir sin riesgo: si una colección ya existe, actualiza su validador con `collMod`. Los documentos existentes no se revalidan; las reglas aplican a las escrituras nuevas.

Este paso tiene un candado: solo se aplica si la variable `BRUJULA_APLICAR_ESQUEMA` vale exactamente `si`. Sin ella, tanto este comando como el arranque de la API omiten el esquema y no tocan la base (la API deja en el log la línea `init_db omitido`). Así, levantar la API con código nuevo no cambia los validadores ni los índices de una base existente.

```powershell
cd back; $env:BRUJULA_APLICAR_ESQUEMA = "si"; python -m app.database; Remove-Item Env:BRUJULA_APLICAR_ESQUEMA; cd ..
```

La variable se define solo a nivel de proceso. Quítala al terminar, como en el comando, para que el siguiente arranque de la API en esa terminal no aplique el esquema sin querer. En el `.env` déjala comentada o en `no`.

### Paso 2: datos de inicio

> [!WARNING]
> Este comando **BORRA y recarga por completo la base `brujula_viajes`** del servidor configurado, y no tiene vuelta atrás. No lo ejecutes sobre una base con datos que importen.

```powershell
cd back; python datos_mongo.py; cd ..
```

Este paso también tiene su candado: si la base configurada no es `brujula_viajes`, el script aborta sin crear, borrar ni escribir nada. Después de verificar el nombre de la base, abre por su cuenta el candado del esquema solo para esa ejecución.

## Arranque y acceso

Usa dos terminales, con el entorno activado en cada una. MongoDB debe estar corriendo y la API debe arrancar primero, porque el frontend solo habla con ella.

**Terminal 1, backend:**

```powershell
cd back; uvicorn main:app --reload
```

Abre en el navegador:

- API: http://127.0.0.1:8000
- Documentación interactiva (Swagger): http://127.0.0.1:8000/docs

**Terminal 2, frontend:**

```powershell
cd front; streamlit run app.py
```

El comando debe correr desde `front/`, porque los logos y el tema de la aplicación se buscan desde esa carpeta.

Streamlit usa su puerto por defecto y normalmente abre el navegador solo. Si no lo hace, entra a http://localhost:8501. Si en el primer arranque la terminal pide un correo, presiona `Enter` para omitirlo.

El frontend busca la API en `http://127.0.0.1:8000`, como indica `front/api_client.py`. Para usar otra dirección, define la variable `API_URL` en la terminal del frontend antes de arrancarlo; esta variable no se lee del `.env`. Si la API está apagada, la página de inicio muestra `Sin conexión con la API`.

**Ingreso del asesor:** la aplicación pide el correo y el código de un asesor activo. Los asesores de prueba están en `back/datos_mongo.py`, en la función `cargar_personas`, y existen en la base después de cargar los datos de inicio.

Detén cada proceso con `Ctrl + C` y vuelve a la raíz con `cd ..`.

## Reportes

| Reporte | Endpoint | Contenido |
|---|---|---|
| B1 | `GET /reportes/ventas-por-mes` | Total vendido y número de reservas por mes, en hora de Colombia |
| B2 | `GET /reportes/destinos-mas-vendidos` | Las 5 ciudades con más ingresos y sus pasajeros |
| B3 | `GET /reportes/ocupacion-vuelos` | Sillas vendidas y porcentaje de ocupación por vuelo |

Las ventas y los destinos no cuentan las reservas canceladas. La ocupación tampoco, porque cancelar devuelve las sillas al inventario.

Los pasajeros de cada destino son una métrica por ítems: suman la cantidad de los ítems de vuelo y paquete, así que no son personas únicas.

## Validaciones

- **Campos:** obligatorios y con tipo definido.
- **Valores permitidos:** listas cerradas para estado de reserva, tarifa y tipo de habitación.
- **Mínimos:** precios e inventarios no pueden ser negativos.
- **Contenido de vuelos y hoteles:** al menos 1 tarifa por vuelo y 1 tipo de habitación por hotel. La regla también está en el validador de MongoDB, así que la base rechaza un insert inválido hecho directamente.
- **Índices únicos:** tipo + documento del cliente, código de vuelo, código de reserva, noche por hotel + tipo + fecha y salida por tour + fecha.
- **Disponibilidad:** si no hay inventario suficiente, la API responde `409`.
- **Pagos e historial:** un pago no puede superar el saldo pendiente, y la reserva guarda el historial de sus estados.

## Códigos HTTP

| Código | Cuándo |
|---|---|
| `201` | Al crear un recurso |
| `404` | El recurso no existe: reserva, cliente, asesor, vuelo, hotel, tour, salida, paquete, ciudad, o la tarifa o tipo de habitación pedido dentro de un producto |
| `409` | Se incumple una regla, por ejemplo: sin cupo, llave única duplicada, asesor inactivo, fecha ya pasada, paquete fuera de su ventana de venta, pago a reserva cancelada, pago que supera el saldo, doble cancelación o referencias inconsistentes. Una llave duplicada responde `{"detail": "Ya existe un registro con ese identificador único"}`, sin el valor duplicado ni el nombre del campo; una escritura masiva en la que todos los errores son de llave duplicada responde `{"detail": "Conflicto de llave única al escribir en la base"}` |
| `422` | Datos inválidos, según Pydantic, una regla del endpoint o el validador de MongoDB. El rechazo del validador responde solo `{"detail": "El documento no cumple el esquema de la base"}`, sin `errInfo`; una escritura masiva en la que todos los errores son de validación responde el mismo texto |
| `500` | Hay dos casos. **Error interno inesperado**, incluido un documento de MongoDB que no cumple el `response_model`: la API responde `{"detail": "Error interno del servidor"}` y registra el fallo en su propio log sin datos sensibles (sin mensajes de error que puedan traer valores, sin URLs reales y sin cuerpos de petición). **Agotamiento de reintentos al generar el código único de reserva:** es la única excepción con mensaje propio, porque ese mensaje es seguro de mostrar |
| `503` | MongoDB no responde o se perdió la conexión. Es un fallo de infraestructura, no de los datos del cliente. Los errores de operación que sí llegaron al servidor no son `503` |

Los errores de negocio no usan `400`. Una petición mal formada a nivel de transporte o protocolo puede recibir `400` del framework antes de llegar a la aplicación.

Si falla una devolución de inventario, el log registra solo el tipo de movimiento y la clase del error, con nivel `ERROR`.

## Límites conocidos

- **Log del servidor:** cuando el handler general de `Exception` responde `500`, Starlette y uvicorn pueden reemitir la excepción al log del servidor, fuera del logger propio `brujula`. Eso no se controla sin middleware adicional, que no se agrega en este proyecto. Por eso, el saneamiento descrito aquí aplica al logger `brujula`, no a todos los registros del servidor.
- **Reservas sin transacción:** crear o cancelar una reserva no es una sola operación atómica. El inventario se descuenta o el estado cambia primero, y la compensación o devolución va después. Una caída en medio puede dejar inventario pendiente de revisión manual. El enunciado no exige transacciones.
- **Concurrencia sin medir:** el descuento condicional por documento está diseñado para evitar la sobreventa entre peticiones simultáneas, pero no se probó con concurrencia real. Es una propiedad del diseño, no una garantía medida.
- **Escrituras tras un `503`:** si una escritura falla con `503` por un corte de red, no se puede saber si MongoDB llegó a aplicarla; así lo documenta PyMongo para `NetworkTimeout`. La API no reintenta escrituras automáticamente para no arriesgar duplicados, como un pago doble. Ante un `503`, revisa el estado antes de reintentar a mano.
- **MongoDB apagado:** la API no arranca, porque `init_db` hace ping al iniciar. Si MongoDB cae a mitad de una petición, la API responde `503`.

## Secretos

Este README no incluye connection strings reales ni contraseñas, y `.env.example` solo trae marcadores. Las credenciales van únicamente en tu `.env`.

## Declaración de uso de IA

En este proyecto se usaron las siguientes herramientas de inteligencia artificial:

- **Instinct:** estructuración de prompts.
- **Claude Code (Opus 5.5, nivel de rendimiento high):** ejecución, revisión de código y pruebas.
- **ChatGPT:** imágenes y logos, y revisión de la definición de marca.
