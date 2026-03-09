# Organizador de datos crudos hidrometeorológicos por estación, año y variable

Este script transforma los archivos crudos diarios descargados desde **SMN–CONAGUA** para el estado de **Sinaloa** en un dataset organizado, limpio y particionado, listo para etapas posteriores de análisis exploratorio, evaluación de valores faltantes, preparación de datos y modelado.

Su función principal es convertir archivos `.txt` originales de estaciones climatológicas en una estructura jerárquica de almacenamiento por:

- **estación**
- **año**
- **variable climática**

Además, genera un índice global con metadatos de salida que facilita la trazabilidad, auditoría y control de calidad del procesamiento. Esta organización corresponde a la capa `interim` del proyecto, separada explícitamente de la capa `raw`.

---

## Objetivo

El objetivo de este script es construir una versión organizada del dataset hidrometeorológico a partir de los archivos crudos descargados previamente desde CONAGUA/SMN, preservando la trazabilidad del dato original y facilitando el acceso eficiente por particiones temporales y variables.

Este paso forma parte de la fase de preparación de datos del proyecto de reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial. La estructura resultante permite trabajar posteriormente con pipelines de imputación, validación estadística y modelado reproducible.

---

## Qué hace el script

El script realiza automáticamente las siguientes tareas:

- Lee todos los archivos `.txt` crudos almacenados en la carpeta `raw`.
- Detecta la línea donde comienza la tabla de datos dentro de cada archivo.
- Extrae únicamente la tabla climatológica útil.
- Convierte los valores `"NULO"` a valores nulos estándar (`NaN`).
- Convierte la columna `FECHA` a tipo fecha.
- Convierte a tipo numérico las variables climáticas esperadas.
- Filtra únicamente registros con fecha válida.
- Ordena cronológicamente los datos.
- Separa los registros por año calendario.
- Divide cada año por variable climática.
- Guarda cada partición en formato `.csv` y `.parquet`.
- Genera un archivo `_index.csv` con información resumida de todos los archivos producidos.

---

## Variables procesadas

El script considera las siguientes variables climáticas como variables esperadas:

| Variable | Descripción |
|----------|-------------|
| `PRECIP` | Precipitación diaria |
| `EVAP`   | Evaporación diaria |
| `TMAX`   | Temperatura máxima diaria |
| `TMIN`   | Temperatura mínima diaria |

Para cada variable, se genera un archivo independiente con dos columnas:

- `date` → fecha en formato `YYYY-MM-DD`
- `value` → valor observado de la variable

Los valores faltantes originalmente etiquetados como `"NULO"` se convierten a `NaN`, manteniendo consistencia con el esquema del dataset organizado definido en el proyecto.

---

## Estructura de entrada

El script espera encontrar los archivos crudos en la siguiente ruta:

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

Estos archivos corresponden a registros diarios históricos por estación climatológica.

---

## Estructura de salida

Los datos organizados se guardan en la siguiente ruta:

```text
data/interim/organized/estado=sin/
```

La estructura final generada es:

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
            │   │   ├── precip.csv
            │   │   ├── precip.parquet
            │   │   ├── evap.csv
            │   │   ├── evap.parquet
            │   │   ├── tmax.csv
            │   │   ├── tmax.parquet
            │   │   ├── tmin.csv
            │   │   └── tmin.parquet
            │   ├── year=1962/
            │   └── ...
            │
            ├── estacion=25002/
            │   └── ...
            │
            └── _index.csv
```

Esta organización jerárquica fue definida precisamente para facilitar trazabilidad, acceso por estación, análisis temporal anual y procesamiento modular por variable.

---

## Estructuración del Dataset

### Organización jerárquica

La estructura del dataset responde a tres niveles principales:

#### Nivel 1: Estación

Cada estación meteorológica se almacena en un directorio independiente con el formato:

```text
estacion=25001/
```

Donde `25001` corresponde a la clave oficial de estación definida por CONAGUA. Se conserva el identificador original de la fuente para mantener consistencia y trazabilidad.

#### Nivel 2: Año

Dentro de cada estación, los datos se organizan por año calendario:

```text
year=1961/
year=1962/
...
```

Esto permite:

- acceso eficiente a periodos específicos
- segmentación temporal para entrenamiento, validación y prueba
- reducción de carga en memoria al procesar subconjuntos anuales

#### Nivel 3: Variable climática

Dentro de cada carpeta anual, los datos se almacenan por variable:

```text
precip.csv / precip.parquet
evap.csv   / evap.parquet
tmax.csv   / tmax.parquet
tmin.csv   / tmin.parquet
```

Cada archivo contiene solamente las columnas `date` y `value`. Esta forma de organización fue elegida para facilitar el procesamiento posterior dentro del pipeline del proyecto.

---

### Convenciones de nomenclatura

Se utilizan convenciones tipo `key=value` en nombres de carpetas, por ejemplo:

```text
estado=sin
estacion=25001
year=1961
```

Estas convenciones permiten:

- escalabilidad futura
- claridad semántica
- compatibilidad con pipelines y sistemas de particionado de datos
- integración sencilla con flujos de procesamiento tipo data engineering

Los archivos de salida siguen la convención `<variable>.csv` / `<variable>.parquet`, siempre en minúsculas:

```text
precip.csv
tmax.parquet
```

---

### Formatos de almacenamiento

El script guarda cada variable en dos formatos complementarios:

**CSV**
- Alta compatibilidad
- Fácil inspección manual
- Útil para revisión rápida
- Interoperabilidad con múltiples herramientas

**Parquet**
- Formato columnar optimizado
- Menor tamaño en disco
- Mejor rendimiento de lectura y escritura
- Preservación de tipos de datos
- Recomendable para procesamiento analítico y modelado

La coexistencia de ambos formatos permite tener tanto un formato accesible para inspección como uno optimizado para pipelines de ciencia de datos.

---

### Archivo de índice global

El script genera un archivo global llamado `_index.csv`, ubicado en:

```text
data/interim/organized/estado=sin/_index.csv
```

Este archivo contiene las siguientes columnas:

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año del registro |
| `variable` | Variable climática |
| `path_parquet` | Ruta al archivo Parquet |
| `path_csv` | Ruta al archivo CSV |
| `rows` | Número de filas |
| `missing_pct` | Porcentaje de valores faltantes |

Su propósito es proporcionar un registro centralizado de todas las particiones generadas y apoyar tareas de auditoría, control de calidad, trazabilidad completa, monitoreo de cobertura temporal y evaluación de porcentaje de faltantes por archivo.

---

## Flujo general del script

1. Define la carpeta raíz del proyecto.
2. Localiza la carpeta de archivos crudos descargados.
3. Crea la carpeta de salida si no existe.
4. Inicializa el archivo `_index.csv` si aún no existe.
5. Verifica que `pyarrow` esté disponible para exportar archivos Parquet.
6. Recorre todos los archivos `.txt` encontrados.
7. Extrae el identificador de estación desde el nombre del archivo.
8. Detecta la línea donde inicia la tabla de datos (`FECHA`).
9. Carga la tabla con `pandas`.
10. Elimina columnas vacías o auxiliares.
11. Filtra únicamente fechas válidas.
12. Convierte las variables climáticas a formato numérico.
13. Crea una columna `year`.
14. Divide el dataset por año.
15. Divide cada año por variable.
16. Guarda cada variable en CSV y Parquet.
17. Registra la salida en `_index.csv`.

---

## Requisitos

Este script requiere:

- Python 3.x
- `pandas`
- `pyarrow`

### Instalación de dependencias

```bash
pip install pandas pyarrow
```

---

## Ejecución

```bash
python organize_raw_by_station_year_variable_parquet.py
```

### Configuración importante

La ruta raíz del proyecto se define manualmente dentro del script:

```python
PROJECT_ROOT = r"C:\Users\Jose Garcia\Documents\10_SEMESTRE_TEC\RESIDENCIAS\Reconstruccion_de_Base_de_Datos_Nuestro"
```

> Nota: Si el proyecto se mueve a otra ubicación, esta ruta debe actualizarse antes de ejecutar el script.

---

## Validaciones incorporadas

El script incluye varias validaciones útiles para asegurar consistencia durante el procesamiento:

- Verifica que exista la carpeta de entrada.
- Verifica que existan archivos `.txt`.
- Detecta si falta el encabezado `FECHA`.
- Elimina columnas `Unnamed` generadas por tabulaciones extra.
- Filtra únicamente fechas con formato válido.
- Convierte automáticamente valores no numéricos a `NaN`.
- Verifica que `pyarrow` esté instalado antes de guardar Parquet.

> Si alguna estación falla durante el procesamiento, el script continúa con las demás y reporta el error en consola.

---

## Ejemplo de salida en consola

```text
Encontrados 192 archivos crudos en:
C:\...\data\raw\conagua_smn\estado=sin\fuente=normales_climatologicas\producto=diarios_txt

[OK] Estación 25001: 23011 filas, años=63
[OK] Estación 25002: 21435 filas, años=59
[FAIL] dia25099.txt: No encontré encabezado de tabla 'FECHA'

Listo
Índice generado en:
C:\...\data\interim\organized\estado=sin\_index.csv
Salida organizada en:
C:\...\data\interim\organized\estado=sin
```

---

## Rol dentro del proyecto

Este script corresponde a la transición entre la capa de datos crudos (`raw`) y la capa de datos organizados (`interim`).

Dentro del proyecto de reconstrucción hidrometeorológica, este paso permite preparar una base estructurada y trazable para etapas posteriores como:

- Análisis exploratorio de datos
- Análisis de valores faltantes
- Análisis temporal y estacional
- Limpieza y normalización
- Segmentación train/validation/test
- Modelado de imputación generativa

Desde el punto de vista arquitectónico, esta organización responde a principios de **modularidad**, **separación de capas**, **escalabilidad**, **reproducibilidad** y **trazabilidad del dato**, facilitando la implementación del pipeline de reconstrucción planteado en el proyecto.

---

## Nombre del script

```text
organize_raw_by_station_year_variable_parquet.py
```

---

## Autor

**Proyecto de Residencias**  
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*
