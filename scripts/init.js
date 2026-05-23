/**
 * init.js — Attaches all event listeners for the dashboard UI.
 * Replaces the inline onclick/onchange/oninput/onmouseenter/onmouseleave
 * attributes that were previously scattered through index.html.
 */

document.addEventListener('DOMContentLoaded', function () {

    // ── Sidebar ──────────────────────────────────────────────────────────────
    document.getElementById('btn-sidebar-toggle')
        ?.addEventListener('click', () => toggleSidebar());

    // ── Main tab navigation ──────────────────────────────────────────────────
    ['charts', 'stats', 'knn', 'backtest', 'trend', 'scanner', 'data-manager', 'daily-edge']
        .forEach(tab => {
            document.getElementById(`tab-${tab}`)
                ?.addEventListener('click', () => switchTab(tab));
        });

    // ── Adaptive Trend sub-tabs ──────────────────────────────────────────────
    document.getElementById('trend-stab-chart')
        ?.addEventListener('click', () => switchTrendTab('chart'));
    document.getElementById('trend-stab-scan')
        ?.addEventListener('click', () => switchTrendTab('scan'));

    document.querySelectorAll('.trend-method-btn').forEach(btn => {
        btn.addEventListener('click', () => setTrendMethod(btn.dataset.val));
    });

    document.querySelectorAll('.trend-freq-btn').forEach(btn => {
        btn.addEventListener('click', () => setTrendFreq(btn.dataset.val));
    });

    // Trend line toggle + description hover
    ['sb', 'mb', 'lb', 'sdb', 'mrt', 'mdb', 'lrt', 'ldb'].forEach(line => {
        const btn = document.getElementById(`trend-toggle-${line}`);
        if (!btn) return;
        btn.addEventListener('click',      () => toggleTrendLine(line));
        btn.addEventListener('mouseenter', () => showLineDesc(line));
        btn.addEventListener('mouseleave', () => clearLineDesc());
    });

    // Trend scan panel
    document.getElementById('btn-trend-scan')
        ?.addEventListener('click', () => loadTrendScan());
    document.querySelectorAll('.trend-scan-freq-btn').forEach(btn => {
        btn.addEventListener('click', () => setTrendScanFreq(btn.dataset.val));
    });

    // ── Scanner ──────────────────────────────────────────────────────────────
    document.getElementById('btn-scan')
        ?.addEventListener('click', () => loadScannerData());
    document.querySelectorAll('.scan-grp-btn').forEach(btn => {
        btn.addEventListener('click', () => toggleScanGroup(btn.dataset.grp));
    });

    // ── Data Manager ─────────────────────────────────────────────────────────
    document.getElementById('dm-search')
        ?.addEventListener('input', () => dmFilterTickers());
    document.getElementById('btn-dm-select-all')
        ?.addEventListener('click', () => dmSelectAll());
    document.getElementById('btn-dm-select-none')
        ?.addEventListener('click', () => dmSelectNone());
    document.getElementById('btn-dm-fetch')
        ?.addEventListener('click', () => dmStartBatch());
    document.getElementById('btn-dm-abort')
        ?.addEventListener('click', () => dmAbortBatch());

    // ── Daily Edge / Newsletter ───────────────────────────────────────────────
    document.getElementById('btn-nl-refresh')
        ?.addEventListener('click', () => window.nlRefresh?.());
    document.getElementById('nl-n-select')
        ?.addEventListener('change', () => window.nlRefresh?.());
    document.getElementById('nl-sort-select')
        ?.addEventListener('change', () => window.nlApplyFilters?.());

    document.querySelectorAll('.nl-filter-pill').forEach(btn => {
        btn.addEventListener('click', () => window.nlSetFilter?.(btn.dataset.filter));
    });
    document.querySelectorAll('.nl-view-btn').forEach(btn => {
        btn.addEventListener('click', () => window.nlSetView?.(btn.dataset.view));
    });

    // ── Bulk Add Modal ────────────────────────────────────────────────────────
    document.getElementById('bulk-modal')
        ?.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeBulkModal();
        });
    document.getElementById('btn-bulk-close')
        ?.addEventListener('click', () => closeBulkModal());
    document.getElementById('btn-bulk-cancel')
        ?.addEventListener('click', () => closeBulkModal());
    document.getElementById('btn-bulk-submit')
        ?.addEventListener('click', () => bulkAddSymbols());
});
