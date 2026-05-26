# Guía de Configuración — HydroImpute

Explica en lenguaje sencillo cada parámetro disponible en la pestaña **Configuración** de la app.

---

## ¿Qué puedo configurar?

La página de Configuración expone únicamente los parámetros que tienen sentido ajustar según el dataset o el hardware disponible. Los parámetros estadísticos internos (niveles de significancia, tamaño de ventana del modelo, etc.) están fijos porque cambiarlos sin formación especializada produce resultados incorrectos.

---

## Módulo: Imputación Generativa (Etapa 9)

### Límites físicos

Rango de valores que se consideran físicamente posibles para cada variable.
Cualquier valor imputado fuera de estos rangos se recorta al límite más cercano.

| Variable | Mínimo por defecto | Máximo por defecto |
|----------|-------------------|-------------------|
| Precipitación | 0 mm | 500 mm |
| Evaporación | 0 mm | 60 mm |
| Temperatura máxima | -5 °C | 55 °C |
| Temperatura mínima | -15 °C | 45 °C |

Ajusta estos valores si trabajas con datos de una región distinta a Sinaloa.

### Hardware

| Parámetro | Por defecto | Qué hace | Cuándo cambiarlo |
|-----------|-------------|----------|-----------------|
| Dispositivo de cómputo | `auto` | Elige GPU si está disponible; si no, usa CPU. | Para forzar `cpu` o `cuda` explícitamente. |
| Tamaño de lote (batch_size) | 512 | Cuántas ventanas procesa el modelo a la vez. Más alto = más rápido en GPU. | Si aparece error de memoria en GPU, reduce a 256 o 128. |

### Huecos de datos

| Parámetro | Por defecto | Qué hace | Cuándo cambiarlo |
|-----------|-------------|----------|-----------------|
| Máximo hueco a cubrir (días) | 365 | Huecos consecutivos más largos que este valor se dejan como NaN residuales. | Si tienes estaciones con huecos de más de un año que quieras cubrir, o si prefieres ser más conservador. |

### Información fija del modelo

**Ventana del modelo: 30 días** — este valor está fijado por el entrenamiento de BiGRU-opt y no puede cambiarse desde la interfaz. Modificarlo requeriría reentrenar el modelo completo.

---

## Módulo: Quality Gate (Etapa 8)

### Límites físicos

Igual que en Imputación Generativa. Los registros fuera de estos rangos se marcan como anomalías en el reporte PASS/WARNING/FAIL.

### Umbrales de datos faltantes

A partir de qué porcentaje de faltantes por estación se emite una advertencia WARNING.

| Variable | Umbral por defecto | Nota |
|----------|--------------------|------|
| Precipitación | 60% | — |
| Evaporación | 85% | Alto porque la evaporación tiene faltantes estructurales en muchas estaciones de Sinaloa. |
| Temperatura máxima | 60% | — |
| Temperatura mínima | 60% | — |

Ajusta si trabajas con una región donde la cobertura histórica es muy diferente.

---

## Módulo: Monitoreo del modelo (Etapa 11)

Detecta si la distribución de los datos actuales se aleja del período histórico de referencia (drift).

### Período de referencia climático

| Parámetro | Por defecto | Qué hace | Cuándo cambiarlo |
|-----------|-------------|----------|-----------------|
| Año inicio | 1970 | — | Si necesitas otro período de referencia climático. |
| Año fin | 2000 | El sistema compara cada década contra este rango. | Ídem. El estándar internacional de la OMM es 1970–2000. |

### Cobertura mínima esperada

| Parámetro | Por defecto | Qué hace | Cuándo cambiarlo |
|-----------|-------------|----------|-----------------|
| Cobertura objetivo (%) | 99% | Si la cobertura real cae por debajo, se emite una alerta en el dashboard. | Si aceptas una cobertura menor, por ejemplo en regiones con muchas estaciones discontinuas. |

---

## Módulo: Validación Estadística (Etapa 10)

### Límites físicos

Deben coincidir con los del módulo de Imputación Generativa. Se usan para verificar que los valores post-imputación sean válidos.

### Cobertura mínima esperada

Igual que en Monitoreo. Si la fracción de NaN rellenados cae por debajo de este porcentaje, la etapa marca FAIL.

---

## Regla de oro

> Cambia solo los **Límites físicos** si tienes datos de una región diferente a Sinaloa.
> Los demás parámetros en sus valores por defecto producen los mejores resultados documentados en el proyecto.

---

**Laboratorio de Geomática y Teledetección — TECNM Campus Culiacán**
