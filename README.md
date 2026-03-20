# Reconstrucción de Base de Datos Hidrometeorológica con IA

Sistema para imputar valores faltantes en registros históricos de estaciones climatológicas de Sinaloa, a partir de datos oficiales del **SMN/CONAGUA**, mediante técnicas de Inteligencia Artificial. El proyecto construye un pipeline reproducible y trazable desde la descarga de datos crudos hasta la generación de una base reconstruida y validada estadísticamente.

> Proyecto de Residencias Profesionales — Laboratorio de Geomática y Teledetección  
> Estado: **En desarrollo**

---

## ¿Qué problema resuelve?

Las bases de datos hidrometeorológicas históricas presentan valores faltantes, discontinuidades e inconsistencias causadas por fallas instrumentales, mantenimiento de estaciones o errores de transmisión. Esto compromete análisis hidrológicos, modelos climáticos y la detección de eventos extremos.

Este proyecto reconstruye esas series comparando modelos estadísticos clásicos contra técnicas de aprendizaje profundo especializadas en imputación de series temporales, garantizando trazabilidad completa de cada valor reconstruido.

---

## Estado del proyecto

| Módulo | Estado |
|--------|--------|
| Descarga de datos crudos (SMN/CONAGUA) | Listo |
| Estructuración del dataset (raw → interim) | Listo |
| EDA general | Listo |
| Análisis de valores faltantes | Listo |
| Análisis temporal y estacional | Listo |
| Preprocesamiento y feature engineering | Pendiente |
| Modelado e imputación | Pendiente |
| Validación estadística / Quality Gate | Pendiente |
| Exportación de base reconstruida | Pendiente |

---

## Estructura del repositorio

```
.
├── Obtencion de Datos Crudos/
│   ├── download_sinaloa_raw_pro.py          # Descarga automática desde SMN/CONAGUA
│   └── README.md
│
├── Estructuracion del Dataset/
│   ├── organize_raw_by_station_year_variable_parquet.py  # Organiza raw → interim
│   └── README.md
│
├── eda_general_sinaloa.ipynb                # EDA: estadística descriptiva y outliers
├── analisis_valores_faltantes.ipynb         # Análisis granular de faltantes sobre parquet
├── analisis_temporal_estacional.ipynb       # Variaciones anuales, estacionales y ciclo hidrológico
│
├── reports/
│   └── figures/
│       ├── analisis_temporal/               # Figuras del análisis temporal
│       │   ├── tendencia_anual_variables.png
│       │   ├── perfil_estacional_mensual.png
│       │   ├── estacional_por_decadas.png
│       │   ├── ciclo_hidrologico_variables.png
│       │   ├── ciclo_hidrologico_integrado.png
│       │   └── ciclo_hidrologico_decadal.png
│       └── analisis_valores_faltantes/      # Figuras del análisis de faltantes
│           ├── clasificacion_estaciones_faltantes.png
│           ├── correlacion_faltantes_variables.png
│           ├── heatmap_estacional_faltantes.png
│           ├── heatmap_faltantes_estacion_variable.png
│           ├── heatmap_faltantes_temporal.png
│           ├── patron_estacional_faltantes.png
│           ├── rachas_faltantes_por_variable.png
│           └── tendencia_faltantes_temporal.png
│
├── docs/
│   └── img/                                 # Diagramas de arquitectura del sistema
│
├── data/                                    # No versionado (.gitignore)
│   ├── raw/
│   │   └── conagua_smn/
│   │       └── estado=sin/
│   │           ├── fuente=normales_climatologicas/
│   │           │   └── producto=diarios_txt/  # dia25001.txt, dia25002.txt ...
│   │           ├── _logs/
│   │           │   ├── download_manifest.csv  # Resultado detallado por clave
│   │           │   ├── download_run.log       # Log con marca de tiempo
│   │           │   └── download_summary.csv   # Métricas globales de la descarga
│   │           └── _meta/
│   │               └── stations_sin.csv       # Catálogo de claves con archivo válido
│   └── interim/
│       └── organized/
│           └── estado=sin/
│               ├── estacion=25001/
│               │   ├── year=1961/
│               │   │   ├── precip.csv / precip.parquet  # columnas: date, value
│               │   │   ├── evap.csv   / evap.parquet
│               │   │   ├── tmax.csv   / tmax.parquet
│               │   │   └── tmin.csv   / tmin.parquet
│               │   └── year=.../
│               ├── estacion=.../
│               └── _index.csv               # Índice global con % de faltantes por partición
│
└── README.md
```

---

## Pipeline de datos

El procesamiento sigue la metodología **CRISP-ML(Q)** organizado en capas diferenciadas, donde cada etapa produce una salida validable que sirve como entrada a la siguiente.

![Pipeline CRISP-ML(Q)](docs/img/CRISP-ML(Q)_Pipeline.jpg)

### Capa `raw` — Descarga de datos crudos

**Script:** `download_sinaloa_raw_pro.py`

Escanea el rango de claves de Sinaloa (`25001–25300`) y descarga automáticamente los archivos `.txt` de todas las estaciones disponibles en el portal del SMN/CONAGUA, sin necesidad de mantener una lista manual. Las descargas se ejecutan en paralelo con 10 hilos simultáneos usando `ThreadPoolExecutor`. Las claves sin archivo devuelven HTTP 404 y se descartan silenciosamente en consola, pero quedan registradas en el manifiesto. La escritura al manifiesto y al log es thread-safe mediante `threading.Lock`. Los archivos ya descargados se omiten con `SKIP_EXISTS` para evitar descargas repetidas.

Genera tres archivos de trazabilidad:
- `download_manifest.csv` — resultado detallado por clave: status, ssl_mode, duración, tamaño
- `download_run.log` — log con marca de tiempo de cada evento
- `download_summary.csv` — métricas globales: discovered, not_found_404, coverage_percent

Consulta el [README de Obtencion de Datos Crudos](Obtencion%20de%20Datos%20Crudos/README.md) para más detalles.

### Capa `interim` — Estructuración del dataset

**Script:** `organize_raw_by_station_year_variable_parquet.py`

Transforma los archivos `.txt` crudos en un dataset estructurado jerárquicamente por estación, año y variable climática. El script detecta automáticamente la línea de inicio de la tabla en cada archivo, salta el encabezado y la línea de unidades, y asigna nombres de columnas fijos. Convierte los valores nulos (`NULO`, `Nulo`, `nulo`, cadena vacía) a `NaN` y genera una partición independiente en CSV y Parquet por cada combinación estación–año–variable. Genera un `_index.csv` global con el porcentaje de valores faltantes por partición, que sirve como catálogo central para todos los análisis posteriores.

Variables procesadas: `PRECIP` (mm), `EVAP` (mm), `TMAX` (°C), `TMIN` (°C).

Consulta el [README de Estructuracion del Dataset](Estructuracion%20del%20Dataset/README.md) para más detalles.

### EDA general

**Notebook:** `eda_general_sinaloa.ipynb`

Análisis exploratorio completo sobre los **6,405,536 registros diarios** del dataset. Cubre tres criterios principales:

- **Análisis descriptivo:** estadísticas completas (media, mediana, moda, std, percentiles p5–p95) para las cuatro variables numéricas, y distribución de frecuencias por variable, estación y año.
- **Visualizaciones:** histogramas con líneas de media y mediana, boxplots, diagramas de dispersión entre pares de variables con correlación de Pearson, y series temporales de ejemplo.
- **Valores atípicos:** detección por criterio IQR×1.5, registro detallado por estación y fecha, documentación de posibles causas y visualización sobre la distribución de cada variable.

Hallazgos principales: 168 estaciones con registros entre 1908 y 2026, EVAP con 39.5% de faltantes promedio, PRECIP con apenas 0.8%, correlación TMAX–EVAP de r=0.572, 275,627 registros atípicos detectados (4.3% de los valores válidos).

### Análisis de valores faltantes

**Notebook:** `analisis_valores_faltantes.ipynb`  
**Figuras:** `reports/figures/analisis_valores_faltantes/`

Análisis granular operando directamente sobre los 19,220 archivos parquet individuales (6,392,652 registros diarios reales), lo que permite detectar patrones de ausencia que no serían visibles en estadísticas agregadas. Genera siete visualizaciones: heatmap estación×variable, heatmap temporal año×variable, patrón estacional por mes, heatmap mes×variable anotado, distribución de rachas de faltantes, clasificación de estaciones y correlación de patrones de ausencia entre variables.

Hallazgos principales:
- 13.3% de faltantes globales (847,508 días sin dato)
- 69% de estaciones con menos del 25% de faltantes — base sólida para el modelado
- EVAP con racha mediana de 1,307 días (~3.6 años): faltantes estructurales, no puntuales
- Correlación perfecta entre patrones de faltantes de TMAX y TMIN (r=1.00): comparten instrumento
- Sin estacionalidad en los faltantes: la ausencia es de origen operativo o instrumental, no climático

### Análisis temporal y estacional

**Notebook:** `analisis_temporal_estacional.ipynb`  
**Figuras:** `reports/figures/analisis_temporal/`

Caracterización del comportamiento temporal de las variables en tres escalas. Incluye comparación de perfiles por décadas (1960–2020) y estadísticos descriptivos por temporada seca (oct–may) vs lluviosa (jun–sep).

- **Variaciones anuales:** regresión lineal sobre series de medias anuales para detectar tendencias de largo plazo. Solo se incluyen años con ≥10 estaciones activas para garantizar representatividad.
- **Variaciones estacionales:** perfil mensual con media, mediana y rango P25–P75, comparación por décadas.
- **Ciclo hidrológico:** reordenamiento en ciclo Oct–Sep, representación integrada precipitación–temperatura y evolución decadal.

Hallazgos principales:
- Tendencia ascendente significativa en TMAX (r=0.303, p=0.009): +0.76 °C acumulados en 73 años
- Régimen monzónico confirmado: máximo de precipitación en agosto (6.4 mm/día), período seco nov–may con precipitaciones cercanas a cero
- Desfase entre pico térmico (junio, ~36.6 °C) y pico pluviométrico (agosto): característica definitoria del Monzón Mexicano
- EVAP presenta tendencia descendente significativa (r=−0.559, p<0.001) influenciada por cambios en la red de estaciones

---

## Arquitectura del sistema

El sistema adopta un estilo de **pipeline de procesamiento de datos** con módulos secuenciales y acoplamiento bajo. Cada módulo expone una interfaz estandarizada (DataFrames) y consume únicamente la salida del módulo anterior, lo que facilita la validación por etapas, la sustitución de modelos y la trazabilidad del dato desde su origen hasta la base reconstruida.

### Vista conceptual

Muestra los cuatro módulos principales del sistema y cómo interactúan el investigador y la fuente CONAGUA con el pipeline. El flujo va de izquierda a derecha: ingesta → procesamiento → reconstrucción con IA → salida, con retroalimentación hacia la capa de datos central.

![Arquitectura Conceptual](docs/img/Diagrama_arq_conceptual.jpg)

### Ciclo de vida metodológico — CRISP-ML(Q)

Representa las siete fases del proyecto organizadas en torno al conjunto de datos hidrometeorológicos. Las flechas continuas indican el flujo principal y las discontinuas los ciclos de retroalimentación, que permiten regresar a fases anteriores cuando una evaluación no supera el Quality Gate. Las fases incluyen: comprensión del problema, comprensión de los datos, preparación, modelado, evaluación, despliegue y monitoreo.

![Metodología CRISP-ML(Q)](docs/img/diagramaCRISP-ML(Q).jpg)

### Arquitectura de componentes

Vista detallada del pipeline completo con todas las etapas, herramientas y tecnologías asociadas a cada una. Muestra los tres grupos de modelos (estadísticos, ML y deep learning) que operan dentro del módulo de reconstrucción en paralelo, el flujo de retroalimentación desde el módulo de monitoreo hacia el reentrenamiento, y las herramientas de cada etapa (pandas, scikit-learn, TensorFlow/PyTorch, MLflow).

![Arquitectura de Componentes](docs/img/CRIPS_ML(Q)_Diagrama_arq_componentes.jpg)

### Diagrama UML de módulos

Describe los ocho componentes de software del sistema y sus interfaces de intercambio: `IDataIngested`, `IDataCleaned`, `IDataPreprocessed`, `IReconstructedSeries` e `IValidatedResults`. El acoplamiento entre módulos se da exclusivamente a través de estas interfaces estandarizadas, lo que permite reemplazar cualquier componente (por ejemplo, sustituir un modelo de imputación por otro) sin afectar al resto del pipeline.

![Diagrama UML de Componentes](docs/img/Diagrama_UML_componentes.jpg)

### Modelo de datos

Define la estructura relacional de la base de datos reconstruida. La entidad central `EstacionClimatologica` (identificada por `id_estacion PK`) se relaciona en 1:N con registros diarios, mensuales y anuales. Cada registro incluye los campos `fuente_dato`, `fecha_actualizacion` y `tipo_dato` para registrar si el valor es original o imputado, con qué modelo y en qué fecha, garantizando auditabilidad completa del proceso de reconstrucción.

![Diagrama Entidad-Relación](docs/img/Diagrama_ER.drawio.png)

---

## Modelos a implementar

Se compararán tres familias de modelos para determinar cuál preserva mejor la estructura estadística y los patrones estacionales de las series:

| Familia | Modelos |
|---------|---------|
| Estadísticos (baseline) | SARIMA, TBATS, Prophet |
| Machine Learning | XGBoost |
| Deep Learning | LSTM, Autoencoders, BRITS, GAN, SAITS, CSDI |

La selección del modelo final se determina mediante un **Quality Gate** que evalúa no solo el error numérico, sino la preservación de estacionalidad, autocorrelación y eventos extremos hidrológicos.

---

## Métricas de evaluación

| Métrica | Propósito |
|---------|-----------|
| RMSE / MAE / MAPE | Error de imputación general |
| R² | Ajuste global |
| NSE (Nash-Sutcliffe) | Eficiencia predictiva hidrológica |
| KPSS | Verificación de estacionariedad |
| ACF / PACF | Preservación de autocorrelación pre/post imputación |

> Los resultados comparativos entre modelos se publicarán aquí al completar la fase de evaluación.

---

## Instalación

**Requisitos:** Python 3.9 o superior

```bash
git clone https://github.com/Josegas/Residencias_Imputacion_Generativa_Hidrometeorologica.git
cd Residencias_Imputacion_Generativa_Hidrometeorologica

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# Dependencias para los scripts de datos
pip install pandas pyarrow

# Dependencias adicionales para los notebooks de análisis
pip install numpy matplotlib seaborn scipy jupyter
```

El script de descarga (`download_sinaloa_raw_pro.py`) no requiere dependencias externas, usa únicamente la biblioteca estándar de Python.

---

## Uso

### 1. Descargar los datos crudos

```bash
cd "Obtencion de Datos Crudos"
python download_sinaloa_raw_pro.py
```

Escanea el rango `25001–25300` con 10 hilos en paralelo y descarga los archivos disponibles en `data/raw/`. Las claves ya descargadas se omiten automáticamente. El tiempo estimado es de 3-5 minutos en la primera ejecución.

Salida esperada en consola:
```
[2026-03-01 10:00:00] INICIO | Estado=sin | Rango=25001–25300 | Claves a escanear=300
[2026-03-01 10:00:00] CONFIG | timeout=25s | retries=3 | sleep_between=0.2s
[2026-03-01 10:00:02] OK   P1 25001 | ssl=insecure | intento=1 | bytes=539742
[2026-03-01 10:00:02] SKIP P1 25002 (ya existe)
...
[2026-03-01 10:03:30] FIN
[2026-03-01 10:03:30] SUMMARY | discovered=168 | coverage_percent=56.0
```

> El orden de las líneas puede variar porque las descargas son paralelas.

### 2. Estructurar el dataset

```bash
cd "Estructuracion del Dataset"
python organize_raw_by_station_year_variable_parquet.py
```

Transforma los archivos crudos en particiones organizadas en `data/interim/`. Requiere que el paso anterior haya completado al menos algunas descargas.

Salida esperada:
```
PROJECT_ROOT: /ruta/al/proyecto
RAW_DIR: .../producto=diarios_txt
OUT_DIR: .../interim/organized/estado=sin

Encontrados 168 archivos crudos en: ...

[OK] Estación 25001: 23011 filas, años=63
[FAIL] dia25099.txt: No encontré encabezado de tabla 'FECHA'
...
Listo
Índice generado en: .../estado=sin/_index.csv
```

### 3. Ejecutar los notebooks de análisis

Los notebooks deben ejecutarse en el siguiente orden, ya que cada uno depende de que el dataset esté organizado en `data/interim/`:

```bash
jupyter notebook eda_general_sinaloa.ipynb
jupyter notebook analisis_valores_faltantes.ipynb
jupyter notebook analisis_temporal_estacional.ipynb
```

> Antes de ejecutar cada notebook, actualiza la variable `PROJECT_ROOT` con la ruta local de tu proyecto:
> ```python
> PROJECT_ROOT = Path(r"ruta/a/tu/proyecto")
> ```

---

## Fuentes de datos

- [Sinaloa — Mendeley Data](https://data.mendeley.com/datasets/gb8jp62vm5/4)
- [CONAGUA / SMN — Información estadística climatológica](https://smn.conagua.gob.mx/es/climatologia/informacion-climatologica/informacion-estadistica-climatologica)

---

## Documentación técnica

El diseño completo del sistema está documentado en el Documento de Arquitectura de Software (DAS) v4.0, que incluye requerimientos funcionales y no funcionales, decisiones arquitectónicas, modelo de datos relacional y metodología detallada bajo CRISP-ML(Q).

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
