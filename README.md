# Reconstrucción de Base de Datos Hidrometeorológica con IA

Sistema para imputar valores faltantes en registros históricos de estaciones climatológicas de Sinaloa, a partir de datos oficiales del **SMN/CONAGUA**, mediante técnicas de Inteligencia Artificial. El proyecto construye un pipeline reproducible y trazable desde la descarga de datos crudos hasta la generación de una base reconstruida y validada.

> Proyecto de Residencias Profesionales — Laboratorio de Geomática y Teledetección  
> Estado: **En desarrollo** | Sprint actual: 3

---

## ¿Qué problema resuelve?

Las bases de datos hidrometeorológicas históricas presentan valores faltantes, discontinuidades e inconsistencias causadas por fallas instrumentales, mantenimiento de estaciones o errores de transmisión. Esto compromete análisis hidrológicos, modelos climáticos y la detección de eventos extremos.

Este proyecto reconstruye esas series comparando modelos estadísticos clásicos contra técnicas de aprendizaje profundo especializadas en imputación de series temporales, garantizando trazabilidad completa de cada valor reconstruido.

---

## Estado del proyecto

| Módulo | Estado |
|--------|--------|
| Descarga de datos crudos (CONAGUA/SMN) | Listo |
| Estructuración del dataset (raw → interim) | Listo |
| Análisis exploratorio (EDA) | En desarrollo |
| Preprocesamiento y feature engineering | Pendiente |
| Modelado e imputación | Pendiente |
| Validación estadística / Quality Gate | Pendiente |
| Exportación de base reconstruida | Pendiente |

---

## Estructura del repositorio

```
.
├── Obtencion de Datos Crudos/
│   ├── download_sinaloa_raw_pro.py     # Descarga automática desde SMN/CONAGUA
│   └── README.md
│
├── Estructuracion del Dataset/
│   ├── organize_raw_by_station_year_variable_parquet.py
│   └── README.md
│
├── data/                               # No versionado (.gitignore)
│   ├── raw/
│   │   └── conagua_smn/
│   │       └── estado=sin/
│   │           ├── fuente=normales_climatologicas/
│   │           │   └── producto=diarios_txt/    # dia25001.txt, dia25002.txt ...
│   │           ├── _logs/                       # Manifiestos y logs de descarga
│   │           └── _meta/                       # stations_sin.csv
│   │
│   └── interim/
│       └── organized/
│           └── estado=sin/
│               ├── estacion=25001/
│               │   ├── year=1961/
│               │   │   ├── precip.csv / precip.parquet
│               │   │   ├── evap.csv   / evap.parquet
│               │   │   ├── tmax.csv   / tmax.parquet
│               │   │   └── tmin.csv   / tmin.parquet
│               │   └── ...
│               └── _index.csv                   # Índice global con % de faltantes
│
├── docs/
│   └── img/                            # Diagramas de arquitectura
│
└── README.md
```

---

## Pipeline de datos

El proyecto organiza el procesamiento en capas diferenciadas siguiendo la metodología **CRISP-ML(Q)**:

![Pipeline CRISP-ML(Q)](docs/img/CRISP-ML_Q__Pipeline.jpg)

### Capa raw — Descarga de datos crudos

El script `download_sinaloa_raw_pro.py` automatiza la descarga de archivos `.txt` diarios de estaciones climatológicas de Sinaloa desde el portal del SMN/CONAGUA. Genera un manifiesto de descarga y logs de ejecución para garantizar trazabilidad desde el primer paso.

Fuente:
```
https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/sin/dia{clave}.txt
```

Consulta el [README de Obtencion de Datos Crudos](Obtencion%20de%20Datos%20Crudos/README.md) para instrucciones detalladas.

### Capa interim — Estructuración del dataset

El script `organize_raw_by_station_year_variable_parquet.py` transforma los archivos `.txt` crudos en un dataset estructurado jerárquicamente por estación, año y variable climática. Genera particiones en formato `.csv` y `.parquet`, y produce un índice global `_index.csv` con porcentaje de valores faltantes por archivo.

Variables procesadas: `PRECIP`, `EVAP`, `TMAX`, `TMIN`.

Consulta el [README de Estructuracion del Dataset](Estructuracion%20del%20Dataset/README.md) para instrucciones detalladas.

---

## Arquitectura del sistema

### Vista conceptual

![Arquitectura Conceptual](docs/img/Diagrama_arq_conceptual.jpg)

### Ciclo de vida metodológico — CRISP-ML(Q)

![Metodología CRISP-ML(Q)](docs/img/diagramaCRISP-ML_Q_.jpg)

### Arquitectura de componentes

![Arquitectura de Componentes](docs/img/CRIPS_ML_Q__Diagrama_arq_componentes.jpg)

### Diagrama UML de módulos

![Diagrama UML de Componentes](docs/img/Diagrama_UML_componentes.jpg)

### Modelo de datos

![Diagrama Entidad-Relación](docs/img/Diagrama_ER_drawio.png)

---

## Modelos a implementar

Se compararán tres familias de modelos para determinar cuál preserva mejor la estructura estadística de las series:

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

> Los resultados comparativos entre modelos se publicarán en esta sección al completar la fase de evaluación.

---

## Instalación

### Requisitos

- Python 3.9 o superior

### Pasos

```bash
# Clonar el repositorio
git clone https://github.com/Josegas/Residencias_Imputacion_Generativa_Hidrometeorologica.git
cd Residencias_Imputacion_Generativa_Hidrometeorologica

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install pandas pyarrow
```

Los scripts de descarga no requieren dependencias externas, solo la biblioteca estándar de Python.

---

## Uso rápido

### 1. Descarga de datos crudos

```bash
cd "Obtencion de Datos Crudos"
python download_sinaloa_raw_pro.py
```

Descarga los archivos `.txt` de todas las estaciones de Sinaloa en `data/raw/`.

### 2. Estructuración del dataset

```bash
cd "Estructuracion del Dataset"
python organize_raw_by_station_year_variable_parquet.py
```

Transforma los archivos crudos en particiones organizadas por estación, año y variable en `data/interim/`.

> Antes de ejecutar cualquier script, actualiza la variable `PROJECT_ROOT` dentro del archivo con la ruta local de tu proyecto.

---

## Fuentes de datos

- [Sinaloa — Mendeley Data](https://data.mendeley.com/datasets/gb8jp62vm5/4)
- [CONAGUA / SMN — Información estadística climatológica](https://smn.conagua.gob.mx/es/climatologia/informacion-climatologica/informacion-estadistica-climatologica)

---

## Documentación técnica

El diseño completo del sistema está documentado en el Documento de Arquitectura de Software (DAS) v4.0, que incluye requerimientos, decisiones arquitectónicas, modelo de datos y metodología detallada.

---

## Autores

| Nombre | GitHub |
|--------|--------|
| José Ángel García Pérez | [@Josegas](https://github.com/Josegas) |
| Sebastián Verdugo Bermúdez | [@Sebastian1247](https://github.com/Sebastian1247) |

**Laboratorio de Geomática y Teledetección**
