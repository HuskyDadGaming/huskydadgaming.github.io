/* ---------------------------------------------------------------------------
 * dungeon_filter.js — filter logic for KCraft dungeon pages
 *
 * This is the DOM-walking renderer for dungeon pages. Each row already
 * exists in the HTML; this script just toggles `display:none` to filter.
 * All filter RULES live in smart_filter_block.js (window.KCraftFilter) —
 * shared with the Find Loot tab, so both pages give identical answers.
 *
 * Required scripts (in order):
 *   <script src="smart_filter_block.js"></script>  ← KCraftFilter API
 *   <script src="dungeon_filter.js"></script>       ← this file
 *
 * Required DOM:
 *   .filter-btn[data-role]            — role buttons (data-role="all|tank|heal|melee|ranged")
 *   #class-dropdown                   — class <select>
 *   #quality-dropdown                 — quality <select> (values: '', '2', '3', '4')
 *   #reset-filters                    — reset button
 *   .item-row                         — table rows with data-item-json (full item)
 *   .boss-card                        — wrapper cards (each with .no-loot fallback msg)
 *   #count-all, #count-tank, etc.     — live count spans inside the role buttons
 * --------------------------------------------------------------------------- */
(function () {
    'use strict';

    // Collapse all boss-cards before first paint. Runs synchronously when
    // this script tag is parsed (placed at the bottom of <body>, so all
    // .boss-card elements already exist). Avoids the flash-of-open-cards
    // on legacy HTMLs that still ship `open` from build_pages.py.
    document.querySelectorAll('.boss-card').forEach(c => { c.open = false; });

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        // -- guards ----------------------------------------------------------
        const KF = window.KCraftFilter;
        if (!KF || !KF.classFillsRole) {
            console.warn('[dungeon_filter] window.KCraftFilter not loaded — filter disabled');
            return;
        }

        const roleButtons     = document.querySelectorAll('.filter-btn[data-role]');
        const classDropdown   = document.getElementById('class-dropdown');
        const qualityDropdown = document.getElementById('quality-dropdown');
        const itemRows        = document.querySelectorAll('.item-row');
        const bossCards       = document.querySelectorAll('.boss-card');
        const resetBtn        = document.getElementById('reset-filters');
        const applyBtn        = document.getElementById('apply-filters');
        const filterDetails   = document.querySelector('.filter-bar-collapsible');
        const filterSummary   = document.querySelector('.filter-summary');

        // Mobile-only hint shown when no filter is applied AND the filter
        // is closed: instead of dumping the full loot list onto a phone
        // screen, ask the user to pick a filter first. Mirrors the Find
        // Loot pattern. Injected at runtime so the existing 9 dungeon
        // HTMLs get this without needing a rebuild.
        let mobileHint = document.getElementById('mobile-filter-hint');
        if (!mobileHint && filterDetails && filterDetails.parentNode) {
            mobileHint = document.createElement('div');
            mobileHint.id = 'mobile-filter-hint';
            mobileHint.textContent = 'Pick a filter above to see loot.';
            mobileHint.style.cssText =
                'display:none;text-align:center;padding:3rem 1rem;' +
                'color:#666;font-style:italic;';
            filterDetails.parentNode.insertBefore(
                mobileHint, filterDetails.nextSibling);
        }

        // Collapse filter bar by default on mobile so items are visible
        // immediately on page load. HTML defaults to <details open> for the
        // no-JS / desktop case; we close it here only when the viewport is
        // narrow. Once the user toggles it, we don't fight them on resize.
        if (filterDetails && window.innerWidth <= 600) {
            filterDetails.open = false;
        }

        // When the user expands the filter, scroll the page so the filter
        // lands at the top of the viewport. Without this, expanding from
        // mid-scroll leaves the now-tall filter sticky-overlapping whatever
        // the user was reading; they'd have to scroll up by hand to see all
        // the controls. The toggle event fires after the open state changes,
        // so checking filterDetails.open tells us the new state.
        if (filterDetails) {
            filterDetails.addEventListener('toggle', () => {
                syncMobileFilterFocus();
                if (filterDetails.open) {
                    filterDetails.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        }

        // Mobile-only: when the filter is open, hide everything else on
        // the page so the filter ends up at the top of the visible area
        // naturally (no scroll tricks, no fixed-position gymnastics).
        // That means: navbar, anything in the container BEFORE the filter
        // (back link, h1, intro, summary), AND boss-cards + trash-section
        // AFTER. Closing restores everything and applyFilters() re-runs.
        function getElementsAroundFilter() {
            const navbar = document.querySelector('.navbar');
            const beforeFilter = [];
            if (filterDetails && filterDetails.parentElement) {
                for (const child of filterDetails.parentElement.children) {
                    if (child === filterDetails) break;
                    beforeFilter.push(child);
                }
            }
            return { navbar, beforeFilter };
        }
        let prevFilterFocusMode = false;
        function syncMobileFilterFocus() {
            if (!filterDetails) return;
            const isMobile = window.innerWidth <= 600;
            const focusMode = isMobile && filterDetails.open;
            const { navbar, beforeFilter } = getElementsAroundFilter();
            if (focusMode) {
                bossCards.forEach(c => { c.style.display = 'none'; });
                const trashSection = document.querySelector('.trash-section');
                if (trashSection) trashSection.style.display = 'none';
                if (navbar) navbar.style.display = 'none';
                beforeFilter.forEach(el => { el.style.display = 'none'; });
                // Clear any leftover inline styles from earlier
                // position:fixed attempts so the filter sits in flow
                // at the (now-empty) top of the page.
                Object.assign(filterDetails.style, {
                    position: '', top: '', left: '', right: '',
                    zIndex: '', maxHeight: '', overflowY: '',
                });
            } else {
                if (navbar) navbar.style.display = '';
                beforeFilter.forEach(el => { el.style.display = ''; });
                applyFilters();
                // Mirror the Find Loot Apply behaviour: when the filter
                // closes from full-screen focus, scroll the collapsed bar
                // to the top of the viewport so results land directly
                // below it instead of leaving the user mid-page next to
                // the navbar/intro. Only fire on the focus → no-focus
                // transition so we don't scroll on initial page load.
                if (prevFilterFocusMode) {
                    filterDetails.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
            prevFilterFocusMode = focusMode;
        }

        if (!roleButtons.length || !classDropdown) return;  // page lacks scaffolding

        // -- KCraftFilter handles ------------------------------------------
        const ROLE_CLASSES   = KF.ROLE_CLASSES;
        const ALL_CLASSES    = ROLE_CLASSES[''] || [];
        const passesArmor    = KF.passesClassArmor;
        const classFillsRole = KF.classFillsRole;

        // Build CLASS → fillable roles, derived from ROLE_CLASSES so we
        // never duplicate the membership rule.
        const CLASS_ROLES = {};
        ALL_CLASSES.forEach(c => { CLASS_ROLES[c] = []; });
        ['tank', 'heal', 'melee', 'ranged'].forEach(r => {
            (ROLE_CLASSES[r] || []).forEach(c => {
                if (CLASS_ROLES[c]) CLASS_ROLES[c].push(r);
            });
        });

        // -- parse and cache item objects from the rows --------------------
        // build_pages.py already stamps a JSON blob on every row for the
        // tooltip; we reuse it for filter logic so we never duplicate data.
        const rowItem = new Map();
        itemRows.forEach(row => {
            const raw = row.getAttribute('data-item-json');
            if (!raw) return;
            try {
                rowItem.set(row, JSON.parse(raw.replace(/&quot;/g, '"')));
            } catch (e) {
                // Bad JSON — skip silently; row will still render but filter
                // will treat it as a no-op match.
            }
        });

        // -- state ---------------------------------------------------------
        let activeRole    = 'all';
        let activeClass   = 'all';
        let activeQuality = '';   // '' = any; '2' = ≥uncommon; '3' = ≥rare; '4' = epic only

        // Mirrors index.html applyFilters logic — single source of truth for
        // "would this item pass with class X and role Y?".
        function rowMatchesWith(item, cls, role) {
            if (!item) return true;  // graceful fallback for unparseable rows
            if (cls !== 'all') {
                if (!item.classes || !item.classes.includes(cls)) return false;
                // When ONLY class is selected, apply strict armor floor
                // (warriors don't see cloth they're "technically proficient"
                // with). Armor floor moves with role inside classFillsRole.
                if (role === 'all' && !passesArmor(item, cls, null)) return false;
            }
            if (role !== 'all') {
                if (cls !== 'all') {
                    if (!classFillsRole(item, cls, role)) return false;
                } else {
                    // No class selected: any class proficient with this item
                    // could fulfil the role.
                    const anyMatch = (item.classes || []).some(
                        c => classFillsRole(item, c, role)
                    );
                    if (!anyMatch) return false;
                }
            }
            // Quality threshold pulled from closure so role/class counts
            // automatically reflect "what would I see if I picked this?"
            // under the current quality selection.
            if (activeQuality !== '') {
                const q = (item.quality === undefined || item.quality === null) ? -1 : item.quality;
                const t = parseInt(activeQuality, 10);
                if (t === 4) {
                    if (q !== 4) return false;       // Epic only
                } else if (q < t) {
                    return false;                    // Uncommon/Rare and above
                }
            }
            return true;
        }

        // -- counts --------------------------------------------------------

        function updateRoleCounts() {
            const counts = { all: 0, tank: 0, heal: 0, melee: 0, ranged: 0 };
            itemRows.forEach(row => {
                const it = rowItem.get(row);
                ['all', 'tank', 'heal', 'melee', 'ranged'].forEach(r => {
                    if (rowMatchesWith(it, activeClass, r)) counts[r]++;
                });
            });

            ['all', 'tank', 'heal', 'melee', 'ranged'].forEach(r => {
                const el = document.getElementById('count-' + r);
                if (el) el.textContent = counts[r];
            });

            // Hide role buttons whose count is zero under the active class.
            roleButtons.forEach(btn => {
                const role = btn.dataset.role;
                if (role !== 'all') {
                    btn.style.display = (activeClass !== 'all' && counts[role] === 0)
                        ? 'none' : '';
                }
            });
        }

        function updateClassDropdown() {
            const counts = { all: 0 };
            ALL_CLASSES.forEach(c => counts[c] = 0);

            itemRows.forEach(row => {
                const it = rowItem.get(row);
                if (rowMatchesWith(it, 'all', activeRole)) counts.all++;
                ALL_CLASSES.forEach(c => {
                    if (rowMatchesWith(it, c, activeRole)) counts[c]++;
                });
            });

            // Rebuild the dropdown options from scratch.
            classDropdown.innerHTML = '';
            const allOpt = document.createElement('option');
            allOpt.value = 'all';
            allOpt.textContent = `All classes (${counts.all})`;
            classDropdown.appendChild(allOpt);

            const validClasses = activeRole === 'all'
                ? ALL_CLASSES
                : (ROLE_CLASSES[activeRole] || ALL_CLASSES);

            // Sort alphabetically by display name (e.g. "Death Knight" before
            // "Druid", "Warlock" before "Warrior") so users can scan by name.
            const sortedClasses = [...validClasses].sort((a, b) => {
                const aLabel = a === 'dk' ? 'death knight' : a;
                const bLabel = b === 'dk' ? 'death knight' : b;
                return aLabel.localeCompare(bLabel);
            });

            sortedClasses.forEach(cls => {
                if (counts[cls] > 0) {
                    const opt = document.createElement('option');
                    opt.value = cls;
                    const display = (cls === 'dk') ? 'Death Knight'
                                  : cls.charAt(0).toUpperCase() + cls.slice(1);
                    opt.textContent = `${display} (${counts[cls]})`;
                    classDropdown.appendChild(opt);
                }
            });

            // Auto-reset activeClass if it's no longer a valid option (matches
            // Find Loot behaviour — prevents the "0 results, why?" trap).
            const optionExists = Array.from(classDropdown.options)
                .some(o => o.value === activeClass);
            if (!optionExists) {
                activeClass = 'all';
            }
            classDropdown.value = activeClass;
        }

        // -- pill visibility within visible rows ---------------------------
        // The pill's title attribute holds the human name (e.g. "Death Knight"),
        // but activeClass and classFillsRole use the slug ("dk"). For every
        // class except DK these strings match after lowercasing — DK is the
        // outlier and needs an explicit map back to its slug.
        const TITLE_TO_SLUG = { 'death knight': 'dk' };
        const pillSlugOf = pill =>
            TITLE_TO_SLUG[(pill.getAttribute('title') || '').toLowerCase()] ||
            (pill.getAttribute('title') || '').toLowerCase();

        function refinePills(row, item) {
            // Class pills: which classes get shown on this specific row?
            row.querySelectorAll('.class-pill').forEach(pill => {
                const pillClass = pillSlugOf(pill);
                let show = true;
                if (activeClass !== 'all') {
                    show = (pillClass === activeClass);
                } else if (activeRole !== 'all') {
                    // Show classes that actually fill the active role for THIS item
                    show = item ? classFillsRole(item, pillClass, activeRole)
                                : (ROLE_CLASSES[activeRole] || []).includes(pillClass);
                }
                pill.style.display = show ? '' : 'none';
            });

            // Role pills: AND of class-allows-role and selected-role match.
            row.querySelectorAll('.role-pill').forEach(pill => {
                const pillTitle = (pill.getAttribute('title') || '').toLowerCase();
                let pillRole = null;
                if (pillTitle.includes('tank')) pillRole = 'tank';
                else if (pillTitle.includes('healer')) pillRole = 'heal';
                else if (pillTitle.includes('melee')) pillRole = 'melee';
                else if (pillTitle.includes('ranged')) pillRole = 'ranged';
                if (!pillRole) { pill.style.display = ''; return; }

                let classAllowed = true;
                if (activeClass !== 'all') {
                    classAllowed = item
                        ? classFillsRole(item, activeClass, pillRole)
                        : (CLASS_ROLES[activeClass] || []).includes(pillRole);
                }
                const roleAllowed = (activeRole === 'all') || (pillRole === activeRole);
                pill.style.display = (classAllowed && roleAllowed) ? '' : 'none';
            });
        }

        // -- main render ---------------------------------------------------
        function applyFilters() {
            // Mobile: while the filter is open, defer all card/trash
            // rendering until Apply (filter close). The user sees clean
            // filter UI with live counts on the role buttons; loot only
            // materialises once they commit. Counts/dropdown still update
            // because rowMatchesWith is independent of row display state.
            if (window.innerWidth <= 600 && filterDetails && filterDetails.open) {
                bossCards.forEach(c => { c.style.display = 'none'; });
                const ts = document.querySelector('.trash-section');
                if (ts) ts.style.display = 'none';
                if (mobileHint) mobileHint.style.display = 'none';
                updateRoleCounts();
                updateClassDropdown();
                updateFilterSummary();
                return;
            }

            itemRows.forEach(row => {
                const it = rowItem.get(row);
                if (rowMatchesWith(it, activeClass, activeRole)) {
                    row.style.display = '';
                    refinePills(row, it);
                } else {
                    row.style.display = 'none';
                }
            });

            // Show/hide boss cards based on filter results.
            //
            // Three cases:
            //   1. Placeholder boss (no <.item-row> in HTML at all — server
            //      had no loot for it at the configured quality floor).
            //      ALWAYS shown so users still see the boss exists. The
            //      built-in "no loot at this quality" message stays visible.
            //   2. Boss with items, some pass current filters: card shown
            //      with its table.
            //   3. Boss with items, ALL filtered out: hide the entire card —
            //      avoids cluttering the page with empty boss cards when
            //      the user is filtering by class/role/quality.
            bossCards.forEach(card => {
                const allRows = card.querySelectorAll('.item-row');
                const isPlaceholder = allRows.length === 0;
                if (isPlaceholder) {
                    card.style.display = '';
                    return;
                }
                const visibleRows = card.querySelectorAll(
                    '.item-row:not([style*="display: none"])'
                );
                if (visibleRows.length === 0) {
                    card.style.display = 'none';
                } else {
                    card.style.display = '';
                    const table  = card.querySelector('table');
                    const noLoot = card.querySelector('.no-loot');
                    if (noLoot) noLoot.style.display = 'none';
                    if (table)  table.style.display  = '';
                }
            });

            // Trash section is a <details> wrapping a set of boss-cards.
            // If filtering hides all of them, hide the whole section so the
            // collapsible header doesn't sit there with nothing inside.
            const trashSection = document.querySelector('.trash-section');
            if (trashSection) {
                const trashCards = trashSection.querySelectorAll('.boss-card');
                const anyVisible = Array.from(trashCards)
                    .some(c => c.style.display !== 'none');
                trashSection.style.display = anyVisible ? '' : 'none';
            }

            // Auto-expand boss-cards when a role or class filter is active so
            // the matching loot is visible immediately. Collapse back to the
            // default scan-friendly layout when filters reset to all/all.
            // Quality alone doesn't trigger the open — it's a refinement, not
            // a "show me what I'm looking for" intent. The trash-section
            // wrapper follows the same rule so trash matches aren't hidden
            // behind its collapsed summary when a filter is on.
            const filterActive = activeRole !== 'all' || activeClass !== 'all';
            bossCards.forEach(card => { card.open = filterActive; });
            if (trashSection) trashSection.open = filterActive;

            // Mobile: with no filter applied AND the filter closed, hide
            // every boss-card/trash and show the "pick a filter" hint.
            // Filter open = focus mode (handled by syncMobileFilterFocus
            // separately) so we explicitly skip the hint there — the user
            // is already mid-interaction with the filter.
            const isMobile = window.innerWidth <= 600;
            const noFilter = activeRole === 'all' && activeClass === 'all'
                             && activeQuality === '';
            const showHint = isMobile && noFilter && !filterDetails.open;
            if (showHint) {
                bossCards.forEach(c => { c.style.display = 'none'; });
                if (trashSection) trashSection.style.display = 'none';
            }
            if (mobileHint) {
                mobileHint.style.display = showHint ? 'block' : 'none';
            }

            updateRoleCounts();
            updateClassDropdown();
            updateFilterSummary();
        }

        // Refresh the collapsed-state filter summary text so users can see
        // at a glance which filters are active without expanding. Called
        // every applyFilters() so it stays current when toggles happen.
        function updateFilterSummary() {
            if (!filterSummary) return;

            const ROLE_NAMES = {
                tank: '🛡 Tank', heal: '+ Healer',
                melee: '⚔ Melee', ranged: '🏹 Ranged'
            };
            const QUALITY_NAMES = {
                '2': 'Uncommon+', '3': 'Rare+', '4': 'Epic only'
            };

            const parts = [];
            if (activeRole !== 'all') {
                parts.push(ROLE_NAMES[activeRole] || activeRole);
            }
            if (activeClass !== 'all') {
                // Pick the class display name out of the dropdown's selected option
                const opt = classDropdown.options[classDropdown.selectedIndex];
                if (opt) parts.push(opt.textContent.replace(/\s*\(\d+\)\s*$/, ''));
            }
            if (activeQuality) {
                parts.push(QUALITY_NAMES[activeQuality] || '');
            }

            const visible = Array.from(itemRows).filter(r => r.style.display !== 'none').length;
            const total = itemRows.length;

            let text;
            if (parts.length === 0) {
                text = `🔧 Filters · all ${total} items`;
            } else {
                const itemWord = visible === 1 ? 'item' : 'items';
                text = `🔧 Filters · ${parts.join(' · ')} · ${visible} ${itemWord}`;
            }
            filterSummary.textContent = text;
        }

        // -- wiring --------------------------------------------------------
        roleButtons.forEach(button => {
            button.addEventListener('click', () => {
                roleButtons.forEach(b => b.classList.remove('active'));
                button.classList.add('active');
                activeRole = button.dataset.role;

                // If the locked class can't fulfil the new role, drop class.
                if (activeRole !== 'all' && activeClass !== 'all') {
                    const validClasses = ROLE_CLASSES[activeRole] || [];
                    if (!validClasses.includes(activeClass)) activeClass = 'all';
                }
                applyFilters();
            });
        });

        classDropdown.addEventListener('change', () => {
            activeClass = classDropdown.value;
            // If active role isn't fillable by the new class, drop role.
            if (activeClass !== 'all' && activeRole !== 'all') {
                const validRoles = CLASS_ROLES[activeClass] || [];
                if (!validRoles.includes(activeRole)) {
                    activeRole = 'all';
                    roleButtons.forEach(btn => {
                        btn.classList.toggle('active', btn.dataset.role === 'all');
                    });
                }
            }
            applyFilters();
        });

        if (qualityDropdown) {
            qualityDropdown.addEventListener('change', () => {
                activeQuality = qualityDropdown.value;
                applyFilters();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                activeRole    = 'all';
                activeClass   = 'all';
                activeQuality = '';
                roleButtons.forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.role === 'all');
                });
                classDropdown.value = 'all';
                if (qualityDropdown) qualityDropdown.value = '';
                applyFilters();
            });
        }

        // Apply button: filters already update live as the user picks options,
        // so this is purely a UI signal — "I'm done, collapse this and let me
        // see results". Closes the filter <details> if present.
        if (applyBtn) {
            applyBtn.addEventListener('click', () => {
                if (filterDetails) filterDetails.open = false;
            });
        }

        // Expand all / Collapse all — manual override of the auto-open logic
        // in applyFilters(). Toggles every boss-card AND the trash-section
        // wrapper so the user can survey the entire dungeon at once or
        // collapse everything back to the scan-friendly default.
        const expandAllBtn   = document.getElementById('expand-all');
        const collapseAllBtn = document.getElementById('collapse-all');
        function setAllOpen(open) {
            bossCards.forEach(c => { c.open = open; });
            const trashSection = document.querySelector('.trash-section');
            if (trashSection) trashSection.open = open;
        }
        if (expandAllBtn)   expandAllBtn.addEventListener('click',   () => setAllOpen(true));
        if (collapseAllBtn) collapseAllBtn.addEventListener('click', () => setAllOpen(false));

        applyFilters();
    }
})();
