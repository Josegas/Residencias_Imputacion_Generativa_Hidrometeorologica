# Descarga de datos crudos diarios de CONAGUA para Sinaloa

Este script automatiza la descarga de archivos diarios de estaciones climatológicas del estado de **Sinaloa** desde la fuente oficial del **Servicio Meteorológico Nacional (SMN) / CONAGUA**, como parte de la etapa inicial de ingesta de datos del proyecto de reconstrucción de una base de datos hidrometeorológica mediante técnicas de imputación generativa.

---

## Objetivo

Construir la capa **raw** del proyecto descubriendo y descargando automáticamente los archivos `.txt` diarios de todas las estaciones meteorológicas disponibles en el rango de claves de Sinaloa, almacenándolos en una estructura organizada junto con archivos de metadatos y trazabilidad completa del proceso.

---

## Qué hace el script

- Resuelve la ruta raíz del proyecto automáticamente a partir de su propia ubicación (`Path(__file__).resolve().parent.parent`), sin necesidad de configurar rutas manualmente.
- Escanea el rango de claves definido (`25001–25300` por defecto) e intenta descargar cada una.
- Las claves sin archivo en CONAGUA devuelven HTTP 404 y se descartan silenciosamente. Las claves con archivo válido se guardan en disco.
- Si CONAGUA incorpora nuevas estaciones dentro del rango, se descubren automáticamente en la siguiente ejecución.
- Ejecuta las descargas en paralelo usando `MAX_WORKERS` hilos simultáneos para reducir el tiempo total.
- Usa escritura thread-safe con locks para garantizar integridad del manifiesto y el log cuando múltiples hilos escriben al mismo tiempo.
- Evita volver a descargar archivos que ya existen localmente y tienen contenido (tamaño > 0).
- Usa un archivo temporal `.part` durante la descarga que solo se renombra al destino final si el contenido es válido (no vacío y no HTML inesperado del servidor).
- Se conecta directamente con SSL no verificado, ya que el portal de CONAGUA no soporta SSL verificado.
- Realiza hasta 3 reintentos con backoff progresivo (`2s × intento`) ante errores temporales.
- Genera tres archivos de trazabilidad: manifiesto detallado, log de ejecución y resumen global.

---

## Fuente de datos

Los archivos se descargan desde:

```text
https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/sin/dia{clave}.txt
```

Ejemplo:

```text
https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/sin/dia25001.txt
```

---

## Estructura de salida

```text
data/
└── raw/
    └── conagua_smn/
        └── estado=sin/
            ├── fuente=normales_climatologicas/
            │   └── producto=diarios_txt/
            │       ├── dia25001.txt
            │       ├── dia25002.txt
            │       └── ...
            │
            ├── _logs/
            │   ├── download_manifest.csv
            │   ├── download_run.log
            │   └── download_summary.csv
            │
            └── _meta/
                └── stations_sin.csv
```

---

## Archivos generados

### 1. Archivos crudos descargados

```text
data/raw/conagua_smn/estado=sin/fuente=normales_climatologicas/producto=diarios_txt/
```

Cada archivo sigue la convención `dia<clave>.txt`, por ejemplo `dia25001.txt`.

### 2. Catálogo de estaciones descubiertas

```text
data/raw/conagua_smn/estado=sin/_meta/stations_sin.csv
```

Contiene únicamente las claves que tienen archivo disponible en CONAGUA:

| Columna | Descripción |
|---------|-------------|
| `clave` | Clave oficial de la estación |
| `estado` | Estado (`sin`) |
| `status` | Resultado de la descarga (`OK` o `SKIP_EXISTS`) |
| `file_size_bytes` | Tamaño del archivo descargado en bytes |

### 3. Manifiesto de descarga

```text
data/raw/conagua_smn/estado=sin/_logs/download_manifest.csv
```

Registra el resultado detallado de cada intento de descarga:

| Columna | Descripción |
|---------|-------------|
| `timestamp` | Fecha y hora del intento (ISO 8601) |
| `pass_no` | Número de pasada (siempre 1) |
| `estado` | Clave del estado (`sin`) |
| `clave` | Clave escaneada |
| `status` | Resultado de la descarga (ver tabla de estados) |
| `error_type` | Tipo de error si aplica |
| `error_detail` | Detalle del error |
| `url` | URL utilizada |
| `file` | Ruta del archivo local |
| `file_size_bytes` | Tamaño del archivo descargado en bytes |
| `ssl_mode` | Modo SSL usado (siempre `insecure`) |
| `attempt` | Número de intento |
| `duration_ms` | Duración de la operación en milisegundos |

### 4. Log de ejecución

```text
data/raw/conagua_smn/estado=sin/_logs/download_run.log
```

Mensajes con marca de tiempo del progreso, incluyendo configuración inicial, resultado de descargas exitosas, errores distintos a 404 y métricas finales.

### 5. Resumen global

```text
data/raw/conagua_smn/estado=sin/_logs/download_summary.csv
```

| Métrica | Descripción |
|---------|-------------|
| `estado` | Clave del estado |
| `project_root` | Ruta raíz resuelta del proyecto |
| `range_start` | Clave de inicio del rango escaneado |
| `range_end` | Clave de fin del rango escaneado |
| `claves_escaneadas` | Total de claves intentadas |
| `ok` | Descargas exitosas |
| `skip_exists` | Archivos omitidos por ya existir |
| `discovered` | Total de estaciones con archivo válido (`ok + skip_exists`) |
| `not_found_404` | Claves sin archivo en CONAGUA |
| `fail` | Otros errores (timeout, connection, etc.) |
| `coverage_percent` | Porcentaje de claves con archivo sobre el rango total |

---

## Estados posibles en el manifiesto

| Status | Descripción | ¿Se reintenta? |
|--------|-------------|----------------|
| `OK` | Descarga exitosa | — |
| `SKIP_EXISTS` | Archivo ya existía localmente con contenido | — |
| `HTTP_404` | Clave sin archivo en el servidor (silencioso en consola) | No |
| `HTTP_500` / `502` / `503` / `504` | Error temporal del servidor | Sí |
| `SSL_ERROR` | Error de certificado SSL | Sí |
| `TIMEOUT` | Tiempo de espera agotado | Sí |
| `URL_ERROR` | Error de conexión o resolución de URL | Sí |
| `CONTENT_ERROR` | El servidor devolvió HTML en lugar del archivo esperado | No |
| `ERROR` | Otro error inesperado | No |

---

## Lógica general del script

1. Crear las carpetas de salida si no existen.
2. Inicializar el manifiesto si aún no existe.
3. Generar la lista de claves del rango definido.
4. Lanzar `MAX_WORKERS` hilos en paralelo, cada uno descargando una clave:
   - Si el archivo ya existe con contenido → registrar `SKIP_EXISTS` y continuar.
   - Si no existe → intentar descarga con SSL no verificado.
   - Validar que el contenido no esté vacío ni sea HTML del servidor.
   - Reintentar hasta 3 veces con backoff `2s × intento` ante errores temporales.
   - Los HTTP 404 se registran en el manifiesto pero no se imprimen en consola.
   - Registrar resultado en el manifiesto y en el log de forma thread-safe.
5. Guardar el catálogo `stations_sin.csv` con las claves que tienen archivo válido.
6. Calcular métricas globales y guardar `download_summary.csv`.

---

## Parámetros de configuración

| Parámetro | Valor por defecto | Descripción |
|-----------|------------------|-------------|
| `STATION_RANGE_START` | `25001` | Clave de inicio del rango a escanear |
| `STATION_RANGE_END` | `25300` | Clave de fin del rango a escanear (inclusive) |
| `REQUEST_TIMEOUT` | `25` | Tiempo máximo de espera por solicitud (segundos) |
| `RETRIES_PER_PASS` | `3` | Reintentos ante errores temporales |
| `SLEEP_BETWEEN_CLAVES` | `0.2` | Pausa entre requests dentro de cada hilo (segundos) |
| `MAX_WORKERS` | `10` | Hilos de descarga simultáneos (no subir de 20) |

---

## Requisitos

No requiere instalación de dependencias externas. Usa únicamente la biblioteca estándar de Python.

Módulos utilizados: `pathlib`, `csv`, `ssl`, `socket`, `time`, `datetime`, `urllib.request`, `urllib.error`, `concurrent.futures`, `threading`.

**Python 3.9 o superior recomendado.**

---

## Ejecución

```bash
python download_sinaloa_raw_pro.py
```

> El script resuelve la ruta del proyecto automáticamente asumiendo que vive en una subcarpeta de primer nivel del repositorio (por ejemplo `Obtencion de Datos Crudos/`). Si se mueve a otra ubicación, ajusta la línea:
> ```python
> PROJECT_ROOT = Path(__file__).resolve().parent.parent
> ```

### Salida esperada en consola

```
[2026-03-01 10:00:00] INICIO | Estado=sin | Rango=25001–25300 | Claves a escanear=300
[2026-03-01 10:00:00] PROJECT_ROOT=/ruta/al/proyecto
[2026-03-01 10:00:00] CONFIG | timeout=25s | retries=3 | sleep_between=0.2s
[2026-03-01 10:00:02] OK   P1 25001 | ssl=insecure | intento=1 | bytes=539742
[2026-03-01 10:00:02] OK   P1 25003 | ssl=insecure | intento=1 | bytes=426493
[2026-03-01 10:00:02] SKIP P1 25002 (ya existe)
...
[2026-03-01 10:03:30] FIN
[2026-03-01 10:03:30] SUMMARY | discovered=168 | not_found_404=132 | coverage_percent=56.0
```

> El orden de las líneas en consola puede variar porque las descargas se ejecutan en paralelo.

---

## Consideraciones

- El script está diseñado específicamente para el estado de **Sinaloa** (`estado=sin`).
- El portal de CONAGUA no soporta SSL verificado, por lo que el script usa directamente SSL no verificado.
- Los HTTP 404 no se imprimen en consola para evitar ruido, ya que la mayoría de claves del rango no tienen archivo. Quedan registrados en el manifiesto.
- El orden de aparición en el log no es secuencial porque las descargas son paralelas.
- Este script forma parte de la etapa de ingesta de datos crudos, previa a la organización, limpieza, análisis exploratorio y modelado.

---

## Rol dentro del proyecto

Este script corresponde a la **primera fase del pipeline de datos**. Su función es construir una capa `raw` reproducible y trazable que preserve los archivos originales descargados desde la fuente oficial antes de cualquier transformación posterior.

Los datos generados son el insumo directo del script de estructuración del dataset (`organize_raw_by_station_year_variable_parquet.py`), que transforma estos archivos `.txt` en particiones organizadas por estación, año y variable.

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Proyecto de Residencias Profesionales**  
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*  
Laboratorio de Geomática y Teledetección
