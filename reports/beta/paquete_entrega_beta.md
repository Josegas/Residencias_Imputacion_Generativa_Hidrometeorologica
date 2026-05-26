<style>
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a1a;
    background-color: #ffffff;
    color-scheme: light;
    max-width: 920px;
    margin: 0 auto;
  }
  h1 { font-size: 19pt; color: #263238; border-bottom: 2.5px solid #37474f; padding-bottom: 6px; margin-top: 32px; }
  h2 { font-size: 13.5pt; color: #37474f; border-bottom: 1px solid #b0bec5; padding-bottom: 4px; margin-top: 28px; }
  h3 { font-size: 11pt; color: #263238; font-weight: 600; margin-top: 18px; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 9.5pt;
    margin: 14px 0;
  }
  th {
    background-color: #455a64;
    color: #ffffff;
    padding: 7px 10px;
    text-align: left;
    font-weight: 600;
  }
  td {
    padding: 6px 10px;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: top;
    color: #1a1a1a !important;
  }
  tr:nth-child(even) td { background-color: #f5f7f8; }
  tr:hover td { background-color: #eceff1; }
  blockquote {
    border-left: 4px solid #b0bec5;
    margin: 10px 0;
    padding: 6px 14px;
    background: #f5f7f8 !important;
    color: #1a1a1a !important;
    font-size: 9.5pt;
  }
  code {
    background: #d0d7e8 !important;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 9pt;
    font-family: 'Courier New', monospace;
    color: #0d1117 !important;
  }
  pre {
    background: #d0d7e8 !important;
    border-radius: 4px;
    padding: 12px 16px;
    font-size: 9pt;
    font-family: 'Courier New', monospace;
    overflow-x: auto;
  }
  .portada {
    text-align: center;
    border: 1.5px solid #455a64;
    border-radius: 6px;
    padding: 28px 24px;
    margin: 24px 0 36px 0;
    background: #f8f9fa;
  }
  .portada h2 {
    border: none;
    font-size: 16pt;
    color: #263238;
    margin: 8px 0 6px 0;
  }
  .portada .subtitulo { font-size: 11.5pt; color: #263238; margin: 4px 0; }
  .portada .meta { font-size: 9.5pt; color: #333; margin: 4px 0; }
  .portada .separador { border: none; border-top: 1px solid #b0bec5; margin: 14px 0; }
  .checklist-ok { color: #2e7d32; font-weight: bold; }
  .nota-importante {
    border: 1.5px solid #ff8f00;
    border-radius: 4px;
    padding: 10px 16px;
    background: #fff8e1;
    color: #212121;
    font-size: 9.5pt;
    margin: 12px 0;
  }
  .page-break { page-break-after: always; }
</style>

<div class="portada">
  <div class="subtitulo">Laboratorio de Geomática y Teledetección</div>
  <div class="subtitulo">Residencias Profesionales — Ingeniería en Sistemas Computacionales</div>
  <hr class="separador">
  <h2>Manifiesto de Entrega — Versión Beta</h2>
  <div class="subtitulo">Imputación Generativa de Datos Hidrometeorológicos<br>Red CONAGUA-SMN · 173 Estaciones · Sinaloa, México</div>
  <hr class="separador">
  <div class="meta">US 5.3 &nbsp;|&nbsp; RES-133</div>
  <div class="meta">Fecha: 16 de mayo de 2026 &nbsp;|&nbsp; Versión: Beta 1.0</div>
  <hr class="separador">
  <div class="meta"><strong>Autores:</strong> José Ángel García Pérez &nbsp;·&nbsp; Sebastián Verdugo Bermúdez</div>
  <div class="meta"><strong>Asesores:</strong> Dr. Jesús Gabriel Rangel Peraza &nbsp;·&nbsp; Dr. Zuriel Dathan Mora Félix</div>
</div>

---

# Manifiesto de Entrega — Versión Beta

## Descripción del sistema

El presente documento lista todos los componentes del paquete de entrega de la versión beta del **sistema de imputación generativa hidrometeorológica** para 173 estaciones de la red CONAGUA-SMN en Sinaloa. El sistema implementa el pipeline CRISP-ML(Q) en 10 etapas automatizadas, con el modelo BiGRU-opt como núcleo de imputación (NSE global = 0.621, cobertura de imputación = 99.8%).

**Artefacto principal de salida:** `data/imputed/dataset_imputado.parquet`  
1,611,118 registros · 173 estaciones · 4 variables (precip, evap, tmax, tmin) · escala original (mm, °C)

---

## 1. Scripts del pipeline

### 1.1 Orquestador

| Archivo | Descripción |
|---------|-------------|
| `Pipeline Reproducible/run_pipeline.py` | Ejecuta las 10 etapas en orden verificando salidas intermedias |
| `Pipeline Reproducible/config.yaml` | Define etapas, scripts, rutas y artefactos de verificación |

**Ejecución completa:**
```bash
python "Pipeline Reproducible/run_pipeline.py"
```

**Ejecución parcial (etapas 8-10, asumiendo etapas 1-7 completadas):**
```bash
python "Pipeline Reproducible/run_pipeline.py" --from-stage 8

# O individualmente:
python "Quality Gate/quality_gate.py"
python "Imputación Generativa/impute.py"
python "Validación Estadística/validate_imputation.py"
```

### 1.2 Scripts por etapa

| Etapa | Script | Entrada principal | Salida verificable |
|-------|--------|------------------|--------------------|
| 1 | `Obtencion de Datos Crudos/download_sinaloa_raw_pro.py` | API CLICOM | `data/raw/` |
| 2 | `Estructuracion del Dataset/organize_raw_by_station_year_variable_parquet.py` | `data/raw/` | `data/interim/` |
| 3 | `Validacion y limpieza/cleaning.py` | `data/interim/` | `data/cleaned/` |
| 4 | `Preprocesamiento/normalize.py` | `data/cleaned/` | `models/scalers/*.pkl` |
| 5 | `Dataset Final Procesado/pipeline.py` | `data/cleaned/` + scalers | `data/processed/dataset_final.parquet` |
| 6 | `División Train-Val-Test/split.py` | `dataset_final.parquet` | `data/splits/` |
| 7 | `Construcción de Tensores/tensor_builder.py` | `data/splits/` | `data/tensors/` |
| **8** | **`Quality Gate/quality_gate.py`** | `dataset_final.parquet` | `reports/quality_gate/quality_gate_report.csv` |
| **9** | **`Imputación Generativa/impute.py`** | `dataset_final.parquet` | `data/imputed/dataset_imputado.parquet` |
| **10** | **`Validación Estadística/validate_imputation.py`** | dataset_final + dataset_imputado | `reports/validacion_estadistica/` |

> Las etapas 8, 9 y 10 son las nuevas etapas entregadas en la versión beta (US 5.3).

---

## 2. Archivos de configuración

| Archivo | Etapa | Parámetros clave |
|---------|-------|-----------------|
| `Pipeline Reproducible/config.yaml` | Orquestador | 10 etapas, rutas, artefactos de verificación |
| `Quality Gate/config.yaml` | 8 | Límites físicos, umbrales de faltantes, KPSS |
| `Imputación Generativa/config.yaml` | 9 | Arquitectura BiGRU-opt, scalers, ventanas, semilla |
| `Validación Estadística/config.yaml` | 10 | Entradas, salidas, significancia KS/KPSS |
| `Validacion y limpieza/config.yaml` | 3 | Reglas de limpieza, límites físicos (fuente de verdad) |
| `Preprocesamiento/config.yaml` | 4 | Tipo de escalador por variable |
| `Construcción de Tensores/config.yaml` | 7 | Ventana = 30 días, stride = 7 (debe coincidir con impute.py) |

---

## 3. Artefactos del modelo

### 3.1 Checkpoint del modelo ganador

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `models/optimizacion/bigru_opt.pt` | 1.6 MB | Checkpoint PyTorch — BiGRU-opt (hidden = 128, layers = 2, dropout = 0.103) |

**Hiperparámetros óptimos (Optuna TPE, 50 trials):**

| Hiperparámetro | Valor óptimo |
|----------------|-------------|
| `hidden_size` | 128 |
| `n_layers` | 2 |
| `dropout` | 0.103 |
| `learning_rate` | 1.9 × 10⁻³ |
| `batch_size` | 128 |
| `window_size` | 30 días |

### 3.2 Scalers de normalización

| Archivo | Variable | Tipo | Parámetros |
|---------|----------|------|------------|
| `models/scalers/scaler_precip.pkl` | precip | MinMaxScaler [0, 1] | min = 0.0, max = 500.0 |
| `models/scalers/scaler_evap.pkl` | evap | MinMaxScaler [0, 1] | min = 0.0, max = 60.0 |
| `models/scalers/scaler_tmax.pkl` | tmax | StandardScaler | μ = 32.67 °C, σ = 4.90 |
| `models/scalers/scaler_tmin.pkl` | tmin | StandardScaler | μ = 16.71 °C, σ = 6.21 |
| `models/scalers/scalers_metadata.csv` | — | Metadatos | Parámetros completos de todos los scalers |

### 3.3 Selección del modelo ganador

| Archivo | Descripción |
|---------|-------------|
| `reports/optimizacion/seleccion_ejecutiva.csv` | Leído en tiempo de ejecución por `impute.py` para selección dinámica del ganador |
| `reports/optimizacion/seleccion_modelo_ganador.pdf` | Reporte técnico completo (19 pp.) — metodología MCDM y justificación de selección |

<div class="nota-importante">
<strong>Nota importante:</strong> <code>dataset_final.parquet</code> está en escala normalizada (salida de <code>normalize.py</code>). Los scripts de etapas 8, 9 y 10 aplican <code>inverse_transform</code> internamente antes de verificaciones físicas y antes del procesamiento del modelo. El dataset imputado de salida está en escala original (mm, °C).
</div>

---

## 4. Datos

### 4.1 Datos de entrada requeridos

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `data/processed/dataset_final.parquet` | 8.7 MB | Dataset normalizado — 1,611,118 filas, 173 estaciones, 4 variables |

### 4.2 Datos de salida generados

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `data/imputed/dataset_imputado.parquet` | 16 MB | Dataset imputado en escala original (mm, °C) |
| `data/imputed/dataset_imputado.csv` | — | Copia CSV del dataset imputado |

**Estadísticas de cobertura:**

| Variable | NaN originales | Rellenados | Residuales | Cobertura |
|----------|---------------|-----------|------------|-----------|
| precip | 10,858 | 10,811 | 47 | 99.6% |
| evap | 623,106 | 622,268 | 838 | 99.9% |
| tmax | 113,162 | 112,942 | 220 | 99.8% |
| tmin | 113,162 | 112,942 | 220 | 99.8% |
| **Total** | **860,288** | **858,963** | **1,325** | **99.8%** |

---

## 5. Reportes generados

| Archivo | Etapa | Contenido |
|---------|-------|-----------|
| `reports/quality_gate/quality_gate_report.csv` | 8 | Criterios críticos y advertencias pre-imputación |
| `reports/quality_gate/_logs/quality_gate_run.log` | 8 | Log completo de ejecución |
| `reports/imputacion/imputacion_report.csv` | 9 | NaN rellenados por variable y estación |
| `reports/imputacion/_logs/` | 9 | Log de imputación |
| `reports/validacion_estadistica/metricas_imputacion.csv` | 10 | Cobertura de imputación por variable |
| `reports/validacion_estadistica/ks_test_report.csv` | 10 | KS-test distribución observada vs. imputada |
| `reports/validacion_estadistica/correlaciones_comparativas.csv` | 10 | Correlaciones inter-variable antes/después |
| `reports/validacion_estadistica/_logs/` | 10 | Log completo de validación |
| `reports/beta/beta_test_results.md` | — | Resultados de pruebas funcionales (RES-132) |
| `reports/beta/validacion_criterios_aceptacion.md` | — | Validación de criterios de aceptación (RES-134) |
| `reports/beta/paquete_entrega_beta.md` | — | Este documento (RES-133) |

---

## 6. Documentación

| Documento | Descripción |
|-----------|-------------|
| `README.md` | Visión general del pipeline, instalación, quick start |
| `Pipeline Reproducible/README.md` | Uso del orquestador, flags, tabla de 10 etapas |
| `Imputación Generativa/README.md` | Arquitectura BiGRU-opt, parámetros, criterios de aceptación |

---

## 7. Dependencias

```
Python >= 3.10

torch >= 2.0          # modelo BiGRU-opt
pandas >= 2.0
numpy >= 1.24
pyarrow >= 12.0       # lectura/escritura parquet
scikit-learn >= 1.3   # MinMaxScaler, StandardScaler
pyyaml >= 6.0         # configuración YAML
scipy >= 1.11         # ks_2samp (KS-test)
statsmodels >= 0.14   # kpss
tqdm >= 4.65          # progreso
```

**Hardware mínimo:** 4 GB RAM, 2 GB almacenamiento libre. GPU no requerida (etapa 9 completada en 42.8 s en CPU).

---

## 8. Verificación rápida del resultado

```python
import pandas as pd

df = pd.read_parquet("data/imputed/dataset_imputado.parquet")
print(f"Filas         : {len(df):,}")           # esperado: 1,611,118
print(f"Estaciones    : {df['estacion'].nunique()}")  # esperado: 173
print(f"NaN residuales: {df[['precip','evap','tmax','tmin']].isna().sum().sum()}")  # esperado: < 1,325
```

---

## 9. Checklist de componentes del paquete

| Componente | Tamaño | Estado |
|-----------|--------|--------|
| `Pipeline Reproducible/run_pipeline.py` | — | SI |
| `Quality Gate/quality_gate.py` + `config.yaml` | — | SI |
| `Imputación Generativa/impute.py` + `config.yaml` | — | SI |
| `Validación Estadística/validate_imputation.py` + `config.yaml` | — | SI |
| `models/optimizacion/bigru_opt.pt` | 1.6 MB | SI |
| `models/scalers/scaler_*.pkl` (4 archivos) | — | SI |
| `reports/optimizacion/seleccion_ejecutiva.csv` | — | SI |
| `data/processed/dataset_final.parquet` | 8.7 MB | SI |
| `data/imputed/dataset_imputado.parquet` | 16 MB | SI |
| `reports/quality_gate/quality_gate_report.csv` | — | SI |
| `reports/validacion_estadistica/metricas_imputacion.csv` | — | SI |
| `reports/beta/beta_test_results.md` | — | SI |
| `reports/beta/validacion_criterios_aceptacion.md` | — | SI |
| `README.md` | — | SI |

**Estado del paquete: COMPLETO — todos los componentes presentes y verificados.**

---

*Documento generado: 16 de mayo de 2026 · Laboratorio de Geomática y Teledetección*
