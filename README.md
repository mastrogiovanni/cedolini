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
    "name": "SPIKETRAP INC.",
    "address": "VIA DELLA MERCEDE, 12A",
    "cap": "00187",
    "city": "ROMA",
    "cf": "96468650583",
    "matricola_inps": "7073463019",
    "pat_inail": "096044893"
  },
  "employee": {
    "matricola": "7",
    "cognome": "MASTROGIOVANNI",
    "nome": "MICHELE",
    "cf": "MSTMHL80E19D708X",
    "data_nascita": "19/05/1980",
    "qualifica": "2 - Impiegati",
    "livello": "Q",
    "mansione": "ING. INFORMATICO",
    "data_assunzione": "28/01/2025"
  },
  "periodo": { "mese": "Maggio", "anno": "2026" },
  "elementi_retribuzione": {
    "minimo": "2.255,62",
    "contingenza": "539,99",
    "edr": "10,33",
    "superminimo": "5.924,83",
    "totale": "8.730,77"
  },
  "items": [
    {
      "voce": "1",
      "descrizione": "RETRIBUZIONE ORDINARIA",
      "quantita": "173,00",
      "base": "50,46688",
      "competenza": "8.730,77",
      "trattenuta": ""
    },
    {
      "voce": "1705",
      "descrizione": "ASSENZE (giorni)",
      "quantita": "1,00",
      "base": "335,79885",
      "competenza": "",
      "trattenuta": "335,80"
    }
  ],
  "totali": { "competenza": "9.066,57", "trattenuta": "335,80" },
  "contributi": {
    "ivs_imponibile": "8.731,00",
    "ivs_contributi": "802,38",
    "add_ivs_imponibile": "4.046,00",
    "add_ivs_contributi": "40,46",
    "totale": "842,84"
  },
  "irpef": {
    "reddito": "7.887,93",
    "imponibile": "7.887,93",
    "lorda": "2.741,81",
    "detrazioni": "",
    "totale_mese": "2.741,81"
  },
  "addizionali": {
    "reg_anno": "261,89",
    "com_anno": "76,68",
    "reg_ap": "",
    "com_acc_saldo": "28,12",
    "totale": "366,69"
  },
  "ferie":       { "anni_prec": "2,68",  "maturati": "9,40",  "goduti": "1,00", "residui": "11,08" },
  "ex_festivita":{ "anni_prec": "29,37", "maturati": "13,35", "goduti": "4,00", "residui": "38,72" },
  "rol":         { "anni_prec": "58,05", "maturati": "27,75", "goduti": "",     "residui": "85,80" },
  "netto": "4.779,00",
  "iban": "IT68K0301503200000002509835",
  "banca": "FINECO BANK SPA",
  "progressivi_anno": {
    "imponibile_contributi": "43.199,00",
    "contributi": "4.167,72",
    "imponibile_inail": "43.199,00",
    "imponibile_irpef": "59.051,26",
    "detrazioni": "",
    "irpef_pagata": "22.142,04"
  },
  "tfr": {
    "fondo_in_azienda": "7.201,34",
    "mese": "43,66",
    "spettante": "10.330,83"
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
