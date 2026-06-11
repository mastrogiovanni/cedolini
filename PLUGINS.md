# Plugin system

## Data model

Every plugin returns a single Python dict matching `CEDOLINO_SCHEMA` (defined in `plugins/base.py`). The schema has fixed top-level sections and one variable-length list.

### Fixed sections

| Key | Description |
|-----|-------------|
| `plugin` | Name slug of the plugin that produced this result |
| `company` | Employer: name, address, CAP, city, CF, INPS matricola, INAIL PAT |
| `employee` | Worker: matricola, cognome, nome, CF, data_nascita, qualifica, livello, mansione, data_assunzione |
| `periodo` | `mese` (e.g. `"Maggio"`) and `anno` (e.g. `"2026"`) |
| `elementi_retribuzione` | Base salary components: minimo, contingenza, EDR, superminimo, totale |
| `totali` | Sum of all competenze and all trattenute from the items list |
| `contributi` | IVS and Add.IVS: imponibile, contributi, totale |
| `irpef` | reddito, imponibile, lorda, detrazioni, totale_mese |
| `addizionali` | Regional/municipal surtaxes: reg_anno, com_anno, reg_ap, com_acc_saldo, totale |
| `ferie` | Leave balance: anni_prec, maturati, goduti, residui |
| `ex_festivita` | Ex-holiday balance: anni_prec, maturati, goduti, residui |
| `rol` | ROL balance: anni_prec, maturati, goduti, residui |
| `netto` | Net pay |
| `iban` | Bank IBAN |
| `banca` | Bank name |
| `progressivi_anno` | Year-to-date totals: imponibile_contributi, contributi, imponibile_inail, imponibile_irpef, detrazioni, irpef_pagata |
| `tfr` | TFR fund: fondo_in_azienda, mese, spettante |

### Variable section: `items`

The central list — the only part of the payslip that varies in length. Each entry represents one pay component (voce).

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `voce` | `str` | Component code | `"1705"` |
| `descrizione` | `str` | Component label | `"ASSENZE (giorni)"` |
| `quantita` | `str` | Quantity (hours, days, units) | `"1,00"` |
| `base` | `str` | Unit rate (hourly/daily, many decimal places) | `"335,79885"` |
| `competenza` | `str` | Earning amount; empty if this is a deduction | `"335,80"` |
| `trattenuta` | `str` | Deduction amount; empty if this is an earning | `""` |

All amounts use Italian locale notation (`1.234,56`). Empty fields are `""`, never `null` or omitted.

---

## Plugin API

All plugins live in `plugins/` and must:

1. Inherit from `plugins.base.CedolinoPlugin`
2. Be decorated with `@plugins.register`
3. Set `name` (unique slug) and `description` class attributes
4. Implement `can_handle(cls, pdf_path: str) -> bool`
5. Implement `extract(cls, pdf_path: str) -> dict`

### `can_handle(cls, pdf_path: str) -> bool`

- **Never raise** — wrap the entire body in `try/except Exception: return False`.
- **Be fast** — convert the full text once but look only for a short fingerprint. If the PDF is large, limit inspection to the first ~8 KB.
- **Be specific** — combine a format-unique string (software name, reversed copyright, etc.) with generic payslip markers (`IVS`, `IRPEF`) to minimise false positives.

### `extract(cls, pdf_path: str) -> dict`

- Start from `empty_cedolino()` to guarantee all keys are present.
- Build the items list with `empty_item()` dicts.
- Fields that cannot be extracted must remain `""` — never omit them.
- Numbers stay as strings in Italian locale (`"1.234,56"`); do not convert to `float`.

---

## Adding a new plugin

### 1. Inspect the raw text

```python
from markitdown import MarkItDown
text = MarkItDown().convert("unknown.pdf").text_content
print(text)
```

Look for:
- A software name or copyright string (sometimes reversed or sideways).
- Unique labels that would not appear in other formats.
- The structure: where the items list starts and ends, where IRPEF/IVS figures appear.

### 2. Write the plugin

Create `plugins/<slug>.py`:

```python
"""Plugin for <Software Name> payslips."""

import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import register
from plugins.base import CedolinoPlugin, empty_cedolino, empty_item
from markitdown import MarkItDown


@register
class MyPlugin(CedolinoPlugin):
    name = "<slug>"
    description = "<Software Name> cedolino paga"

    @classmethod
    def can_handle(cls, pdf_path: str) -> bool:
        try:
            text = MarkItDown().convert(pdf_path).text_content
            return "UNIQUE_FINGERPRINT" in text and "IVS" in text and "IRPEF" in text
        except Exception:
            return False

    @classmethod
    def extract(cls, pdf_path: str) -> dict:
        text = MarkItDown().convert(pdf_path).text_content
        result = empty_cedolino()
        result["plugin"] = cls.name

        # Fill fixed sections
        result["company"]["cf"] = _extract_cf(text)
        # ...

        # Fill items list
        for voce, desc, comp, tratt in _parse_items(text):
            item = empty_item()
            item["voce"] = voce
            item["descrizione"] = desc
            item["competenza"] = comp
            item["trattenuta"] = tratt
            result["items"].append(item)

        return result
```

### 3. Test

```bash
python main.py detect unknown.pdf          # should report your new plugin
python main.py parse  unknown.pdf          # should produce valid JSON
```

Verify:
- `items` is non-empty with at least one entry having a non-empty `voce`.
- `employee.cognome` and `netto` are correct.
- `totali.competenza` equals the sum of all `items[*].competenza` values.

### Guidelines

- Use `MarkItDown` as the sole OCR engine — do not shell out to other tools.
- Payslip software often prints labels sideways or with characters spaced out. Use flexible regex patterns (`\s*` between expected letters) for labels; exact matches for data values.
- COMPETENZA vs TRATTENUTA: when the PDF linearises two columns, a large whitespace gap (>15 chars) before the last monetary amount on an item line usually indicates the TRATTENUTA column.
- If a section does not exist in the format (e.g., no ROL), leave those fields as `""`.

---

## Claude skill: `/new-plugin`

Run `/new-plugin /path/to/unknown.pdf` inside Claude Code. Claude will follow the steps in `.claude/commands/new-plugin.md` to analyse the PDF, identify the format, and write a complete plugin file.

---

## CLI reference

```
python main.py list-plugins
python main.py detect  <file.pdf>
python main.py parse   <file.pdf> [--plugin NAME] [--output out.json]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--plugin NAME` | auto | Force a specific plugin by name |
| `--output FILE` | stdout | Write JSON to FILE instead of printing |
