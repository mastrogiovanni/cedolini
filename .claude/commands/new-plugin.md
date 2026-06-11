Create a new cedolino plugin for a PDF that was not recognised by any existing plugin.

Usage: /new-plugin <path-to-pdf>

## Steps

1. **Convert the PDF to text** using the project's venv:
   ```bash
   cd /mnt/09b6776d-0aa6-40e1-b37d-eb5004c761a8/Projects/cedolini
   .venv/bin/python -c "
   from markitdown import MarkItDown
   print(MarkItDown().convert('$ARGUMENTS').text_content)
   "
   ```

2. **Identify the software/format** from the text output:
   - Look for a software name, copyright string, or reversed text (some payslip software prints its name sideways).
   - Look for a unique fingerprint string that would NOT appear in other formats.
   - Note the overall structure: company header, employee section, items list, contributions, tax, net pay.

3. **Map the text to the schema** defined in `plugins/base.py`:
   - `company`: name, address, CF, INPS matricola, INAIL PAT
   - `employee`: matricola, cognome, nome, CF, data_nascita, qualifica, livello, mansione, data_assunzione
   - `periodo`: mese, anno
   - `elementi_retribuzione`: minimo, contingenza, EDR, superminimo, totale
   - `items` (the variable-length central list): each entry has voce, descrizione, quantita, base, competenza, trattenuta
   - `contributi`: IVS imponibile/contributi, Add. IVS, totale
   - `irpef`: reddito, imponibile, lorda, detrazioni, totale_mese
   - `addizionali`: reg_anno, com_anno, reg_ap, com_acc_saldo, totale
   - `ferie`, `ex_festivita`, `rol`: anni_prec, maturati, goduti, residui
   - `netto`, `iban`, `banca`
   - `progressivi_anno`: cumulative year-to-date figures
   - `tfr`: fondo_in_azienda, mese, spettante

4. **Write the plugin file** at `plugins/<software_slug>.py`:
   - Use the existing `plugins/roncalli.py` as a template.
   - Set a unique `name` slug (e.g. `zucchetti`, `paghe-web`, `teamsystem`).
   - Set a clear `description`.
   - `can_handle`: convert the first ~6000 chars, check for the unique fingerprint + generic payslip markers (`IVS`, `IRPEF`). Never raise; return False on error.
   - `extract`: return a dict from `empty_cedolino()` with all parseable fields filled.
   - Each extractor function should match patterns against the raw MarkItDown text.
   - For the items list: find the header line containing `VOCE` and `DESCRIZIONE`, collect lines until the contributions section, parse each item row.
   - Unparseable fields must be left as `""` (empty string), never omitted.

5. **Test the new plugin**:
   ```bash
   cd /mnt/09b6776d-0aa6-40e1-b37d-eb5004c761a8/Projects/cedolini
   .venv/bin/python main.py detect "$ARGUMENTS"
   .venv/bin/python main.py parse  "$ARGUMENTS"
   ```
   Verify that:
   - `detect` reports the new plugin name.
   - `parse` outputs valid JSON.
   - Key fields (employee name, netto, periodo) are correctly extracted.
   - `items` is a non-empty list with at least one entry having a non-empty `voce` and non-empty `competenza` or `trattenuta`.

6. **If extraction is incomplete**, inspect the raw text again, refine the regexes, and re-test.
