# Quality Gate — Etapa 8 del pipeline

Verificación de calidad del dataset procesado antes de ejecutar la imputación generativa, siguiendo el estándar CRISP-ML(Q).

**Jira:** RES-35  
**Responsable:** Ingeniero de ML  
**Dependencia:** 5.1 (Pipeline reproducible — etapa 7 completada)

> Esta etapa es la **etapa 8** del pipeline automatizado. Se ejecuta automáticamente al correr `run_pipeline.py`, o de forma independiente con `python "Quality Gate/quality_gate.py"`.

---

## ¿Qué hace?

Carga `dataset_final.parquet` (escala normalizada), aplica inverse-transform para verificar límites físicos en escala original, y evalúa dos tipos de criterios:

- **Criterios CRÍTICOS**: si fallan, el pipeline se detiene (exit code 1) y la imputación no se ejecuta.
- **Criterios WARNING**: se registran en el reporte pero no bloquean el pipeline.

Al finalizar genera un reporte CSV y tres figuras de resumen.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `quality_gate.py` | Script principal del Quality Gate |
| `config.yaml` | Límites físicos, umbrales de faltantes, parámetros KPSS |
| `README.md` | Este archivo |

---

## Uso

```bash
# Ejecución estándar
python "Quality Gate/quality_gate.py"

# Config alternativo
python "Quality Gate/quality_gate.py" --config ruta/config.yaml
```

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Dataset final | `data/processed/dataset_final.parquet` | `Dataset Final Procesado/pipeline.py` |
| Scalers | `models/scalers/scaler_*.pkl` | `Preprocesamiento/normalize.py` |

---

## Salidas generadas

| Artefacto | Ruta | Descripción |
|-----------|------|-------------|
| Reporte CSV | `reports/quality_gate/quality_gate_report.csv` | Resultado (PASS/WARNING/FAIL) por criterio y variable |
| Log | `reports/quality_gate/_logs/quality_gate_run.log` | Registro completo de ejecución |
| Figura criterios | `reports/quality_gate/figuras/qg_criterios.png` | Estado de cada criterio por variable |
| Figura faltantes | `reports/quality_gate/figuras/qg_missing_rate.png` | Tasa real vs umbral máximo por variable |
| Figura KPSS | `reports/quality_gate/figuras/qg_kpss.png` | % estaciones estacionarias por variable |

---

## Criterios evaluados

### Críticos (exit 1 si fallan)

| Criterio | Descripción |
|----------|-------------|
| `physical_limits` | Ningún valor observado fuera de rangos físicos (mm, °C) |
| `min_valid_obs` | Cada estación tiene >= 365 observaciones válidas |
| `tmax_gte_tmin_observed` | tmax >= tmin en todos los pares observados |

### Advertencia (se registran, no bloquean)

| Criterio | Umbral | Descripción |
|----------|--------|-------------|
| `missing_rate` | precip/tmax/tmin ≤ 60%, evap ≤ 85% | Tasa global de faltantes por variable |
| `kpss_stationarity` | >= 70% estaciones estacionarias | Test KPSS α=0.05 por estación |

---

## Configuración (`config.yaml`)

```yaml
input:
  dataset: "data/processed/dataset_final.parquet"

output:
  report:  "reports/quality_gate/quality_gate_report.csv"
  log_dir: "reports/quality_gate/_logs"
  # figuras → reports/quality_gate/figuras/ (generado automáticamente)

physical_limits:
  precip: {min: 0.0, max: 500.0}
  evap:   {min: 0.0, max:  60.0}
  tmax:   {min: -5.0, max: 55.0}
  tmin:   {min: -15.0, max: 45.0}

missing_rate_thresholds:
  precip: 0.60
  evap:   0.85
  tmax:   0.60
  tmin:   0.60

min_valid_obs_per_station: 365
kpss_significance: 0.05
```

---

## Requisitos

```bash
pip install pandas numpy pyarrow scikit-learn pyyaml statsmodels matplotlib
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
