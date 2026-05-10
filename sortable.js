/* sortable.js — Click-to-sort table headers on dungeon pages.
 *
 * Wires up every <table> inside a .boss-card so each boss's loot table can
 * be sorted independently. Tries to parse cell text as a number first
 * (handles "45.5%", "—", "1,234" → 45.5, null, 1234); falls back to
 * locale-aware string compare. Three click states: unsorted → asc → desc
 * (then back to asc on next click).
 *
 * Headers can opt out by adding class="no-sort" — used for the STATS
 * column where text-based sorting wouldn't be meaningful.
 *
 * Filtering and sorting are independent: smart_filter_block.js / dungeon_filter.js
 * use display:none to hide rows, leaving the DOM order intact, so a
 * sort applied before filtering survives any filter change.
 */
(function () {
    'use strict';

    function parseCellNumber(s) {
        if (!s) return null;
        const cleaned = s.replace(/[%,]/g, '').trim();
        if (cleaned === '' || cleaned === '—' || cleaned === '–') return null;
        const n = parseFloat(cleaned);
        return Number.isNaN(n) ? null : n;
    }

    function compareCells(aText, bText, dir) {
        const aNum = parseCellNumber(aText);
        const bNum = parseCellNumber(bText);
        let cmp;
        // If both parse as numbers, numeric compare. Otherwise null sinks to
        // the bottom of an ascending sort, so empty/dash rows don't pollute
        // the top.
        if (aNum !== null && bNum !== null) {
            cmp = aNum - bNum;
        } else if (aNum === null && bNum !== null) {
            cmp = 1;
        } else if (aNum !== null && bNum === null) {
            cmp = -1;
        } else {
            cmp = (aText || '').localeCompare(bText || '');
        }
        return dir === 'asc' ? cmp : -cmp;
    }

    function sortTable(table, colIdx, dir) {
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const aText = (a.children[colIdx]?.textContent || '').trim();
            const bText = (b.children[colIdx]?.textContent || '').trim();
            return compareCells(aText, bText, dir);
        });
        // Re-appending in order moves nodes — preserves event listeners,
        // data-* attributes, and the display:none state set by the filter.
        rows.forEach(r => tbody.appendChild(r));
    }

    function wireUpTable(table) {
        const ths = table.querySelectorAll('thead th');
        ths.forEach((th, idx) => {
            if (th.classList.contains('no-sort')) return;
            th.classList.add('sortable');
            th.addEventListener('click', () => {
                const wasAsc = th.classList.contains('sort-asc');
                // Clear all sort indicators on this table — only one column
                // is sorted at a time per boss.
                ths.forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
                const dir = wasAsc ? 'desc' : 'asc';
                th.classList.add('sort-' + dir);
                sortTable(table, idx, dir);
            });
        });
    }

    function init() {
        document.querySelectorAll('.boss-card table').forEach(table => {
            wireUpTable(table);
            // Items are server-side sorted by drop chance descending in
            // build_dungeons.py. Mark the DROP column accordingly so the
            // indicator matches the actual row order on first paint.
            const ths = table.querySelectorAll('thead th');
            const dropTh = ths[ths.length - 1];  // DROP is always last
            if (dropTh && !dropTh.classList.contains('no-sort')) {
                dropTh.classList.add('sort-desc');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
