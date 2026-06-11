"""Unit tests for MarkDownSpreadsheetEngine."""

from __future__ import annotations

import pytest

from md_spreadsheet_engine.engine import FORMULA_END, FORMULA_START, MarkDownSpreadsheetEngine
from conftest import computed_cell, formula_cell, md, run_document


class TestLocalFormulas:
    def test_basic_arithmetic_and_sum(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} Item | Qty | Price | Total |
            | :--- | :-: | :-: | :--- |
            | Widgets | 5 | 10.00 | {formula_cell('=B1*C1')} |
            | **Sum** | {formula_cell('=SUM(B1:B1)')} | | {formula_cell('=SUM(D1:D1)')} |
            """
        )

        output = run_document(engine, "doc1", content)

        assert computed_cell("=B1*C1", 50) in output
        assert computed_cell("=SUM(B1:B1)", 5) in output
        assert computed_cell("=SUM(D1:D1)", 50) in output

    def test_plain_numeric_cells_are_preserved(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:inventory {FORMULA_END} SKU | Units |
            | :--- | :---: |
            | ABC-001 | 42 |
            """
        )

        output = run_document(engine, "inventory", content)

        assert "ABC-001" in output
        assert "| 42" in output


class TestCrossTableReferences:
    def test_reference_between_tables(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} Val |
            | :--- |
            | 100 |

            | {FORMULA_START} table:t2 {FORMULA_END} Output |
            | :--- |
            | {formula_cell('=t1!A1 + 50')} |
            """
        )

        output = run_document(engine, "doc1", content)

        assert computed_cell("=t1!A1 + 50", 150) in output

    def test_indented_tables_are_split_correctly(self, engine: MarkDownSpreadsheetEngine) -> None:
        """Regression: leading whitespace must not collapse multiple tables into one block."""
        content = (
            f"    | {FORMULA_START} table:t1 {FORMULA_END} Val |\n"
            f"    | :--- |\n"
            f"    | 100 |\n\n"
            f"    | {FORMULA_START} table:t2 {FORMULA_END} Output |\n"
            f"    | :--- |\n"
            f"    | {formula_cell('=t1!A1 + 50')} |\n"
        )

        output = run_document(engine, "doc1", content)

        assert computed_cell("=t1!A1 + 50", 150) in output
        assert len([token for token in engine.document_cache["doc1"] if token["type"] == "table"]) == 2

    def test_interdependent_tables(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} Base Rate | Adjusted Metric |
            | :--- | :--- |
            | 500 | {formula_cell('=t2!B1 * 0.10')} |

            | {FORMULA_START} table:t2 {FORMULA_END} Modifier | Derived Subtotal |
            | :--- | :--- |
            | 2 | {formula_cell('=t1!A1 * A1')} |
            """
        )

        output = run_document(engine, "mutual_doc", content)

        assert computed_cell("=t1!A1 * A1", 1000) in output
        assert computed_cell("=t2!B1 * 0.10", 100) in output

    def test_implicit_table_names(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = md(
            f"""
            | Header A |
            | :--- |
            | 10 |

            | Header B |
            | :--- |
            | {formula_cell('=table_0!A1 * 2')} |
            """
        )

        output = run_document(engine, "doc1", content)

        assert computed_cell("=table_0!A1 * 2", 20) in output


class TestCrossDocumentReferences:
    def test_quoted_doc_table_reference(self, engine: MarkDownSpreadsheetEngine) -> None:
        doc_a = md(
            f"""
            | {FORMULA_START} table:metrics {FORMULA_END} Score |
            | :--- |
            | 85 |
            """
        )
        doc_b = md(
            f"""
            | {FORMULA_START} table:summary {FORMULA_END} Final Calculation |
            | :--- |
            | {formula_cell("= 'main:metrics'!A1 + 15")} |
            """
        )

        engine.load_markdown_document("main", doc_a)
        engine.load_markdown_document("report", doc_b)
        engine.evaluate()
        output = engine.regenerate_markdown_document("report")

        assert computed_cell("= 'main:metrics'!A1 + 15", 100) in output

    def test_unquoted_doc_table_reference(self, engine: MarkDownSpreadsheetEngine) -> None:
        doc_a = md(
            f"""
            | {FORMULA_START} table:metrics {FORMULA_END} Score |
            | :--- |
            | 85 |
            """
        )
        doc_b = md(
            f"""
            | {FORMULA_START} table:summary {FORMULA_END} Final Calculation |
            | :--- |
            | {formula_cell('=main:metrics!A1 + 15')} |
            """
        )

        engine.load_markdown_document("main", doc_a)
        engine.load_markdown_document("report", doc_b)
        engine.evaluate()
        output = engine.regenerate_markdown_document("report")

        assert computed_cell("=main:metrics!A1 + 15", 100) in output


class TestColumnFormatting:
    def test_uniform_column_width_adds_padding(self) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} Item | Qty |
            | :--- | :--- |
            | Widgets | 5 |
            | Gadgets | 100 |
            """
        )

        default_engine = MarkDownSpreadsheetEngine()
        padded_engine = MarkDownSpreadsheetEngine(
            uniform_column_width=True, column_padding=1
        )

        default_output = run_document(default_engine, "doc1", content)
        padded_output = run_document(padded_engine, "doc1", content)

        assert "Widgets" in default_output and "| 5" in default_output
        assert "Gadgets" in default_output and "100" in default_output
        assert len(padded_output) > len(default_output)

    def test_column_padding_is_configurable(self) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} A |
            | :--- |
            | hi |
            """
        )

        engine = MarkDownSpreadsheetEngine(uniform_column_width=True, column_padding=3)
        output = run_document(engine, "doc1", content)

        assert "hi" in output
        assert "<!-- table:t1 --> A" in output


class TestDocumentStructure:
    def test_text_and_newline_preservation(self, engine: MarkDownSpreadsheetEngine) -> None:
        content = (
            "# Document Header\n\n"
            "Some initial descriptive text details.\n\n"
            f"| {FORMULA_START} table:t1 {FORMULA_END} Fixed |\n"
            "| :--- |\n"
            "| 42 |\n\n"
            "Trailing footnotes and markdown explanations go here."
        )

        output = run_document(engine, "doc1", content)

        assert output.startswith("# Document Header\n\nSome initial descriptive text details.\n\n")
        assert output.endswith("\nTrailing footnotes and markdown explanations go here.")

    def test_multiple_documents_keep_separate_outputs(
        self, engine: MarkDownSpreadsheetEngine
    ) -> None:
        doc_a = md(
            f"""
            | {FORMULA_START} table:a {FORMULA_END} Value |
            | :--- |
            | 10 |
            """
        )
        doc_b = md(
            f"""
            | {FORMULA_START} table:b {FORMULA_END} Value |
            | :--- |
            | {formula_cell('=main:a!A1 * 3')} |
            """
        )

        engine.load_markdown_document("main", doc_a)
        engine.load_markdown_document("report", doc_b)
        engine.evaluate()

        assert "10" in engine.regenerate_markdown_document("main")
        assert computed_cell("=main:a!A1 * 3", 30) in engine.regenerate_markdown_document("report")

    def test_unloaded_document_raises(self, engine: MarkDownSpreadsheetEngine) -> None:
        with pytest.raises(ValueError, match="Document 'ghost' has not been loaded."):
            engine.regenerate_markdown_document("ghost")


class TestFormulaPreprocessing:
    def test_local_table_reference_is_mapped_to_virtual_sheet(
        self, engine: MarkDownSpreadsheetEngine
    ) -> None:
        engine._get_or_create_sheet_index("doc1", "sales")
        processed = engine._preprocess_formula("doc1", "=sales!B2 + 1")

        assert processed == "=Sheet0!B2 + 1"

    def test_cross_document_reference_is_mapped_to_virtual_sheet(
        self, engine: MarkDownSpreadsheetEngine
    ) -> None:
        engine._get_or_create_sheet_index("main", "metrics")
        processed = engine._preprocess_formula("report", "= 'main:metrics'!A1 + 15")

        assert processed == "= Sheet0!A1 + 15"

    def test_formula_registry_tracks_original_expressions(
        self, engine: MarkDownSpreadsheetEngine
    ) -> None:
        content = md(
            f"""
            | {FORMULA_START} table:t1 {FORMULA_END} Total |
            | :--- |
            | {formula_cell('=5 + 7')} |
            """
        )

        engine.load_markdown_document("doc1", content)

        assert engine.formula_registry[("doc1", "t1", 1, 1)] == "=5 + 7"
