# Diccionario de Datos

## Proyecto: Reconstrucción de una Base de Datos Hidrometeorológica a partir de técnicas de Inteligencia Artifical para el laboratorio de Geomática y Teledetección

**Fuente:** CONAGUA – Servicio Meteorológico Nacional
**Estado:** Sinaloa
**Producto:** Registro Diario Histórico

---

# 1. Descripción General

El presente diccionario documenta las variables resultantes del proceso de organización de los datos climatológicos diarios provenientes de la Base de Datos Climatológica Nacional.

Los datos fueron estructurados jerárquicamente por:

- Estación
- Año
- Variable climática

Cada archivo por variable contiene dos columnas: `date` y `value`.

---

# 2. Variables de los Archivos por Variable (precip, evap, tmax, tmin)

## 2.1 date

| Atributo           | Descripción                                         |
| ------------------ | ---------------------------------------------------- |
| Nombre de variable | date                                                 |
| Tipo de dato       | Fecha (datetime)                                     |
| Formato            | YYYY-MM-DD                                           |
| Unidad             | No aplica                                            |
| Descripción       | Fecha calendario correspondiente al registro diario. |
| Fuente original    | Columna FECHA del archivo oficial SMN                |
| Ejemplo            | 1961-01-01                                           |

---

## 2.2 value

| Atributo           | Descripción                                                                   |
| ------------------ | ------------------------------------------------------------------------------ |
| Nombre de variable | value                                                                          |
| Tipo de dato       | Numérico (float)                                                              |
| Unidad             | Depende de la variable                                                         |
| Valores faltantes  | NaN (convertido desde "NULO")                                                  |
| Descripción       | Valor observado de la variable climática correspondiente a la fecha indicada. |

---

# 3. Variables Climáticas Incluidas

## 3.1 precip

| Campo           | Valor                            |
| --------------- | -------------------------------- |
| Nombre original | PRECIP                           |
| Descripción    | Precipitación acumulada diaria  |
| Unidad          | Milímetros (mm)                 |
| Tipo            | Numérico (float)                |
| Rango esperado  | ≥ 0                             |
| Observaciones   | Puede contener valores faltantes |

---

## 3.2 evap

| Campo           | Valor                                              |
| --------------- | -------------------------------------------------- |
| Nombre original | EVAP                                               |
| Descripción    | Evaporación diaria medida en tanque evaporímetro |
| Unidad          | Milímetros (mm)                                   |
| Tipo            | Numérico (float)                                  |
| Observaciones   | Puede contener valores faltantes                   |

---

## 3.3 tmax

| Campo           | Valor                                 |
| --------------- | ------------------------------------- |
| Nombre original | TMAX                                  |
| Descripción    | Temperatura máxima diaria registrada |
| Unidad          | Grados Celsius (°C)                  |
| Tipo            | Numérico (float)                     |
| Observaciones   | Puede contener valores faltantes      |

---

## 3.4 tmin

| Campo           | Valor                                 |
| --------------- | ------------------------------------- |
| Nombre original | TMIN                                  |
| Descripción    | Temperatura mínima diaria registrada |
| Unidad          | Grados Celsius (°C)                  |
| Tipo            | Numérico (float)                     |
| Observaciones   | Puede contener valores faltantes      |

---

# 4. Diccionario del Archivo \_index.csv

Este archivo consolida metadatos del proceso de organización.

## 4.1 station

| Atributo     | Descripción                                                    |
| ------------ | --------------------------------------------------------------- |
| Tipo         | Entero                                                          |
| Unidad       | No aplica                                                       |
| Descripción | Clave oficial de estación climatológica asignada por CONAGUA. |
| Ejemplo      | 25001                                                           |

---

## 4.2 year

| Atributo     | Descripción                                                   |
| ------------ | -------------------------------------------------------------- |
| Tipo         | Entero                                                         |
| Unidad       | Año calendario                                                |
| Descripción | Año correspondiente a los registros contenidos en el archivo. |
| Ejemplo      | 1961                                                           |

---

## 4.3 variable

| Atributo           | Descripción                                    |
| ------------------ | ----------------------------------------------- |
| Tipo               | Texto                                           |
| Valores permitidos | precip, evap, tmax, tmin                        |
| Descripción       | Variable climática correspondiente al archivo. |

---

## 4.4 path_parquet

| Atributo     | Descripción                                             |
| ------------ | -------------------------------------------------------- |
| Tipo         | Texto                                                    |
| Descripción | Ruta absoluta del archivo almacenado en formato Parquet. |

---

## 4.5 path_csv

| Atributo     | Descripción                                         |
| ------------ | ---------------------------------------------------- |
| Tipo         | Texto                                                |
| Descripción | Ruta absoluta del archivo almacenado en formato CSV. |

---

## 4.6 rows

| Atributo     | Descripción                                                                 |
| ------------ | ---------------------------------------------------------------------------- |
| Tipo         | Entero                                                                       |
| Descripción | Número total de registros diarios contenidos en el archivo correspondiente. |

---

## 4.7 missing_pct

| Atributo     | Descripción                                                                    |
| ------------ | ------------------------------------------------------------------------------- |
| Tipo         | Numérico (float)                                                               |
| Unidad       | Porcentaje (%)                                                                  |
| Rango        | 0 – 100                                                                        |
| Descripción | Porcentaje de valores faltantes en la variable correspondiente dentro del año. |

---

# 5. Tratamiento de Valores Faltantes

Los valores originales etiquetados como "NULO" en los archivos oficiales fueron convertidos a valores nulos estándar (NaN) durante el proceso de transformación, permitiendo su manejo adecuado en análisis estadístico y modelado.

---

# 6. Consideraciones Técnicas

- Los archivos se almacenan en formato CSV y Parquet.
- Parquet es utilizado para procesamiento eficiente y modelado.
- CSV se mantiene para compatibilidad e inspección manual.
- La estructura sigue convenciones tipo key=value para facilitar escalabilidad.

---
