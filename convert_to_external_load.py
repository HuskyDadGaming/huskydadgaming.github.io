"""
One-time converter: switch dungeon HTMLs from inline-IIFE filter logic
to external <script src="smart_filter_block.js"> load.

After running this with --apply, smart_filter_block.js becomes the SINGLE
source of truth. Edits to that file propagate to all dungeon pages and
Find Loot automatically. patch_dungeons.py becomes obsolete.

USAGE:
    cd C:\\KCraftDungeons
    python convert_to_external_load.py             # dry run (default)
    python convert_to_external_load.py --apply     # actually modify

Idempotent and safe to re-run. Reports per file:
    OK     — already external-load, no change
    PATCH  — would convert / converted
    SKIP   — file not found
    WARN   — unexpected structure, manual fix needed (won't modify)

The converter looks for the inline filter IIFE (signature: an IIFE that
sets window.KCraftFilter) and:

  1. If the IIFE is the ONLY code in its <script>...</script> block,
     replaces the whole block with <script src="smart_filter_block.js">.
  2. If the IIFE shares a <script> with other code, removes just the
     IIFE and inserts a <script src="..."> tag right before that block.

Backups: pass --backup to write `<filename>.bak` before each modification.
"""
import argparse
import re
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

EXTERNAL_TAG = '<script src="smart_filter_block.js"></script>'

# Detects either the marker-comment form OR a bare IIFE that defines KCraftFilter.
# Captures the full block so we can excise it.
IIFE_RE = re.compile(
    r"(?P<marker>//\s*=+\s*KCraft smart filter logic\s*=+\s*\n\s*)?"
    r"(?P<iife>\(function\s*\([^)]*\)\s*\{[^\x00]*?"
    r"\.KCraftFilter\s*=\s*\{[^\x00]*?\}\s*;\s*\}\s*\)\s*\([^)]*\)\s*;)",
    re.DOTALL,
)


def find_enclosing_script(html: str, span: tuple) -> tuple | None:
    """Given a (start, end) span inside an HTML doc, find the enclosing
    <script>...</script> block. Returns (script_open_start, script_close_end,
    body_start) or None if not enclosed by a script tag."""
    start, end = span
    # Find the most recent <script ...> opener before `start`
    open_re = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
    last_open = None
    for m in open_re.finditer(html, 0, start):
        last_open = m
    if last_open is None:
        return None
    body_start = last_open.end()
    # Find the next </script> after `end`
    close_match = re.search(r"</script\s*>", html[end:], re.IGNORECASE)
    if close_match is None:
        return None
    close_end = end + close_match.end()
    # Sanity: the opener's tag must not have a `src=` attribute
    if "src=" in last_open.group(0):
        return None
    return last_open.start(), close_end, body_start, end + close_match.start()


def convert_html(html: str) -> tuple[str, str]:
    """Returns (new_html, status). new_html is unchanged if status starts OK/SKIP/WARN."""
    if EXTERNAL_TAG in html and "KCraftFilter = {" not in html:
        return html, "OK     external-load already, no inline IIFE"

    if EXTERNAL_TAG in html and "KCraftFilter = {" in html:
        # Both present — the inline IIFE is now redundant. Just remove it.
        m = IIFE_RE.search(html)
        if m is None:
            return html, "WARN   has external tag AND defines KCraftFilter, but couldn't locate IIFE"
        new_html = html[: m.start()] + html[m.end() :]
        return new_html, "PATCH  removed redundant inline IIFE (external already present)"

    m = IIFE_RE.search(html)
    if m is None:
        return html, "WARN   no inline IIFE found and no external script — manual check needed"

    enclosing = find_enclosing_script(html, m.span())
    if enclosing is None:
        return html, "WARN   IIFE not inside a <script> block — odd structure, manual fix"

    script_open_start, script_close_end, body_start, body_end_of_iife = enclosing
    body_before = html[body_start : m.start()]
    body_after = html[m.end() : body_end_of_iife]

    if body_before.strip() == "" and body_after.strip() == "":
        # Whole script block is just the IIFE — replace the entire block
        new_html = (
            html[:script_open_start]
            + EXTERNAL_TAG
            + html[script_close_end:]
        )
        return new_html, "PATCH  replaced standalone <script> with external load"
    else:
        # Script has other code — remove only the IIFE and insert
        # <script src="..."> immediately before the block
        new_html = (
            html[:script_open_start]
            + EXTERNAL_TAG
            + "\n"
            + html[script_open_start : m.start()]
            + html[m.end() : script_close_end]
            + html[script_close_end:]
        )
        return new_html, "PATCH  removed inline IIFE, inserted external load before <script>"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually write changes (default: dry run)")
    parser.add_argument("--backup", action="store_true", help="write <file>.bak before each modification")
    args = parser.parse_args()

    here = Path(__file__).parent
    sfb = here / "smart_filter_block.js"
    if not sfb.exists():
        sys.exit(f"smart_filter_block.js not found at {sfb}. Run from the dungeon folder.")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    if args.apply and args.backup:
        print("Backups: yes (.bak files)")
    print()

    for name in DUNGEON_FILES:
        path = here / name
        if not path.exists():
            print(f"  SKIP   {name} — file not found")
            continue
        original = path.read_text(encoding="utf-8")
        new_text, status = convert_html(original)
        print(f"  {status}  ({name})")
        if args.apply and new_text != original:
            if args.backup:
                (path.parent / (name + ".bak")).write_text(original, encoding="utf-8")
            path.write_text(new_text, encoding="utf-8")

    if not args.apply:
        print("\n(Dry run. Re-run with --apply to write changes.)")


if __name__ == "__main__":
    main()
