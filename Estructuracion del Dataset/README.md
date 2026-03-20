# Organizador de datos crudos hidrometeorológicos por estación, año y variable

Este script transforma los archivos crudos diarios descargados desde **SMN–CONAGUA** para el estado de **Sinaloa** en un dataset organizado, limpio y particionado, listo para etapas posteriores de análisis exploratorio, evaluación de valores faltantes, preparación de datos y modelado.

Su función principal es convertir archivos `.txt` originales de estaciones climatológicas en una estructura jerárquica de almacenamiento por:

- **estación**
- **año**
- **variable climática**

Además, genera un índice global con metadatos de salida que facilita la trazabilidad, auditoría y control de calidad del procesamiento. Esta organización corresponde a la capa `interim` del proyecto, separada explícitamente de la capa `raw`.

---

## Objetivo

Construir una versión organizada del dataset hidrometeorológico a partir de los archivos crudos descargados previamente desde CONAGUA/SMN, preservando la trazabilidad del dato original y facilitando el acceso eficiente por particiones temporales y variables.

Este paso forma parte de la fase de preparación de datos del proyecto de reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial. La estructura resultante permite trabajar posteriormente con pipelines de imputación, validación estadística y modelado reproducible.

---

## Qué hace el script

- Resuelve la ruta raíz del proyecto automáticamente a partir de su propia ubicación (`Path(__file__).resolve().parent.parent`), sin necesidad de configurar rutas manualmente.
- Lee todos los archivos `.txt` crudos almacenados en la carpeta `raw`.
- Detecta la línea donde comienza la tabla de datos dentro de cada archivo (encabezado `FECHA`).
- Salta la línea de encabezado y la línea de unidades, y asigna los nombres de columnas directamente: `date`, `PRECIP`, `EVAP`, `TMAX`, `TMIN`.
- Convierte los valores `"NULO"`, `"Nulo"`, `"nulo"` y cadena vacía a valores nulos estándar (`NaN`).
- Filtra únicamente registros con fecha válida en formato `YYYY-MM-DD`.
- Convierte la columna `date` a tipo `datetime` y las variables climáticas a tipo numérico.
- Ordena cronológicamente los datos.
- Separa los registros por año calendario.
- Divide cada año por variable climática.
- Guarda cada partición en formato `.csv` y `.parquet`.
- Genera un archivo `_index.csv` con información resumida de todos los archivos producidos.

---

## Variables procesadas

| Variable | Descripción |
|----------|-------------|
| `PRECIP` | Precipitación diaria |
| `EVAP`   | Evaporación diaria |
| `TMAX`   | Temperatura máxima diaria |
| `TMIN`   | Temperatura mínima diaria |

Para cada variable se genera un archivo independiente con dos columnas:

- `date` → fecha en formato `YYYY-MM-DD`
- `value` → valor observado de la variable

---

## Estructura de entrada

El script espera encontrar los archivos crudos en:

```text
data/raw/conagua_smn/estado=sin/fuente=normales_climatologicas/producto=diarios_txt/
```

Ejemplos de archivos de entrada:

```text
dia25001.txt
dia25002.txt
dia25014.txt
...
```

El nombre de archivo puede tener el formato `dia<clave>.txt` o `<clave>.txt`. Ambos son soportados.

---

## Estructura de salida

Los datos organizados se guardan en:

```text
data/interim/organized/estado=sin/
```

```text
data/
├── raw/
│   └── conagua_smn/
│       └── estado=sin/
│           └── fuente=normales_climatologicas/
│               └── producto=diarios_txt/
│                   ├── dia25001.txt
│                   ├── dia25002.txt
│                   └── ...
│
└── interim/
    └── organized/
        └── estado=sin/
            ├── estacion=25001/
            │   ├── year=1961/
            │   │   ├── precip.csv / precip.parquet
            │   │   ├── evap.csv   / evap.parquet
            │   │   ├── tmax.csv   / tmax.parquet
            │   │   └── tmin.csv   / tmin.parquet
            │   ├── year=1962/
            │   └── ...
            ├── estacion=25002/
            │   └── ...
            └── _index.csv
```

---

## Estructura del dataset

### Organización jerárquica

**Nivel 1 — Estación:** cada estación se almacena en un directorio independiente con el formato `estacion=25001/`, usando la clave oficial de CONAGUA para mantener trazabilidad con la fuente.

**Nivel 2 — Año:** dentro de cada estación los datos se organizan por año calendario (`year=1961/`, `year=1962/`, ...), lo que permite acceso eficiente a períodos específicos y reduce la carga en memoria al procesar subconjuntos anuales.

**Nivel 3 — Variable climática:** dentro de cada carpeta anual se almacena un archivo por variable (`precip`, `evap`, `tmax`, `tmin`), cada uno con únicamente las columnas `date` y `value`.

### Convenciones de nomenclatura

Las carpetas usan la convención `key=value` (`estado=sin`, `estacion=25001`, `year=1961`), que facilita la escalabilidad, claridad semántica y compatibilidad con pipelines de data engineering. Los archivos de salida siempre están en minúsculas (`precip.csv`, `tmax.parquet`).

### Formatos de almacenamiento

Cada partición se guarda en dos formatos complementarios:

- **CSV:** alta compatibilidad, fácil inspección manual, interoperabilidad con múltiples herramientas.
- **Parquet:** formato columnar optimizado, menor tamaño en disco, mejor rendimiento de lectura y preservación de tipos. Recomendado para procesamiento analítico y modelado.

---

## Índice global

El script genera `_index.csv` en:

```text
data/interim/organized/estado=sin/_index.csv
```

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año del registro |
| `variable` | Variable climática (en minúsculas) |
| `path_parquet` | Ruta absoluta al archivo Parquet |
| `path_csv` | Ruta absoluta al archivo CSV |
| `rows` | Número de filas en la partición |
| `missing_pct` | Porcentaje de valores faltantes (redondeado a 3 decimales) |

Su propósito es proporcionar un registro centralizado de todas las particiones generadas para auditoría, control de calidad, monitoreo de cobertura temporal y evaluación de faltantes por archivo.

---

## Flujo general del script

1. Resolver la ruta raíz del proyecto automáticamente.
2. Imprimir `PROJECT_ROOT`, `RAW_DIR` y `OUT_DIR` para verificación.
3. Verificar que `pyarrow` esté disponible; abortar con instrucciones si no está instalado.
4. Crear la carpeta de salida si no existe.
5. Inicializar `_index.csv` si aún no existe.
6. Localizar todos los archivos `.txt` en la carpeta raw.
7. Por cada archivo:
   - Extraer el identificador de estación del nombre del archivo.
   - Detectar la línea de inicio de la tabla (`FECHA`).
   - Cargar la tabla saltando la línea de encabezado y la línea de unidades, asignando nombres de columnas fijos.
   - Filtrar fechas válidas, convertir tipos y ordenar cronológicamente.
   - Dividir por año y por variable.
   - Guardar cada partición en CSV y Parquet.
   - Registrar la salida en `_index.csv`.
8. Al finalizar, imprimir la ubicación del índice y la carpeta de salida.

---

## Validaciones incorporadas

- Verifica que existan archivos `.txt` en la carpeta de entrada.
- Detecta si falta el encabezado `FECHA` en un archivo y reporta el error sin interrumpir el procesamiento de los demás.
- Filtra únicamente fechas con formato válido (`YYYY-MM-DD`).
- Convierte automáticamente valores no numéricos a `NaN`.
- Verifica que `pyarrow` esté instalado antes de iniciar el procesamiento.

> Si alguna estación falla durante el procesamiento, el script reporta el error en consola y continúa con las demás.

---

## Requisitos

- Python 3.9 o superior
- `pandas`
- `pyarrow`

```bash
pip install pandas pyarrow
```

---

## Ejecución

```bash
python organize_raw_by_station_year_variable_parquet.py
```

> El script resuelve la ruta del proyecto automáticamente asumiendo que vive en una subcarpeta de primer nivel del repositorio (por ejemplo `Estructuracion del Dataset/`). Si se mueve a otra ubicación, ajusta la línea:
> ```python
> PROJECT_ROOT = Path(__file__).resolve().parent.parent
> ```

### Salida esperada en consola

```text
PROJECT_ROOT: /ruta/al/proyecto
RAW_DIR: /ruta/al/proyecto/data/raw/conagua_smn/estado=sin/fuente=normales_climatologicas/producto=diarios_txt
OUT_DIR: /ruta/al/proyecto/data/interim/organized/estado=sin

Encontrados 168 archivos crudos en:
/ruta/al/proyecto/data/raw/conagua_smn/estado=sin/fuente=normales_climatologicas/producto=diarios_txt

[OK] Estación 25001: 23011 filas, años=63
[OK] Estación 25002: 21435 filas, años=59
[FAIL] dia25099.txt: No encontré encabezado de tabla 'FECHA'
...
Listo
Índice generado en:
/ruta/al/proyecto/data/interim/organized/estado=sin/_index.csv
Salida organizada en:
/ruta/al/proyecto/data/interim/organized/estado=sin
```

---

## Rol dentro del proyecto

Este script corresponde a la transición entre la capa de datos crudos (`raw`) y la capa de datos organizados (`interim`). Es el paso inmediatamente posterior al script de descarga (`download_sinaloa_raw_pro.py`) y produce la estructura que consumen todos los análisis posteriores del proyecto.

Dentro del proyecto de reconstrucción hidrometeorológica, este paso prepara una base estructurada y trazable para etapas como:

- Análisis exploratorio de datos
- Análisis de valores faltantes
- Análisis temporal y estacional
- Limpieza y normalización
- Segmentación train/validation/test
- Modelado de imputación generativa

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Proyecto de Residencias Profesionales**  
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*  
Laboratorio de Geomática y Teledetección
