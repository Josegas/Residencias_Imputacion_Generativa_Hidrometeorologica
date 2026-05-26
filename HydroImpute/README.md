# HydroImpute — US 6.2

Aplicación web multi-página construida con **Streamlit** para ejecutar el pipeline de imputación generativa hidrometeorológica, visualizar resultados y operar el modelo BiGRU-opt sobre datos propios del usuario.

**Jira:** US 6.2  
**Responsable:** Desarrollador full-stack / Científico de datos  
**Dependencia:** 5.3 (Pruebas beta completadas)

---

## Páginas

| Página | Archivo | Descripción |
|--------|---------|-------------|
| Inicio | `app.py` | Landing page con métricas clave y rendimiento del modelo |
| Dashboard | `pages/1_Dashboard.py` | Estado de las 12 etapas, último log, cobertura y alertas PSI |
| Pipeline | `pages/2_Pipeline.py` | Ejecución del pipeline CONAGUA completo o por etapas con log en tiempo real |
| Datos propios | `pages/3_Datos_Propios.py` | Carga archivos propios (CSV, Excel, Parquet o .txt CONAGUA) y ejecuta el pipeline completo desde la etapa correspondiente |
| Resultados | `pages/4_Resultados.py` | Figuras y reportes de Quality Gate, validación, monitoreo y exportación |
| Configuración | `pages/5_Configuracion.py` | Editor visual de los `config.yaml` de cada módulo del pipeline |

---

## Uso

### Local

```bash
# Desde la raíz del proyecto
streamlit run "HydroImpute/app.py"
```

La aplicación se abre automáticamente en `http://localhost:8501`.

### Streamlit Cloud (opcional)

1. Subir el repositorio a GitHub.
2. Ir a [share.streamlit.io](https://share.streamlit.io) y conectar el repo.
3. Configurar `Main file path`: `HydroImpute/app.py`.
4. Agregar los artefactos del modelo como secretos o incluirlos en el repo si el tamaño lo permite.

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `app.py` | Punto de entrada — página de inicio |
| `utils.py` | Utilidades compartidas: rutas, carga del modelo, imputación en escala original, validación, archivado de reportes (`archive_reports`) |
| `pages/` | Páginas de la app (orden controlado por prefijo numérico) |
| `img/LOGO_TEC_PNG_OK.png` | Escudo del TECNM Campus Culiacán (sidebar) |

---

## Entradas requeridas

| Artefacto | Ruta | Generado por |
|-----------|------|--------------|
| Modelo BiGRU-opt | `models/optimizacion/bigru_opt.pt` | `Optimización/optimizacion_hiperparametros.ipynb` |
| Scaler precip | `models/scalers/scaler_precip.pkl` | `Preprocesamiento/normalize.py` |
| Scaler evap | `models/scalers/scaler_evap.pkl` | `Preprocesamiento/normalize.py` |
| Scaler tmax | `models/scalers/scaler_tmax.pkl` | `Preprocesamiento/normalize.py` |
| Scaler tmin | `models/scalers/scaler_tmin.pkl` | `Preprocesamiento/normalize.py` |

---

## Formatos de entrada (página Datos propios)

La página acepta cuatro tipos de archivo con flujos distintos:

### CSV / Excel / TXT plano (`.csv`, `.xlsx`, `.xls`, `.txt`)

Archivo plano con las columnas requeridas. Los `.txt` se leen con separador auto-detectado (coma, tabulador, punto y coma o espacio). Entra en la **Etapa 3**.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `estacion` | str / int | Identificador de la estación |
| `date` | fecha | `YYYY-MM-DD` |
| `precip` | float | Precipitación en mm — `NaN` = faltante |
| `evap` | float | Evaporación en mm — `NaN` = faltante |
| `tmax` | float | Temperatura máxima en °C — `NaN` = faltante |
| `tmin` | float | Temperatura mínima en °C — `NaN` = faltante |

### Parquet plano

Mismo contenido que CSV. La app pregunta si son datos en escala original o un `dataset_final.parquet` ya procesado:

- **Escala original** → igual que CSV, entra en la **Etapa 3**
- **dataset_final.parquet** (salida de la Etapa 5, datos normalizados) → se copia directamente a `data/processed/` y entra en la **Etapa 8** (Quality Gate)

### Archivos `.txt` formato CONAGUA/SMN

Uno o varios archivos con el formato oficial de CONAGUA (encabezado de metadatos + tabla con `NULO` para faltantes). El ID de estación se extrae del nombre del archivo (`dia25001.txt → 25001`). Se guardan en el directorio de datos crudos y la **Etapa 2** los procesa igual que en el pipeline original. Entra en la **Etapa 2**.

---

## Flujo de la página Datos propios

Dependiendo del tipo de archivo, el pipeline arranca desde una etapa distinta.
Las etapas 6 y 7 (División train-val-test y Construcción de tensores) se omiten siempre — son artefactos de entrenamiento del modelo, no de inferencia.

| Tipo de archivo | Etapa de entrada | Etapas ejecutadas |
|----------------|-----------------|-------------------|
| CSV / Excel / TXT plano / Parquet en escala original | 3 | 3, 4, 5, 8, 9, 10, 11, 12 |
| Parquet `dataset_final` ya procesado | 8 | 8, 9, 10, 11, 12 |
| `.txt` CONAGUA/SMN (uno o varios) | 2 | 2, 3, 4, 5, 8, 9, 10, 11, 12 |

Antes de ejecutar, la app muestra un aviso y solicita confirmación mediante un checkbox, ya que la ejecución sobreescribe los resultados del pipeline vigente.

**Flujo A — CSV / Excel / TXT plano / Parquet plano:**
1. El archivo se guarda en `data/raw/external/`
2. `ingest_external.py` lo convierte a particiones en `data/interim/organized_external/estado=sin/` (nunca toca `organized/`)
3. `run_pipeline.py --from-stage 3 --skip-stages 1,2,6,7 --force --external`
4. Etapas 3-5 leen/escriben en `*_external/`; scalers originales se preservan (`--transform-only`)

**Flujo A2 — Parquet ya procesado:**
1. El archivo se copia directamente a `data/processed/dataset_final.parquet`
2. `run_pipeline.py --from-stage 8 --force` (sin `--external`, no se tocan dirs de datos)

**Flujo B — Archivos .txt CONAGUA:**
1. Se limpia `data/interim/organized_external/estado=sin/` y `RAW_TXT_DIR` (solo directorios externos)
2. Los archivos `.txt` se guardan en `RAW_TXT_DIR`
3. `run_pipeline.py --from-stage 2 --skip-stages 1,6,7 --force --external`
4. Etapa 2 escribe en `organized_external/`; etapas 3-5 igual que Flujo A

Los reportes completos quedan disponibles en la página Resultados.

---

## Trazabilidad CRISP-ML(Q)

Antes de cada ejecución del pipeline (tanto en la página Pipeline como en Datos propios), la función `archive_reports()` de `utils.py` mueve los reportes vigentes a un directorio con timestamp:

```
reports/
  quality_gate/             ← resultado más reciente
  validacion_estadistica/
  monitoreo/
  archive/
    20260523_143022/        ← ejecución anterior completa
      quality_gate/
      validacion_estadistica/
      monitoreo/
```

Los logs de ejecución ya se guardan con timestamp propio en `data/pipeline_logs/`. Esto garantiza trazabilidad completa de cada corrida del pipeline.

---

## Criterios de aceptación (US 6.2)

| Criterio | Verificación |
|----------|-------------|
| El usuario puede cargar datos propios | Acepta CSV, Excel, TXT plano, Parquet y `.txt` CONAGUA (múltiples archivos) |
| La aplicación detecta el tipo de archivo y ajusta el flujo | Parquet: radio para elegir si es escala original o `dataset_final`; `.txt`: flujo CONAGUA automático |
| El usuario puede ejecutar el pipeline completo sobre sus datos | Botón "Ejecutar pipeline completo" con log en tiempo real; etapa de entrada según el tipo de archivo |
| Los resultados se muestran claramente | Métricas de cobertura y descarga del CSV final |
| El usuario puede ver los reportes completos | Página Resultados muestra figuras, Quality Gate, KS-test, PSI |
| El pipeline CONAGUA es operable desde la app | Página Pipeline ejecuta `run_pipeline.py` con streaming de logs |
| Los parámetros son configurables desde la app | Página Configuración edita los `config.yaml` sin abrir archivos |

---

## Requisitos

```bash
pip install streamlit pandas numpy torch pyarrow scikit-learn pyyaml openpyxl
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección — TECNM Campus Culiacán**
