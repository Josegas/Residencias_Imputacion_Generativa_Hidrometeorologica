# Descarga de datos crudos diarios de CONAGUA para Sinaloa

Este script automatiza la descarga de archivos diarios de estaciones climatológicas del estado de **Sinaloa** desde la fuente oficial del **Servicio Meteorológico Nacional (SMN) / CONAGUA**, como parte de la etapa inicial de ingesta de datos del proyecto de reconstrucción de una base de datos hidrometeorológica mediante técnicas de imputación generativa.

---

## Objetivo

El propósito del script es construir la capa **raw** del proyecto, descargando los archivos `.txt` diarios de las estaciones meteorológicas de Sinaloa y almacenándolos en una estructura organizada, junto con archivos de metadatos y trazabilidad del proceso.

---

## Qué hace el script

- Define el estado objetivo como **Sinaloa** (`sin`).
- Construye automáticamente la URL de descarga de cada estación usando su clave oficial.
- Recorre una lista predefinida de estaciones climatológicas de Sinaloa.
- Descarga los archivos diarios en formato `.txt` desde el portal del SMN/CONAGUA.
- Evita volver a descargar archivos que ya existen localmente.
- Genera un archivo de metadatos con la lista de estaciones.
- Registra un manifiesto de descarga con el resultado de cada intento.
- Genera un log de ejecución para auditoría y seguimiento.
- Introduce una pequeña pausa entre descargas para no saturar el servidor.

---

## Fuente de datos

Los archivos se descargan desde la ruta base:

```text
https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/{estado}/dia{clave}.txt
```

Para este caso:

- `estado = sin`
- `clave` = clave oficial de estación

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
            │   └── download_run.log
            │
            └── _meta/
                └── stations_sin.csv
```

---

## Archivos generados

### 1. Archivos crudos descargados

Ruta:

```text
data/raw/conagua_smn/estado=sin/fuente=normales_climatologicas/producto=diarios_txt/
```

Cada archivo descargado sigue la convención `dia<clave>.txt`, por ejemplo:

```text
dia25001.txt
```

### 2. Archivo de metadatos de estaciones

Ruta:

```text
data/raw/conagua_smn/estado=sin/_meta/stations_sin.csv
```

Contiene las columnas:

| Columna | Descripción |
|---------|-------------|
| `clave` | Clave oficial de la estación |
| `nombre_estacion` | Nombre de la estación |
| `municipio` | Municipio al que pertenece |
| `situacion` | Situación operativa |
| `estado` | Estado (Sinaloa) |

Este archivo sirve como referencia de las estaciones consideradas en la descarga.

### 3. Manifiesto de descarga

Ruta:

```text
data/raw/conagua_smn/estado=sin/_logs/download_manifest.csv
```

Registra el resultado de cada intento de descarga con las columnas:

| Columna | Descripción |
|---------|-------------|
| `timestamp` | Fecha y hora del intento |
| `estado` | Estado del proceso |
| `clave` | Clave de la estación |
| `status` | Resultado de la descarga |
| `url` | URL utilizada |
| `file` | Ruta del archivo local |
| `error` | Mensaje de error (si aplica) |

Permite auditar qué archivos fueron descargados correctamente, cuáles ya existían y cuáles fallaron.

### 4. Log de ejecución

Ruta:

```text
data/raw/conagua_smn/estado=sin/_logs/download_run.log
```

Almacena mensajes de ejecución con marca de tiempo, incluyendo inicio, progreso, errores y resumen final.

---

## Lógica general del script

1. Crear las carpetas necesarias si no existen.
2. Guardar el catálogo de estaciones de Sinaloa en un CSV.
3. Inicializar el archivo de manifiesto si aún no existe.
4. Recorrer cada estación definida en la lista `STATIONS`.
5. Construir la URL de descarga para cada clave.
6. Verificar si el archivo ya existe localmente:
   - Si existe → se omite la descarga.
   - Si no existe → se intenta descargar.
7. Registrar el resultado en el manifiesto y en el log.
8. Al finalizar, escribir un resumen con número de descargas exitosas, archivos omitidos y fallos.

---

## Estados posibles de descarga

El campo `status` del manifiesto puede tomar los siguientes valores:

| Status | Descripción |
|--------|-------------|
| `OK` | Descarga exitosa |
| `SKIP_EXISTS` | El archivo ya existía localmente |
| `HTTP_<codigo>` | Error HTTP (ej. `HTTP_404`) |
| `URL_ERROR` | Error de conexión o resolución de URL |
| `ERROR` | Otro error inesperado |

---

## Requisitos

Este script usa únicamente librerías estándar de Python, por lo que **no requiere instalación de dependencias externas**.

Módulos utilizados: `os`, `csv`, `time`, `urllib.request`, `urllib.error`, `datetime`.

---

## Ejecución

```bash
python download_sinaloa_raw_pro.py
```

### Configuración importante

Dentro del script se define manualmente la ruta raíz del proyecto:

```python
PROJECT_ROOT = r"C:\Users\Jose Garcia\Documents\10_SEMESTRE_TEC\RESIDENCIAS\Reconstruccion_de_Base_de_Datos_Nuestro"
```

> Nota: Si el proyecto se mueve a otra ubicación, esta ruta debe actualizarse antes de ejecutar el script.

---

## Consideraciones

- El script está diseñado específicamente para el estado de **Sinaloa**.
- La lista de estaciones está codificada manualmente en la variable `STATIONS`.
- La descarga depende de la disponibilidad de los archivos en el portal oficial de CONAGUA.
- Se utiliza una pausa de **0.2 segundos** entre solicitudes para realizar una descarga más amable con el servidor.
- Este script forma parte de la etapa de ingesta de datos crudos, previa al proceso de organización, limpieza, análisis exploratorio y modelado.

---

## Rol dentro del proyecto

Este script corresponde a la **primera fase del pipeline de datos** del proyecto. Su función es construir una capa `raw` reproducible y trazable, que preserve los archivos originales descargados desde la fuente oficial antes de cualquier transformación posterior.

Posteriormente, estos datos pueden ser utilizados para procesos como:

- Organización por estación, año y variable
- Limpieza y estandarización
- Análisis exploratorio
- Detección de valores faltantes
- Preparación de datasets para imputación generativa

---

## Autor

**Proyecto de Residencias**  
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*
