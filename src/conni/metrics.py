from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .data import ConniData, normalize_label


AREA_FALLBACK = "Sin clasificación"
QUALITY_PRIORITY_ORDER = {"Crítico": 0, "Alto": 1, "Medio": 2, "Informativo": 3}


def text_contains(series: pd.Series, pattern: str) -> pd.Series:
    return series.fillna("").map(normalize_label).str.contains(pattern, regex=True)


def filter_period_and_area(
    data: ConniData,
    period: str,
    strategies: list[str] | None = None,
    organizations: list[str] | None = None,
) -> ConniData:
    def apply(frame: pd.DataFrame) -> pd.DataFrame:
        filtered = frame.loc[frame["period"].eq(period)].copy() if "period" in frame else frame.copy()
        if strategies and "strategy" in filtered:
            filtered = filtered.loc[filtered["strategy"].isin(strategies)]
        if organizations and "organization" in filtered:
            filtered = filtered.loc[filtered["organization"].isin(organizations)]
        return filtered.reset_index(drop=True)

    personal = apply(data.personal)
    socio = apply(data.sociodemo)
    survey = data.encuesta.copy()
    if "period" in survey and survey["period"].notna().any():
        survey = survey.loc[survey["period"].isna() | survey["period"].eq(period)].copy()
    return ConniData(personal, socio, survey, data.source_name, data.is_demo)


def plant_metrics(personal: pd.DataFrame) -> dict[str, float | int]:
    positions = personal.loc[personal["position_id"].notna()].copy()
    authorized = int(positions["position_id"].nunique())
    occupied = int(positions.loc[positions["is_occupied"], "position_id"].nunique())
    vacant = positions["is_vacant"]
    onc = int(positions.loc[vacant & positions["onc_flag"], "position_id"].nunique())
    available = int(positions.loc[vacant & ~positions["onc_flag"], "position_id"].nunique())
    approval = positions["approval_reason"].fillna("").map(normalize_label)
    practitioners = int(positions.loc[approval.str.contains("practica"), "position_id"].nunique())
    siso = int(positions.loc[approval.str.contains("siso"), "position_id"].nunique())
    need_service = int(positions.loc[approval.str.contains("necesidad.*servicio", regex=True), "position_id"].nunique())
    occupied_rows = positions.loc[positions["is_occupied"]]
    return {
        "authorized": authorized,
        "occupied": occupied,
        "coverage": occupied / authorized if authorized else 0.0,
        "vacant": available,
        "onc": onc,
        "practitioners": practitioners,
        "siso": siso,
        "need_service": need_service,
        "vacation_days": float(occupied_rows["vacation_days"].fillna(0).sum()),
        "vacation_days_net": float(occupied_rows["vacation_days_net"].fillna(0).sum()),
    }


def plant_by_area(personal: pd.DataFrame) -> pd.DataFrame:
    df = personal.copy()
    df["area"] = df["strategy"].fillna(df["organization"]).fillna(AREA_FALLBACK)
    grouped = []
    for area, group in df.groupby("area", dropna=False):
        metrics = plant_metrics(group)
        grouped.append(
            {
                "Área": area,
                "Autorizada": metrics["authorized"],
                "Ocupada": metrics["occupied"],
                "Vacantes": metrics["vacant"],
                "ONC": metrics["onc"],
            }
        )
    return pd.DataFrame(grouped).sort_values("Autorizada", ascending=False)


def gender_by_area(personal: pd.DataFrame) -> pd.DataFrame:
    occupied = personal.loc[personal["is_occupied"]].copy()
    occupied["Área"] = occupied["strategy"].fillna(occupied["organization"]).fillna(AREA_FALLBACK)
    occupied["Género"] = occupied["gender"].fillna("Sin información")
    return (
        occupied.groupby(["Área", "Género"], dropna=False)["person_id"]
        .nunique()
        .rename("Personas")
        .reset_index()
    )


def vacation_by_area(personal: pd.DataFrame) -> pd.DataFrame:
    occupied = personal.loc[personal["is_occupied"]].copy()
    occupied["Área"] = occupied["strategy"].fillna(occupied["organization"]).fillna(AREA_FALLBACK)
    return (
        occupied.groupby("Área", dropna=False)
        .agg(
            **{
                "Días pasivo real": ("vacation_days", "sum"),
                "Días pasivo depurado": ("vacation_days_net", "sum"),
                "Personas": ("person_id", "nunique"),
            }
        )
        .reset_index()
        .sort_values("Días pasivo real", ascending=False)
    )


def vacation_period_distribution(personal: pd.DataFrame) -> pd.DataFrame:
    occupied = personal.loc[personal["is_occupied"]].copy()
    periods = occupied["vacation_periods"].fillna(0).round().clip(lower=0, upper=4).astype(int)
    occupied["Periodos"] = periods.map(lambda value: f"{value} per." if value < 4 else "4+ per.")
    order = ["0 per.", "1 per.", "2 per.", "3 per.", "4+ per."]
    result = occupied.groupby("Periodos")["person_id"].nunique().reindex(order, fill_value=0)
    return result.rename("Personas").reset_index()


def commute_minutes(value: object) -> float:
    if value is None or pd.isna(value):
        return np.nan
    text = normalize_label(value)
    numbers = [float(x) for x in re.findall(r"\d+(?:[.,]\d+)?", text.replace(",", "."))]
    if not numbers:
        return np.nan
    if len(numbers) >= 2:
        return float(sum(numbers[:2]) / 2)
    return numbers[0]


def socio_metrics(socio: pd.DataFrame) -> dict[str, float | int | str]:
    population = int(socio["person_id"].nunique())
    age = pd.to_numeric(socio["age"], errors="coerce")
    valid_age = age.where(age.between(16, 80, inclusive="both"))
    transport = socio["transport"].fillna("").map(normalize_label)
    public = transport.str.contains("public")
    commute = socio["commute_range"].map(commute_minutes)
    distance = socio["distance_range"].dropna()
    predominant_distance = distance.mode().iloc[0] if not distance.mode().empty else "Sin información"
    return {
        "population": population,
        "average_age": float(valid_age.mean()) if valid_age.notna().any() else np.nan,
        "min_age": float(valid_age.min()) if valid_age.notna().any() else np.nan,
        "max_age": float(valid_age.max()) if valid_age.notna().any() else np.nan,
        "public_transport": float(public.sum() / population) if population else 0.0,
        "average_commute": float(commute.mean()) if commute.notna().any() else np.nan,
        "commute_reported": int(commute.notna().sum()),
        "predominant_distance": str(predominant_distance),
    }


def categorical_count(socio: pd.DataFrame, column: str, label: str) -> pd.DataFrame:
    values = socio[column].fillna("Sin información")
    return (
        pd.DataFrame({label: values, "person_id": socio["person_id"]})
        .groupby(label, dropna=False)["person_id"]
        .nunique()
        .rename("Personas")
        .reset_index()
        .sort_values("Personas", ascending=False)
    )


def quality_summary(data: ConniData) -> pd.DataFrame:
    personal = data.personal
    socio = data.sociodemo
    survey = data.encuesta
    duplicate_positions = int(personal.duplicated(["period", "position_id"], keep=False).sum())
    duplicate_people = int(
        personal.loc[personal["person_id"].notna()].duplicated(["period", "person_id"], keep=False).sum()
    )
    duplicate_socio = int(socio.duplicated(["period", "person_id"], keep=False).sum())
    duplicate_docs = int(survey.loc[survey["document_id"].notna()].duplicated("document_id", keep=False).sum())
    return pd.DataFrame(
        [
            ("Posiciones duplicadas por período", duplicate_positions, "Crítico"),
            ("Personas duplicadas en Personal", duplicate_people, "Crítico"),
            ("Personas duplicadas en Sociodemo", duplicate_socio, "Crítico"),
            ("Documentos duplicados en Encuesta", duplicate_docs, "Alto"),
            ("Posiciones sin persona", int(personal["person_id"].isna().sum()), "Informativo"),
            ("Personas sin documento", int(personal.loc[personal["person_id"].notna(), "document_id"].isna().sum()), "Alto"),
            ("Fechas de nacimiento vacías", int(socio["birth_date"].isna().sum()), "Medio"),
            ("Encuestas sin período", int(survey["period"].isna().sum()), "Alto"),
            ("Conflictos indicador vacante", int(personal["vacancy_flag_conflict"].sum()), "Medio"),
        ],
        columns=["Control", "Registros", "Prioridad"],
    )


def classify_quality_controls(summary: pd.DataFrame) -> dict[str, pd.DataFrame | int]:
    """Split a quality summary into active, actionable, and clean controls.

    The input is left untouched so ``quality_summary`` can retain its public
    three-column contract. Returned frames add presentation-only fields:
    ``ConResultado`` and ``Estado``.
    """
    required = {"Control", "Registros", "Prioridad"}
    missing = required.difference(summary.columns)
    if missing:
        missing_labels = ", ".join(sorted(missing))
        raise ValueError(f"Faltan columnas requeridas para clasificar calidad: {missing_labels}")

    classified = summary.copy()
    classified["Registros"] = pd.to_numeric(classified["Registros"], errors="coerce").fillna(0).astype(int)
    classified["ConResultado"] = classified["Registros"].gt(0)

    has_result = classified["ConResultado"]
    classified["Estado"] = np.select(
        [
            ~has_result,
            classified["Prioridad"].eq("Informativo"),
            classified["Prioridad"].eq("Medio"),
            classified["Prioridad"].isin(["Crítico", "Alto"]),
        ],
        ["Sin hallazgos", "Contexto", "Revisar", "Acción prioritaria"],
        default="Revisar",
    )
    classified["_priority_rank"] = (
        classified["Prioridad"].map(QUALITY_PRIORITY_ORDER).fillna(len(QUALITY_PRIORITY_ORDER)).astype(int)
    )

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return (
            frame.sort_values(["_priority_rank", "Registros"], ascending=[True, False])
            .drop(columns="_priority_rank")
            .reset_index(drop=True)
        )

    active = ordered(classified.loc[has_result])
    clear = ordered(classified.loc[~has_result])
    actionable = active.loc[active["Prioridad"].ne("Informativo")].reset_index(drop=True)
    return {
        "active": active,
        "clear": clear,
        "actionable": actionable,
        "total": int(len(classified)),
        "active_count": int(len(active)),
        "clean_count": int(len(clear)),
        "action_count": int(len(actionable)),
    }
