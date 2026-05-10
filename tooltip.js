/**
 * KCraft tooltip — shared in-game style item tooltip.
 *
 * Used by armoury.html, index.html (Find Loot tab), and dungeon pages.
 *
 * Usage:
 *   1. Include this script in your page:
 *        <script src="tooltip.js"></script>
 *
 *   2. On any element you want to show a tooltip for, set:
 *        data-item-id="123"
 *        data-item-json='{"id":123, "name":"...", "color":"#0070dd", ...}'
 *
 *   The script auto-attaches body-level mouse/touch listeners on load and
 *   shows the WoW-style tooltip on hover (desktop) or tap (mobile).
 *
 * Required item fields (all optional except id+name+color):
 *   id, name, color, qualityName, bondingName,
 *   slotFilter (or invType), armorType,
 *   damage (string), stats (array of strings),
 *   maxDurability, durability,
 *   reqLevel (or req),
 *   sellPrice, sellGold, sellSilver, sellCopper
 */
(function() {
  'use strict';

  // ============================================================
  // Styles — injected once on init
  // ============================================================
  const CSS = `
    #kcraft-tooltip {
      position: fixed; z-index: 9999;
      background: #000000; color: #ffffff;
      border: 1px solid #444; border-radius: 3px;
      padding: 8px 12px;
      font-size: 0.82rem; line-height: 1.4;
      min-width: 180px; max-width: 280px;
      pointer-events: none;
      opacity: 0; visibility: hidden;
      transition: opacity 0.08s;
      box-shadow: 0 4px 12px rgba(0,0,0,0.6);
    }
    #kcraft-tooltip.visible { opacity: 1; visibility: visible; }
    #kcraft-tooltip .tt-name {
      font-size: 0.95rem; font-weight: 600; margin-bottom: 2px;
    }
    #kcraft-tooltip .tt-bind { color: #ffffff; font-size: 0.78rem; }
    #kcraft-tooltip .tt-slot-row {
      display: flex; justify-content: space-between; margin-top: 4px;
    }
    #kcraft-tooltip .tt-slot-row .tt-slot { color: #ffffff; }
    #kcraft-tooltip .tt-slot-row .tt-armor-type { color: #ffffff; }
    #kcraft-tooltip .tt-stat { color: #ffffff; }
    #kcraft-tooltip .tt-bonus { color: #1eff00; }
    #kcraft-tooltip .tt-damage-row {
      display: flex; justify-content: space-between; margin-top: 2px;
    }
    #kcraft-tooltip .tt-damage-row .tt-damage  { color: #ffffff; }
    #kcraft-tooltip .tt-damage-row .tt-speed   { color: #ffffff; }
    #kcraft-tooltip .tt-dps {
      color: #ffffff; font-size: 0.8rem; margin-left: 4px;
    }
    #kcraft-tooltip .tt-effect {
      color: #1eff00; margin-top: 4px; line-height: 1.3;
    }
    #kcraft-tooltip .tt-durability { color: #ffffff; margin-top: 4px; }
    #kcraft-tooltip .tt-required { color: #ffffff; margin-top: 4px; }
    #kcraft-tooltip .tt-sell {
      margin-top: 4px;
      display: flex; gap: 6px; align-items: center;
    }
    #kcraft-tooltip .tt-sell-label { color: #ffffff; }
    #kcraft-tooltip .tt-coin {
      display: inline-flex; align-items: center; gap: 2px;
      font-variant-numeric: tabular-nums;
    }
    #kcraft-tooltip .tt-coin-icon {
      display: inline-block; width: 11px; height: 11px;
      border-radius: 50%; border: 1px solid rgba(0,0,0,0.4);
    }
    #kcraft-tooltip .tt-coin-gold .tt-coin-icon   { background: #ffd700; }
    #kcraft-tooltip .tt-coin-silver .tt-coin-icon { background: #c8c8c8; }
    #kcraft-tooltip .tt-coin-copper .tt-coin-icon { background: #c97a36; }
    #kcraft-tooltip .tt-id {
      color: #555; font-size: 0.7rem; margin-top: 4px;
      border-top: 1px solid #1f1f1f; padding-top: 4px;
    }
    /* Item set block — yellow set name, dim grey piece list, green bonuses,
       matching the in-game tooltip styling shown to players. */
    #kcraft-tooltip .tt-set-heading {
      color: #ffd100; margin-top: 6px; font-weight: 600;
    }
    #kcraft-tooltip .tt-set-piece {
      color: #888; padding-left: 6px; line-height: 1.3;
    }
    #kcraft-tooltip .tt-set-bonus {
      color: #1eff00; line-height: 1.3; margin-top: 1px;
    }
    #kcraft-tooltip .tt-set-bonus .tt-set-pieces { color: #888; }
    [data-item-id].tooltip-active { outline: 1px solid #555; outline-offset: -1px; }

    /* Mobile: narrower, smaller font, never go off-edge */
    @media (max-width: 600px) {
      #kcraft-tooltip {
        max-width: calc(100vw - 24px);
        min-width: 0;
        font-size: 0.78rem;
        padding: 6px 10px;
      }
      #kcraft-tooltip .tt-name { font-size: 0.88rem; }
    }

    /* Modal mode (small viewports): the tooltip fills the entire viewport
       so it's easy to read on phones. Tapping anywhere on it dismisses
       and returns the user to the item list (the tap-handler in tooltip.js
       handles this). Scrolling within long tooltips still works thanks
       to the 10px movement threshold that distinguishes tap from scroll. */
    #kcraft-tooltip.tt-modal {
      position: fixed;
      inset: 0;
      left: 0 !important;
      top: 0 !important;
      transform: none;
      width: 100vw;
      height: 100vh;
      max-width: none;
      max-height: none;
      border-radius: 0;
      padding: 20px 16px;
      overflow-y: auto;
      pointer-events: auto;
      z-index: 10001;
      cursor: pointer;
    }
    #kcraft-tooltip.tt-modal::after {
      /* Subtle hint: tells the user how to get back. Sticky so it stays
         visible while they scroll long set-bonus lists. */
      content: '✕ Tap anywhere to close';
      display: block;
      position: sticky;
      bottom: -20px;
      margin-top: 16px;
      padding: 8px;
      text-align: center;
      color: #666;
      font-size: 0.75rem;
      background: rgba(20, 20, 20, 0.9);
      border-top: 1px solid #333;
    }

    .tt-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      z-index: 10000;
      display: none;
    }
    .tt-backdrop.visible { display: block; }
  `;

  // ============================================================
  // Helpers
  // ============================================================
  function escape(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Build the in-game style tooltip HTML for an item.
  function buildTooltipHTML(it) {
    const parts = [];

    // Name in quality colour
    parts.push(
      `<div class="tt-name" style="color:${escape(it.color || '#fff')}">${escape(it.name)}</div>`
    );

    // Soulbound / BoE / quest line
    if (it.bondingName) {
      parts.push(`<div class="tt-bind">${escape(it.bondingName)}</div>`);
    }

    // Slot ↔ armor type row
    // The loot-data JSON uses `slotFilter` for the bare slot name; the armoury
    // API uses `invType`. Accept either.
    const slot = it.invType || it.slotFilter || '';
    const armorType = it.armorType || '';
    if (slot || armorType) {
      parts.push(
        `<div class="tt-slot-row">` +
          `<span class="tt-slot">${escape(slot)}</span>` +
          `<span class="tt-armor-type">${escape(armorType)}</span>` +
        `</div>`
      );
    }

    // Weapon damage line: "X-Y Damage" with "Speed Z.ZZ" on the right and
    // "(W.W damage per second)" below — matches the in-game tooltip layout.
    if (it.damage) {
      if (it.speed) {
        parts.push(
          `<div class="tt-damage-row">` +
            `<span class="tt-damage">${escape(it.damage)}</span>` +
            `<span class="tt-speed">Speed ${Number(it.speed).toFixed(2)}</span>` +
          `</div>`
        );
        if (it.dps) {
          parts.push(
            `<div class="tt-dps">(${Number(it.dps).toFixed(1)} damage per second)</div>`
          );
        }
      } else {
        parts.push(`<div class="tt-stat">${escape(it.damage)}</div>`);
      }
    }

    // Stats list — values starting with "+" are highlighted green
    (it.stats || []).forEach(s => {
      const isBonus = /^[+]/.test(s);
      const cls = isBonus ? 'tt-stat tt-bonus' : 'tt-stat';
      parts.push(`<div class="${cls}">${escape(s)}</div>`);
    });

    // Durability (if present — characters only; loot data omits)
    if (it.maxDurability) {
      const cur = (it.durability != null) ? it.durability : it.maxDurability;
      parts.push(`<div class="tt-durability">Durability ${cur} / ${it.maxDurability}</div>`);
    }

    // Required level. Accept either reqLevel (armoury) or req (loot guide).
    const reqLvl = it.reqLevel || it.req;
    if (reqLvl) {
      parts.push(`<div class="tt-required">Requires Level ${reqLvl}</div>`);
    }

    // Equip: / Use: / Chance on hit: effects (in green, same as in-game)
    (it.effects || []).forEach(e => {
      const trigger = e.trigger ? `${escape(e.trigger)}: ` : '';
      parts.push(`<div class="tt-effect">${trigger}${escape(e.text)}</div>`);
    });

    // Item set block — yellow heading "Set Name (n/m)", greyed-out piece list,
    // green bonus lines. Mirrors the in-game set tooltip; we don't know how
    // many pieces the player owns so the heading shows total only ("(5)").
    if (it.set && it.set.name) {
      const s = it.set;
      const pieceCount = (s.items || []).length;
      const heading = pieceCount
        ? `${escape(s.name)} (${pieceCount})`
        : escape(s.name);
      parts.push(`<div class="tt-set-heading">${heading}</div>`);
      (s.items || []).forEach(piece => {
        const name = escape(piece.name || `Item ${piece.id}`);
        parts.push(`<div class="tt-set-piece">${name}</div>`);
      });
      (s.bonuses || []).forEach(b => {
        parts.push(
          `<div class="tt-set-bonus">` +
            `<span class="tt-set-pieces">(${b.pieces}) Set:</span> ` +
            `${escape(b.text)}` +
          `</div>`
        );
      });
    }

    // Sell price with coin indicators
    if (it.sellPrice && it.sellPrice > 0) {
      const coins = [];
      if (it.sellGold > 0) coins.push(
        `<span class="tt-coin tt-coin-gold">${it.sellGold}<span class="tt-coin-icon"></span></span>`
      );
      if (it.sellSilver > 0 || it.sellGold > 0) coins.push(
        `<span class="tt-coin tt-coin-silver">${it.sellSilver}<span class="tt-coin-icon"></span></span>`
      );
      coins.push(
        `<span class="tt-coin tt-coin-copper">${it.sellCopper}<span class="tt-coin-icon"></span></span>`
      );
      parts.push(
        `<div class="tt-sell">` +
          `<span class="tt-sell-label">Sell Price:</span>` +
          coins.join('') +
        `</div>`
      );
    }

    // Item ID footer
    if (it.id) {
      parts.push(`<div class="tt-id">Item ID: ${escape(it.id)}</div>`);
    }

    return parts.join('');
  }

  // ============================================================
  // Tooltip element + show/hide/position
  // ============================================================
  let tooltipEl = null;
  let tooltipShownFor = null;

  function getOrCreateTooltipEl() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.getElementById('kcraft-tooltip');
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.id = 'kcraft-tooltip';
      tooltipEl.setAttribute('role', 'tooltip');
      tooltipEl.setAttribute('aria-hidden', 'true');
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  // Mobile = small viewport. Threshold matches the CSS @media breakpoint so
  // visual layout and JS behaviour switch together. Probed each call rather
  // than cached so it tracks orientation changes and viewport resizes.
  const MOBILE_BREAKPOINT = 600;
  function isMobileViewport() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
  }

  function getOrCreateBackdropEl() {
    let bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) return bd;
    bd = document.createElement('div');
    bd.id = 'kcraft-tooltip-backdrop';
    bd.className = 'tt-backdrop';
    document.body.appendChild(bd);
    return bd;
  }

  function showTooltip(it, ev, row) {
    const el = getOrCreateTooltipEl();
    el.innerHTML = buildTooltipHTML(it);
    el.classList.add('visible');
    el.setAttribute('aria-hidden', 'false');
    positionTooltip(ev);
    if (tooltipShownFor && tooltipShownFor !== row) {
      tooltipShownFor.classList.remove('tooltip-active');
    }
    if (row) row.classList.add('tooltip-active');
    tooltipShownFor = row || null;
  }

  function hideTooltip() {
    const el = getOrCreateTooltipEl();
    el.classList.remove('visible');
    el.classList.remove('tt-modal');
    el.setAttribute('aria-hidden', 'true');
    // Reset inline positioning so a future desktop hover doesn't inherit
    // the centered modal coordinates.
    el.style.left = '';
    el.style.top = '';
    const bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) bd.classList.remove('visible');
    if (tooltipShownFor) tooltipShownFor.classList.remove('tooltip-active');
    tooltipShownFor = null;
  }

  function positionTooltip(ev) {
    const el = getOrCreateTooltipEl();
    if (isMobileViewport()) {
      // Modal mode: tooltip centered, backdrop dims the page. CSS handles
      // the actual centering — this just toggles classes and clears any
      // leftover inline coords from a previous desktop hover.
      el.classList.add('tt-modal');
      el.style.left = '';
      el.style.top = '';
      getOrCreateBackdropEl().classList.add('visible');
      return;
    }
    // Desktop: position next to the cursor with viewport-edge clamping.
    el.classList.remove('tt-modal');
    const bd = document.getElementById('kcraft-tooltip-backdrop');
    if (bd) bd.classList.remove('visible');
    const pad = 14;
    const tw = el.offsetWidth;
    const th = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    if (x + tw + 8 > vw) x = ev.clientX - tw - pad;
    if (y + th + 8 > vh) y = ev.clientY - th - pad;
    if (x < 4) x = 4;
    if (y < 4) y = 4;
    el.style.left = x + 'px';
    el.style.top  = y + 'px';
  }

  // Lookup item data on a row. Returns null if attribute is missing/invalid.
  function readItemFromRow(row) {
    const json = row.dataset && row.dataset.itemJson;
    if (!json) return null;
    try {
      return JSON.parse(json);
    } catch (e) {
      return null;
    }
  }

  // ============================================================
  // Event listeners — body-level delegation, survives re-renders
  // ============================================================
  function setupEventListeners() {
    // Hover (desktop)
    document.body.addEventListener('mouseover', (ev) => {
      const row = ev.target.closest('[data-item-id]');
      if (!row) return;
      if (tooltipShownFor === row) return;
      const data = readItemFromRow(row);
      if (data) showTooltip(data, ev, row);
    });

    document.body.addEventListener('mousemove', (ev) => {
      if (!tooltipShownFor) return;
      positionTooltip(ev);
    });

    document.body.addEventListener('mouseout', (ev) => {
      if (!tooltipShownFor) return;
      const leaving = ev.target.closest('[data-item-id]');
      if (leaving === tooltipShownFor && !leaving.contains(ev.relatedTarget)) {
        hideTooltip();
      }
    });

    // Touch (mobile) — distinguish a tap from a scroll-gesture
    let touchStart = null;
    const TAP_MOVE_THRESHOLD_PX = 10;

    document.body.addEventListener('touchstart', (ev) => {
      if (ev.touches.length !== 1) {
        touchStart = { x: 0, y: 0, isScroll: true };
        return;
      }
      const t = ev.touches[0];
      touchStart = { x: t.clientX, y: t.clientY, isScroll: false };
    }, { passive: true });

    document.body.addEventListener('touchmove', (ev) => {
      if (!touchStart) return;
      const t = ev.touches[0];
      if (!t) return;
      const dx = Math.abs(t.clientX - touchStart.x);
      const dy = Math.abs(t.clientY - touchStart.y);
      if (dx > TAP_MOVE_THRESHOLD_PX || dy > TAP_MOVE_THRESHOLD_PX) {
        touchStart.isScroll = true;
      }
    }, { passive: true });

    document.body.addEventListener('touchend', (ev) => {
      const wasScroll = !touchStart || touchStart.isScroll;
      touchStart = null;
      if (wasScroll) return;

      const row = ev.target.closest('[data-item-id]');
      if (row) {
        if (tooltipShownFor === row) {
          ev.preventDefault();
          return;
        }
        const data = readItemFromRow(row);
        if (data) {
          const touch = ev.changedTouches[0];
          const fakeEv = { clientX: touch.clientX, clientY: touch.clientY };
          showTooltip(data, fakeEv, row);
          ev.preventDefault();
        }
      } else if (tooltipShownFor) {
        // Tap anywhere — including on the tooltip itself in full-screen
        // modal mode — dismisses and returns to the items. Scrolling
        // inside the tooltip is preserved by the touchmove threshold
        // earlier (a >10px drag flips isScroll=true and we never get
        // here on touchend).
        hideTooltip();
      }
    }, { passive: false });

    // Dismiss on scroll (any kind — programmatic, momentum, container scroll)
    window.addEventListener('scroll', () => {
      if (tooltipShownFor) hideTooltip();
    }, { passive: true, capture: true });
  }

  // ============================================================
  // Init
  // ============================================================
  function injectStyles() {
    if (document.getElementById('kcraft-tooltip-styles')) return;
    const style = document.createElement('style');
    style.id = 'kcraft-tooltip-styles';
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function init() {
    injectStyles();
    getOrCreateTooltipEl();
    setupEventListeners();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for manual control
  window.KCraftTooltip = {
    init: init,
    show: showTooltip,
    hide: hideTooltip,
    buildHTML: buildTooltipHTML,
  };
})();
