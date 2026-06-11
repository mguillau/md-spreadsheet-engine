# Examples

Runnable Markdown spreadsheets that demonstrate the engine. Each file contains formulas in HTML comments; computed values appear after `-->`.

| Example | File(s) | Demonstrates |
|---|---|---|
| Invoice | [`invoice.md`](invoice.md) | Local formulas and `SUM` |
| Cross-table | [`cross_table.md`](cross_table.md) | `table!cell` references in one file |
| Cross-document | [`cross_document/`](cross_document/) | `doc:table!cell` across files |
| Mixed content | [`budget.md`](budget.md) | Headings and prose preserved around tables |

## Run locally

Single file:

```bash
md-calc -i examples/invoice.md
```

Cross-document group (must be evaluated together):

```bash
md-calc -i \
  -n inventory examples/cross_document/inventory.md \
  -n summary examples/cross_document/summary.md
```

Recompute every example:

```bash
python scripts/compute_examples.py
```

Only files that changed since the last commit:

```bash
python scripts/compute_examples.py --changed
```
