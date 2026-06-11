# cedolini

Plugin-based parser for Italian payslips (cedolini) that converts PDFs to structured JSON using [MarkItDown](https://github.com/microsoft/markitdown) for OCR.

## Setup

```bash
uv venv
uv pip install -e .
```

## Usage

```bash
# List all installed plugins
python main.py list-plugins

# Auto-detect the format of a PDF
python main.py detect payslip.pdf

# Parse a payslip (auto-detect plugin, print JSON to stdout)
python main.py parse payslip.pdf

# Force a specific plugin
python main.py parse payslip.pdf --plugin roncalli

# Write JSON to a file
python main.py parse payslip.pdf --output result.json
```

## Output format

Every plugin returns a single JSON object with the following structure.  The only variable-length field is **`items`** — the central pay-components list.

```json
{
  "plugin": "roncalli",
  "company": {
    "name": "...",
    "address": "...",
    "cap": "...",
    "city": "...",
    "cf": "...",
    "matricola_inps": "...",
    "pat_inail": "..."
  },
  "employee": {
    "matricola": "...",
    "cognome": "...",
    "nome": "...",
    "cf": "...",
    "data_nascita": "...",
    "qualifica": "...",
    "livello": "...",
    "mansione": "...",
    "data_assunzione": "..."
  },
  "periodo": { "mese": "...", "anno": "..." },
  "elementi_retribuzione": {
    "minimo": "...",
    "contingenza": "...",
    "edr": "...",
    "superminimo": "...",
    "totale": "..."
  },
  "items": [
    {
      "voce": "1",
      "descrizione": "RETRIBUZIONE ORDINARIA",
      "quantita": "...",
      "base": "...",
      "competenza": "...",
      "trattenuta": ""
    },
    {
      "voce": "1705",
      "descrizione": "ASSENZE (giorni)",
      "quantita": "...",
      "base": "...",
      "competenza": "",
      "trattenuta": "..."
    }
  ],
  "totali": { "competenza": "...", "trattenuta": "..." },
  "contributi": {
    "ivs_imponibile": "...",
    "ivs_contributi": "...",
    "add_ivs_imponibile": "...",
    "add_ivs_contributi": "...",
    "totale": "..."
  },
  "irpef": {
    "reddito": "...",
    "imponibile": "...",
    "lorda": "...",
    "detrazioni": "",
    "totale_mese": "..."
  },
  "addizionali": {
    "reg_anno": "...",
    "com_anno": "...",
    "reg_ap": "",
    "com_acc_saldo": "...",
    "totale": "..."
  },
  "ferie":       { "anni_prec": "...", "maturati": "...", "goduti": "...", "residui": "..." },
  "ex_festivita":{ "anni_prec": "...", "maturati": "...", "goduti": "...", "residui": "..." },
  "rol":         { "anni_prec": "...", "maturati": "...", "goduti": "",    "residui": "..." },
  "netto": "...",
  "iban": "...",
  "banca": "...",
  "progressivi_anno": {
    "imponibile_contributi": "...",
    "contributi": "...",
    "imponibile_inail": "...",
    "imponibile_irpef": "...",
    "detrazioni": "",
    "irpef_pagata": "..."
  },
  "tfr": {
    "fondo_in_azienda": "...",
    "mese": "...",
    "spettante": "..."
  }
}
```

All monetary amounts use Italian locale formatting (`1.234,56`). Unparseable fields are empty strings (`""`), never omitted.

---

## Plugin system

### How plugins are discovered

Every `.py` file inside `plugins/` (except `base.py`) is imported automatically at startup. Any class decorated with `@register` is added to the registry. No manual registration outside the plugin file is needed.

### Plugin API

All plugins must:

1. Inherit from `plugins.base.CedolinoPlugin`
2. Be decorated with `@plugins.register`
3. Set `name` (unique slug) and `description` class attributes
4. Implement `can_handle(cls, pdf_path: str) -> bool`
5. Implement `extract(cls, pdf_path: str) -> dict`

#### `can_handle`

- Must **never raise** — catch all exceptions and return `False`.
- Should be fast: convert only enough text to spot the format signature.
- Return `True` only when confident the plugin will produce correct output.

#### `extract`

- Start from `empty_cedolino()` (from `plugins.base`) and fill in the fields.
- The `items` key must be a list of `empty_item()` dicts, one per pay component.
- Leave unparseable fields as `""` — do not omit them.

### Minimal plugin skeleton

```python
"""Plugin for MyPayroll payslips."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import register
from plugins.base import CedolinoPlugin, empty_cedolino, empty_item
from markitdown import MarkItDown


@register
class MyPayrollPlugin(CedolinoPlugin):
    name = "mypayroll"
    description = "MyPayroll software cedolino"

    @classmethod
    def can_handle(cls, pdf_path: str) -> bool:
        try:
            text = MarkItDown().convert(pdf_path).text_content
            return "MY_UNIQUE_SIGNATURE" in text and "IVS" in text
        except Exception:
            return False

    @classmethod
    def extract(cls, pdf_path: str) -> dict:
        text = MarkItDown().convert(pdf_path).text_content
        result = empty_cedolino()
        result["plugin"] = cls.name

        # --- parse logic here ---
        # result["employee"]["cognome"] = ...
        # result["items"].append({**empty_item(), "voce": "1", ...})

        return result
```

---

## Adding a plugin with Claude

If `python main.py detect unknown.pdf` finds no match, run the `/new-plugin` slash command inside Claude Code:

```
/new-plugin /path/to/unknown.pdf
```

Claude will:
1. Convert the PDF to text with MarkItDown and inspect the structure.
2. Identify a unique fingerprint for the format.
3. Write a new plugin file in `plugins/`.
4. Test it with `detect` and `parse`.

---

## Available plugins

| Name | Software | Detection |
|------|----------|-----------|
| `roncalli` | Roncalli Software S.r.l. | Reversed copyright string `ihcconaR` + `IVS` + `IRPEF` present |

---

## Project layout

```
cedolini/
├── main.py                     # CLI entry point
├── pyproject.toml
├── plugins/
│   ├── base.py                 # CedolinoPlugin ABC, CEDOLINO_SCHEMA, ITEM_SCHEMA
│   ├── __init__.py             # Registry: register, detect, list_plugins, get_plugin
│   └── roncalli.py             # Plugin for Roncalli Software payslips
└── .claude/
    └── commands/
        └── new-plugin.md       # /new-plugin Claude skill
```
