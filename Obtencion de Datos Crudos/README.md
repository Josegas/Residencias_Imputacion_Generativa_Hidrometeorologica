# Descarga de datos crudos diarios de CONAGUA para Sinaloa

Este script automatiza la descarga de archivos diarios de estaciones climatológicas del estado de **Sinaloa** desde la fuente oficial del **Servicio Meteorológico Nacional (SMN) / CONAGUA**, como parte de la etapa inicial de ingesta de datos del proyecto de reconstrucción de una base de datos hidrometeorológica mediante técnicas de imputación generativa.

## Objetivo

El propósito del script es construir la capa **raw** del proyecto, descargando los archivos `.txt` diarios de las estaciones meteorológicas de Sinaloa y almacenándolos en una estructura organizada, junto con archivos de metadatos y trazabilidad del proceso.

## Qué hace el script

El script realiza las siguientes tareas:

- Define el estado objetivo como **Sinaloa** (`sin`).
- Construye automáticamente la URL de descarga de cada estación usando su clave oficial.
- Recorre una lista predefinida de estaciones climatológicas de Sinaloa.
- Descarga los archivos diarios en formato `.txt` desde el portal del SMN/CONAGUA.
- Evita volver a descargar archivos que ya existen localmente.
- Genera un archivo de metadatos con la lista de estaciones.
- Registra un manifiesto de descarga con el resultado de cada intento.
- Genera un log de ejecución para auditoría y seguimiento.
- Introduce una pequeña pausa entre descargas para no saturar el servidor.

## Fuente de datos

Los archivos se descargan desde la ruta base:

```text
https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/{estado}/dia{clave}.txt