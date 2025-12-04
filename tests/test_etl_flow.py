"""Integration tests for the ETL demo application.

Validates: Requirements 9.1 - Complete data pipeline execution
"""

from necrostack.apps.etl.organs import (
    CleanData,
    ExportSummary,
    ExtractCSV,
    TransformData,
)
from necrostack.core.event import Event

SAMPLE_CSV = """name,age,salary
Alice,30,75000
Bob,25,55000
Charlie,35,85000
"""


def test_extract_csv_organ():
    """Test ExtractCSV organ parses CSV data correctly."""
    organ = ExtractCSV()

    event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": SAMPLE_CSV,
            "source_name": "test.csv",
        },
    )

    result = organ.handle(event)

    assert result.event_type == "RAW_DATA_LOADED"
    assert result.payload["source_name"] == "test.csv"
    assert result.payload["row_count"] == 3
    assert result.payload["headers"] == ["name", "age", "salary"]
    assert len(result.payload["records"]) == 3
    assert result.payload["records"][0]["name"] == "Alice"


def test_clean_data_organ():
    """Test CleanData organ removes rows with empty values."""
    organ = CleanData()

    event = Event(
        event_type="RAW_DATA_LOADED",
        payload={
            "source_name": "test.csv",
            "headers": ["name", "age"],
            "records": [
                {"name": "Alice", "age": "30"},
                {"name": "Bob", "age": ""},  # Empty age
                {"name": "Charlie", "age": "35"},
            ],
        },
    )

    result = organ.handle(event)

    assert result.event_type == "DATA_CLEANED"
    assert result.payload["row_count"] == 2
    assert result.payload["removed_count"] == 1
    # Bob should be removed (names are lowercased by CleanData)
    names = [r["name"] for r in result.payload["records"]]
    assert "bob" not in names
    assert "alice" in names
    assert "charlie" in names


def test_transform_data_organ():
    """Test TransformData organ computes statistics correctly."""
    organ = TransformData()

    event = Event(
        event_type="DATA_CLEANED",
        payload={
            "source_name": "test.csv",
            "headers": ["name", "value"],
            "records": [
                {"name": "A", "value": "10"},
                {"name": "B", "value": "20"},
                {"name": "C", "value": "30"},
            ],
        },
    )

    result = organ.handle(event)

    assert result.event_type == "DATA_TRANSFORMED"
    assert "numeric_stats" in result.payload
    assert "value" in result.payload["numeric_stats"]

    stats = result.payload["numeric_stats"]["value"]
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0
    assert stats["sum"] == 60.0
    assert stats["avg"] == 20.0


def test_export_summary_organ():
    """Test ExportSummary organ produces correct output."""
    outputs = []
    organ = ExportSummary(output_callback=outputs.append)

    event = Event(
        event_type="DATA_TRANSFORMED",
        payload={
            "source_name": "test.csv",
            "headers": ["name", "value"],
            "records": [{"name": "A", "value": "10"}],
            "row_count": 1,
            "numeric_stats": {"value": {"min": 10.0, "max": 10.0, "sum": 10.0, "avg": 10.0}},
        },
    )

    result = organ.handle(event)

    # ExportSummary emits ETL_COMPLETE to signal completion
    assert result is not None
    assert result.event_type == "ETL_COMPLETE"
    assert result.payload["source_name"] == "test.csv"
    assert result.payload["row_count"] == 1
    assert len(outputs) == 1
    assert "ETL Summary" in outputs[0]
    assert "test.csv" in outputs[0]
    assert "Total rows processed: 1" in outputs[0]


def test_etl_complete_chain():
    """Test complete ETL chain by manually passing events through organs."""
    outputs = []

    # Create organs
    extract = ExtractCSV()
    clean = CleanData()
    transform = TransformData()
    export = ExportSummary(output_callback=outputs.append)

    # Start event
    start_event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": SAMPLE_CSV,
            "source_name": "test.csv",
        },
    )

    # Run through chain
    raw_event = extract.handle(start_event)
    assert raw_event.event_type == "RAW_DATA_LOADED"

    cleaned_event = clean.handle(raw_event)
    assert cleaned_event.event_type == "DATA_CLEANED"

    transformed_event = transform.handle(cleaned_event)
    assert transformed_event.event_type == "DATA_TRANSFORMED"

    result = export.handle(transformed_event)
    # ExportSummary emits ETL_COMPLETE to signal completion
    assert result is not None
    assert result.event_type == "ETL_COMPLETE"

    # Verify final output
    assert len(outputs) == 1
    output = outputs[0]
    assert "ETL Summary" in output
    assert "test.csv" in output
    assert "Total rows processed: 3" in output


def test_etl_chain_with_dirty_data():
    """Test ETL chain correctly cleans dirty data."""
    outputs = []

    csv_with_empty = """name,age,salary
Alice,30,75000
Bob,,55000
Charlie,35,85000
"""

    extract = ExtractCSV()
    clean = CleanData()
    transform = TransformData()
    export = ExportSummary(output_callback=outputs.append)

    start_event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": csv_with_empty,
            "source_name": "dirty.csv",
        },
    )

    raw = extract.handle(start_event)
    cleaned = clean.handle(raw)
    transformed = transform.handle(cleaned)
    export.handle(transformed)

    assert len(outputs) == 1
    assert "Total rows processed: 2" in outputs[0]


def test_etl_empty_csv():
    """Test ETL chain handles empty CSV gracefully."""
    outputs = []

    extract = ExtractCSV()
    clean = CleanData()
    transform = TransformData()
    export = ExportSummary(output_callback=outputs.append)

    start_event = Event(
        event_type="ETL_START",
        payload={
            "csv_data": "",
            "source_name": "empty.csv",
        },
    )

    raw = extract.handle(start_event)
    cleaned = clean.handle(raw)
    transformed = transform.handle(cleaned)
    export.handle(transformed)

    assert len(outputs) == 1
    assert "Total rows processed: 0" in outputs[0]
