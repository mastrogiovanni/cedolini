"""Plugin for cedolini produced by Roncalli Software S.r.l.

Detection: MarkItDown renders the PDF text and includes the software copyright
string reversed (as it appears printed sideways on the form): 'ihcconaR' is
'Roncalli' backwards.  We also verify Italian payslip markers (IVS, IRPEF).

Structure of the Roncalli payslip:
  - Header: employer info (name, address, CF, INPS/INAIL codes), period
  - Employee section: name, CF, birth date, qualification, level, seniority
  - Salary elements (right column): MINIMO, CONTINGENZA, EDR, SUPERMINIMO
  - Central items list (variable length): VOCE, DESCRIZIONE, COMPETENZA, TRATTENUTA
  - Contributions: IVS, addizionale IVS
  - IRPEF and regional/municipal surtaxes
  - Leave balances: FERIE, EX FESTIVITÀ, ROL
  - Net pay, IBAN, year-to-date totals, TFR
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from plugins import register
from plugins.base import CedolinoPlugin, empty_cedolino, empty_item

# ─── Compiled patterns ────────────────────────────────────────────────────────

# Italian monetary amounts: 1.234,56 or 1234,56 or 1234,56789
AMOUNT_RE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2,5}")

# Italian codice fiscale (16 chars)
CF_RE = re.compile(r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]")

# Date dd/mm/yyyy — also catches "1 9/05/1980" style after digit-space cleanup
DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")

ITALIAN_MONTHS = {
    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
}

# Roncalli software fingerprint (copyright string appears reversed in the PDF)
_FINGERPRINTS = ["ihcconaR", "Roncalli"]


# ─── Text helpers ─────────────────────────────────────────────────────────────

def _get_text(pdf_path: str) -> str:
    from markitdown import MarkItDown
    return MarkItDown().convert(pdf_path).text_content


def _collapse_spaced_digits(s: str) -> str:
    """'1 7 0 5' → '1705'  (apply until stable)."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"(\d) (\d)", r"\1\2", s)
    return s


def _strip_line(line: str) -> str:
    """Remove table markers and collapse internal whitespace."""
    line = re.sub(r"[|]", " ", line)
    return re.sub(r" {2,}", "  ", line)


def _is_separator(line: str) -> bool:
    return bool(re.match(r"^[\|\-\s]+$", line.strip())) and len(line.strip()) > 2


def _first_n_amounts(text: str, n: int = 10) -> list[str]:
    return AMOUNT_RE.findall(text)[:n]


def _first_amount(text: str) -> str:
    m = AMOUNT_RE.search(text)
    return m.group() if m else ""


def _last_amount(text: str) -> str:
    matches = AMOUNT_RE.findall(text)
    return matches[-1] if matches else ""


def _parse_float(s: str) -> float:
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


# ─── Field extractors ─────────────────────────────────────────────────────────

def _extract_company(text: str) -> dict:
    c = {"name": "", "address": "", "cap": "", "city": "", "cf": "", "matricola_inps": "", "pat_inail": ""}

    lines = [l for l in text.split("\n") if l.strip()]

    # Company name: first line, part before a large whitespace run.
    # Merge leading 1-3 char token with the next long token ("SP IKETRAP" → "SPIKETRAP").
    if lines:
        first = re.split(r" {5,}", lines[0])[0].strip()
        first = re.sub(r"^([A-Z]{1,3})\s+([A-Z]{3,})", r"\1\2", first)
        c["name"] = re.sub(r"\s+", " ", first).strip()

    # Address: first line where collapsed text contains VIA/CORSO/PIAZZA etc.
    # Fix "VI A" → "VIA" (2-char prefix + single-char + space pattern at line start).
    for line in lines[:10]:
        part = re.split(r" {5,}", line)[0].strip()
        collapsed = re.sub(r"\s+", "", part)
        if re.search(r"(VIA|CORSO|PIAZZA|LARGO|VIALE)", collapsed, re.I):
            # Collapse "XX Y " at start (street-type abbreviation split into two parts)
            part = re.sub(r"^([A-Z]{2,3})\s+([A-Z])\s", r"\1\2 ", part)
            c["address"] = re.sub(r"\s+", " ", part).strip()
            break

    # CAP / City: look for a 5-digit postal code in a table cell
    cap_m = re.search(r"\b(\d{2}\s*\d{3})\s+([A-Z]{2,})", text)
    if cap_m:
        c["cap"] = cap_m.group(1).replace(" ", "")
        c["city"] = cap_m.group(2).strip().split()[0]

    # CF azienda
    cf_m = re.search(r"CF\s*:\s*(\d{11})", text)
    if cf_m:
        c["cf"] = cf_m.group(1)

    # MATRICOLA INPS (10 digits) + PAT INAIL (9 digits) on the same line
    mat_m = re.search(r"(\d{10})\s+(\d{9})", text)
    if mat_m:
        c["matricola_inps"] = mat_m.group(1)
        c["pat_inail"] = mat_m.group(2)

    return c


def _extract_periodo(text: str) -> dict:
    p = {"mese": "", "anno": ""}
    for month, num in ITALIAN_MONTHS.items():
        m = re.search(rf"\b{month}\b\s+(\d{{4}})", text, re.IGNORECASE)
        if m:
            p["mese"] = month.capitalize()
            p["anno"] = m.group(1)
            break
    return p


def _extract_employee(text: str) -> dict:
    e = {"matricola": "", "cognome": "", "nome": "", "cf": "", "data_nascita": "",
         "qualifica": "", "livello": "", "mansione": "", "data_assunzione": ""}

    # Employee CF: may have one spurious space (e.g. "M STMHL80E19D708X")
    # Pattern: 1 uppercase letter + optional space + 5 uppercase + 2 digits + letter + 2 digits + letter + 3 digits + letter
    cf_m = re.search(r"([A-Z])\s?([A-Z]{5}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])", text)
    if cf_m:
        e["cf"] = cf_m.group(1) + cf_m.group(2)

    # Name: <matricola>  COGNOME NOME  (leading digit then two all-caps words)
    name_m = re.search(r"^\s+(\d+)\s{2,}([A-Z]{2,})\s+([A-Z]{2,})", text, re.MULTILINE)
    if name_m:
        e["matricola"] = name_m.group(1).strip()
        e["cognome"] = name_m.group(2)
        e["nome"] = name_m.group(3)

    # Work on digit-collapsed text for date extraction
    clean = _collapse_spaced_digits(text)
    all_dates = DATE_RE.findall(clean)

    # Data nascita: the date matching birth year range (1940-2010)
    for d in all_dates:
        year = int(d[-4:])
        if 1940 <= year <= 2010:
            e["data_nascita"] = d
            break

    # Data assunzione: dates that are not the birth date and not the stamp date
    stamp_date = ""
    stamp_m = re.search(r"Stampato\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if stamp_m:
        stamp_date = _collapse_spaced_digits(stamp_m.group(1))
    for d in all_dates:
        if d != e["data_nascita"] and d != stamp_date:
            e["data_assunzione"] = d
            break

    # Qualifica: "2-Impiegati" or "2 -Impiegati" — stop before whitespace runs or "DATA"
    q_m = re.search(r"(\d\s*-\s*[A-Za-z][A-Za-z]+)", text)
    if q_m:
        e["qualifica"] = re.sub(r"\s+", "", q_m.group()).replace("-", " - ", 1)

    # Livello: single uppercase letter after garbled LIVELLO
    liv_m = re.search(r"L\s*I\s*V\s*E\s*L\s*L\s*O\s+([A-Z])\b", text)
    if liv_m:
        e["livello"] = liv_m.group(1)

    # Mansione: uppercase words after MANSIONE (possibly garbled "M   AN   S   IO   N   E")
    # Value appears as e.g. "I NG. INFORMATICO" (single-char prefix before abbreviation)
    mans_m = re.search(r"M\s*A\s*N\s*S\s*I\s*O\s*N\s*E\s+([A-Z][^\|\n]{4,30}?)(?:\s{3,}|\|)", text)
    if mans_m:
        raw = mans_m.group(1).strip()
        # Collapse single uppercase char followed by uppercase: "I NG." → "ING."
        raw = re.sub(r"\b([A-Z])\s+([A-Z]{2,})", r"\1\2", raw)
        e["mansione"] = re.sub(r"\s+", " ", raw).strip()

    return e


def _extract_elementi_retribuzione(text: str) -> dict:
    er = {"minimo": "", "contingenza": "", "edr": "", "superminimo": "", "totale": ""}

    # Each element appears as  LABEL <amounts>  (two amounts: prev month, current month)
    # We take the last (current month) amount for each.

    def _pair(pattern: str) -> str:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return ""
        rest = text[m.end():]
        amts = _first_n_amounts(rest, 2)
        return amts[-1] if amts else ""

    er["minimo"] = _pair(r"M\s*INIMO")
    er["contingenza"] = _pair(r"CONTINGENZA")
    er["edr"] = _pair(r"\bEDR\b")
    er["superminimo"] = _pair(r"SUPERMINIMO")

    # RETRIBUZIONE DI FATTO: appears as "...FATTO  <val>  <val>"
    fatto_m = re.search(r"FATTO\s+([\d.,]+)\s+([\d.,]+)", text)
    if fatto_m:
        er["totale"] = fatto_m.group(2)
    else:
        # Sum from components as fallback
        vals = [_parse_float(v) for v in [er["minimo"], er["contingenza"], er["edr"], er["superminimo"]] if v]
        if vals:
            total = sum(vals)
            er["totale"] = f"{total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return er


# ─── Items (central list) ─────────────────────────────────────────────────────

def _split_item_amounts(amounts: list[str]) -> tuple[str, str, str]:
    """Return (quantita, base, final_monetary_amount)."""
    if not amounts:
        return "", "", ""

    # Base amounts have 4+ decimal places (hourly/daily rates)
    base_amts = [a for a in amounts if "," in a and len(a.split(",")[1]) >= 4]
    other_amts = [a for a in amounts if a not in base_amts]

    base = base_amts[0] if base_amts else ""

    if not other_amts:
        return "", base, ""
    if len(other_amts) == 1:
        return "", base, other_amts[0]

    # Multiple non-base amounts: smallest value = quantita, largest = monetary total
    try:
        other_sorted = sorted(other_amts, key=_parse_float)
        return other_sorted[0], base, other_sorted[-1]
    except Exception:
        return other_amts[0], base, other_amts[-1]


def _classify_final_amount(line: str, final: str) -> tuple[str, str]:
    """(competenza, trattenuta) — uses whitespace gap before the final amount."""
    if not final:
        return "", ""
    pos = line.rfind(final)
    before = line[:pos]
    prev_matches = list(AMOUNT_RE.finditer(before))
    if prev_matches:
        prev_end = prev_matches[-1].end()
        gap = pos - prev_end
    else:
        gap = 0
    # Large gap (>15 chars) means the value sits in the TRATTENUTA column
    if gap > 15:
        return "", final
    return final, ""


def _clean_description(raw: str) -> str:
    """Best-effort collapse of spaced-out uppercase text like 'R ET R I B' → 'RETRIB'."""
    # Split on 2+ spaces (act as word boundaries in the garbled text)
    parts = re.split(r" {2,}", raw)
    result = []
    for part in parts:
        frags = part.split(" ")
        if frags and all(re.match(r"^[A-Za-z\(\)\'\.]{1,3}$", f) or f == "" for f in frags):
            merged = "".join(f for f in frags if f)
            result.append(merged)
        else:
            result.append(part.strip())
    return " ".join(r for r in result if r).strip()


def _extract_items(text: str) -> tuple[list[dict], str, str]:
    """Return (items_list, total_competenza, total_trattenuta)."""
    lines = text.split("\n")

    # Locate items header
    start_idx = None
    header_line = ""
    for i, line in enumerate(lines):
        if "VOCE" in line and "DESCRIZIONE" in line and "COMPETENZA" in line:
            start_idx = i + 1
            header_line = line
            break
    if start_idx is None:
        return [], "", ""

    # Locate end of items (first line with IVS or ENTE-VOCE outside a table)
    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        line = lines[i]
        if re.search(r"\bIVS\b", line) and AMOUNT_RE.search(line) and "|" not in line:
            end_idx = i
            break
        if re.search(r"ENTE.?VOCE", line, re.I):
            end_idx = i
            break

    items: list[dict] = []
    total_competenza = ""
    total_trattenuta = ""

    for raw_line in lines[start_idx:end_idx]:
        if _is_separator(raw_line):
            continue

        clean = _strip_line(raw_line)
        clean = _collapse_spaced_digits(clean)

        amounts = AMOUNT_RE.findall(clean)
        if not amounts:
            continue

        # Totals line: no voce code, just amounts — the last item-section line
        # Pattern: leading spaces + amount (no letter prefix)
        if re.match(r"^\s*[\d.,]+", clean) and not re.match(r"^\s+\d+\s+[A-Z]", clean):
            if len(amounts) >= 2:
                total_competenza = amounts[0]
                total_trattenuta = amounts[1] if len(amounts) > 1 else ""
            continue

        # Item line: leading spaces + digit(s) + uppercase text + amounts
        item_m = re.match(r"^\s+(\d+)\s+(.+)", clean)
        if not item_m:
            continue

        voce = item_m.group(1)
        rest = item_m.group(2).strip()

        # Remove calendar symbols (single/double uppercase letter at end)
        rest = re.sub(r"\s+[A-Z]{1,2}\s*$", "", rest)
        # Remove calendar day numbers at end (1–31 isolated)
        rest = re.sub(r"\s+\d{1,2}\s*$", "", rest)

        # Remove amounts from rest to isolate description
        desc_raw = rest
        for amt in amounts:
            desc_raw = desc_raw.replace(amt, "", 1)
        desc_raw = re.sub(r"\s{2,}", "  ", desc_raw).strip()
        descrizione = _clean_description(desc_raw)

        quantita, base, final = _split_item_amounts(amounts)
        competenza, trattenuta = _classify_final_amount(raw_line, final)

        item = empty_item()
        item["voce"] = voce
        item["descrizione"] = descrizione
        item["quantita"] = quantita
        item["base"] = base
        item["competenza"] = competenza
        item["trattenuta"] = trattenuta
        items.append(item)

    return items, total_competenza, total_trattenuta


# ─── Contributions / IRPEF / Addizionali ─────────────────────────────────────

def _extract_contributi(text: str) -> dict:
    c = {"ivs_imponibile": "", "ivs_contributi": "", "add_ivs_imponibile": "", "add_ivs_contributi": "", "totale": ""}

    ivs_m = re.search(r"\bIVS\b\s+([\d.,]+)\s+([\d.,]+)", text)
    if ivs_m:
        c["ivs_imponibile"] = ivs_m.group(1)
        c["ivs_contributi"] = ivs_m.group(2)

    add_m = re.search(r"Add\.\s*IVS\s+([\d.,]+)\s+([\d.,]+)", text, re.IGNORECASE)
    if add_m:
        c["add_ivs_imponibile"] = add_m.group(1)
        c["add_ivs_contributi"] = add_m.group(2)

    # Total = sum of IVS + Add.IVS contributions (most reliable)
    if c["ivs_contributi"] and c["add_ivs_contributi"]:
        total = _parse_float(c["ivs_contributi"]) + _parse_float(c["add_ivs_contributi"])
        c["totale"] = f"{total:.2f}".replace(".", ",")

    return c


def _extract_irpef(text: str) -> dict:
    ir = {"reddito": "", "imponibile": "", "lorda": "", "detrazioni": "", "totale_mese": ""}

    # The IRPEF section has a header line (garbled) then a data line with amounts.
    # Data line pattern: reddito  [oneri]  imponibile  lorda  [detrazioni]  totale_mese
    # We search for the IVS section to anchor ourselves, then look ahead.
    ivs_pos = text.find("IVS")
    if ivs_pos == -1:
        return ir

    after_ivs = text[ivs_pos:]
    # The IRPEF data line has 2–4 amounts separated by large gaps
    # Characteristic: reddito == imponibile (when no oneri deducibili)
    irpef_m = re.search(
        r"([\d.,]+)\s{10,}([\d.,]+)\s+([\d.,]+)\s{10,}([\d.,]+)",
        after_ivs,
    )
    if irpef_m:
        ir["reddito"] = irpef_m.group(1)
        ir["imponibile"] = irpef_m.group(2)
        ir["lorda"] = irpef_m.group(3)
        ir["totale_mese"] = irpef_m.group(4)
    else:
        # Fallback: simpler match
        irpef_m2 = re.search(r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)", after_ivs)
        if irpef_m2:
            ir["reddito"] = irpef_m2.group(1)
            ir["imponibile"] = irpef_m2.group(1)
            ir["lorda"] = irpef_m2.group(2)
            ir["totale_mese"] = irpef_m2.group(3)

    return ir


def _extract_addizionali(text: str) -> dict:
    a = {"reg_anno": "", "com_anno": "", "reg_ap": "", "com_acc_saldo": "", "totale": ""}

    # Addizionali data appears after the IRPEF section on a single line with 4+ amounts
    # where the gap between the 2nd and 3rd amount is ≥20 chars (empty reg_ap column).
    # Process line-by-line to avoid cross-line matches.
    for line in text.split("\n"):
        if not line.strip() or "|" in line:
            continue
        matches = list(AMOUNT_RE.finditer(line))
        if len(matches) < 4:
            continue
        # Require large gap between 2nd and 3rd amount (empty column in the middle)
        gap = matches[2].start() - matches[1].end()
        if gap < 15:
            continue
        # Sanity check: addizionali are regional/municipal surtaxes, all < 2000
        vals = [_parse_float(m.group()) for m in matches[:4]]
        if any(v >= 2000 for v in vals):
            continue
        # First amount must be the largest single component (reg_anno typically > com_anno)
        a["reg_anno"] = matches[0].group()
        a["com_anno"] = matches[1].group()
        a["com_acc_saldo"] = matches[2].group()
        a["totale"] = matches[3].group()
        break

    return a


def _extract_leave(text: str) -> tuple[dict, dict, dict]:
    """Return (ferie, ex_festivita, rol) dicts.

    FERIE and EX FESTIVITA appear on the same line in this format:
      FE R IE  <4 amounts>  E X  F E ST I VI TA'  <4 amounts>
    ROL appears on its own line with 3 amounts (no 'goduti' column).
    """
    mk = lambda: {"anni_prec": "", "maturati": "", "goduti": "", "residui": ""}
    ferie, ex_fest, rol = mk(), mk(), mk()

    # FERIE + EX FESTIVITA on the same line (8 amounts total)
    fer_m = re.search(
        r"F\s*E\s*R\s*I\s*E\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)"
        r".*?"
        r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)",
        text,
    )
    if fer_m:
        ferie["anni_prec"] = fer_m.group(1)
        ferie["maturati"] = fer_m.group(2)
        ferie["goduti"] = fer_m.group(3)
        ferie["residui"] = fer_m.group(4)
        ex_fest["anni_prec"] = fer_m.group(5)
        ex_fest["maturati"] = fer_m.group(6)
        ex_fest["goduti"] = fer_m.group(7)
        ex_fest["residui"] = fer_m.group(8)

    # ROL: "R OL" or "ROL" followed by 3 amounts (anni_prec, maturati, residui; goduti implicit 0)
    rol_m = re.search(r"R\s*OL\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)", text)
    if rol_m:
        rol["anni_prec"] = rol_m.group(1)
        rol["maturati"] = rol_m.group(2)
        rol["goduti"] = ""
        rol["residui"] = rol_m.group(3)

    return ferie, ex_fest, rol


def _extract_netto(text: str) -> str:
    # NETTO appears as a column header; the value is on the following line, last amount
    netto_m = re.search(r"NETTO\s*\n(.*)", text)
    if netto_m:
        return _last_amount(netto_m.group(1))
    # Fallback: look for ARROTOND and NETTO together, value follows
    arr_m = re.search(r"ARROTOND.*?NETTO.*?\n\s*([\d.,]+)\s+([\d.,]+)", text, re.DOTALL)
    if arr_m:
        return arr_m.group(2)
    return ""


def _extract_iban_banca(text: str) -> tuple[str, str]:
    iban = ""
    banca = ""

    # IBAN and bank appear on the ACCREDITO line, all characters spaced out:
    # "A  C C R  E D  IT  O   I T 6 8  / K / ...  -  F I N  E C O B  A N K  S P A  - ..."
    acc_m = re.search(r"A\s*C\s*C\s*R\s*E\s*D\s*I\s*T\s*O(.*?)(?:\n|$)", text, re.IGNORECASE)
    if acc_m:
        acc_line = acc_m.group(1)
        # Collapse spaces and slashes to reconstruct IBAN and bank name
        collapsed = re.sub(r"[\s/]+", "", acc_line)
        iban_m = re.search(r"IT\d{2}[A-Z0-9]{22,25}", collapsed)
        if iban_m:
            iban = iban_m.group()

        # Bank name: find "-" separator after IBAN in the collapsed string,
        # then take the word(s) up to the next "-" or end
        parts = re.split(r"-", collapsed)
        for part in parts[1:]:
            # Skip parts that look like "SEDEDIROMA" (city/location suffixes)
            if re.search(r"(SEDE|ROMA|MILANO|DI[A-Z]{3,})", part, re.I):
                break
            candidate = part.strip()
            if candidate and re.search(r"[A-Z]{4,}", candidate):
                # Insert spaces before known patterns (BANK, SPA, etc.)
                banca = re.sub(r"(BANK|BANCA)(SPA|SRL)?", r" \1 \2", candidate).strip()
                banca = re.sub(r"\s+", " ", banca).strip()
                break

    return iban, banca


def _extract_progressivi(text: str) -> dict:
    p = {"imponibile_contributi": "", "contributi": "", "imponibile_inail": "",
         "imponibile_irpef": "", "detrazioni": "", "irpef_pagata": ""}

    # Header: "IMPONIBILE CONTRIBUTI  CONTRIBUTI  IMPONIBILE INAIL  IMPONIBILE IRPEF ... IRPEF PAGATA"
    # Data line immediately below (single line): amounts with large gap before irpef_pagata
    prog_m = re.search(
        r"IMPONIBILE\s+CONTRIBUTI.*?IRPEF\s+PAGATA[^\n]*\n([^\n]+)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if prog_m:
        data_line = prog_m.group(1)
        amounts = AMOUNT_RE.findall(data_line)
        if len(amounts) >= 4:
            p["imponibile_contributi"] = amounts[0]
            p["contributi"] = amounts[1]
            p["imponibile_inail"] = amounts[2]
            p["imponibile_irpef"] = amounts[3]
        if len(amounts) >= 5:
            p["irpef_pagata"] = amounts[-1]

    return p


def _extract_tfr(text: str) -> dict:
    t = {"fondo_in_azienda": "", "mese": "", "spettante": ""}

    # TFR data line appears after "DATA VALUTA" header line, with one intermediate line
    # (a small counter value like "6 0") between the header and the data.
    tfr_m = re.search(
        r"DATA\s+VALUTA[^\n]*\n[^\n]*\n\s*([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)",
        text, re.IGNORECASE,
    )
    if tfr_m:
        t["fondo_in_azienda"] = tfr_m.group(1)
        t["mese"] = tfr_m.group(2)
        t["spettante"] = tfr_m.group(3)

    return t


# ─── Plugin class ─────────────────────────────────────────────────────────────

@register
class RoncalliPlugin(CedolinoPlugin):
    name = "roncalli"
    description = "Roncalli Software S.r.l. cedolino paga (Italian payslip)"

    @classmethod
    def can_handle(cls, pdf_path: str) -> bool:
        try:
            from markitdown import MarkItDown
            text = MarkItDown().convert(pdf_path).text_content
            has_signature = any(fp in text for fp in _FINGERPRINTS)
            has_payslip = "IVS" in text and "IRPEF" in text
            return has_signature and has_payslip
        except Exception:
            return False

    @classmethod
    def extract(cls, pdf_path: str) -> dict:
        text = _get_text(pdf_path)
        result = empty_cedolino()
        result["plugin"] = cls.name

        result["company"] = _extract_company(text)
        result["periodo"] = _extract_periodo(text)
        result["employee"] = _extract_employee(text)
        result["elementi_retribuzione"] = _extract_elementi_retribuzione(text)

        items, total_comp, total_tratt = _extract_items(text)
        result["items"] = items
        result["totali"]["competenza"] = total_comp
        result["totali"]["trattenuta"] = total_tratt

        result["contributi"] = _extract_contributi(text)
        result["irpef"] = _extract_irpef(text)
        result["addizionali"] = _extract_addizionali(text)

        ferie, ex_fest, rol = _extract_leave(text)
        result["ferie"] = ferie
        result["ex_festivita"] = ex_fest
        result["rol"] = rol

        result["netto"] = _extract_netto(text)
        result["iban"], result["banca"] = _extract_iban_banca(text)
        result["progressivi_anno"] = _extract_progressivi(text)
        result["tfr"] = _extract_tfr(text)

        return result
