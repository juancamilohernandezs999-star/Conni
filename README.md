# Conni · Gestión de Personas

Prototipo de una aplicación Streamlit para explorar dos módulos:

1. **Planta y vacaciones:** planta autorizada, ocupación, vacantes, ONC y pasivo vacacional.
2. **Perfil sociodemográfico:** edad, género, transporte, distancia, desplazamiento y mascotas.

La aplicación abre con datos sintéticos. Al cargar `Maestro_Databricks.xlsx`, procesa el libro en memoria y sustituye la demostración por los resultados reales.

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
5. Cuando la aplicación abra, carga manualmente `Maestro_Databricks.xlsx` desde la barra lateral.

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
