import re
import sys
import logging
import click

import ironcalc as ic
from md_spreadsheet_parser import scan_tables

# Token separator used to qualify external sheets, e.g. 'report:q1_sales'!A1
DOC_TAB_SEP = ":"

# Core syntax configuration delimiters
FORMULA_START = "<!--"
FORMULA_END = "-->"

# Setup centralized logging defaults pointing cleanly to stderr stream
logger = logging.getLogger("md_spreadsheet_engine")
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.WARNING)  # Default threshold overrideable via CLI flags


class MarkDownSpreadsheetEngine:
    def __init__(
        self,
        model_name: str = "md_spreadsheet_model",
        *,
        uniform_column_width: bool = False,
        column_padding: int = 1,
    ):
        """Initialize the backend IronCalc workbook and local tracking variables.

        Args:
            model_name: IronCalc workbook name.
            uniform_column_width: When True, pad every cell in a column to the
                same width (longest cell content in that column plus padding).
            column_padding: Extra spaces added to each column width when
                ``uniform_column_width`` is enabled.
        """
        self.workbook = ic.create(model_name, "en", "UTC", "en")
        self.formula_registry = {}      # {(doc, table, r, c): "formula"}
        self.table_to_sheet_map = {}    # {"doc:table": sheet_index}
        self.sheet_symbols = []         # Maps index to string 'SheetX'
        self.current_sheet_index = 0
        self.document_cache = {}        # {"doc": [token_dict, ...]}
        self.uniform_column_width = uniform_column_width
        self.column_padding = column_padding

    def _get_or_create_sheet_index(self, doc_name: str, table_id: str) -> int:
        key = f"{doc_name}{DOC_TAB_SEP}{table_id}"
        if key in self.table_to_sheet_map:
            return self.table_to_sheet_map[key]

        allocated_index = self.current_sheet_index
        table_symbol = f'Sheet{allocated_index}'
        logger.info(f"Mapping namespace '{key}' onto virtual spreadsheet workspace '{table_symbol}'")

        if self.current_sheet_index > 0:
            self.workbook.add_sheet(table_symbol)
        else:
            self.workbook.rename_sheet(0, table_symbol)

        self.table_to_sheet_map[key] = self.current_sheet_index
        self.sheet_symbols.append(table_symbol)
        self.current_sheet_index += 1
        return allocated_index

    def _resolve_table_key(self, doc_name: str, sheet_ref: str) -> str:
        """Build a canonical doc:table key from a local or fully-qualified table reference."""
        if DOC_TAB_SEP in sheet_ref:
            return sheet_ref
        return f"{doc_name}{DOC_TAB_SEP}{sheet_ref}"

    def _preprocess_formula(self, doc_name: str, formula_str: str) -> str:
        """Translates local table identifiers (t1!A1) into virtual backend symbols (Sheet0!A1)."""
        def replace_tab_ref_with_symbol(match):
            sheet_ref = match.group(1) or match.group(2)
            key = self._resolve_table_key(doc_name, sheet_ref)
            d_name, s_ref = key.split(DOC_TAB_SEP, 1)
            t_idx = self._get_or_create_sheet_index(d_name, s_ref)
            return f"{self.sheet_symbols[t_idx]}!"

        # Quoted ('doc:table'!) and unquoted (doc:table! / table!) refs in one pass
        # so virtual SheetN! symbols are never re-processed.
        table_ref_pattern = (
            r"'([^']+)'!"
            r"|"
            r"([A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?)!"
        )
        formula_str = re.sub(table_ref_pattern, replace_tab_ref_with_symbol, formula_str)
        return formula_str

    def _extract_table_id(self, table_text: str, table_index: int) -> str:
        """Read an explicit table id from a comment, or fall back to table_{n}."""
        fs_esc = re.escape(FORMULA_START)
        fe_esc = re.escape(FORMULA_END)
        id_match = re.search(
            fr"{fs_esc}\s*table:\s*([A-Za-z0-9_]+)\s*{fe_esc}",
            table_text,
        )
        return id_match.group(1) if id_match else f"table_{table_index}"

    def _load_table(
        self,
        doc_name: str,
        table_id: str,
        table_obj,
    ) -> None:
        """Register one parsed table with the workbook and formula registry."""
        fs_esc = re.escape(FORMULA_START)
        fe_esc = re.escape(FORMULA_END)
        sheet_idx = self._get_or_create_sheet_index(doc_name, table_id)

        for r_idx, row in enumerate(table_obj.rows, start=1):
            for c_idx, cell_value in enumerate(row, start=1):
                cell_str = str(cell_value).strip()
                formula_match = re.search(fr"{fs_esc}\s*(=.*?)\s*{fe_esc}", cell_str)

                if formula_match:
                    formula = formula_match.group(1)
                    self.formula_registry[(doc_name, table_id, r_idx, c_idx)] = formula
                    processed_formula = self._preprocess_formula(doc_name, formula)
                    self.workbook.set_user_input(
                        sheet_idx, r_idx, c_idx, processed_formula
                    )
                else:
                    self.workbook.set_user_input(sheet_idx, r_idx, c_idx, cell_str)

    def load_markdown_document(self, doc_name: str, markdown_content: str):
        """Slices document text into elements, registers cell parameters, and builds structures."""
        logger.info(f"Parsing document stream profile: '{doc_name}'")
        tokens = []
        table_regex = r"((?:^[ \t]*\|.*\|[ \t]*$(?:\r?\n)?)+)"
        parts = re.split(table_regex, markdown_content, flags=re.MULTILINE)
        table_index = 0

        for part in parts:
            if part.strip().startswith("|"):
                parsed_tables = scan_tables(part)
                if not parsed_tables:
                    tokens.append({"type": "text", "content": part})
                    continue

                part_lines = part.splitlines()
                for table_obj in parsed_tables:
                    if table_obj.start_line is not None and table_obj.end_line is not None:
                        table_text = "\n".join(
                            part_lines[table_obj.start_line : table_obj.end_line]
                        )
                    else:
                        table_text = part

                    table_id = self._extract_table_id(table_text, table_index)
                    table_index += 1
                    self._load_table(doc_name, table_id, table_obj)
                    tokens.append({"type": "table", "id": table_id, "obj": table_obj})
            else:
                tokens.append({"type": "text", "content": part})

        self.document_cache[doc_name] = tokens

    def evaluate(self):
        """Triggers the backend Rust dependency calculation execution layer."""
        logger.info("Executing global spreadsheet graph formula evaluation pass...")
        self.workbook.evaluate()

    def _column_widths(self, rows: list[list[str]]) -> list[int]:
        """Return per-column content widths for table rendering."""
        if not rows:
            return []

        col_count = len(rows[0])
        max_widths = [0] * col_count
        for row in rows:
            for c_idx, cell in enumerate(row):
                max_widths[c_idx] = max(max_widths[c_idx], len(str(cell)))

        if self.uniform_column_width:
            max_widths = [width + self.column_padding for width in max_widths]

        return max_widths

    def _format_table_row(self, cells: list[str], col_widths: list[int]) -> str:
        """Format one markdown table row with uniform column widths."""
        formatted = " | ".join(
            str(cell).ljust(col_widths[c_idx]) for c_idx, cell in enumerate(cells)
        )
        return f"| {formatted} |"

    def _format_alignment_row(
        self,
        col_widths: list[int],
        alignments: list[str] | None = None,
    ) -> str:
        """Format the markdown alignment row beneath the header."""
        sep_cells = []
        for idx, width in enumerate(col_widths):
            w = max(width, 3)
            alignment = (
                alignments[idx]
                if alignments and idx < len(alignments)
                else "default"
            )
            if alignment == "center":
                sep_cells.append(":" + "-" * w + ":")
            elif alignment == "right":
                sep_cells.append("-" * w + ":")
            elif alignment == "left":
                sep_cells.append(":" + "-" * w)
            else:
                sep_cells.append("-" * (w + 2))
        return f"| {' | '.join(sep_cells)} |"

    def _table_render_rows(self, table_obj) -> list[list[str]]:
        """Return header (if any) plus data rows for width calculation and output."""
        rows: list[list[str]] = []
        if table_obj.headers:
            rows.append([str(cell) for cell in table_obj.headers])
        rows.extend(table_obj.rows)
        return rows

    def regenerate_markdown_document(self, doc_name: str) -> str:
        """Assembles data layers, formats column padding widths, and generates output strings."""
        tokens = self.document_cache.get(doc_name)
        if not tokens:
            raise ValueError(f"Document '{doc_name}' has not been loaded.")

        output_segments = []

        for token in tokens:
            if token["type"] == "text":
                output_segments.append(token["content"])
            elif token["type"] == "table":
                table_id = token["id"]
                table_obj = token["obj"]
                sheet_idx = self.table_to_sheet_map[f"{doc_name}{DOC_TAB_SEP}{table_id}"]

                # 1. Update mutable cell arrays with calculated variables
                for r_idx in range(1, len(table_obj.rows) + 1):
                    row_data = table_obj.rows[r_idx - 1]
                    for c_idx in range(1, len(row_data) + 1):
                        coord_key = (doc_name, table_id, r_idx, c_idx)

                        if coord_key in self.formula_registry:
                            formula = self.formula_registry[coord_key]
                            calculated_val = self.workbook.get_formatted_cell_value(sheet_idx, r_idx, c_idx)
                            table_obj.rows[r_idx - 1][c_idx - 1] = f"{FORMULA_START} {formula} {FORMULA_END} {calculated_val}"
                        else:
                            # Normalize non-formula strings to clean trailing/leading spaces
                            table_obj.rows[r_idx - 1][c_idx - 1] = str(table_obj.rows[r_idx - 1][c_idx - 1]).strip()

                render_rows = self._table_render_rows(table_obj)
                col_widths = self._column_widths(render_rows)
                table_lines = []

                if table_obj.headers:
                    table_lines.append(
                        self._format_table_row(render_rows[0], col_widths)
                    )
                    table_lines.append(
                        self._format_alignment_row(
                            col_widths, table_obj.alignments
                        )
                    )
                    body_rows = render_rows[1:]
                else:
                    table_lines.append(
                        self._format_table_row(render_rows[0], col_widths)
                    )
                    table_lines.append(self._format_alignment_row(col_widths))
                    body_rows = render_rows[1:]

                for row in body_rows:
                    table_lines.append(self._format_table_row(row, col_widths))

                table_md = "\n".join(table_lines) + "\n"
                output_segments.append(table_md)

        return "".join(output_segments)


@click.command()
@click.argument('input-files', nargs=-1, type=click.Path(exists=True))
@click.option('--doc-name', '-n', multiple=True, help="Custom document names matching the input files order.")
@click.option('--verbose', '-v', is_flag=True, default=False, help="Enable detailed INFO level logging outputs to stderr.")
@click.option('--uniform-columns', '-u', is_flag=True, default=False, help="Pad each column to the same width (max content + 1 space).")
@click.option('--in-place', '-i', is_flag=True, default=False, help="Write computed output back to each input file.")
@click.option('--test', '-t', is_flag=True, default=False, help="Run internal mock test suite pipeline validation scenario.")
def process_markdown_content(input_files, doc_name, verbose, uniform_columns, in_place, test):
    """Processes, computes, and prints calculated configurations from markdown files containing tables."""
    if verbose:
        logger.setLevel(logging.INFO)
        logger.info("Verbose execution monitoring active.")

    engine = MarkDownSpreadsheetEngine(uniform_column_width=uniform_columns)

    if test:
        logger.info("Running internal engine validation scenario tests...")
        mock_content = (
            f"# Test Space\n\n"
            f"| {FORMULA_START} table:t1 {FORMULA_END} Item | Value |\n"
            f"| :--- | :--- |\n"
            f"| Core Cost | 250 |\n"
            f"| Scaled Total | {FORMULA_START} =t1!B1 * 2 {FORMULA_END} |\n"
        )
        engine.load_markdown_document("mock_doc", mock_content)
        engine.evaluate()
        print(engine.regenerate_markdown_document("mock_doc"))
        return

    if not input_files:
        # Fallback to streaming raw content from stdin pipes
        logger.info("Awaiting input stream pipeline from stdin interface allocation...")
        stdin_content = sys.stdin.read()
        default_name = doc_name[0] if doc_name else "stdin_document"
        engine.load_markdown_document(default_name, stdin_content)
        engine.evaluate()
        print(engine.regenerate_markdown_document(default_name))
        return

    # Process files sequentially
    files_list = list(input_files)
    names_list = list(doc_name)

    # Match missing document names with file paths as keys
    while len(names_list) < len(files_list):
        fallback = files_list[len(names_list)]
        names_list.append(fallback)

    # Step 1: Load and parse documents sequentially
    for path, name in zip(files_list, names_list):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        engine.load_markdown_document(name, content)

    # Step 2: Compute formula values using the underlying evaluation tracker
    engine.evaluate()

    # Step 3: Regenerate and output the updated document strings sequentially
    for path, name in zip(files_list, names_list):
        output = engine.regenerate_markdown_document(name)
        if in_place:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(output)
            logger.info(f"Wrote computed output to: '{path}'")
        else:
            logger.info(f"Streaming final output reconstruction data arrays for: '{name}'")
            print(output)


if __name__ == "__main__":
    process_markdown_content()