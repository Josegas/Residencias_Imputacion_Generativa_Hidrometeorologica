# Pipeline Reproducible

Orquestador end-to-end del pipeline de datos del proyecto de imputación hidrometeorológica, siguiendo la metodología CRISP-ML(Q).

**Jira:** RES-33 | **Subtareas:** RES-126, RES-127  
**Responsable:** Ingeniero de ML  
**Dependencia:** 4.3 (Optimización y selección del modelo ganador)

---

## Qué hace este script

Ejecuta en orden las **12 etapas del pipeline** (descarga → validación estadística), verificando que cada salida exista antes de continuar. Las etapas 8-9-10 aplican el Quality Gate CRISP-ML(Q), el modelo BiGRU-opt y la validación estadística post-imputación.

Las etapas de modelado experimental (Modelos Base, Generativos, Optimización) **no se automatizan** porque son notebooks de experimentación que documentan el proceso de selección del modelo. Sus artefactos (pesos del modelo ganador) se verifican al finalizar.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `run_pipeline.py` | Script principal del pipeline |
| `ingest_external.py` | Adaptador para datos externos: convierte un CSV/Excel/Parquet plano a la estructura de particiones que espera la Etapa 3 |
| `config.yaml` | Definición de etapas, rutas y artefactos (sin hardcoding) |
| `README.md` | Este archivo |

---

## Uso

```bash
# Ejecutar todas las etapas de datos
python "Pipeline Reproducible/run_pipeline.py"

# Desde una etapa específica (omite las anteriores)
python "Pipeline Reproducible/run_pipeline.py" --from-stage 3

# Solo una etapa
python "Pipeline Reproducible/run_pipeline.py" --only-stage 6

# Omitir etapas específicas (útil para datos externos — saltar 6 y 7)
python "Pipeline Reproducible/run_pipeline.py" --from-stage 3 --skip-stages 6,7 --force

# Forzar re-ejecución aunque la salida ya exista
python "Pipeline Reproducible/run_pipeline.py" --force

# Ver estado de cada etapa
python "Pipeline Reproducible/run_pipeline.py" --list-stages
```

### Datos externos (ingest_external.py + --external)

Para ejecutar el pipeline con un archivo propio **sin modificar los datos CONAGUA**:

```bash
# 1. Convertir el archivo al formato de particiones (escribe en organized_external/)
python "Pipeline Reproducible/ingest_external.py" --input mi_dataset.csv --force

# 2. Ejecutar en modo --external: etapas 3-5 usan directorios aislados
#    y normalize.py aplica los scalers originales sin re-ajustarlos
python "Pipeline Reproducible/run_pipeline.py" --from-stage 3 --skip-stages 1,2,6,7 --force --external
```

El flag `--external` pasa automáticamente a cada etapa los argumentos necesarios:

| Etapa | Argumento extra | Efecto |
|-------|----------------|--------|
| 2 | `--output-dir data/interim/organized_external/estado=sin` | Escribe en directorio externo |
| 3 | `--input-dir ...organized_external --output-dir data/cleaned_external` | Lee/escribe en dirs externos |
| 4 | `--input-dir data/cleaned_external --output-dir data/scaled_external --transform-only` | Usa scalers originales sin re-ajustar |
| 5 | `--input-dir data/scaled_external` | Lee datos externos escalados |
| 8-12 | (sin cambios) | Siempre leen de `dataset_final.parquet` |

El archivo debe tener las columnas: `estacion`, `date`, `precip`, `evap`, `tmax`, `tmin`.  
Formatos aceptados: `.csv`, `.txt` (separador auto-detectado), `.xlsx`, `.xls`, `.parquet`.  
Las etapas 6 y 7 (División train-val-test y Construcción de tensores) se omiten porque son artefactos de entrenamiento del modelo, no de inferencia.

---

## Etapas automatizadas

| # | Etapa | Script | Salida que verifica |
|---|-------|--------|---------------------|
| 1 | Descarga de datos crudos | `Obtencion de Datos Crudos/download_sinaloa_raw_pro.py` | `data/raw/.../download_summary.csv` |
| 2 | Estructuración del dataset | `Estructuracion del Dataset/organize_raw_by_station_year_variable_parquet.py` | `data/interim/.../_index.csv` |
| 3 | Limpieza y validación | `Validacion y limpieza/cleaning.py` | `data/cleaned/.../_index_cleaned.csv` |
| 4 | Normalización y escalamiento | `Preprocesamiento/normalize.py` | `models/scalers/scaler_precip.pkl` |
| 5 | Dataset final procesado | `Dataset Final Procesado/pipeline.py` | `data/processed/dataset_final.parquet` |
| 6 | División train/val/test | `División Train-Val-Test/split.py` + `verify_leakage.py` | `data/splits/train/train.parquet` |
| 7 | Construcción de tensores | `Construcción de Tensores/tensor_builder.py` + `validate_tensors.py` | `data/tensors/X_train.pt` |
| 8 | Quality Gate CRISP-ML(Q) | `Quality Gate/quality_gate.py` | `reports/quality_gate/quality_gate_report.csv` |
| 9 | Imputación generativa | `Imputación Generativa/impute.py` | `data/imputed/dataset_imputado.parquet` |
| 10 | Validación estadística | `Validación Estadística/validate_imputation.py` | `reports/validacion_estadistica/metricas_imputacion.csv` |
| 11 | Monitoreo del modelo | `Monitoreo/monitor.py` | `reports/monitoreo/drift_report.csv` |
| 12 | Análisis y exportación | `Análisis y Exportación/export.py` | `data/export/dataset_imputado.csv` |

---

## Comportamiento de omisión de etapas

Si el artefacto de verificación (`check_output`) de una etapa ya existe, esa etapa se omite automáticamente con un aviso `[AVISO] Salida ya existe`. Esto permite reanudar el pipeline desde cualquier punto sin re-procesar pasos ya completados.

Para forzar la re-ejecución de una etapa específica:

```bash
python "Pipeline Reproducible/run_pipeline.py" --only-stage 4 --force
```

---

## Configuración (`config.yaml`)

Todos los parámetros del pipeline se gestionan en `config.yaml`. No es necesario editar el script para adaptar rutas o añadir etapas:

```yaml
stages:
  - id: 1
    name: "Descarga de datos crudos"
    script: "Obtencion de Datos Crudos/download_sinaloa_raw_pro.py"
    check_output: "data/raw/conagua_smn/estado=sin/_logs/download_summary.csv"
  ...
```

Para agregar una nueva etapa, basta con añadir una entrada al listado `stages` en `config.yaml`.

---

## Criterios de aceptación (RES-126 / RES-127)

| Criterio | Cómo se cumple |
|----------|----------------|
| Ejecución end-to-end sin errores | Exit code 0 al finalizar; cada etapa muestra `PASS` |
| Reproducible con un solo comando | `python "Pipeline Reproducible/run_pipeline.py"` |
| Documentación clara de ejecución | Este README + `--list-stages` + main README |

---

## Log de ejecución

Cada ejecución genera un log con marca de tiempo en:

```
data/pipeline_logs/pipeline_run_YYYYMMDD_HHMMSS.log
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
