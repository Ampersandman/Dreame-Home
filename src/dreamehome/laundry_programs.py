"""Exact L9 app program identities with consistent English display names.

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
_KNOWN_CODES = {WASHER: frozenset(range(20)) | {21, 22}, DRYER: frozenset(range(31))}
_GROUPS = {
    "wash": {"en": "Wash"},
    "dry": {"en": "Dry"},
    "care": {"en": "Care"},
    "additional": {"en": "Cloud programs"},
}
# Translate the visible app names where the source's English string describes a
# different garment or differs from the supplied app program list. The source
# string remains separate from presentation so write validation never depends
# on a translated label.
_DISPLAY_OVERRIDES = {
    WASHER: {8: "Underwear", 10: "Outerwear", 11: "Anti-Allergen", 16: "Shirts"},
    DRYER: {7: "Baby Care", 8: "Underwear", 11: "Outerwear", 19: "Cold Air"},
}


def program_language(language=None):
    """Keep the integration's program presentation English for every HA locale."""
    return "en"


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
    if ({row["value"] for row in rows} != _KNOWN_CODES[model]
            or len(rows) != len(_KNOWN_CODES[model])
            or any(type(row["value"]) is not int for row in rows)):
        raise ValueError("Program identities differ from exact source codes")
    result = []
    for row in rows:
        code = row["value"]
        group = ("additional" if code in _WASHER_CLOUD else "wash") if model == WASHER else (
            "dry" if code < 16 else "care" if code < 25 else "additional")
        minutes = row.get("default_duration_minutes", row.get("default_minutes"))
        label = _DISPLAY_OVERRIDES[model].get(code, row["label"])
        result.append({"value": code, "label": label, "source_label": row["label"],
                       "labels": {"en": label},
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
    """Bijective English labels, independent of the HA or frontend locale.

    The optional language argument remains accepted for existing consumers.
    Duplicate care/dry names are distinguished by their English group name.
    """
    language = "en"
    rows = program_catalog(model, include_additional=include_additional)
    names = [row["labels"][language] for row in rows if row["standard"]]
    pairs = []
    for row in rows:
        label = row["labels"][language]
        if not row["standard"] or names.count(label) > 1:
            label = row["group_labels"][language] + ": " + label
        pairs.append((label, row["value"]))
    if len({label for label, _ in pairs}) != len(pairs):
        raise ValueError("English program choices are not unique")
    return tuple(pairs)
