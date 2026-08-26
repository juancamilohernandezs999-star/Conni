import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conni.data import demo_data
from conni.metrics import filter_period_and_area, plant_metrics, quality_summary, socio_metrics


def test_plant_equation_reconciles():
    data = demo_data()
    filtered = filter_period_and_area(data, "2026-07")
    metrics = plant_metrics(filtered.personal)
    assert metrics["authorized"] == metrics["occupied"] + metrics["vacant"] + metrics["onc"]
    assert 0 < metrics["coverage"] < 1


def test_socio_metrics_have_expected_ranges():
    data = demo_data()
    filtered = filter_period_and_area(data, "2026-07")
    metrics = socio_metrics(filtered.sociodemo)
    assert metrics["population"] > 0
    assert 18 <= metrics["average_age"] <= 65
    assert 0 <= metrics["public_transport"] <= 1


def test_quality_summary_never_exposes_pii_columns():
    summary = quality_summary(demo_data())
    assert list(summary.columns) == ["Control", "Registros", "Prioridad"]

