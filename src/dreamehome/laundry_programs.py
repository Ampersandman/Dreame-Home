"""Exact L9 app program identities and localized display information.

Standard choices match the model plugins' main program tabs. Cloud-program
codes remain recognizable, but are not selectable in the default HA profile.
Reference durations are source defaults, never live remaining-time estimates.
"""

from copy import deepcopy
from functools import lru_cache

from .catalog import load_catalog

WASHER = "dreame.washer.l9nacn"
DRYER = "dreame.dryer.l9nacn"
_CATALOGS = {WASHER: "l9_washer", DRYER: "l9_dryer"}
_WASHER_CLOUD = frozenset((7, 10, 15, 16, 17, 18, 19))
_DE = {
    WASHER: {
        0: "KI-Wäsche", 22: "ECO 40-60", 1: "Schnellwäsche", 2: "Gemischt",
        3: "Große Gegenstände", 4: "Baumwolle", 5: "Daunen", 6: "Wolle",
        21: "Handtücher", 8: "Unterwäsche", 9: "Baby-pflege", 11: "Anti-Allergen",
        # Vendor German says 'Nur schleud'; the English Spin Only proves the
        # complete meaning without relying on the truncated screenshot title.
        12: "Nur schleudern", 13: "Spülen + Schleudern", 14: "Trommel-Reinigung",
        15: "Farbpflege", 16: "Hemden", 17: "Tiefenreinigung", 18: "Sportbekleidung",
        19: "Schuluniform", 7: "Seide", 10: "Oberbekleidung",
    },
    DRYER: {
        0: "KI-Trocknen", 1: "Schnelltrocknen", 2: "Große Gegenstände", 3: "Wolle",
        4: "Daunen", 5: "ÖKO", 6: "Hemden", 7: "Baby-pflege", 8: "Unterwäsche",
        9: "Synthetik", 10: "Sportbekleidung", 11: "Oberbekleidung",
        12: "Kleine Ladung", 13: "Seide", 14: "Trocken desinfizieren", 15: "Tierhaare",
        18: "Heiße Luft", 19: "Kalte Luft", 16: "Quilt-Aktualisierung", 17: "Wolle",
        20: "Runter", 21: "Hemden", 22: "Seide", 23: "Baumwolle",
        24: "Hygienische Pflege", 25: "Farbpflege", 26: "Schuluniform",
        27: "Synthetik", 28: "Heimtextilien", 29: "Lufttrocknen", 30: "Denim",
    },
}
_GROUPS = {
    "wash": {"en": "Wash", "de": "Waschen"},
    "dry": {"en": "Dry", "de": "Trocknen"},
    "care": {"en": "Care", "de": "Pflege"},
    "additional": {"en": "Cloud programs", "de": "Cloud-Programme"},
}


def program_language(language=None):
    """Only explicitly provided German locales select German display strings."""
    return "de" if isinstance(language, str) and language.lower().replace("_", "-").split("-")[0] == "de" else "en"


@lru_cache(maxsize=2)
def _programs(model):
    catalog = load_catalog(_CATALOGS[model])
    if catalog.get("model") != model:
        raise ValueError("Program catalogue does not match its exact model")
    if model == WASHER:
        rows = catalog["programs"]
        table = {"module": "projects_dreame.washer.l9nacn_dictionary_index", "line": 1122}
        grouping = {"module": "projects_dreame.washer.l9nacn_views_Home_index", "lines": [11481, 11491, 11497]}
    else:
        selection = catalog["program_table_selection"]
        if selection["selected_table"] != "ProgramMode_W" or selection["is_export_sales_literal"] != 1:
            raise ValueError("Unexpected dryer export program table")
        selected = catalog["programs"]["ProgramMode_W"]
        rows, table = selected["values"], selected["provenance"]
        grouping = {"module": "projects_dreame.dryer.l9nacn_views_Home_index", "lines": [10269, 10303, 10310]}
    if {row["value"] for row in rows} != set(_DE[model]):
        raise ValueError("Localized program identities differ from source codes")
    result = []
    for row in rows:
        code = row["value"]
        group = ("additional" if code in _WASHER_CLOUD else "wash") if model == WASHER else (
            "dry" if code < 16 else "care" if code < 25 else "additional")
        minutes = row.get("default_duration_minutes", row.get("default_minutes"))
        result.append({"value": code, "label": row["label"],
                       "labels": {"en": row["label"], "de": _DE[model][code]},
                       "group": group, "group_labels": deepcopy(_GROUPS[group]),
                       "reference_duration_minutes": minutes if type(minutes) is int and minutes > 0 else None,
                       "reference_duration_kind": "source-default",
                       "standard": group != "additional",
                       "provenance": {"source": deepcopy(catalog["source"]), "table": deepcopy(table),
                                      "grouping": deepcopy(grouping),
                                      "translations": "assets/projects/" + model + "/assets/string/{en,de}.json"}})
    return tuple(result)


def program_catalog(model, *, include_additional=False):
    """Independent raw-code descriptors, in exact source order, for this model."""
    if model not in _CATALOGS:
        return []
    return deepcopy([row for row in _programs(model) if include_additional or row["standard"]])


def program_definition(model, value):
    """Recognize every source code without making additional choices writable."""
    if type(value) is not int:
        return None
    return next((row for row in program_catalog(model, include_additional=True) if row["value"] == value), None)


def program_option_pairs(model, language=None, *, include_additional=True):
    """Bijective localized labels; care choices are distinguished by their group."""
    language = program_language(language)
    rows = program_catalog(model, include_additional=include_additional)
    names = [row["labels"][language] for row in rows if row["standard"]]
    pairs = []
    for row in rows:
        label = row["labels"][language]
        if not row["standard"] or names.count(label) > 1:
            label = row["group_labels"][language] + ": " + label
        pairs.append((label, row["value"]))
    if len({label for label, _ in pairs}) != len(pairs):
        raise ValueError("Localized program choices are not unique")
    return tuple(pairs)
