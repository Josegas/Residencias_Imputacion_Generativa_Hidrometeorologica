# Resumen de Contexto — Proyecto de Residencias Profesionales

**Laboratorio de Geomática y Teledetección — TECNM Campus Culiacán**  
**Autores:** José Ángel García Pérez · Sebastián Verdugo Bermúdez  
**Metodología:** CRISP-ML(Q)  
**Fecha de este documento:** 2026-05-17

---

## 1. Problema y objetivo

Las bases de datos históricas de las estaciones climatológicas del estado de Sinaloa, administradas por CONAGUA/SMN, presentan valores faltantes estructurales producidos por fallas de equipo, periodos sin operación y diferencias en los tipos de estación (pluviométricas puras vs. completas). El objetivo del proyecto es reconstruir esas series preservando la estructura estadística original mediante un modelo de aprendizaje profundo entrenado con los propios datos históricos.

---

## 2. Dataset

| Atributo | Valor |
|----------|-------|
| Fuente | CONAGUA/SMN — claves 25001–25300 |
| Estado | Sinaloa, México |
| Estaciones | 173 (activas con datos suficientes) |
| Período | 1908–2026, granularidad diaria |
| Variables | `precip` (mm), `evap` (mm), `tmax` (°C), `tmin` (°C) |
| Registros totales | ~6.4 M |
| Registros en dataset final | ~1.6 M |

**Faltantes reales por variable:**

| Variable | Faltantes | Mecanismo |
|----------|-----------|-----------|
| precip | 0.8 % | MAR (equipos) |
| tmax | ~9 % | MAR (equipos) |
| tmin | ~9 % | MAR (equipos) |
| evap | 38–48 % | **MNAR estructural** (estaciones pluviométricas no miden evaporación) |

---

## 3. Pipeline completo (12 etapas)

El pipeline está orquestado por `Pipeline Reproducible/run_pipeline.py` con su configuración en `Pipeline Reproducible/config.yaml`.

| Etapa | Módulo/Script | Artefacto de salida |
|-------|--------------|---------------------|
| 1 | `Obtencion de Datos Crudos/download_sinaloa_raw_pro.py` | `data/raw/conagua_smn/estado=sin/` |
| 2 | `Estructuracion del Dataset/organize_raw_by_station_year_variable_parquet.py` | `data/interim/organized/` (Hive: `estado/estacion/anio/`) |
| 3 | `Validacion y limpieza/cleaning.py` | `data/cleaned/organized/` |
| 4 | `Preprocesamiento/normalize.py` | `data/scaled/` + `models/scalers/*.pkl` |
| 5 | `Dataset Final Procesado/pipeline.py` | `data/processed/dataset_final.parquet` |
| 6 | `División Train-Val-Test/split.py` | `data/splits/` (70/15/15 cronológico por estación) |
| 7 | `Construcción de Tensores/tensor_builder.py` | `data/tensors/*.pt` (ventana 30 días, stride 7) |
| 8 | `Quality Gate/quality_gate.py` | `reports/quality_gate/quality_gate_report.csv` |
| 9 | `Imputación Generativa/impute.py` | `data/imputed/dataset_imputado.parquet` |
| 10 | `Validación Estadística/validate_imputation.py` | `reports/validacion_estadistica/` |
| 11 | `Monitoreo/monitor.py` | `reports/monitoreo/drift_report.csv` |
| 12 | `Análisis y Exportación/export.py` | `data/export/dataset_imputado.csv` + Excel 4 hojas |

Las etapas 8–12 son idempotentes: si el artefacto de salida ya existe y no se usa `--force`, la etapa se omite.

---

## 4. Preprocesamiento y tensores

**Scalers globales** (ajustados sobre el split de entrenamiento):

| Variable | Scaler | Parámetros clave |
|----------|--------|-----------------|
| precip | MinMaxScaler [0,1] | — |
| evap | MinMaxScaler [0,1] | — |
| tmax | StandardScaler | μ = 32.67 °C, σ = 4.90 °C |
| tmin | StandardScaler | μ = 16.71 °C, σ = 6.21 °C |

**Splits:**

| Split | Filas | Secuencias |
|-------|-------|-----------|
| train | 1,127,704 | 160,041 |
| val | 241,673 | 33,831 |
| test | 241,741 | 33,678 |

**Tensores PyTorch** — forma `(N, T=30, F=4)`:

| Tensor | Contenido |
|--------|-----------|
| `X_*.pt` | Valores escalados (NaN → 0) |
| `mask_*.pt` | 1 = observado, 0 = faltante |
| `delta_*.pt` | Días desde la última observación (para BRITS) |
| `meta_*.pt` | `[station_idx, start_date_ordinal]` |

---

## 5. Experimentación de modelos

### US 4.1 — Modelos Base (`Modelos Base/`)

| Notebook | Modelos |
|----------|---------|
| `modelos_base_estadisticos.ipynb` | SARIMA, ETS, Prophet, TBATS |
| `modelos_base_xgboost.ipynb` | XGBoost (lags 1/2/3/7/14/30d, rolling means, covariables cruzadas) |
| `modelos_base_autoencoder.ipynb` | Autoencoder Conv1D bidireccional (PyTorch) |
| `modelos_base_lstm_gru.ipynb` | BiGRU / BiLSTM con máscara concatenada al input |
| `comparacion_modelos_base.ipynb` | Heatmap, radar chart, boxplot por familia |

### US 4.2 — Modelos Generativos (`Modelos Generativos/`)

| Notebook | Modelo |
|----------|--------|
| `modelo_generativo_vae.ipynb` | VAE Conv1D con β-VAE ELBO |
| `modelo_generativo_brits.ipynb` | BRITS bidireccional + decaimiento temporal |
| `modelo_generativo_gan.ipynb` | GAIN (Generator + Discriminator + hint matrix) |
| `modelo_generativo_saits.ipynb` | SAITS DMSA + joint ORT+MIT loss |
| `modelo_generativo_csdi.ipynb` | CSDI difusión condicional (cosine schedule, T=50) |
| `comparacion_modelos_generativos.ipynb` | Comparación vs. baselines |

### US 4.3 — Optimización y Selección Final (`Optimización/`)

Optimización de hiperparámetros con **Optuna TPE (50 trials)**:

| Notebook | Estado |
|----------|--------|
| `optimizacion_hiperparametros.ipynb` | **Ejecutado** — artefactos generados |
| `backtesting_evaluacion_retrospectiva.ipynb` | Pendiente de ejecución |
| `seleccion_modelo_ganador.ipynb` | Pendiente (depende del backtesting) |

**Resultados de optimización (espacio escalado):**

| Modelo | RMSE default | RMSE óptimo | NSE default | NSE óptimo |
|--------|-------------|-------------|-------------|------------|
| BRITS | 0.3832 | 0.2576 | 0.7292 | 0.8782 |
| SAITS | 0.3158 | 0.2464 | 0.8166 | 0.8881 |
| BiGRU | 0.2379 | 0.2436 | 0.8965 | 0.8905 |
| XGBoost | 0.2639 | 0.2612 | 0.8720 | 0.8746 |

**Hiperparámetros óptimos:**

| Modelo | Configuración |
|--------|--------------|
| BiGRU | hidden=128, layers=2, lr=1.9e-3, batch=128, dropout=0.103 |
| BRITS | hidden=64, lr=5.4e-4, batch=128 |
| SAITS | d_model=128, heads=8, layers=3, lr=2.4e-3, batch=256 |
| XGBoost | n_estimators=361, max_depth=9, lr=0.085 |

---

## 6. Modelo ganador: BiGRU-opt

**Seleccionado** mediante la matriz de decisión US 4.3.3:
- NSE 30 % + RMSE 25 % + estabilidad temporal 20 % + KPSS 15 % + complejidad 10 %

**Checkpoint:** `models/optimizacion/bigru_opt.pt`

**Rendimiento — Backtesting 4-fold, protocolo MCAR 20 % sobre test:**

| Variable | NSE |
|----------|-----|
| tmax | 0.847 |
| tmin | 0.931 |
| evap | 0.648 |
| precip | 0.056 (zero-inflated: 84.7 % de días = 0 mm) |
| **Global** | **0.621** |

CV-NSE = 0.007 (alta estabilidad temporal entre décadas).

Alternativas documentadas: XGBoost-opt (mejor en evap: 0.676), BRITS-opt (mayor estabilidad: CV=0.005), SAITS-opt (mejor cociente arquitectura/rendimiento en tmax).

---

## 7. Módulos del pipeline post-entrenamiento

### Quality Gate (Etapa 8)

Verifica el dataset antes de imputar. Criterios **críticos** (exit 1): límites físicos violados, insuficientes observaciones por estación, tmax < tmin en datos observados. Criterios **WARNING**: tasa de faltantes alta, pérdida de estacionariedad KPSS.

Parámetros clave en `Quality Gate/config.yaml`: `kpss_significance: 0.05`, `kpss_station_threshold: 0.70`, `missing_rate_thresholds: {precip:0.60, evap:0.85, tmax:0.60, tmin:0.60}`.

Figuras generadas: `qg_criterios.png`, `qg_missing_rate.png`, `qg_kpss.png`.

### Imputación Generativa (Etapa 9)

Ventanas deslizantes de 30 días, stride 7, batch_size 512. Post-procesamiento: inverse-transform con scalers + límites físicos + restricción tmax ≥ tmin. Parámetro `device: auto` usa CUDA si está disponible.

Parámetros clave en `Imputación Generativa/config.yaml`: `sequence: {window_size:30, stride:7, max_gap_days:365}`, `inference: {batch_size:512, device:auto}`.

### Validación Estadística (Etapa 10)

KS-test (distribución observado vs. imputado), correlaciones inter-variable antes/después, cobertura de imputación por variable. Objetivo de cobertura: 99 %. Incluye validación estacional y multianual (US 6.1).

Figuras: `val_cobertura.png`, `val_distribucion.png`, `val_correlaciones.png`, `val_ks_test.png`, `val_estacional.png`, `val_multianual.png`.

### Monitoreo (Etapa 11)

Detecta drift distribucional con PSI por ventanas decadales respecto a la referencia 1970–2000. Umbrales: WARNING en PSI > 0.10, CRITICAL (alerta de reentrenamiento) en PSI > 0.20. También corre KS-test por ventana.

Figuras: `drift_decadal.png`, `cobertura_temporal.png`.

### Análisis y Exportación (Etapa 12)

Exporta el dataset imputado final a `data/export/dataset_imputado.csv` y genera `data/export/resumen_estadistico.xlsx` con 4 hojas: estadísticas descriptivas, cobertura por estación, cobertura por variable y manifiesto de exportación.

---

## 8. Hardcoding eliminado

A lo largo del proyecto se auditaron y corrigieron los siguientes hardcodings en los módulos del pipeline:

| Módulo | Valor corregido | Ahora en config.yaml |
|--------|----------------|----------------------|
| `monitor.py` | Título de figura con "1970–2000" literal | `reference_window.start` / `reference_window.end` |
| `monitor.py` | Objetivo de cobertura 99 % fijo | `coverage_target_pct` |
| `quality_gate.py` | Ruta de scalers `"models/scalers"` | `scalers.dir` |
| `quality_gate.py` | Umbral KPSS 0.70 fijo | `kpss_station_threshold` |
| `validate_imputation.py` | Umbral KPSS 0.70 fijo | `kpss_station_threshold` |
| `validate_imputation.py` | Objetivo de cobertura 99/95 % en figuras | `coverage_target_pct` |
| `validate_imputation.py` | Ruta de scalers | `scalers.dir` + `scalers.prefix` |
| `impute.py` | Ruta de entrada fallback hardcoded | `input.dataset` en config |

---

## 9. Aplicación web: HydroImpute

**Directorio:** `HydroImpute/`  
**Punto de entrada:** `streamlit run "HydroImpute/app.py"`  
**Puerto por defecto:** `http://localhost:8501`

Aplicación Streamlit multi-página construida sobre el pipeline real. El modelo BiGRU-opt se carga una sola vez con `@st.cache_resource` y se reutiliza en todas las páginas.

**Páginas:**

| Archivo | Página | Función |
|---------|--------|---------|
| `app.py` | Inicio | Landing con métricas clave y rendimiento del modelo |
| `pages/1_Dashboard.py` | Dashboard | Estado de las 12 etapas, último log, métricas de cobertura, alertas PSI |
| `pages/2_Pipeline.py` | Pipeline | Ejecuta `run_pipeline.py` con streaming de logs en tiempo real (`subprocess.Popen`) |
| `pages/3_Imputar.py` | Imputar | Carga datos del usuario, imputa en escala original y exporta CSV/Excel |
| `pages/4_Resultados.py` | Resultados | Visualiza figuras y reportes de cada etapa del pipeline |
| `pages/5_Configuracion.py` | Configuración | Editor visual de los `config.yaml` de los 4 módulos |

**Utilidades compartidas** (`HydroImpute/utils.py`):
- `APP_DIR`, `ROOT`, `IMPUTE_DIR`, `PIPELINE_DIR`, `LOGO_PATH`
- `get_pipeline()` — carga el modelo con `@st.cache_resource`
- `impute_original_scale()` — imputa datos en escala original llamando directamente a `_scale`, `_impute_station`, `_inverse_scale`, `_apply_physical_limits`, `_apply_tmax_tmin_constraint` (evita el inverse-transform inicial de `impute_dataframe()`)
- `validate_df()`, `read_upload()`, `to_csv_bytes()`, `to_excel_bytes()`

**Logo:** `HydroImpute/img/LOGO_TEC_PNG_OK.png` — escudo del Instituto Tecnológico de Culiacán, aparece en el sidebar de todas las páginas.

---

## 10. Estructura de directorios (raíz del proyecto)

```
.
├── Análisis y Exportación/      export.py + config.yaml + README.md
├── Construcción de Tensores/    tensor_builder.py + validate_tensors.py
├── Dataset Final Procesado/     pipeline.py
├── División Train-Val-Test/     split.py + verify_leakage.py
├── EDA/                         notebooks exploratorios
├── Estructuracion del Dataset/  organize_raw_by_station_year_variable_parquet.py
├── HydroImpute/                 Aplicación Streamlit multi-página
│   ├── app.py
│   ├── utils.py
│   ├── img/LOGO_TEC_PNG_OK.png
│   ├── pages/
│   │   ├── 1_Dashboard.py
│   │   ├── 2_Pipeline.py
│   │   ├── 3_Imputar.py
│   │   ├── 4_Resultados.py
│   │   └── 5_Configuracion.py
│   └── README.md
├── Imputación Generativa/       impute.py + config.yaml + README.md
├── Modelos Base/                5 notebooks US 4.1
├── Modelos Generativos/         6 notebooks US 4.2
├── Monitoreo/                   monitor.py + config.yaml + README.md
├── Obtencion de Datos Crudos/   download_sinaloa_raw_pro.py
├── Optimización/                3 notebooks US 4.3
├── Pipeline Reproducible/       run_pipeline.py + config.yaml + README.md
├── Preprocesamiento/            normalize.py
├── Quality Gate/                quality_gate.py + config.yaml + README.md
├── Validación Estadística/      validate_imputation.py + validacion_estacional_multianual.ipynb
│                                + config.yaml + README.md
├── Validacion y limpieza/       cleaning.py
├── data/                        raw/ interim/ cleaned/ scaled/ processed/ splits/ tensors/ imputed/ export/
├── models/                      scalers/*.pkl + optimizacion/*.pt
├── reports/                     quality_gate/ validacion_estadistica/ monitoreo/ exportacion/
└── README.md
```

---

## 11. Hallazgos técnicos clave

- **Precipitación es el mayor reto:** distribución zero-inflada (84.7 % de días con 0 mm). Ningún modelo supera NSE = 0.14 en esta variable. Se documenta como limitación del mecanismo MNAR.
- **evap tiene faltantes MNAR:** las estaciones pluviométricas puras no tienen evaporímetro, lo que hace que la ausencia no sea aleatoria. El mecanismo de decaimiento temporal de BRITS es clave para esta variable.
- **Estacionariedad preservada:** todos los modelos pasan el KPSS en 28/28 tests (base) y 20/20 (generativos).
- **BRITS/GAIN/CSDI** preservan la función de autocorrelación perfectamente (Δρ₁ = 0) por re-inyección de valores observados.
- **Los modelos estadísticos** (SARIMA, ETS, Prophet, TBATS) tienen NSE < 0 porque son modelos de forecasting, no de interpolación/imputación — no son aptos para este problema.
- **Nota de arquitectura:** `"date"` y `"value"` en `cleaning.py` son nombres de columna del formato intermedio parquet (fijo por diseño), no hardcoding configurable.

---

## 12. Dependencias Python principales

```
streamlit pandas numpy torch pyarrow scikit-learn pyyaml openpyxl
statsmodels prophet tbats xgboost optuna scipy
```

---

*Generado automáticamente el 2026-05-17 a partir del contexto completo de la sesión de trabajo.*

---

## 13. Estado de la tesis y archivos MD generados

**Documento:** `reports/documentacion/Tesis_ReconstruccionHidrometeorologica_v2.docx`  
**Formato de referencias:** APA 7ª edición  
**Directorio de secciones generadas:** `tesis_secciones/`

### Estado de sesiones de escritura — TODAS COMPLETADAS (2026-05-17)

| # | Capítulo | Archivo MD | Estado |
|---|----------|-----------|--------|
| 1 | Introducción | — | ✅ Ya completo en el .docx |
| 2 | Marco Teórico | `00_NOTA_MARCO_TEORICO.md` | ⚠️ Pendiente corrección en próxima sesión |
| 3 | Estado del Arte | `01_ESTADO_DEL_ARTE.md` | ✅ **FINALIZADO** — 16 secciones, 12 figs, 3 tablas, 7 ecs, ~42 refs, ~20–22 pp. |
| 4 | Metodología | `02_METODOLOGIA_adiciones.md` | ✅ Secciones 3.7–3.15 con scripts, configs y datos reales |
| 5 | Resultados | `03_RESULTADOS_adiciones.md` | ✅ 9 secciones con datos reales de CSVs |
| 6 | Conclusiones | `04_CONCLUSIONES.md` | ✅ 7 conclusiones + tabla evolución dataset + limitaciones |

### Archivos MD y su contenido (para pegar manualmente en Word)

**`tesis_secciones/00_NOTA_MARCO_TEORICO.md`**
- Instrucción: renombrar heading "FUNDAMENTO TEÓRICO" → "MARCO TEÓRICO". Sin cambio de contenido.

**`tesis_secciones/01_ESTADO_DEL_ARTE.md`**
- Capítulo nuevo entre Marco Teórico y Metodología — **EXPANDIDO Y FINALIZADO** (sesión 2026-05-17)
- **455 líneas ≈ 20–22 páginas en Word**
- **16 secciones** (en orden):
  1. Metodología de búsqueda bibliográfica
  2. Características de las series temporales hidrometeorológicas
  3. Métodos estadísticos clásicos (SARIMA, ETS, TBATS, Prophet, KNN, MICE)
  4. Aprendizaje automático (XGBoost, Random Forest) + subsección precipitación zero-inflada
  5. Redes neuronales recurrentes (LSTM, BiLSTM, BiGRU)
  6. Autoencoders para imputación multivariada (Conv1D, VAE)
  7. Modelos generativos especializados: BRITS / GAIN / Transformers+atención / SAITS / CSDI
  8. Optimización bayesiana de hiperparámetros (Optuna, TPE)
  9. Métricas de evaluación (NSE, RMSE, MAE, R², CRPS, KPSS, CV-NSE) + Tabla 2
  10. Validación temporal y backtesting cronológico + Tabla 3
  11. Marco metodológico: CRISP-DM → CRISP-ML(Q)
  12. Aplicaciones en redes climatológicas MNAR (CONAGUA/SMN, Sinaloa)
  13. Monitoreo de deriva distribucional (PSI)
  14. Síntesis comparativa de modelos (Tabla 1 — 14 filas con benchmarks de la literatura)
  15. Síntesis y brechas identificadas (4 brechas → justificación del trabajo)
  16. Referencias (~42 refs APA 7ª edición)
- **12 figuras** de papers con captions APA (GRU, VAE, BRITS×2, GAIN, SAITS×3, CSDI×2, CRISP-ML(Q)×2)
- **3 tablas:** Tabla 1 (benchmarks literatura), Tabla 2 (métricas), Tabla 3 (estructura folds backtesting)
- **7 ecuaciones** (BRITS decay, VAE loss, Transformer attention, NSE, PSI, y otras)
- **IMPORTANTE:** No contiene resultados propios del proyecto — solo benchmarks de papers citados. Los resultados propios están en `03_RESULTADOS_adiciones.md`
- 4 brechas identificadas en la literatura que justifican este trabajo

**`tesis_secciones/02_METODOLOGIA_adiciones.md`**
- Secciones 3.7–3.15 para agregar al final del capítulo Metodología (después de "3.6 Normalización")
- Incluye scripts exactos: `pipeline.py`, `split.py`, `verify_leakage.py`, `tensor_builder.py`, `mask_generator.py`, `sequence_generator.py`, `validate_tensors.py`, `quality_gate.py`, `impute.py`, `validate_imputation.py`, `validate_seasonal_multianual.py`, `monitor.py`, `export.py`
- Parámetros reales de todos los config.yaml
- Tabla de tensores con shapes reales por split y tasas de observación
- Tabla de Quality Gate con resultados PASS/WARNING reales
- Tabla de cobertura de imputación: precip 99.57 %, evap 99.87 %, tmax/tmin 99.81 %
- Arquitectura de HydroImpute con código de utils.py y tabla de las 6 páginas

**`tesis_secciones/03_RESULTADOS_adiciones.md`**
- Correcciones a 4.3.1 con datos reales (1,611,118 registros, 858,963 imputados)
- 9 secciones nuevas (4.4–4.9): ranking 17 modelos, backtesting BiGRU-opt por fold/variable, Quality Gate, KPSS, correlaciones, monitoreo PSI
- Tabla de 17 modelos con NSE, RMSE, CV-NSE y score total
- Tabla NSE por fold × variable para BiGRU-opt
- Resultados KS-test reales (precip=0.772, evap=0.344, tmax=0.584, tmin=0.469)
- Correlaciones reales del CSV con deltas exactos (tmax-tmin Δ=+0.001)
- PSI por variable y por décadas del CSV de monitoreo

**`tesis_secciones/04_CONCLUSIONES.md`**
- Reemplaza 5 párrafos genéricos del .docx
- Tabla de evolución del dataset: 6,444,472 obs. crudas → 858,963 imputadas → 125.77 MB exportados
- 7 conclusiones numeradas con métricas específicas del proyecto
- Limitaciones con números reales (NSE máx precip = 0.068, 1,325 NaN residuales, 0.15 %)
- 4 líneas de trabajo futuro

### Datos clave descubiertos durante la generación (2026-05-17)

| Dato | Valor | Fuente |
|------|-------|--------|
| Filas crudas formato largo | 6,444,472 | `data/interim/organized/estado=sin/_index.csv` |
| Particiones raw | 19,392 (173 est × años × 4 vars) | mismo índice |
| Outliers IQR marcados como NaN | 275,213 | `reports/cleaning_report.csv` |
| Total registros dataset final | 1,611,118 | `data/processed/_index_processed.csv` |
| Split: train/val/test filas | 1,127,704 / 241,673 / 241,741 | `reports/split_report.csv` |
| Split: sin leakage temporal | True | `split_report.csv: leakage_detectado=False` |
| Rango temporal train | 1908-11-01 / 2024-05-29 | `split_report.csv` |
| Rango temporal test | 1967-09-10 / 2026-02-28 | `split_report.csv` |
| Secuencias tensor train/val/test | 160,041 / 33,831 / 33,678 | `reports/tensor_report.csv` |
| obs_evap tasa (train) | 61.63 % (MNAR estaciones pluvio.) | `tensor_report.csv` |
| NaN imputados total | 858,963 / 860,288 = 99.85 % | `reports/imputacion/imputacion_report.csv` |
| NaN residuales | 1,325 (0.15 % de faltantes) | `reports/validacion_estadistica/metricas_imputacion.csv` |
| CSV exportado | 67.47 MB | `reports/exportacion/export_report.csv` |
| 173 CSVs por estación | 58.30 MB | `export_report.csv` |
| KPSS pre-imputación evap | WARNING: 89/137 = 64.96 % | `reports/quality_gate/quality_gate_report.csv` |
| KPSS post-imput. BiGRU precip | False (4/4 folds — introduce tendencia) | `reports/optimizacion/backtesting_kpss.csv` |
| Score matriz decisión BiGRU-opt | 0.8014 (2.° lugar, 1.° XGBoost-opt 0.8173) | `reports/optimizacion/ranking_final_completo.csv` |
| PSI evap 2018–2026 | 0.248 CRITICAL (cambio climático) | `reports/monitoreo/drift_report.csv` |
| Correlación tmax–tmin Δ | +0.001 (de 0.5255 a 0.5258) | `reports/validacion_estadistica/correlaciones_comparativas.csv` |

### Instrucción para sesiones futuras
Si se necesita revisar o expandir algún capítulo:
1. Leer `resumen_contexto.md` (contexto completo)
2. Leer el archivo MD correspondiente en `tesis_secciones/`
3. Leer el .docx para ver el estado actual antes de modificar
4. Los CSVs en `reports/` contienen todos los datos reales disponibles

---

## 14. Expansión del Marco Teórico — sesión 2026-05-18

### Estado tras la sesión

El Marco Teórico pasó de 16 pp / 5 secciones a ~24 pp / 6 secciones. Todas las adiciones están en `tesis_secciones/00_NOTA_MARCO_TEORICO.md` listas para aplicar en Word.

### Brechas identificadas y cubiertas

| Bloque | Sección destino | Contenido |
|--------|----------------|-----------|
| A | §2.3.1 (al final, tras Figura 2) | GRU 4 ecuaciones + BiGRU — remisión a Figura 1 Estado del Arte |
| B | Nueva §2.3.2 (antes de GAN) | VAE: ELBO + reparametrización — remisión a Figura 2 Estado del Arte |
| C | §2.3.3 GAN (al final) | GAIN: hint matrix H + función objetivo L_G |
| D | §2.4 (al final, antes de tabla eliminada) | CV-NSE + KS-test con ecuaciones formales |
| E | §2.5 (al final, antes de Figura 5) | PSI con ecuación Σ(A_i−E_i)·ln(A_i/E_i) + umbrales |
| F | Nueva §2.6 (nueva sección final) | Optuna/TPE: EI(λ)∝l/g + **Figura 6** = `figMTOptuna.png` |
| G | Nueva §2.3.x (antes de §2.4) | Tabla 1 síntesis 9 arquitecturas |

### Correcciones al contenido existente

| Corrección | Qué hacer en Word |
|------------|------------------|
| 1 | Eliminar 2 párrafos de TTI (Du 2024) y AST (Li 2024) en §2.3.3 |
| 2 | Eliminar Tabla 1 comparación de métodos en §2.4 |
| 3 | Verificar numeración de figuras y tablas tras cambios |

### Numeración final Marco Teórico

**Figuras:** 1=MCAR/MAR/MNAR, 2=LSTM, 3=GAN, 4=BRITS, 5=CRISP-ML(Q), 6=Optuna (`figMTOptuna.png`)
**Tablas:** 1=Síntesis arquitecturas (Bloque G)

### Estructura §2.3 tras inserción de bloques

```
§2.3.1  Redes LSTM, GRU y Modelos Recurrentes Bidireccionales
§2.3.2  Autoencoders y Autoencoders Variacionales (VAE)  [nuevo]
§2.3.3  Redes Generativas Adversariales (GAN) + GAIN
§2.3.4  BRITS, SAITS y Modelos de Difusión
§2.3.5  Síntesis de Arquitecturas — Tabla 1  [nuevo]
```

### Diferenciación Marco Teórico vs Estado del Arte — verificada ✅

- Marco Teórico: define conceptos con ecuaciones (cómo funciona)
- Estado del Arte: benchmarks de papers y 4 brechas (qué lograron otros)
- Figuras GRU y VAE: solo en Estado del Arte; Marco Teórico las referencia con remisión cruzada

### Pendientes para aplicar en Word

1. Usar Word **desktop** para ecuaciones (`Alt+=` + LaTeX) — Word Online no soporta
2. Renombrar "FUNDAMENTO TEÓRICO" → "MARCO TEÓRICO"
3. Aplicar Correcciones 1–3
4. Insertar Bloques A–G en sus secciones correspondientes
5. Insertar `figMTOptuna.png` como Figura 6 en §2.6
6. Agregar 10 referencias nuevas en §7
7. Presionar `Ctrl+A` → `F9` al finalizar para actualizar numeración
8. **Pendiente menor:** ecuación decaimiento temporal BRITS (γ_t) aún no agregada al MD

### Papers descargados en `reports/documentacion/papers/`

| Archivo | Paper |
|---------|-------|
| `GRUPaper.pdf` | Cho et al. (2014) — Figure 2 = celda GRU |
| `VAEPaper.pdf` | Kingma y Welling (2013) — Figure 1 = grafo VAE |
| `OptunaPaper.pdf` | Akiba et al. (2019) — Figure 6 = sistema Optuna |
| `figMTOptuna.png` | Captura de Figure 6 guardada en `imagenes_tesis/` |

### Próxima sesión: Metodología

Leer `02_METODOLOGIA_adiciones.md` y el capítulo Metodología del .docx para hacer la misma revisión: identificar brechas, verificar diferenciación con otros capítulos y completar secciones faltantes.
