"""
One-time inserter: add <script src="kcraft_pills.js"> between smart_filter_block.js
and dungeon_filter.js in each dungeon HTML.

Idempotent — running it twice is a no-op.

USAGE:
    cd C:\\KCraftDungeons
    python add_kcraft_pills_tag.py             # dry run
    python add_kcraft_pills_tag.py --apply     # actually modify

After running with --apply, edit build_pages.py to also emit this tag in
future builds (so the inserter never needs to run again).
"""
import argparse
import sys
from pathlib import Path

DUNGEON_FILES = [
    "ragefire-chasm.html",
    "wailing-caverns.html",
    "the-deadmines.html",
    "shadowfang-keep.html",
    "the-stockade.html",
    "blackfathom-deeps.html",
    "gnomeregan.html",
    "razorfen-kraul.html",
    "scarlet-monastery.html",
]

NEW_TAG = '<script src="kcraft_pills.js"></script>'
ANCHOR_BEFORE = '<script src="dungeon_filter.js"></script>'
SMART_FILTER_TAG = '<script src="smart_filter_block.js"></script>'


def patch(html: str) -> tuple[str, str]:
    if NEW_TAG in html:
        return html, "OK     already present"
    if SMART_FILTER_TAG not in html:
        return html, "WARN   smart_filter_block.js script tag missing — manual fix needed"
    if ANCHOR_BEFORE not in html:
        # No dungeon_filter.js anchor — insert after smart_filter_block.js instead
        new_html = html.replace(
            SMART_FILTER_TAG,
            SMART_FILTER_TAG + "\n" + NEW_TAG,
            1,
        )
        return new_html, "PATCH  inserted after smart_filter_block.js (no dungeon_filter.js anchor found)"
    new_html = html.replace(
        ANCHOR_BEFORE,
        NEW_TAG + "\n" + ANCHOR_BEFORE,
        1,
    )
    return new_html, "PATCH  inserted before dungeon_filter.js"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    here = Path(__file__).parent
    if not (here / "kcraft_pills.js").exists():
        sys.exit("kcraft_pills.js not found in this folder. Drop it next to the dungeon HTMLs first.")
    if not (here / "smart_filter_block.js").exists():
        sys.exit("smart_filter_block.js not found in this folder.")

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    for name in DUNGEON_FILES:
        path = here / name
        if not path.exists():
            print(f"  SKIP   {name} — file not found")
            continue
        original = path.read_text(encoding="utf-8")
        new_text, status = patch(original)
        print(f"  {status}  ({name})")
        if args.apply and new_text != original:
            path.write_text(new_text, encoding="utf-8")

    if not args.apply:
        print("\n(Dry run. Re-run with --apply to write.)")


if __name__ == "__main__":
    main()
