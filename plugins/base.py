"""Abstract base class and shared schema for cedolino plugins."""

from abc import ABC, abstractmethod
import copy


ITEM_SCHEMA: dict = {
    "voce": "",
    "descrizione": "",
    "quantita": "",
    "base": "",
    "competenza": "",
    "trattenuta": "",
}

CEDOLINO_SCHEMA: dict = {
    "plugin": "",
    "company": {
        "name": "",
        "address": "",
        "cap": "",
        "city": "",
        "cf": "",
        "matricola_inps": "",
        "pat_inail": "",
    },
    "employee": {
        "matricola": "",
        "cognome": "",
        "nome": "",
        "cf": "",
        "data_nascita": "",
        "qualifica": "",
        "livello": "",
        "mansione": "",
        "data_assunzione": "",
    },
    "periodo": {
        "mese": "",
        "anno": "",
    },
    "elementi_retribuzione": {
        "minimo": "",
        "contingenza": "",
        "edr": "",
        "superminimo": "",
        "totale": "",
    },
    # Central list — the only variable-length section
    "items": [],
    "totali": {
        "competenza": "",
        "trattenuta": "",
    },
    "contributi": {
        "ivs_imponibile": "",
        "ivs_contributi": "",
        "add_ivs_imponibile": "",
        "add_ivs_contributi": "",
        "totale": "",
    },
    "irpef": {
        "reddito": "",
        "imponibile": "",
        "lorda": "",
        "detrazioni": "",
        "totale_mese": "",
    },
    "addizionali": {
        "reg_anno": "",
        "com_anno": "",
        "reg_ap": "",
        "com_acc_saldo": "",
        "totale": "",
    },
    "ferie": {"anni_prec": "", "maturati": "", "goduti": "", "residui": ""},
    "ex_festivita": {"anni_prec": "", "maturati": "", "goduti": "", "residui": ""},
    "rol": {"anni_prec": "", "maturati": "", "goduti": "", "residui": ""},
    "netto": "",
    "iban": "",
    "banca": "",
    "progressivi_anno": {
        "imponibile_contributi": "",
        "contributi": "",
        "imponibile_inail": "",
        "imponibile_irpef": "",
        "detrazioni": "",
        "irpef_pagata": "",
    },
    "tfr": {
        "fondo_in_azienda": "",
        "mese": "",
        "spettante": "",
    },
}


def empty_cedolino() -> dict:
    return copy.deepcopy(CEDOLINO_SCHEMA)


def empty_item() -> dict:
    return copy.deepcopy(ITEM_SCHEMA)


class CedolinoPlugin(ABC):
    """Base class every cedolino-format plugin must extend."""

    name: str = ""
    description: str = ""

    @classmethod
    @abstractmethod
    def can_handle(cls, pdf_path: str) -> bool:
        """Return True when this plugin recognises and can parse the file.

        Must be fast (check only first few KB of text) and never raise.
        """
        ...

    @classmethod
    @abstractmethod
    def extract(cls, pdf_path: str) -> dict:
        """Parse pdf_path and return a dict matching CEDOLINO_SCHEMA.

        The 'items' key holds the variable-length central list.
        Unparseable fields must be empty strings, not omitted.
        """
        ...
