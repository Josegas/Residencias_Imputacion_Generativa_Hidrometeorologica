# Monitoreo del modelo — Etapa 11 del pipeline

Detección de drift distribucional en el dataset imputado: compara cada ventana temporal decadal contra una ventana de referencia (1970–2000) usando PSI y KS-test. Genera alertas de reentrenamiento cuando el drift supera los umbrales configurados.

**Responsable:** Ingeniero de ML  
**Dependencia:** Etapa 9 (Imputación Generativa) — `data/imputed/dataset_imputado.parquet` disponible

> Esta etapa es la **etapa 11** del pipeline automatizado. Se ejecuta automáticamente al correr `run_pipeline.py`, o de forma independiente con `python "Monitoreo/monitor.py"`.

> **El monitoreo es informacional:** siempre devuelve exit code 0. Las alertas de reentrenamiento quedan registradas en el log y en `drift_report.csv` para revisión humana, pero no bloquean el pipeline.

---

## ¿Qué hace?

Carga el dataset original (`dataset_final.parquet`) y el imputado (`dataset_imputado.parquet`), y calcula por cada variable y ventana decadal:

1. **PSI (Population Stability Index):** mide cuánto cambió la distribución respecto a la ventana de referencia 1970–2000.
2. **KS-test:** prueba de Kolmogorov-Smirnov entre cada ventana decadal y la referencia.
3. **Cobertura temporal:** tasa de NaN residual por período — cuántos NaN originales fueron efectivamente imputados en cada década.

Al finalizar genera dos reportes CSV y dos figuras de resumen.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `monitor.py` | Script principal de monitoreo |
| `config.yaml` | Ventana de referencia, umbrales PSI/KS, rutas de entrada/salida |
| `README.md` | Este archivo |

---

## Uso

```bash
# Ejecución estándar
python "Monitoreo/monitor.py"

# Config alternativo
python "Monitoreo/monitor.py" --config ruta/config.yaml
```

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Dataset original | `data/processed/dataset_final.parquet` | `Dataset Final Procesado/pipeline.py` |
| Dataset imputado | `data/imputed/dataset_imputado.parquet` | `Imputación Generativa/impute.py` |

---

## Salidas generadas

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Reporte drift | `reports/monitoreo/drift_report.csv` | PSI y KS-test por variable y ventana decadal |
| Reporte cobertura | `reports/monitoreo/cobertura_temporal.csv` | NaN originales, rellenados y tasa de cobertura por década |
| Log | `reports/monitoreo/_logs/monitoreo_run.log` | Registro completo de ejecución |
| Figura drift | `reports/monitoreo/figuras/drift_decadal.png` | PSI por década — barras con umbrales WARNING/CRITICAL |
| Figura cobertura | `reports/monitoreo/figuras/cobertura_temporal.png` | Tasa de cobertura de imputación (%) por década |

---

## Métricas calculadas

### PSI (Population Stability Index)

```
PSI = Σ (actual% − esperado%) × ln(actual% / esperado%)
```

| Rango | Nivel | Acción |
|-------|-------|--------|
| < 0.10 | OK | Sin cambio significativo |
| 0.10 – 0.20 | WARNING | Cambio moderado — monitorear |
| > 0.20 | CRITICAL | Drift significativo → RETRAIN ALERT |

La alerta se evalúa sobre la **ventana más reciente** del dataset. Si el PSI supera 0.20, se registra `[RETRAIN ALERT]` en el log.

### KS-test

Compara la distribución empírica de cada ventana decadal contra la referencia. Un p-value < 0.05 se reporta como `WARNING` en `drift_report.csv`. El KS-test es complementario al PSI — confirma si la diferencia distribucional es estadísticamente significativa.

### Nota sobre evaporación

La variable `evap` presenta drift estructural en décadas previas a 1985 y en la ventana 2016–2025 por mecanismo **MNAR (Missing Not At Random)**: la evaporación no se midió sistemáticamente hasta los años 90 en Sinaloa. Este resultado es esperado y no indica falla del modelo de imputación.

---

## Configuración (`config.yaml`)

```yaml
input:
  original: "data/processed/dataset_final.parquet"
  imputed:  "data/imputed/dataset_imputado.parquet"

reference_window:
  start: 1970
  end:   2000

window_years: 10       # tamaño de ventana decadal en años

psi_warning:  0.10     # drift moderado
psi_critical: 0.20     # drift significativo → RETRAIN ALERT

ks_significance: 0.05  # α KS-test

coverage_target_pct: 99  # objetivo de cobertura en figura
```

---

## Requisitos

```bash
pip install pandas numpy pyarrow pyyaml scipy matplotlib
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
