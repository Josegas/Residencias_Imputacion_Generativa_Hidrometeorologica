# Limpieza inicial del dataset hidrometeorológico

Este script aplica la limpieza inicial al dataset hidrometeorológico de **Sinaloa** organizado en la capa `interim`, generando una capa `cleaned` lista para las etapas posteriores de normalización, segmentación y modelado de imputación generativa.

Su función principal es detectar y tratar valores inconsistentes en las cuatro variables climáticas del dataset (`precip`, `evap`, `tmax`, `tmin`), documentar los cambios realizados y verificar que los datos resultantes cumplen los criterios de calidad definidos en el EDA.

---

## Objetivo

Producir una versión limpia y auditada del dataset hidrometeorológico a partir de la capa `interim`, eliminando únicamente los errores de captura que no tienen explicación física posible y conservando los valores atípicos que podrían ser registros reales de estaciones en la sierra de Sinaloa.

Este paso corresponde a la **Actividad 3.1** del proyecto y satisface los criterios de aceptación de los tickets RES-94, RES-95, RES-96 y RES-97.

---

## Qué hace el script

- Resuelve la ruta raíz del proyecto automáticamente a partir de su propia ubicación (`Path(__file__).resolve().parent.parent`), sin necesidad de configurar rutas manualmente.
- Carga todos los parámetros de limpieza desde `config.yaml` (rutas, límites físicos, umbrales IQR).
- Lee el índice de particiones generado por `organize_raw_by_station_year_variable_parquet.py`.
- Por cada partición (estación × año × variable):
  - Corrige tipos: `date` → `datetime64`, `value` → `float64`.
  - Elimina filas con fecha duplicada (conserva la primera ocurrencia).
  - Documenta outliers IQR del EDA (los conserva — posibles registros reales).
  - Aplica límites físicos: convierte a `NaN` los valores imposibles físicamente.
  - Ordena cronológicamente y guarda el parquet limpio.
- Genera `cleaning_report.csv` con métricas detalladas por partición.
- Genera `_index_cleaned.csv` con el índice de la capa `cleaned`.
- Ejecuta una pasada de validación post-limpieza que verifica que los archivos guardados cumplen el AC: *"no quedan valores inconsistentes"*.
- Si la validación detecta problemas, genera `validation_report.csv` con el detalle.

---

## Variables procesadas

| Variable | Descripción | Límite inferior | Límite superior |
|----------|-------------|-----------------|-----------------|
| `precip` | Precipitación diaria (mm) | 0.0 | 500.0 |
| `evap`   | Evaporación diaria (mm)   | 0.0 | 60.0  |
| `tmax`   | Temperatura máxima (°C)   | -5.0 | 55.0 |
| `tmin`   | Temperatura mínima (°C)   | -15.0 | 45.0 |

Los límites físicos se basan en los hallazgos del EDA (actividad 2.4) y pueden modificarse en `config.yaml` sin tocar el script.

### Decisión sobre outliers IQR

Los outliers detectados con el criterio IQR del EDA se **conservan** en los datos limpios. Esta decisión se basa en el análisis territorial: Sinaloa incluye estaciones en la sierra donde temperaturas bajas (`TMAX < 20.25°C`, `TMIN < -3.75°C`) son físicamente plausibles. Solo se eliminan los valores fuera de los límites físicos absolutos.

---

## Estructura de entrada

El script espera el índice generado por `organize_raw_by_station_year_variable_parquet.py` en:

```text
data/interim/organized/estado=sin/_index.csv
```

Y los parquets organizados en:

```text
data/interim/organized/estado=sin/
├── estacion=25001/
│   ├── year=1961/
│   │   ├── precip.parquet
│   │   ├── evap.parquet
│   │   ├── tmax.parquet
│   │   └── tmin.parquet
│   └── ...
└── ...
```

---

## Estructura de salida

Los datos limpios se guardan en:

```text
data/
└── cleaned/
    ├── organized/
    │   └── estado=sin/
    │       ├── estacion=25001/
    │       │   ├── year=1961/
    │       │   │   ├── precip.parquet
    │       │   │   ├── evap.parquet
    │       │   │   ├── tmax.parquet
    │       │   │   └── tmin.parquet
    │       │   └── ...
    │       └── _index_cleaned.csv
    └── logs/
        └── cleaning_run.log

reports/
├── cleaning_report.csv
└── validation_report.csv   ← solo se genera si hay problemas
```

---

## Reportes generados

### `reports/cleaning_report.csv`

Una fila por partición con las métricas de cada paso de limpieza.

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año |
| `variable` | Variable climática |
| `filas_originales` | Filas antes de limpiar |
| `fechas_invalidas` | Filas eliminadas por fecha no convertible |
| `duplicados` | Filas eliminadas por fecha duplicada |
| `outliers_iqr_bajo` | Valores bajo el umbral IQR (documentados, conservados) |
| `outliers_iqr_alto` | Valores sobre el umbral IQR (documentados, conservados) |
| `outliers_fisicos_bajo` | Valores convertidos a NaN por estar bajo el límite físico |
| `outliers_fisicos_alto` | Valores convertidos a NaN por estar sobre el límite físico |
| `nulos_antes` | Valores NaN preexistentes antes de la limpieza |
| `nulos_despues` | Valores NaN tras aplicar límites físicos |
| `missing_pct_clean` | Porcentaje de faltantes en la partición limpia |
| `path_parquet_clean` | Ruta al parquet limpio guardado |

### `data/cleaned/organized/estado=sin/_index_cleaned.csv`

Índice de todas las particiones limpias generadas.

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año |
| `variable` | Variable climática |
| `path_parquet` | Ruta al parquet limpio |
| `rows` | Número de filas |
| `missing_pct` | Porcentaje de faltantes |

### `reports/validation_report.csv` *(solo si hay problemas)*

Lista de particiones que no superaron la validación post-limpieza, con el tipo de problema detectado.

---

## Configuración (`config.yaml`)

Todos los parámetros de limpieza se gestionan en `config.yaml`. No es necesario editar el script para adaptar el pipeline:

```yaml
paths:
  interim_subpath: [data, interim, organized, "estado=sin"]
  cleaned_subpath: [data, cleaned, organized, "estado=sin"]
  ...

physical_limits:
  precip: {min: 0.0, max: 500.0}
  evap:   {min: 0.0, max: 60.0}
  tmax:   {min: -5.0, max: 55.0}
  tmin:   {min: -15.0, max: 45.0}

iqr_thresholds:
  tmax: {lower: 20.25, upper: 45.45, nota: "..."}
  ...
```

---

## Flujo general del script

1. Cargar configuración desde `config.yaml`.
2. Resolver la ruta raíz del proyecto automáticamente.
3. Leer y desduplicar el índice de particiones `_index.csv`.
4. Por cada partición:
   - Leer el parquet de `data/interim/`.
   - Corregir tipos (`date`, `value`).
   - Eliminar filas con fecha duplicada.
   - Contar outliers IQR (sin eliminar).
   - Aplicar límites físicos (valores extremos → `NaN`).
   - Ordenar cronológicamente.
   - Guardar en `data/cleaned/`.
5. Guardar `cleaning_report.csv` e `_index_cleaned.csv`.
6. Ejecutar la validación post-limpieza (RES-96):
   - Verificar tipos correctos.
   - Verificar ausencia de fechas duplicadas.
   - Verificar que ningún valor no-nulo viola los límites físicos.
7. Imprimir resumen final en consola y en el log.

Si alguna partición falla durante la lectura o escritura, el error se registra en el log y el pipeline continúa con las demás.

---

## Validaciones incorporadas

- Verifica que el índice de entrada existe antes de iniciar.
- Verifica que cada archivo parquet existe antes de intentar leerlo.
- Captura errores de lectura y escritura por partición sin detener el pipeline.
- **Validación post-limpieza**: re-lee cada parquet limpio y verifica activamente que cumple los criterios de calidad (tipos, duplicados, límites físicos). Satisface el AC de RES-96: *"no quedan valores inconsistentes"*.

---

## Requisitos

- Python 3.9 o superior
- `pandas`
- `pyarrow`
- `numpy`
- `pyyaml`

```bash
pip install pandas pyarrow numpy pyyaml
```

---

## Ejecución

```bash
python "Validacion y limpieza/cleaning.py"
```

> El script resuelve la ruta del proyecto automáticamente asumiendo que vive en una subcarpeta de primer nivel del repositorio. Si se mueve a otra ubicación, ajusta la línea:
> ```python
> PROJECT_ROOT = Path(__file__).resolve().parent.parent
> ```

### Modo datos externos (`--input-dir` / `--output-dir`)

Al procesar datos de fuentes externas (no CONAGUA), es posible redirigir las rutas de entrada y salida para mantener los datos originales intactos:

```bash
python "Validacion y limpieza/cleaning.py" \
    --input-dir  data/interim/organized_external/estado=sin \
    --output-dir data/cleaned_external
```

| Argumento | Descripción |
|-----------|-------------|
| `--input-dir` | Directorio raíz de las particiones organizadas (relativo a la raíz del proyecto o absoluto). Si se omite, se usa `data/interim/organized/estado=sin`. |
| `--output-dir` | Directorio de salida para los parquets limpios e índice. Si se omite, se usa `data/cleaned/organized/estado=sin`. |

El script construye las rutas de salida replicando la estructura relativa de cada partición respecto al `--input-dir`, de modo que la jerarquía `estacion=XXXXX/anio=YYYY/variable=ZZZ/` se conserva en el directorio destino.

Este argumento lo pasa automáticamente `run_pipeline.py` cuando se usa `--external`. No es necesario invocarlo manualmente en ese flujo.

### Salida esperada en consola

```text
2025-xx-xx xx:xx:xx  INFO      INICIO DE LIMPIEZA — dataset hidrometeorologico Sinaloa
2025-xx-xx xx:xx:xx  INFO      Config cargada desde: .../Validacion y limpieza/config.yaml
2025-xx-xx xx:xx:xx  INFO      Particiones en el indice : 19,392
2025-xx-xx xx:xx:xx  INFO      Estaciones               : 168
2025-xx-xx xx:xx:xx  INFO      Variables                : ['evap', 'precip', 'tmax', 'tmin']
...
2025-xx-xx xx:xx:xx  INFO      VALIDACION POST-LIMPIEZA (RES-96)
2025-xx-xx xx:xx:xx  INFO      Particiones validas      : 19,392
2025-xx-xx xx:xx:xx  INFO      VALIDACION EXITOSA: todos los datos limpios cumplen los criterios de calidad
2025-xx-xx xx:xx:xx  INFO      AC RES-96 cumplido: no quedan valores inconsistentes
```

---

## Rol dentro del proyecto

Este script corresponde a la transición entre la capa de datos organizados (`interim`) y la capa de datos limpios (`cleaned`). Es el paso inmediatamente posterior al script de organización (`organize_raw_by_station_year_variable_parquet.py`) y produce la estructura que consume el pipeline de normalización, segmentación y modelado.

Dentro del proyecto de reconstrucción hidrometeorológica, este paso prepara una base estructurada y auditada para etapas como:

- Normalización de variables
- Segmentación train/validation/test
- Modelado de imputación generativa (GAIN, GRUI, etc.)
- Evaluación de modelos

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Proyecto de Residencias Profesionales**
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*
Laboratorio de Geomática y Teledetección
