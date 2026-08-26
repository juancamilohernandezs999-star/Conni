# Lógica de negocio de Conni

Este documento explica qué lee la aplicación, cómo calcula cada indicador y qué debe mantenerse cuando la solución migre a Databricks.

## 1. Qué representa cada hoja

### `02_SRC_PERSONAL`

Es el inventario histórico de la planta. Su nivel correcto es **una fila por período + posición**. Una posición puede estar ocupada o vacante; por eso no se debe eliminar una fila solo porque no tenga número de persona.

Campos centrales:

- `Mes` + `Año`: período mensual de análisis.
- `ID Posición`: identificador de la posición y base para contar la planta.
- `Vacante`: fuente oficial para decidir si la posición está vacante.
- `Orden de No Cubrir`: separa las vacantes disponibles de las posiciones ONC.
- `No personal`: identifica a la persona asociada, si existe.
- `Unidad Estratégica` y `Unidad Organizativa`: filtros y agrupaciones.
- `PASIVO VACACIONAL` y `Dias luego de sol.`: pasivo bruto y pasivo después de solicitudes.

### `01_SRC_SOCIODEMO`

Es la caracterización histórica de personas. Su nivel correcto es **una fila por período + persona**. Alimenta edad, género, transporte, distancia, tiempo de desplazamiento y mascotas.

### `03_SRC_CORREOS`

Contiene respuestas de encuesta identificadas por documento. En la primera versión se conserva para controles de calidad; no se mezcla de manera silenciosa con todos los períodos porque 101 respuestas no tienen mes ni año.

## 2. Regla de período y cruces

La llave mensual se construye como `AAAA-MM` usando `Año` + `Mes`. `Per_Info` se conserva como fecha de corte y solo sirve de respaldo cuando el mes o el año están vacíos.

Orden correcto:

1. Seleccionar el período.
2. Filtrar Personal y Sociodemo por ese período.
3. Aplicar filtros de unidad estratégica y unidad organizativa.
4. Calcular cada tablero en su nivel natural.
5. Si después se necesita un cruce detallado, unir Personal y Sociodemo por `período + número personal`.

No se debe cruzar todo el histórico únicamente por persona, porque multiplicaría registros de distintos meses.

## 3. Dashboard Planta y vacaciones

Para un período y filtros seleccionados:

```text
Planta autorizada = posiciones únicas
Planta ocupada    = posiciones únicas con Vacante = falso
Vacantes          = posiciones únicas con Vacante = verdadero y ONC = no
ONC               = posiciones únicas con Vacante = verdadero y ONC = sí
Cobertura         = Planta ocupada / Planta autorizada
```

Control obligatorio:

```text
Planta autorizada = Planta ocupada + Vacantes + ONC
```

`Tipo de Posición` no sustituye al indicador `Vacante`: existen posiciones rotuladas como disponibles que actualmente tienen persona.

Practicantes, SISO y necesidad del servicio son subgrupos de la planta, no componentes adicionales. El pasivo se suma únicamente sobre posiciones ocupadas y valores numéricos válidos; textos como `No base Vac.` se tratan como no disponibles, no como personas con cero días.

### Control validado para julio de 2026

| Indicador | Resultado |
|---|---:|
| Planta autorizada | 433 |
| Planta ocupada | 405 |
| Vacantes disponibles | 23 |
| ONC | 5 |
| Cobertura | 93,5 % |
| Pasivo bruto | 6.920,45 días |
| Pasivo después de solicitudes | 5.945,45 días |

## 4. Dashboard Perfil sociodemográfico

La población es el número de personas únicas del período después de aplicar los filtros. Los vacíos permanecen visibles como `Sin información`; nunca se completan como si fueran una respuesta real.

- Edad promedio, mínima y máxima: valores numéricos válidos de edad.
- Transporte público: personas que reportan transporte público dividido entre toda la población filtrada. Así, los registros sin respuesta permanecen dentro del denominador.
- Tiempo promedio: promedio entre quienes tienen un rango informado. Se usa el punto medio de cada rango y `más de 180 min` se representa como 180 minutos.
- Distancia predominante: categoría de distancia con mayor número de personas.
- El rótulo fuente `18-25` se muestra como `Hasta 25`, porque el maestro contiene una persona de 17 años dentro de esa categoría.

Control validado para julio de 2026:

| Indicador | Resultado |
|---|---:|
| Personas | 405 |
| Mujeres | 243 |
| Hombres | 162 |
| Edad promedio | 35,27 años |
| Transporte público / población total | 59,5 % |
| Registros con tiempo de desplazamiento | 325 |
| Tiempo promedio | 81,69 minutos |

## 5. Calidad, privacidad y descarga

Antes de presentar resultados se controlan duplicados de posición, persona y documento; períodos ausentes; posiciones sin persona; documentos vacíos y conflictos entre `Vacante` y la presencia de una persona.

El archivo cargado se procesa en memoria. La descarga generada por la app contiene únicamente tablas agregadas: no incluye nombres, documentos, correos, teléfonos, direcciones ni fechas de nacimiento.

## 6. Lo que aún falta para paridad total con el Excel original

Los dos dashboards principales se pueden construir con el maestro actual y sus controles ya cuadran. Para reproducir absolutamente todos los detalles históricos de `Tablero_Subdirección.xlsm` todavía conviene formalizar la tabla manual de posiciones especiales y documentar su responsable, vigencia y reglas de actualización.

## 7. Evolución recomendada

```text
Excel cargado manualmente
        ↓
Tablas Bronze / Silver / Gold en Databricks
        ↓
Databricks App con los mismos componentes Streamlit
        ↓
Resumen agregado en JSON
        ↓
Gemini redacta la explicación y una capa TTS genera la voz
```

La IA no debe recalcular los indicadores ni recibir datos personales. Databricks calcula y valida; la IA explica los resultados agregados, sus variaciones y las alertas de calidad.
