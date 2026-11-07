"""Compare loader_column_types.py outputs: python compare_column_types.py DIR

DIR holds polars-VERSION.CODE.json, with CODE one of published, patched, and guarded.
"""

import json
import sys
from pathlib import Path


def outcome(old, new):
    old_failed, new_failed = old.startswith("ERROR"), new.startswith("ERROR")
    if old_failed and new_failed:
        return "both fail"
    if new_failed:
        return "newly fails"
    if old_failed:
        return "newly works"
    return "same" if old == new else "ROWS DIFFER"


def tally(published, other):
    kinds = {}
    for case, old in published.items():
        kind = case.split("|")[0]
        result = outcome(old, other[case])
        kinds.setdefault(kind, {}).setdefault(result, 0)
        kinds[kind][result] += 1
    return kinds


directory = Path(sys.argv[1])
versions = sorted({p.name.split(".published")[0] for p in directory.glob("*.published.json")})
for version in versions:
    code = {name: json.loads((directory / f"{version}.{name}.json").read_text()) for name in ("published", "patched", "guarded")}
    print(f"\n{version}: published {code['published']['data']}, patched {code['patched']['data']}, guarded {code['guarded']['data']}")
    print(f"  {'column':15s} {'both patches':26s} guarded")
    patched, guarded = tally(code["published"]["out"], code["patched"]["out"]), tally(code["published"]["out"], code["guarded"]["out"])
    for kind in patched:
        print(f"  {kind:15s} {str(patched[kind]):26s} {guarded[kind]}")
    print(f"  cases: {len(code['published']['out'])}")
