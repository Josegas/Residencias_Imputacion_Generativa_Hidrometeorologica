# 3.3 Dataset Final Procesado

## Descripción

Esta etapa consolida todas las transformaciones de limpieza (3.1) y escalamiento (3.2) en un pipeline reproducible y exporta el **dataset final** listo para ser utilizado por los modelos de imputación generativa.

**Jira:** RES-27 | **Subtareas:** RES-105, RES-106, RES-107, RES-108  
**Responsable:** Data engineer / Data scientist  
**Dependencias:** 3.1 (Validación y limpieza), 3.2 (Preprocesamiento)

---

## Entregables

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Script de pipeline | `Dataset Final Procesado/pipeline.py` | Flujo unificado de consolidación y exportación |
| Script de validación | `Dataset Final Procesado/validate.py` | Verificación de integridad y consistencia |
| Dataset por estación (Parquet) | `data/processed/parquet/estacion=XXXXX.parquet` | Un archivo por estación, formato wide |
| Dataset por estación (CSV) | `data/processed/csv/estacion=XXXXX.csv` | Mismo contenido, formato legible |
| Dataset consolidado (Parquet) | `data/processed/dataset_final.parquet` | Todas las estaciones en un solo archivo |
| Dataset consolidado (CSV) | `data/processed/dataset_final.csv` | Ídem en CSV |
| Índice de archivos | `data/processed/_index_processed.csv` | Mapa de todos los archivos generados |
| Reporte de pipeline | `reports/pipeline_report.csv` | Métricas por estación tras la consolidación |
| Reporte de validación | `reports/validation_report.csv` | Resultado de cada check de integridad |

---

## Estructura de `data/processed/`

```
data/processed/
├── parquet/
│   ├── estacion=25001.parquet
│   ├── estacion=25003.parquet
│   └── ...                          # 173 estaciones de Sinaloa
├── csv/
│   ├── estacion=25001.csv
│   └── ...                          # 173 estaciones de Sinaloa
├── dataset_final.parquet            # todas las estaciones (long-format)
├── dataset_final.csv
├── _index_processed.csv             # índice de rutas y métricas
└── _logs/
    ├── pipeline_run.log
    └── validation_run.log
```

---

## Esquema del dataset

### Archivos por estación (`estacion=XXXXX.*`)

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `date` | `datetime64[ns]` | Fecha de la observación (ISO 8601) |
| `precip` | `float64` | Precipitación escalada — MinMaxScaler [0, 1] |
| `evap` | `float64` | Evaporación escalada — MinMaxScaler [0, 1] |
| `tmax` | `float64` | Temperatura máxima escalada — StandardScaler (μ=0, σ=1) |
| `tmin` | `float64` | Temperatura mínima escalada — StandardScaler (μ=0, σ=1) |

### Dataset consolidado (`dataset_final.*`)

Añade la columna `estacion` (str, código SMN) como primera columna:

| Columna | Tipo |
|---------|------|
| `estacion` | `str` |
| `date` | `datetime64[ns]` |
| `precip` | `float64` |
| `evap` | `float64` |
| `tmax` | `float64` |
| `tmin` | `float64` |

Los valores `NaN` representan registros faltantes (datos históricos no disponibles); **no son errores**.

---

## Transformaciones aplicadas

### Etapa 3.1 — Limpieza (`Validacion y limpieza/cleaning.py`)

| Transformación | Detalle |
|----------------|---------|
| Corrección de tipos | `date → datetime64`, `value → float64` |
| Eliminación de duplicados | Se conserva la primera ocurrencia por fecha |
| Límites físicos | Valores fuera de rango → `NaN` (ver tabla abajo) |
| Outliers IQR | Documentados en `cleaning_report.csv`; **conservados** (estaciones de montaña) |

**Límites físicos aplicados:**

| Variable | Mín | Máx | Unidad |
|----------|-----|-----|--------|
| `precip` | 0.0 | 500.0 | mm |
| `evap` | 0.0 | 60.0 | mm |
| `tmax` | −5.0 | 55.0 | °C |
| `tmin` | −15.0 | 45.0 | °C |

### Etapa 3.2 — Escalamiento (`Preprocesamiento/normalize.py`)

| Variable | Scaler | Parámetros | Justificación |
|----------|--------|-----------|---------------|
| `precip` | MinMaxScaler | [0, 1] | Límite inferior fijo en 0; distribución asimétrica con muchos ceros |
| `evap` | MinMaxScaler | [0, 1] | Ídem; preserva proporción entre días de alta/baja evaporación |
| `tmax` | StandardScaler | μ=32.67 °C, σ=4.90 °C | Distribución aproximadamente simétrica; estándar para redes neuronales |
| `tmin` | StandardScaler | μ=16.71 °C, σ=6.21 °C | Ídem |

Los scalers son **globales** (entrenados con datos de todas las estaciones), garantizando que el mismo valor físico siempre mapee al mismo valor escalado.  
Los modelos serializados se encuentran en `models/scalers/scaler_*.pkl`.

### Etapa 3.3 — Consolidación (`Dataset Final Procesado/pipeline.py`)

| Acción | Detalle |
|--------|---------|
| Fusión por estación | Todas las particiones anuales de cada variable se concatenan en un único DataFrame |
| Formato wide | Una columna por variable; filas = fechas únicas ordenadas |
| Exportación dual | Parquet (eficiencia) + CSV (legibilidad) |
| Dataset consolidado | Todas las estaciones en `dataset_final.parquet/.csv` |

---

## Criterios de aceptación

| Criterio | Verificado por |
|----------|----------------|
| Sin valores inconsistentes ni errores de formato | `validate.py` — checks de tipo, duplicados, nulos en fechas |
| Variables escaladas según lo definido en 3.2 | `validate.py` — `precip/evap ∈ [0,1]`; `tmax/tmin ∈ [−6,6]` |
| Estructura compatible con el pipeline de ML | Formato wide, columnas ordenadas, Parquet + CSV en `data/processed/` |

---

## Cómo ejecutar

> Requiere haber completado las etapas 3.1 y 3.2.

```bash
# 1. Generar el dataset final
python "Dataset Final Procesado/pipeline.py"

# 2. Verificar integridad
python "Dataset Final Procesado/validate.py"
```

Los reportes se guardan automáticamente en `reports/`.

### Modo datos externos (`--input-dir`)

Al consolidar datos de fuentes externas, es posible leer desde un directorio escalado alternativo. La salida (`data/processed/dataset_final.parquet`) siempre es la misma, por lo que las etapas 8-12 no requieren cambios:

```bash
python "Dataset Final Procesado/pipeline.py" \
    --input-dir data/scaled_external
```

| Argumento | Descripción |
|-----------|-------------|
| `--input-dir` | Directorio raíz de las particiones escaladas. Si se omite, se usa `data/scaled/organized/estado=sin`. |

Este argumento lo pasa automáticamente `run_pipeline.py` cuando se usa `--external`. No es necesario invocarlo manualmente en ese flujo.

---

## Decisiones de diseño

- **Formato wide por estación**: una fila por fecha, una columna por variable. Facilita la ingesta directa en LSTM, GAN, BRITS y SAITS sin transformaciones adicionales.
- **Dataset consolidado opcional**: `dataset_final.parquet` permite cargar todo en una sola operación; útil para modelos que aprenden representaciones inter-estación (CSDI, GNNs).
- **NaN preservado**: los valores faltantes se mantienen como `NaN` (no imputados en esta etapa). La imputación es el objetivo de las etapas 4+.
- **Escaladores globales**: la reproducibilidad de la transformación inversa (`scaler.inverse_transform`) queda garantizada por los `.pkl` guardados en `models/scalers/`.
