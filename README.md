# Conni · Inteligencia de Talento

Prototipo de una aplicación Streamlit para explorar dos módulos:

1. **Planta y vacaciones:** planta autorizada, ocupación, vacantes, ONC y pasivo vacacional.
2. **Perfil sociodemográfico:** edad, género, transporte, distancia, desplazamiento y mascotas.

La aplicación abre sin cifras precargadas. Sus cuatro ventanas son `Inicio`, `Carga de información`, `Planta y vacaciones` y `Perfil sociodemográfico`; las dos ventanas analíticas se habilitan únicamente después de validar `Maestro_Databricks.xlsx`.

La ventana de Inicio conserva únicamente la experiencia visual de entrada. La carga y el diagnóstico de la fuente viven en una ventana independiente para que el acceso ejecutivo permanezca limpio.

### Organización de los tableros

Los controles se mantienen horizontales en escritorio: navegación principal, categorías, tres filtros y seis KPIs. Para evitar una página excesivamente larga, cada tablero se divide en tres lecturas:

- **Planta y vacaciones:** Resumen gerencial, Estructura de planta y Vacaciones.
- **Perfil sociodemográfico:** Perfil general, Movilidad y Entorno personal.

El propósito y alcance de cada ventana analítica se encuentran contraídos en `Ver propósito, alcance y forma de lectura`; se despliegan únicamente cuando el usuario necesita contexto.

### ¿De dónde salen los datos?

- Sin archivo cargado, la aplicación conserva un estado vacío y no muestra indicadores de ejemplo.
- Al cargar el maestro, Streamlit entrega sus bytes a la aplicación, valida las tres hojas y las convierte en DataFrames de Pandas.
- El resultado real se conserva en `st.session_state`, es decir, en la memoria de esa sesión. El código no escribe el Excel en el repositorio ni en una carpeta del proyecto.
- Al cerrar o reiniciar la sesión o el servicio, esa información deja de estar disponible y el archivo debe cargarse nuevamente.
- En Streamlit Community Cloud el procesamiento sucede en sus servidores. No se debe cargar información real en una publicación pública; el maestro corporativo requiere un entorno autorizado.

La definición completa de hojas, llaves, indicadores, controles y evolución está en [`LOGICA_NEGOCIO.md`](LOGICA_NEGOCIO.md).

## Ejecutar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

En macOS/Linux, activa el entorno con `source .venv/bin/activate`.

## Publicar desde GitHub en Streamlit Community Cloud

1. Crea un repositorio vacío en GitHub.
2. Sube únicamente el contenido de esta carpeta.
3. No subas archivos Excel reales; `.gitignore` los bloquea.
4. En Streamlit Community Cloud selecciona el repositorio y usa `app.py` como archivo principal.
5. Cuando la aplicación abra, entra a `Carga de información` y carga manualmente `Maestro_Databricks.xlsx`.

## Contrato del archivo cargado

El libro debe contener estas hojas:

- `01_SRC_SOCIODEMO`
- `02_SRC_PERSONAL`
- `03_SRC_CORREOS`

Las llaves se convierten a texto y los períodos se derivan de `Mes` + `Año`, con `Per_Info` como respaldo.

## Seguridad

- Los datos cargados se procesan en memoria.
- Los dashboards solo presentan agregados.
- El repositorio no contiene datos personales.
- La descarga analítica excluye nombres, documentos, correos y fechas de nacimiento.
- Para una publicación real se deben añadir autenticación, autorización por rol y política de retención.

## Preparación para Databricks

`app.yaml` contiene el comando de inicio esperado por una futura Databricks App. La capa `src/conni` está separada de Streamlit para que después pueda leer tablas Gold en lugar de un Excel cargado manualmente.

La evolución prevista es:

```text
Excel manual → Tablas Gold → Databricks App → explicación IA/voz
```

La IA deberá recibir únicamente métricas agregadas; Databricks seguirá siendo responsable de calcular y validar los indicadores.
