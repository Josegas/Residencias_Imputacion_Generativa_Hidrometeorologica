# Validación Estadística — Etapa 10 + US 6.1

Verificación estadística post-imputación: compara el dataset original contra el imputado para confirmar que la imputación preserva las propiedades estadísticas de las series.

**Jira:** RES-36 | **Subtareas:** RES-135, RES-138  
**US 6.1:** Validación estacional (6.1.3) y multianual (6.1.4)  
**Responsable:** Ingeniero de ML / Científico de datos  
**Dependencia:** 5.3 (Pruebas beta completadas)

> `validate_imputation.py` es la **etapa 10** del pipeline automatizado y se ejecuta con `run_pipeline.py`.  
> `validate_seasonal_multianual.py` es independiente y cubre las actividades de US 6.1.3 y 6.1.4.

---

## ¿Qué hace cada script?

### `validate_imputation.py` — Etapa 10

Carga el dataset original normalizado y el dataset imputado en escala original, aplica inverse-transform al original para comparar en unidades físicas, y calcula cuatro grupos de métricas:

1. **Cobertura**: NaN rellenados vs NaN originales por variable.
2. **KS-test**: distancia entre distribución observada e imputada (RES-135).
3. **Correlaciones**: Pearson inter-variable antes y después de imputar (RES-138).
4. **Criterios críticos post-imputación**: límites físicos y restricción tmax ≥ tmin.

### `validate_seasonal_multianual.py` — US 6.1.3 / 6.1.4

Extiende la validación estadística con análisis temporal:

5. **Validación estacional** (6.1.3): media mensual (Ene–Dic) observado vs imputado por variable.
6. **Validación multianual** (6.1.4): media y desviación estándar anual observado vs imputado a lo largo del período histórico completo.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `validate_imputation.py` | Etapa 10 — KS-test, correlaciones, cobertura, KPSS, criterios críticos |
| `validacion_estacional_multianual.ipynb` | US 6.1.3 / 6.1.4 — validación estacional y multianual (notebook interactivo) |
| `config.yaml` | Rutas de entrada/salida, umbrales KS y KPSS (compartido por script y notebook) |
| `README.md` | Este archivo |

---

## Uso

```bash
# Etapa 10 del pipeline (KS-test, correlaciones, cobertura, criterios críticos)
python "Validación Estadística/validate_imputation.py"

# Config alternativo
python "Validación Estadística/validate_imputation.py" --config ruta/config.yaml
```

**US 6.1.3 / 6.1.4 — validación estacional y multianual:**  
Abrir y ejecutar el notebook `validacion_estacional_multianual.ipynb` en Jupyter.

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Dataset original | `data/processed/dataset_final.parquet` | `Dataset Final Procesado/pipeline.py` |
| Dataset imputado | `data/imputed/dataset_imputado.parquet` | `Imputación Generativa/impute.py` |
| Scalers | `models/scalers/scaler_*.pkl` | `Preprocesamiento/normalize.py` |

---

## Salidas generadas

### `validate_imputation.py` (Etapa 10)

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Métricas de cobertura | `reports/validacion_estadistica/metricas_imputacion.csv` | NaN originales, rellenados, residuales y tasa por variable |
| KS-test | `reports/validacion_estadistica/ks_test_report.csv` | Estadístico D y p-value por variable |
| Correlaciones | `reports/validacion_estadistica/correlaciones_comparativas.csv` | Pearson inter-variable antes/después con delta |
| Log | `reports/validacion_estadistica/_logs/validacion_estadistica_run.log` | Registro completo de ejecución |
| Figura cobertura | `reports/validacion_estadistica/figuras/val_cobertura.png` | % NaN rellenados por variable vs objetivo 99% |
| Figura distribución | `reports/validacion_estadistica/figuras/val_distribucion.png` | KDE suavizada observado vs imputado por variable (con medias) |
| Figura correlaciones | `reports/validacion_estadistica/figuras/val_correlaciones.png` | Correlaciones antes/después por par de variables |
| Figura KS | `reports/validacion_estadistica/figuras/val_ks_test.png` | Estadístico KS por variable |

### `validacion_estacional_multianual.ipynb` (US 6.1.3 / 6.1.4)

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Estacional mensual | `reports/validacion_estadistica/estacional_mensual.csv` | Media mensual observada vs imputada por variable (Ene–Dic) |
| Multianual anual | `reports/validacion_estadistica/multianual_anual.csv` | Media y std anual observada vs imputada por variable |
| Log | `reports/validacion_estadistica/_logs/validacion_estacional_run.log` | Registro de ejecución estacional/multianual |
| Figura estacional | `reports/validacion_estadistica/figuras/val_estacional.png` | Ciclo anual (media mensual) observado vs imputado — 4 variables |
| Figura multianual | `reports/validacion_estadistica/figuras/val_multianual.png` | Tendencia anual ±1 std observado vs imputado — período histórico completo |

---

## Métricas calculadas

### Cobertura de imputación

| Variable | NaN originales | Rellenados | Cobertura |
|----------|---------------|-----------|-----------|
| precip | 10,858 | 10,811 | 99.6% |
| evap | 623,106 | 622,268 | 99.9% |
| tmax | 113,162 | 112,942 | 99.8% |
| tmin | 113,162 | 112,942 | 99.8% |

### KS-test (RES-135)

Compara los valores imputados (posiciones que eran NaN) contra los valores observados originales. Un p-value bajo no indica fallo del modelo — es esperado por el mecanismo MNAR (Missing Not At Random) estructural de evaporación y la tendencia térmica de las temperaturas.

### Correlaciones inter-variable (RES-138)

Pearson entre precip, evap, tmax y tmin antes y después de la imputación. Deltas pequeños indican que la estructura de dependencia se preservó.

### Criterios críticos post-imputación

| Criterio | Resultado |
|----------|-----------|
| `physical_limits_imputed` | PASS — ningún valor imputado fuera de rango físico |
| `tmax_gte_tmin_imputed` | PASS — ninguna inversión lógica tras imputación |

---

## Configuración (`config.yaml`)

```yaml
input:
  original: "data/processed/dataset_final.parquet"
  imputed:  "data/imputed/dataset_imputado.parquet"

output:
  report_dir:  "reports/validacion_estadistica"
  metrics:     "reports/validacion_estadistica/metricas_imputacion.csv"
  ks_report:   "reports/validacion_estadistica/ks_test_report.csv"
  corr_report: "reports/validacion_estadistica/correlaciones_comparativas.csv"
  # figuras → reports/validacion_estadistica/figuras/ (generado automáticamente)

ks_significance:   0.05   # α Kolmogorov-Smirnov
kpss_significance: 0.05   # α KPSS post-imputación
max_residual_nan_rate: 0.05
```

---

## Requisitos

```bash
pip install pandas numpy pyarrow scikit-learn pyyaml scipy statsmodels matplotlib
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
