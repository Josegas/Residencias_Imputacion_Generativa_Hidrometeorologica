# 5.2 Imputación Generativa

Implementación de la función de imputación generativa final del proyecto, basada en el modelo **BiGRU-opt** seleccionado en la fase de optimización (US 4.3).

**Jira:** RES-34 | **Subtareas:** RES-128, RES-129, RES-130  
**Responsable:** Científico de datos  
**Dependencia:** 5.1 (Pipeline reproducible final)

> Esta etapa es la **etapa 8** del pipeline automatizado. Se ejecuta automáticamente al correr `run_pipeline.py`, o de forma independiente con `python "Imputación Generativa/impute.py"`.

---

## ¿Qué hace?

Carga el modelo `bigru_opt.pt` y los scalers globales, aplica ventanas deslizantes de 30 días sobre cada estación, reconstruye las series temporales completas promediando predicciones solapadas, y devuelve el dataset con los valores faltantes rellenados en escala original.

**Principio de preservación de datos observados:** los valores originales nunca se modifican. Solo las posiciones que eran `NaN` en la entrada reciben una predicción.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `impute.py` | Función de imputación y punto de entrada CLI |
| `config.yaml` | Rutas, hiperparámetros y parámetros de inferencia |
| `README.md` | Este archivo |

---

## Uso

### Línea de comandos

```bash
# Imputar el dataset final (ruta por defecto: data/processed/dataset_final.parquet)
python "Imputación Generativa/impute.py"

# Especificar un archivo de entrada distinto
python "Imputación Generativa/impute.py" --input data/processed/dataset_final.parquet

# Usar un config.yaml alternativo
python "Imputación Generativa/impute.py" --config ruta/a/config.yaml
```

### Como módulo Python

```python
from pathlib import Path
import pandas as pd
from impute import load_pipeline, impute_dataframe, export_imputed

# Cargar modelo y scalers
pipeline = load_pipeline()

# Imputar un DataFrame con NaN
df_raw     = pd.read_parquet("data/processed/dataset_final.parquet")
df_imputed = impute_dataframe(df_raw, pipeline)

# Exportar a Parquet y CSV
export_imputed(df_imputed, pipeline)
```

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Modelo ganador | `models/optimizacion/bigru_opt.pt` | `Optimización/optimizacion_hiperparametros.ipynb` |
| Scaler precip | `models/scalers/scaler_precip.pkl` | `Preprocesamiento/normalize.py` |
| Scaler evap | `models/scalers/scaler_evap.pkl` | `Preprocesamiento/normalize.py` |
| Scaler tmax | `models/scalers/scaler_tmax.pkl` | `Preprocesamiento/normalize.py` |
| Scaler tmin | `models/scalers/scaler_tmin.pkl` | `Preprocesamiento/normalize.py` |
| Dataset final | `data/processed/dataset_final.parquet` | `Dataset Final Procesado/pipeline.py` |

---

## Salidas generadas

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Dataset imputado | `data/imputed/dataset_imputado.parquet` | Dataset completo con NaN rellenados — artefacto interno del pipeline |
| Reporte | `reports/imputacion/imputacion_report.csv` | NaN rellenados por variable y estación |
| Log | `data/imputed/_logs/imputation_run.log` | Registro completo de la ejecución |

---

## Flujo de imputación

```
seleccion_ejecutiva.csv ──► Determinar modelo ganador
                                     │
dataset_final.parquet                ▼
        │              [Por estación, ordenado por fecha]
        │                            │
        │              ├─ Escalar con scalers globales
        │              │     precip/evap: MinMaxScaler [0, 1]
        │              │     tmax/tmin:   StandardScaler
        │              │
        │              ├─ Generar ventanas de 30 días (stride=7) → (N, 30, 4)
        │              │
        │              ├─ BiGRU-opt (modo eval, sin dropout):
        │              │     output = mask*x + (1-mask)*GRU(x, mask)
        │              │
        │              ├─ Promediar predicciones solapadas por posición
        │              │
        │              ├─ Rellenar solo posiciones NaN originales
        │              │
        │              ├─ Transformación inversa de scalers → escala original
        │              │
        │              ├─ Límites físicos (recorte)
        │              │     precip [0, 500] mm  ·  evap [0, 60] mm
        │              │     tmax [-5, 55] °C    ·  tmin [-15, 45] °C
        │              │
        │              └─ Restricción lógica: si tmax_pred < tmin_pred
        │                    (ambas imputadas) → intercambiar valores
        ▼
dataset_imputado.parquet  (NaN → valores reconstruidos)
```

---

## Arquitectura del modelo

**BiGRUImputer** — GRU bidireccional con re-inyección de observados.

```
Input: (N, T=30, F=4) → concatenar con mask → (N, T, 8)
         ↓
    GRU bidireccional (hidden=128 × 2 direcciones, capas=2)
         ↓
    Linear(256 → 4)
         ↓
    output = mask * x + (1 - mask) * predicción
```

| Hiperparámetro | Default | Óptimo (Optuna TPE) |
|----------------|---------|---------------------|
| `hidden_size` | 128 | 128 |
| `n_layers` | 2 | 2 |
| `dropout` | 0.200 | **0.103** |
| `lr` | 1.0 × 10⁻³ | **1.9 × 10⁻³** |
| `batch_size` | 256 | **128** |

Rendimiento (backtesting 4-fold, MCAR 20%):

| Variable | NSE |
|----------|-----|
| tmax | 0.847 |
| tmin | 0.931 |
| evap | 0.648 |
| precip | 0.056 |
| **Global** | **0.621** |

---

## Configuración (`config.yaml`)

Todos los parámetros se gestionan sin tocar el script:

```yaml
model:
  path: "models/optimizacion/bigru_opt.pt"
  hidden_size: 128
  n_layers: 2

inference:
  batch_size: 512
  device: "auto"    # "auto" → CUDA si disponible, si no CPU

output:
  parquet: "data/imputed/dataset_imputado.parquet"
  report:  "reports/imputacion/imputacion_report.csv"
```

---

## Selección dinámica del modelo ganador

El script **no asume** que el ganador siempre es BiGRU-opt. En cada ejecución lee `reports/optimizacion/seleccion_ejecutiva.csv` (generado por `seleccion_modelo_ganador.ipynb`) para determinar el modelo con mayor puntaje en la matriz de decisión multi-criterio (MCDM):

| Criterio | Peso |
|----------|------|
| NSE global (backtesting 4-fold, MCAR 20%) | 30% |
| RMSE ponderado | 25% |
| Estabilidad entre folds (σ NSE) | 20% |
| KPSS (estacionariedad de residuos) | 15% |
| Complejidad del modelo | 10% |

Si el CSV no existe, carga el modelo configurado en `model.default` del `config.yaml`.

Los checkpoints soportados y sus rutas se configuran en `selection.model_paths`:

```yaml
selection:
  report: "reports/optimizacion/seleccion_ejecutiva.csv"
  model_paths:
    BIGRU-OPT:    "models/optimizacion/bigru_opt.pt"
    BRITS-OPT:    "models/optimizacion/brits_opt.pt"
    SAITS-OPT:    "models/optimizacion/saits_opt.pt"
    XGBOOST-OPT:  "models/optimizacion/xgboost_opt.pkl"
```

---

## Post-procesamiento físico

Después de la transformación inversa de escalers, las predicciones se corrigen para garantizar su validez hidrometeorológica:

**Límites físicos** (recorte por variable):

| Variable | Mínimo | Máximo |
|----------|--------|--------|
| precip | 0 mm | 500 mm |
| evap | 0 mm | 60 mm |
| tmax | −5 °C | 55 °C |
| tmin | −15 °C | 45 °C |

**Restricción lógica tmax ≥ tmin:** cuando ambas temperaturas son imputadas (ambas eran NaN) y la predicción resulta en tmax < tmin, se intercambian los valores para respetar la física del sistema. Los valores observados nunca se modifican.

---

## Criterios de aceptación (RES-128 / RES-130)

| Criterio | Verificación |
|----------|-------------|
| La función se ejecuta sin errores | `python "Imputación Generativa/impute.py"` → exit code 0 |
| Retorna dataset imputado válido | `df_imputed[variables].isna().sum()` ≤ NaN originales no cubiertos por ventanas |
| Imputaciones consistentes | Semilla fijada en config (`random_seed: 42`); modo `eval()` desactiva dropout |
| Valores observados preservados | `assert (df_imputed[~mask_original] == df_raw[~mask_original]).all()` |
| Límites físicos respetados | `assert df_imputed["precip"].min() >= 0` y análogos para cada variable |
| Restricción tmax ≥ tmin | `assert (df_imputed["tmax"] >= df_imputed["tmin"]).all()` |

---

## Requisitos

```bash
pip install torch numpy pandas pyarrow scikit-learn pyyaml
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
