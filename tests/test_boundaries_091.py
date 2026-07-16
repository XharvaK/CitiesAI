"""Boundary honesty tests for 0.9.1 tighten."""

from __future__ import annotations

from pathlib import Path

from citiesai.snapshot import load_snapshot_safe
from citiesai.tool_registry import execute_registered_tool, parse_tool_arguments


def test_parse_tool_arguments_rejects_bad_json() -> None:
    err = parse_tool_arguments("{not-json")
    assert isinstance(err, str)
    assert "invalid JSON" in err


def test_parse_tool_arguments_rejects_non_object() -> None:
    err = parse_tool_arguments("[]")
    assert isinstance(err, str)
    assert "JSON object" in err


def test_parse_tool_arguments_accepts_object() -> None:
    assert parse_tool_arguments('{"query": "roads"}') == {"query": "roads"}
    assert parse_tool_arguments({"group": "City"}) == {"group": "City"}


def test_execute_registered_tool_requires_query() -> None:
    result = execute_registered_tool("search_wiki", {}, snapshot={})
    assert "missing required" in result


def test_load_snapshot_safe_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    path.write_text("[]", encoding="utf-8")
    snapshot, err = load_snapshot_safe(path)
    assert snapshot is None
    assert err is not None
    assert "object" in err.lower()


def test_load_snapshot_safe_accepts_object(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    path.write_text('{"City": {"CityName": "Test"}}', encoding="utf-8")
    snapshot, err = load_snapshot_safe(path)
    assert err is None
    assert snapshot is not None
    assert snapshot["City"]["CityName"] == "Test"


def test_schema_md_matches_runtime_version() -> None:
    root = Path(__file__).resolve().parents[1]
    schema_md = (root / "vendor/Cities2-DataExport/SCHEMA.md").read_text(encoding="utf-8")
    sample = (root / "vendor/Cities2-DataExport/sample/latest.sample.json").read_text(
        encoding="utf-8"
    )
    assert "Schema version: `2.12.0`" in schema_md
    assert '"schema_version": "2.12.0"' in sample
