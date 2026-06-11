"""Shared fixtures and helpers for md-spreadsheet-engine tests."""

from __future__ import annotations

import textwrap

import pytest

from md_spreadsheet_engine.engine import (
    FORMULA_END,
    FORMULA_START,
    MarkDownSpreadsheetEngine,
)


@pytest.fixture
def engine() -> MarkDownSpreadsheetEngine:
    """Provide a fresh, isolated engine instance for each test case."""
    return MarkDownSpreadsheetEngine()


def md(content: str) -> str:
    """Dedent and strip a markdown fixture so table lines start at column zero."""
    return textwrap.dedent(content).strip() + "\n"


def formula_cell(expression: str) -> str:
    """Build a formula comment cell value."""
    return f"{FORMULA_START} {expression} {FORMULA_END}"


def computed_cell(expression: str, value: str | int | float) -> str:
    """Build the expected rendered formula cell after evaluation."""
    return f"{FORMULA_START} {expression} {FORMULA_END} {value}"


def run_document(engine: MarkDownSpreadsheetEngine, doc_name: str, content: str) -> str:
    """Load, evaluate, and regenerate a single markdown document."""
    engine.load_markdown_document(doc_name, content)
    engine.evaluate()
    return engine.regenerate_markdown_document(doc_name)
