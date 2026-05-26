# Normalización y escalamiento del dataset hidrometeorológico

Este script aplica la normalización y escalamiento al dataset hidrometeorológico de **Sinaloa** organizado en la capa `cleaned`, generando una capa `scaled` lista para las etapas posteriores de modelado de imputación generativa.

Su función principal es transformar las cuatro variables climáticas del dataset (`precip`, `evap`, `tmax`, `tmin`) a rangos numéricos apropiados para redes neuronales, preservando los valores faltantes y garantizando que la misma transformación sea reproducible en datos nuevos.

---

## Objetivo

Producir una versión escalada y reproducible del dataset hidrometeorológico a partir de la capa `cleaned`, aplicando scalers globales por variable que permitan comparar valores entre estaciones sin sesgo de escala.

Este paso corresponde a la **Actividad 3.2** del proyecto y satisface los criterios de aceptación de los tickets RES-101, RES-103 y RES-104.

---

## Qué hace el script

- Resuelve la ruta raíz del proyecto automáticamente a partir de su propia ubicación (`Path(__file__).resolve().parent.parent`), sin necesidad de configurar rutas manualmente.
- Carga todos los parámetros desde `config.yaml` (rutas, semilla, tipo de scaler por variable).
- Lee el índice de particiones generado por `cleaning.py`.
- Ajusta un **scaler global** por variable usando todos los valores válidos de todas las estaciones (garantiza que el mismo valor físico tenga siempre el mismo valor escalado).
- Por cada partición (estación × año × variable):
  - Aplica la transformación preservando los `NaN` intactos.
  - Guarda el parquet escalado en `data/scaled/`.
- Guarda los scalers entrenados como archivos `.pkl` en `models/scalers/` para reproducibilidad futura.
- Genera `scaling_report.csv` con métricas detalladas por partición.
- Genera `_index_scaled.csv` con el índice de la capa `scaled`.

---

## Variables procesadas

| Variable | Descripción | Scaler | Justificación |
|----------|-------------|--------|---------------|
| `precip` | Precipitación diaria (mm) | `MinMaxScaler [0, 1]` | Límite inferior fijo en 0, distribución asimétrica con muchos ceros |
| `evap`   | Evaporación diaria (mm)   | `MinMaxScaler [0, 1]` | Límite inferior fijo en 0, distribución asimétrica |
| `tmax`   | Temperatura máxima (°C)   | `StandardScaler`      | Distribución aproximadamente simétrica, estándar para redes neuronales |
| `tmin`   | Temperatura mínima (°C)   | `StandardScaler`      | Distribución aproximadamente simétrica, estándar para redes neuronales |

El tipo de scaler y sus parámetros pueden modificarse en `config.yaml` sin tocar el script.

### Decisión: scalers globales

Los scalers se ajustan con **todos los datos de todas las estaciones** (no uno por estación). Esto garantiza que el mismo valor físico —por ejemplo, 35 °C— tenga siempre el mismo valor escalado sin importar la estación, lo cual es indispensable para que los modelos LSTM, BRITS y GAN puedan comparar y relacionar valores entre estaciones correctamente.

---

## Estructura de entrada

El script espera el índice generado por `cleaning.py` en:

```text
data/cleaned/organized/estado=sin/_index_cleaned.csv
```

Y los parquets limpios en:

```text
data/cleaned/organized/estado=sin/
├── estacion=25001/
│   ├── year=1961/
│   │   ├── precip.parquet
│   │   ├── evap.parquet
│   │   ├── tmax.parquet
│   │   └── tmin.parquet
│   └── ...
└── ...
```

---

## Estructura de salida

```text
data/
└── scaled/
    ├── organized/
    │   └── estado=sin/
    │       ├── estacion=25001/
    │       │   ├── year=1961/
    │       │   │   ├── precip.parquet
    │       │   │   ├── evap.parquet
    │       │   │   ├── tmax.parquet
    │       │   │   └── tmin.parquet
    │       │   └── ...
    │       └── _index_scaled.csv
    └── logs/
        └── normalize_run.log

models/
└── scalers/
    ├── scaler_precip.pkl
    ├── scaler_evap.pkl
    ├── scaler_tmax.pkl
    ├── scaler_tmin.pkl
    └── scalers_metadata.csv

reports/
└── scaling_report.csv
```

---

## Reportes generados

### `reports/scaling_report.csv`

Una fila por partición con las métricas del escalamiento.

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año |
| `variable` | Variable climática |
| `tipo_scaler` | Scaler aplicado (`MinMaxScaler` / `StandardScaler`) |
| `filas` | Total de filas en la partición |
| `valores_validos` | Valores no nulos tras el escalamiento |
| `missing_pct` | Porcentaje de faltantes |
| `valor_min_scaled` | Mínimo del rango escalado en esta partición |
| `valor_max_scaled` | Máximo del rango escalado en esta partición |
| `valor_mean_scaled` | Media del rango escalado en esta partición |
| `path_parquet_scaled` | Ruta al parquet escalado guardado |

### `data/scaled/organized/estado=sin/_index_scaled.csv`

Índice de todas las particiones escaladas generadas.

| Columna | Descripción |
|---------|-------------|
| `station` | Clave de estación |
| `year` | Año |
| `variable` | Variable climática |
| `path_parquet` | Ruta al parquet escalado |
| `rows` | Número de filas |
| `missing_pct` | Porcentaje de faltantes |

### `models/scalers/scalers_metadata.csv`

Parámetros aprendidos por cada scaler global.

| Columna | Descripción |
|---------|-------------|
| `variable` | Variable climática |
| `tipo_scaler` | Tipo de scaler aplicado |
| `pkl` | Nombre del archivo `.pkl` correspondiente |
| `param_min` | Mínimo global aprendido (MinMaxScaler) |
| `param_max` | Máximo global aprendido (MinMaxScaler) |
| `param_mean` | Media global aprendida (StandardScaler) |
| `param_std` | Desviación estándar global aprendida (StandardScaler) |

---

## Configuración (`config.yaml`)

Todos los parámetros se gestionan en `config.yaml`. No es necesario editar el script para adaptar el pipeline:

```yaml
paths:
  cleaned_subpath: [data, cleaned, organized, "estado=sin"]
  scaled_subpath:  [data, scaled, organized, "estado=sin"]
  scalers_subpath: [models, scalers]
  ...

reproducibility:
  random_seed: 42

scalers:
  precip:
    tipo: "MinMaxScaler"
    feature_range: [0, 1]
  evap:
    tipo: "MinMaxScaler"
    feature_range: [0, 1]
  tmax:
    tipo: "StandardScaler"
  tmin:
    tipo: "StandardScaler"
```

---

## Flujo general del script

1. Cargar configuración desde `config.yaml`.
2. Resolver la ruta raíz del proyecto automáticamente.
3. Leer y desduplicar el índice de particiones `_index_cleaned.csv`.
4. **PASO 1** — Ajustar scalers globales: para cada variable, leer todos los parquets, extraer valores válidos y ajustar el scaler con el conjunto completo.
5. **PASO 2** — Guardar scalers: serializar cada scaler como `.pkl` y exportar sus parámetros a `scalers_metadata.csv`.
6. **PASO 3** — Escalar particiones: para cada partición, leer el parquet limpio, aplicar la transformación preservando `NaN`, y guardar en `data/scaled/`.
7. **PASO 4** — Guardar reporte e índice: `scaling_report.csv` e `_index_scaled.csv`.

Si alguna partición falla durante la lectura o escritura, el error se registra en el log y el pipeline continúa con las demás.

---

## Reproducibilidad

La reproducibilidad se garantiza en dos niveles:

- **Semilla**: `np.random.seed(42)` fijada al inicio (configurable en `config.yaml`).
- **Scalers serializados**: los archivos `.pkl` en `models/scalers/` permiten aplicar exactamente la misma transformación a datos nuevos sin necesidad de reajustar. Esto es indispensable para que el conjunto de validación y test reciban la misma escala que el de entrenamiento.

Satisface el AC de RES-103: *"el código de normalización y escalamiento es completamente reproducible"*.

---

## Validaciones incorporadas

- Verifica que el índice de entrada existe antes de iniciar.
- Verifica que cada archivo parquet existe antes de intentar leerlo.
- Captura errores de lectura y escritura por partición sin detener el pipeline.
- Preserva los `NaN` durante el escalamiento: el scaler solo transforma valores válidos.

---

## Requisitos

- Python 3.9 o superior
- `pandas`
- `pyarrow`
- `numpy`
- `scikit-learn`
- `pyyaml`

```bash
pip install pandas pyarrow numpy scikit-learn pyyaml
```

---

## Ejecución

```bash
python "Preprocesamiento/normalize.py"
```

> El script resuelve la ruta del proyecto automáticamente asumiendo que vive en una subcarpeta de primer nivel del repositorio. Si se mueve a otra ubicación, ajusta la línea:
> ```python
> PROJECT_ROOT = Path(__file__).resolve().parent.parent
> ```

### Modo datos externos (`--transform-only`, `--input-dir`, `--output-dir`)

Al normalizar datos de fuentes externas (no CONAGUA), **los scalers no deben volver a ajustarse**. El modelo BiGRU-opt fue entrenado con scalers globales ajustados sobre las 173 estaciones de Sinaloa; reajustarlos con datos de una sola estación distorsionaría la escala y degradaría la calidad de la imputación. El flag `--transform-only` carga los scalers existentes sin modificarlos:

```bash
python "Preprocesamiento/normalize.py" \
    --transform-only \
    --input-dir  data/cleaned_external \
    --output-dir data/scaled_external
```

| Argumento | Descripción |
|-----------|-------------|
| `--transform-only` | Carga los scalers serializados en `models/scalers/` y aplica solo la transformación, sin reajustar ni sobreescribir los `.pkl`. |
| `--input-dir` | Directorio raíz de las particiones limpias. Si se omite, se usa `data/cleaned/organized/estado=sin`. |
| `--output-dir` | Directorio de salida para los parquets escalados e índice. Si se omite, se usa `data/scaled/organized/estado=sin`. |

La estructura de salida es idéntica a la del flujo estándar; solo cambia el directorio raíz. El script construye las rutas replicando la jerarquía relativa de cada partición respecto al `--input-dir`.

Estos argumentos los pasa automáticamente `run_pipeline.py` cuando se usa `--external`. No es necesario invocarlos manualmente en ese flujo.

### Salida esperada en consola

```text
2025-xx-xx xx:xx:xx  INFO      INICIO DE NORMALIZACIÓN — dataset hidrometeorológico Sinaloa
2025-xx-xx xx:xx:xx  INFO      Config cargada desde: .../Preprocesamiento/config.yaml
2025-xx-xx xx:xx:xx  INFO      Semilla de reproducibilidad : 42
2025-xx-xx xx:xx:xx  INFO      Scalers configurados:
2025-xx-xx xx:xx:xx  INFO        PRECIP   → MinMaxScaler
2025-xx-xx xx:xx:xx  INFO        EVAP     → MinMaxScaler
2025-xx-xx xx:xx:xx  INFO        TMAX     → StandardScaler
2025-xx-xx xx:xx:xx  INFO        TMIN     → StandardScaler
2025-xx-xx xx:xx:xx  INFO      PASO 1 — Ajustando scalers globales...
...
2025-xx-xx xx:xx:xx  INFO      NORMALIZACIÓN COMPLETADA
```

---

## Orden de ejecución

Este script es el **tercer paso** del pipeline de preprocesamiento:

```
1. download_sinaloa_raw_pro.py          → data/raw/
2. organize_raw_by_station_year_...py   → data/interim/
3. cleaning.py                          → data/cleaned/
4. normalize.py                         → data/scaled/   ← este script
```

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Proyecto de Residencias Profesionales**
*Reconstrucción de una base de datos hidrometeorológica usando técnicas de inteligencia artificial*
Laboratorio de Geomática y Teledetección
