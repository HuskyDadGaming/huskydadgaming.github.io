/* tab-scroll.js — Auto-scroll the tab bar so the active tab is centered
 * within the visible area. Runs on page load AND on tab clicks, so when
 * the user toggles between Browse Dungeons (which clamps to scrollLeft 0,
 * effectively "reset to left") and Find Loot (which scrolls to center),
 * the bar always shows the active tab in a sensible position.
 *
 * Only adjusts .tab-bar's own scrollLeft — doesn't scroll the page
 * itself. No-op when there's no .tab-bar or no .active tab.
 */
(function () {
    'use strict';

    function centerActiveTab() {
        const bar = document.querySelector('.tab-bar');
        if (!bar) return;
        const active = bar.querySelector('.active');
        if (!active) return;
        // Center the active tab horizontally within the bar's viewport.
        // Math.max(0,…) clamps to the left edge when the active tab is
        // already near it (e.g. Browse Dungeons, the leftmost), so we
        // don't try to set a useless negative scrollLeft.
        const target = active.offsetLeft
                     - (bar.clientWidth / 2)
                     + (active.offsetWidth / 2);
        bar.scrollLeft = Math.max(0, target);
    }

    function wireClicks() {
        const bar = document.querySelector('.tab-bar');
        if (!bar) return;
        bar.addEventListener('click', (ev) => {
            if (!ev.target.closest('.tab-btn')) return;
            // setTimeout(0) defers until after the page's own click handler
            // has updated the .active class — without this we'd recenter
            // around the *previous* active tab.
            setTimeout(centerActiveTab, 0);
        });
    }

    function init() {
        centerActiveTab();
        wireClicks();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
