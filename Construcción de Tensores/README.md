# Construcción de Tensores — RES-29

Transforma los splits preprocesados (`train/val/test`) en tensores PyTorch listos para entrenar los modelos de imputación generativa de series temporales hidrometeorologicas de Sinaloa.

---

## Índice

1. [Contexto](#contexto)
2. [Decisión de framework](#decisión-de-framework)
3. [Estructura del módulo](#estructura-del-módulo)
4. [Formato de los tensores](#formato-de-los-tensores)
5. [Convención de máscaras](#convención-de-máscaras)
6. [Delta temporal (BRITS)](#delta-temporal-brits)
7. [Ventanas deslizantes](#ventanas-deslizantes)
8. [Configuración](#configuración)
9. [Cómo ejecutar](#cómo-ejecutar)
10. [Archivos de salida](#archivos-de-salida)
11. [Compatibilidad con modelos](#compatibilidad-con-modelos)
12. [Resultados de validación](#resultados-de-validación)
13. [Dependencias](#dependencias)

---

## Contexto

Esta etapa corresponde a la tarea **3.5 Construcción de tensores** del proyecto de reconstrucción de la base de datos hidrometeorologica de Sinaloa. Recibe los splits temporales generados por la etapa anterior (División Train-Val-Test) y los convierte en tensores con las dimensiones y estructuras que requieren los modelos de deep learning.

**Entradas:**
- `data/splits/train/train.parquet` — 1,127,704 filas, 173 estaciones
- `data/splits/val/val.parquet` — 241,673 filas, 173 estaciones
- `data/splits/test/test.parquet` — 241,741 filas, 173 estaciones

**Variables:** `precip`, `evap`, `tmax`, `tmin` (escaladas en etapas previas)

---

## Decisión de framework

Se eligió **PyTorch** sobre TensorFlow por las siguientes razones:

| Modelo | Framework original |
|--------|--------------------|
| BRITS  | PyTorch |
| SAITS  | PyTorch (PyPOTS) |
| CSDI   | PyTorch |
| LSTM/GRU | PyTorch / TF (compatible) |
| GAN    | PyTorch / TF (compatible) |
| VAE/Autoencoders | PyTorch / TF (compatible) |

Los tres modelos especializados en imputación de series temporales (BRITS, SAITS, CSDI) no tienen implementaciones oficiales en TensorFlow. Usar PyTorch unifica todo el pipeline de modelado en un solo framework.

---

## Estructura del módulo

```
Construcción de Tensores/
├── config.yaml              # Todos los parámetros configurables
├── tensor_builder.py        # Script principal (RES-113) — orquestador
├── sequence_generator.py    # Generación de ventanas deslizantes (RES-114)
├── mask_generator.py        # Máscaras y delta temporal (RES-115)
├── validate_tensors.py      # Validación de compatibilidad PyTorch (RES-116)
└── README.md                # Este archivo
```

### `tensor_builder.py` — RES-113
Orquestador principal. Carga cada split, llama a `SequenceGenerator` y `MaskGenerator`, y guarda los tensores resultantes como archivos `.pt`.

### `sequence_generator.py` — RES-114
Contiene dos clases:
- **`SequenceGenerator`**: genera ventanas deslizantes por estación, respetando el orden cronológico y filtrando ventanas que crucen brechas temporales mayores a `max_gap_days`.
- **`TimeSeriesDataset`**: dataset PyTorch que carga los `.pt` y sirve batches `(X, mask, delta)` para entrenamiento.

### `mask_generator.py` — RES-115
Clase `MaskGenerator` que produce:
- Máscara binaria de observación (1=observado, 0=faltante)
- Tensor X con NaN reemplazados por 0
- Tensor delta (días desde la última observación, para BRITS)

### `validate_tensors.py` — RES-116
Ejecuta 12 checks por split sobre los tensores guardados: shapes, dtypes, ausencia de NaN, máscara binaria, delta no negativo, consistencia entre tensores y compatibilidad con `DataLoader`.

---

## Formato de los tensores

Todos los tensores siguen la convención `(N, T, F)`:

| Dimensión | Significado |
|-----------|-------------|
| `N` | Número de secuencias (ventanas) |
| `T` | Longitud de la ventana (`window_size` = 30 filas) |
| `F` | Número de variables (`n_features` = 4) |

| Tensor | Shape | Dtype | Descripción |
|--------|-------|-------|-------------|
| `X` | `(N, T, F)` | `float32` | Valores escalados. NaN reemplazados por 0. |
| `mask` | `(N, T, F)` | `float32` | 1 = observado, 0 = faltante. |
| `delta` | `(N, T, F)` | `float32` | Días desde la última observación por variable. |
| `meta` | `(N, 2)` | `int64` | `[station_idx, start_date_ordinal]` por secuencia. |

---

## Convención de máscaras

```
mask[n, t, f] = 1  →  el valor X[n, t, f] fue observado (no era NaN)
mask[n, t, f] = 0  →  el valor X[n, t, f] era NaN (faltante o no medido)
```

Esta convención es estándar en BRITS, SAITS y CSDI. Los valores de `observed_value` (1) y `missing_value` (0) son configurables en `config.yaml`.

**Tasas de observación por variable (split train):**

| Variable | Obs% | Nota |
|----------|------|------|
| `precip` | ~99.8% | Casi sin faltantes |
| `evap` | ~70.6% | NaN estructural: no todas las estaciones tienen evaporímetro |
| `tmax` | ~97.8% | Faltantes puntuales |
| `tmin` | ~97.8% | Faltantes puntuales |
| **global** | **~85.7%** | Promedio de las 4 variables |

---

## Delta temporal (BRITS)

El tensor `delta` implementa la fórmula de Cao et al. (2018) adaptada para series irregulares:

```
delta[n, 0, f]   = 0
delta[n, t, f]   = day_diff_t                        si mask[n, t-1, f] = 1
delta[n, t, f]   = delta[n, t-1, f] + day_diff_t    si mask[n, t-1, f] = 0
```

Donde `day_diff_t` son los días calendario entre la fila `t-1` y la fila `t` dentro de la ventana. Al usar días reales en lugar de pasos unitarios, el delta captura el tiempo de ausencia real en series con registros irregulares (brechas entre observaciones de días, semanas o meses).

---

## Ventanas deslizantes

Cada estación se procesa de forma independiente:

1. Se ordenan las filas por fecha.
2. Se calcula la brecha en días entre filas consecutivas.
3. Se generan ventanas de `window_size` filas con paso `stride`.
4. Se descartan ventanas que contengan alguna brecha interna > `max_gap_days` (evita cruzar discontinuidades en la cobertura de la estación).

```
Filas de la estación ordenadas:
[r0, r1, r2, ..., r_T]

Ventana con start=s:  [r_s, r_{s+1}, ..., r_{s+window_size-1}]
Válida si: max(day_diff entre filas internas) <= max_gap_days
```

**Resultados con parámetros por defecto** (`window_size=30`, `stride=7`, `max_gap_days=365`):

| Split | Filas entrada | Secuencias generadas |
|-------|--------------|----------------------|
| train | 1,127,704 | 160,041 |
| val | 241,673 | 33,831 |
| test | 241,741 | 33,678 |

---

## Configuración

Todos los parámetros se controlan desde `config.yaml`. No hay valores hardcodeados en los scripts.

```yaml
input:
  variables:    [precip, evap, tmax, tmin]   # columnas de features
  date_col:     date
  station_col:  estacion

sequence:
  window_size:  30      # filas por ventana
  stride:       7       # paso entre ventanas (7 = semanal)
  max_gap_days: 365     # brecha máxima permitida dentro de una ventana

masks:
  observed_value: 1     # valor en mask para datos observados
  missing_value:  0     # valor en mask para datos faltantes

splits: [train, val, test]

validation:
  batch_size: 32        # batch usado en el check de DataLoader
```

**Nota sobre `stride`:** con `stride=7` los tensores ocupan ~70 MB por split. Cambiar a `stride=1` produce ~480 MB pero maximiza los datos de entrenamiento.

---

## Cómo ejecutar

### Requisito previo

```bash
pip install torch
```

### Construcción de tensores

```bash
python "Construcción de Tensores/tensor_builder.py"
```

O con config personalizado:

```bash
python "Construcción de Tensores/tensor_builder.py" --config ruta/config.yaml
```

### Validación

```bash
python "Construcción de Tensores/validate_tensors.py"
```

### Uso del dataset en entrenamiento

```python
from sequence_generator import TimeSeriesDataset

dataset = TimeSeriesDataset(
    X_path="data/tensors/X_train.pt",
    mask_path="data/tensors/mask_train.pt",
    delta_path="data/tensors/delta_train.pt",
    device="cuda",  # o "cpu"
)

loader = dataset.get_dataloader(batch_size=64, shuffle=True)

for batch in loader:
    X     = batch["X"]      # (64, 30, 4)
    mask  = batch["mask"]   # (64, 30, 4)
    delta = batch["delta"]  # (64, 30, 4)
```

---

## Archivos de salida

```
data/tensors/
├── X_train.pt           # (160041, 30, 4) float32
├── X_val.pt             # (33831,  30, 4) float32
├── X_test.pt            # (33678,  30, 4) float32
├── mask_train.pt        # (160041, 30, 4) float32
├── mask_val.pt          # (33831,  30, 4) float32
├── mask_test.pt         # (33678,  30, 4) float32
├── delta_train.pt       # (160041, 30, 4) float32
├── delta_val.pt         # (33831,  30, 4) float32
├── delta_test.pt        # (33678,  30, 4) float32
├── meta_train.pt        # (160041, 2)     int64
├── meta_val.pt          # (33831,  2)     int64
├── meta_test.pt         # (33678,  2)     int64
├── tensors_metadata.json
└── _logs/
    └── tensor_build.log

reports/
└── tensor_report.csv
```

El archivo `tensors_metadata.json` registra los parámetros de construcción, nombres de variables, lista de estaciones y métricas por split para reproducibilidad.

---

## Compatibilidad con modelos

| Modelo | Tensores requeridos | Notas |
|--------|---------------------|-------|
| **BRITS** | X, mask, delta | delta implementado según el paper original |
| **SAITS** | X, mask | agrega máscara aleatoria adicional en el training loop |
| **CSDI** | X, mask | agrega `gt_mask` aleatoria en el training loop |
| **LSTM/GRU** | X | usar mask en la función de pérdida para ignorar posiciones faltantes |
| **VAE/Autoencoders** | X, mask | reconstrucción enmascarada; VAE usa mask en el ELBO loss |
| **GAN** | X, mask | discriminador opera sobre posiciones observadas |

Los modelos estadísticos (SARIMA, TBATS, Prophet) y XGBoost no usan estos tensores; operan directamente sobre los parquets de los splits.

---

## Resultados de validación

Resultados de la ejecución de `validate_tensors.py` (12 checks por split):

| Split | Secuencias | Shape X | Obs% | Resultado |
|-------|-----------|---------|------|-----------|
| train | 160,041 | (160041, 30, 4) | 85.7% | **PASS** |
| val | 33,831 | (33831, 30, 4) | 91.5% | **PASS** |
| test | 33,678 | (33678, 30, 4) | 86.5% | **PASS** |

Checks ejecutados por split:
- Shape `(N, 30, 4)` para X, mask y delta
- dtype `float32` para X, mask y delta
- dtype `int64` para meta
- Ausencia de NaN en X
- Máscara estrictamente binaria `{0, 1}`
- Delta no negativo
- Consistencia de shapes entre X, mask y delta
- Compatibilidad con `torch.utils.data.DataLoader`

---

## Dependencias

| Paquete | Versión mínima | Uso |
|---------|---------------|-----|
| `torch` | 2.0+ | Guardado/carga de tensores, DataLoader |
| `numpy` | 1.20+ | Generación de ventanas (`sliding_window_view`) |
| `pandas` | 1.3+ | Carga de parquets |
| `pyarrow` | — | Motor de lectura de parquets |
| `pyyaml` | — | Carga de configuración |
