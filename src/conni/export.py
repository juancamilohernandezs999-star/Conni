from __future__ import annotations

from io import BytesIO

import pandas as pd

from .data import ConniData
from .metrics import (
    gender_by_area,
    plant_by_area,
    plant_metrics,
    quality_summary,
    socio_metrics,
    vacation_by_area,
)


def analytics_workbook(data: ConniData) -> bytes:
    """Return an aggregate-only workbook safe for management circulation."""
    periods = sorted(data.personal["period"].dropna().unique())
    summary_rows = []
    plant_areas = []
    vacation_areas = []
    gender_areas = []
    socio_rows = []
    for period in periods:
        p = data.personal.loc[data.personal["period"].eq(period)]
        s = data.sociodemo.loc[data.sociodemo["period"].eq(period)]
        pm = plant_metrics(p)
        sm = socio_metrics(s)
        summary_rows.append({"Periodo": period, **pm})
        socio_rows.append({"Periodo": period, **sm})
        for table, target in (
            (plant_by_area(p), plant_areas),
            (vacation_by_area(p), vacation_areas),
            (gender_by_area(p), gender_areas),
        ):
            if not table.empty:
                block = table.copy()
                block.insert(0, "Periodo", period)
                target.append(block)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="RESUMEN_PLANTA", index=False)
        pd.DataFrame(socio_rows).to_excel(writer, sheet_name="RESUMEN_SOCIO", index=False)
        (pd.concat(plant_areas, ignore_index=True) if plant_areas else pd.DataFrame()).to_excel(
            writer, sheet_name="PLANTA_AREA", index=False
        )
        (pd.concat(vacation_areas, ignore_index=True) if vacation_areas else pd.DataFrame()).to_excel(
            writer, sheet_name="PASIVO_AREA", index=False
        )
        (pd.concat(gender_areas, ignore_index=True) if gender_areas else pd.DataFrame()).to_excel(
            writer, sheet_name="GENERO_AREA", index=False
        )
        quality_summary(data).to_excel(writer, sheet_name="CONTROL_CALIDAD", index=False)
    return output.getvalue()
