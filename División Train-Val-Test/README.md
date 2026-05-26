# 3.4 División Train / Val / Test

## Descripción

Esta etapa separa el dataset procesado en tres subconjuntos de entrenamiento, validación y prueba, respetando el orden cronológico de cada serie de estación para evitar fuga de información entre conjuntos.

**Jira:** RES-28 | **Subtareas:** RES-109, RES-110, RES-111, RES-112  
**Responsable:** Data scientist  
**Dependencia:** 3.3 (Dataset Final Procesado)

---

## Entregables

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Configuración | `División Train-Val-Test/config.yaml` | Proporciones, estrategia y rutas |
| Script principal | `División Train-Val-Test/split.py` | División reproducible por estación |
| Script de verificación | `División Train-Val-Test/verify_leakage.py` | Pruebas de ausencia de leakage |
| Conjunto train | `data/splits/train/train.parquet` / `.csv` | 70 % de los registros |
| Conjunto val | `data/splits/val/val.parquet` / `.csv` | 15 % de los registros |
| Conjunto test | `data/splits/test/test.parquet` / `.csv` | 15 % de los registros |
| Índice de fronteras | `data/splits/split_index.csv` | Fechas de corte por estación |
| Reporte del split | `reports/split_report.csv` | Métricas globales de la partición |

---

## Proporciones y criterios de partición (RES-109)

El dataset se divide en tres subconjuntos con las siguientes proporciones:

| Conjunto | Proporción | Registros reales | Uso |
|----------|-----------|-----------------|-----|
| **train** | 70 % | 1,127,704 | Entrenamiento del modelo generativo |
| **val**   | 15 % | 241,673   | Ajuste de hiperparámetros / early stopping |
| **test**  | 15 % | 241,741   | Evaluación final de métricas de imputación |

### Estrategia: `temporal_per_station`

Cada estación se divide de forma **independiente y cronológica**. Los registros de cada estación se ordenan por fecha y se asignan secuencialmente:

```
[─────────────── 70 % train ───────────────][─── 15 % val ───][─── 15 % test ───]
 ↑ primer registro                                               ↑ último registro
 (fecha más antigua de la estación)               (fecha más reciente de la estación)
```

Esta estrategia se eligió frente a un corte global de fechas por las razones siguientes:

| Criterio | Corte global de fechas | Por estación (elegida) |
|----------|----------------------|----------------------|
| Maximiza datos de entrenamiento | No — estaciones cortas quedan sin test | Sí |
| Respeta heterogeneidad temporal | No | Sí |
| Evita leakage intra-estación | Sí | Sí |
| Reproducible | Sí | Sí |

### Criterio anti-leakage

El límite de corte se calcula con `floor()`, garantizando que ningún registro sea asignado a más de un conjunto. Dentro de cada estación se verifica estrictamente que:

- `max(train.date) < min(val.date)` — entrenamiento termina antes de que empiece validación.
- `max(val.date) < min(test.date)` — validación termina antes de que empiece prueba.

---

## Estructura de `data/splits/`

```
data/splits/
├── train/
│   ├── train.parquet      # 70 % — entrenamiento (1,127,704 filas)
│   └── train.csv
├── val/
│   ├── val.parquet        # 15 % — validación   (241,673 filas)
│   └── val.csv
├── test/
│   ├── test.parquet       # 15 % — prueba       (241,741 filas)
│   └── test.csv
├── split_index.csv        # fronteras temporales por estación
└── _logs/
    └── split_run.log
```

### Esquema de los conjuntos

Los tres archivos comparten el mismo esquema que `dataset_final.parquet`:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `estacion` | `str` | Clave SMN de 5 dígitos |
| `date` | `datetime64[ns]` | Fecha de la observación |
| `precip` | `float64` | Precipitación — MinMaxScaler [0, 1] |
| `evap` | `float64` | Evaporación — MinMaxScaler [0, 1] |
| `tmax` | `float64` | Temperatura máxima — StandardScaler (μ=0, σ=1) |
| `tmin` | `float64` | Temperatura mínima — StandardScaler (μ=0, σ=1) |

### Columnas de `split_index.csv`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `estacion` | str | Clave SMN de la estación |
| `total_registros` | int | Total de días en el dataset final |
| `n_train` / `n_val` / `n_test` | int | Número de registros por conjunto |
| `pct_train` / `pct_val` / `pct_test` | float | Porcentaje real por conjunto |
| `train_start` / `train_end` | date | Rango de fechas del conjunto de entrenamiento |
| `val_start` / `val_end` | date | Rango de fechas del conjunto de validación |
| `test_start` / `test_end` | date | Rango de fechas del conjunto de prueba |

---

## Cómo ejecutar

> Requiere haber completado la etapa 3.3 (Dataset Final Procesado).

```bash
# 1. Generar los tres conjuntos
python "División Train-Val-Test/split.py"

# 2. Verificar ausencia de leakage (retorna exit code 0 si pasa, 1 si falla)
python "División Train-Val-Test/verify_leakage.py"
```

---

## Verificación de ausencia de leakage (RES-111)

`verify_leakage.py` ejecuta cuatro pruebas sobre los conjuntos generados:

| # | Prueba | Descripción |
|---|--------|-------------|
| 1 | Intersección de fechas | Ningún par `(estacion, date)` aparece en más de un conjunto |
| 2 | Orden temporal por estación | Para cada estación: `max(train) < min(val)` y `max(val) < min(test)` |
| 3 | Cobertura completa | La unión de los tres conjuntos cubre exactamente todos los registros del dataset original para las estaciones incluidas |
| 4 | Proporciones globales | Las proporciones reales no se desvían más de ±3 % de las configuradas (70/15/15) |

El script retorna **exit code 0** si todas las pruebas pasan, o **exit code 1** con detalle de errores si falla alguna. Resultado de la última ejecución: **4/4 PASS**.

---

## Resultados del proceso de partición (RES-112)

**Dataset fuente:** `data/processed/dataset_final.parquet`  
1,611,118 registros diarios · 173 estaciones · 1908–2026 · 4 variables escaladas

### Parámetros utilizados

| Parámetro | Valor |
|-----------|-------|
| `train_ratio` | 0.70 |
| `val_ratio` | 0.15 |
| `test_ratio` | 0.15 |
| `strategy` | `temporal_per_station` |
| `min_records_per_station` | 30 |
| `random_seed` | 42 (documentado; sin aleatorización) |

### Valores faltantes por conjunto

Los `NaN` heredan la distribución del dataset original; no existe imputación en esta etapa.

| Variable | Dataset original | train | val | test |
|----------|-----------------|-------|-----|------|
| `precip` | 0.67 % | 0.80 % | 0.21 % | 0.56 % |
| `evap`   | 38.66 % | 38.46 % | 29.66 % | 48.70 % |
| `tmax`   | 7.03 % | 9.04 % | 2.20 % | 2.42 % |
| `tmin`   | 7.03 % | 9.04 % | 2.20 % | 2.42 % |

> `evap` muestra alta variabilidad entre conjuntos porque muchas estaciones solo midieron evaporación en periodos específicos: las series más antiguas (train) y más recientes (test) concentran los periodos de mayor discontinuidad.

### Fronteras de partición — estaciones con mayor cobertura

| Estación | Registros | train | val | test |
|----------|-----------|-------|-----|------|
| 25046 | 29,259 | 1942-01-01 → 1999-07-02 | 1999-07-03 → 2012-04-17 | 2012-04-18 → 2026-01-31 |
| 25081 | 28,898 | 1944-08-01 → 2002-01-22 | 2002-01-23 → 2014-02-06 | 2014-02-07 → 2026-01-31 |
| 25037 | 24,959 | 1953-01-01 → 2005-04-28 | 2005-04-29 → 2015-07-29 | 2015-07-30 → 2025-11-30 |

> Las fronteras exactas para las 173 estaciones están en `data/splits/split_index.csv`.

### Verificación de leakage

```
[1/4] Intersección de fechas entre conjuntos ...  PASS
[2/4] Orden temporal estricto por estación    ...  PASS
[3/4] Cobertura completa vs dataset original  ...  PASS
[4/4] Proporciones globales (tolerancia ±3 %) ...  PASS

Estaciones verificadas: 173 — Sin leakage detectado entre conjuntos
```

---

## Decisiones de diseño

- **Por estación, no por fecha global**: el dataset contiene estaciones con rangos temporales muy distintos (1908–2026 vs series cortas de 5 años). Un corte de fecha global dejaría estaciones históricas sin conjunto de prueba.
- **Sin aleatorización**: la división es puramente determinista por orden cronológico. El `random_seed` está documentado en `config.yaml` por consistencia con el resto del pipeline, pero no se utiliza.
- **Mínimo de 30 registros**: estaciones con menos de 30 días de datos quedan excluidas del split para evitar conjuntos vacíos. Ninguna estación fue excluida en la ejecución actual.
- **Parquet + CSV dual**: mismo criterio que las etapas anteriores — Parquet para eficiencia en el pipeline de ML, CSV para auditoría manual.
