(function () {
    'use strict';

    let _loaded  = false;
    let _rawData = null;
    let _view    = 'grid';
    let _filter  = 'all';

    // ── Tab registration (preferred) with monkey-patch fallback ──
    document.addEventListener('DOMContentLoaded', function () {
        if (window.registerTab) {
            window.registerTab('daily-edge', {
                onShow: function () {
                    var area = document.getElementById('daily-edge-area');
                    ['empty-state','chart-area','stats-area','knn-area',
                     'backtest-area','trend-area','scanner-area','data-manager-area'
                    ].forEach(function (id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                    var tabBar = document.querySelector('.tab-bar');
                    if (tabBar) tabBar.style.display = 'none';
                    if (area) area.style.display = 'flex';
                    if (!_loaded) { _loaded = true; loadNewsletterData(); }
                },
                onHide: function () {
                    // nothing to clean up
                }
            });
        } else {
            // fallback: monkey-patch switchTab as safety net
            var _orig = window.switchTab;
            window.switchTab = async function (tabId) {
                var area = document.getElementById('daily-edge-area');
                if (area) area.style.display = 'none';
                if (tabId === 'daily-edge') {
                    document.querySelectorAll('.tab-btn').forEach(function (btn) {
                        btn.classList.toggle('active', btn.id === 'tab-daily-edge');
                    });
                    ['empty-state','chart-area','stats-area','knn-area',
                     'backtest-area','trend-area','scanner-area','data-manager-area'
                    ].forEach(function (id) {
                        var el = document.getElementById(id);
                        if (el) el.style.display = 'none';
                    });
                    var tabBar = document.querySelector('.tab-bar');
                    if (tabBar) tabBar.style.display = 'none';
                    if (area) area.style.display = 'flex';
                    if (!_loaded) { _loaded = true; loadNewsletterData(); }
                } else {
                    if (typeof _orig === 'function') await _orig(tabId);
                }
            };
        }
    });

    // ── Data fetch ───────────────────────────────────────────
    async function loadNewsletterData() {
        var loadEl = document.getElementById('nl-loading');
        var errEl  = document.getElementById('nl-error');
        var nSel   = document.getElementById('nl-n-select');
        var n      = nSel ? parseInt(nSel.value) : 20;
        if (loadEl) loadEl.style.display = 'flex';
        if (errEl)  errEl.style.display  = 'none';
        try {
            var res = await fetch('/api/newsletter/data?n=' + n);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var data = await res.json();
            _rawData = data;
            var meta = document.getElementById('nl-meta');
            if (meta) meta.textContent = (data.symbol_count || 0) + ' symbols · ' + (data.generated_at || '');
            _applyFilters();
        } catch (e) {
            if (errEl) { errEl.innerHTML = '<strong>Error:</strong> ' + e.message; errEl.style.display = 'block'; }
        } finally {
            if (loadEl) loadEl.style.display = 'none';
        }
    }

    // ── Filter / sort / render ───────────────────────────────
    function _applyFilters() {
        if (!_rawData) return;
        var sortSel = document.getElementById('nl-sort-select');
        var sortKey = sortSel ? sortSel.value : 'score';

        var filterFn = function (item) {
            if (_filter === 'bull') return (item.score || 0) > 0;
            if (_filter === 'bear') return (item.score || 0) < 0;
            return true;
        };
        var sortFn = function (a, b) {
            var af = a.features || {}, bf = b.features || {};
            if (sortKey === 'momentum') return (bf.roc_5d || 0) - (af.roc_5d || 0);
            if (sortKey === 'volume')   return (bf.vol_ratio || 0) - (af.vol_ratio || 0);
            if (sortKey === 'rsi_low')  return (af.rsi || 50) - (bf.rsi || 50);
            if (sortKey === 'rsi_high') return (bf.rsi || 50) - (af.rsi || 50);
            return (b.score || 0) - (a.score || 0);
        };

        var leads = (_rawData.lead_stories || []).filter(filterFn).sort(sortFn);
        var cards = (_rawData.cards        || []).filter(filterFn).sort(sortFn);

        var lc = document.getElementById('nl-lead-count');
        var cc = document.getElementById('nl-card-count');
        if (lc) lc.textContent = leads.length;
        if (cc) cc.textContent = cards.length;

        var tableEl  = document.getElementById('nl-table-view');
        var storiesEl = document.getElementById('nl-lead-stories');
        var gridEl   = document.getElementById('nl-card-grid');

        if (_view === 'table') {
            if (storiesEl) storiesEl.style.display = 'none';
            if (gridEl)    gridEl.style.display    = 'none';
            if (tableEl)   tableEl.style.display   = '';
            _renderTable([].concat(leads, cards));
        } else {
            if (tableEl)   tableEl.style.display   = 'none';
            if (storiesEl) storiesEl.style.display = '';
            if (gridEl)    gridEl.style.display    = '';
            _renderLeads(leads);
            _renderCards(cards);
        }
    }

    // ── Lead stories ─────────────────────────────────────────
    function _renderLeads(stories) {
        var container = document.getElementById('nl-lead-stories');
        if (!container) return;
        container.innerHTML = '';
        stories.forEach(function (s) {
            var scoreVal = s.score || 0;
            var regime   = _regime(s);
            var card = document.createElement('div');
            card.className = 'nl-lead-card nl-card-' + (scoreVal > 0 ? 'bull' : scoreVal < 0 ? 'bear' : 'neut');
            card.innerHTML =
                '<div class="nl-lead-header">' +
                  '<div class="nl-lead-sym-wrap">' +
                    '<span class="nl-lead-sym">' + s.symbol + '</span>' +
                    '<span class="nl-regime-pill nl-regime-' + regime.cls + '">' + regime.label + '</span>' +
                  '</div>' +
                  '<div class="nl-score-big ' + (scoreVal >= 0 ? 'nl-pos' : 'nl-neg') + '">' +
                    '<span class="nl-score-num">' + (scoreVal >= 0 ? '+' : '') + scoreVal.toFixed(2) + '</span>' +
                    '<span class="nl-score-lbl">score</span>' +
                  '</div>' +
                '</div>' +
                '<div class="nl-lead-subtitle">' + (s.subtitle || '') + '</div>' +
                _scoreBarHtml(scoreVal) +
                '<div class="nl-lead-chart-wrap"><canvas class="nl-chart-canvas"></canvas></div>' +
                '<div class="nl-metrics-grid">' + _metricsHtml(s, true) + '</div>';
            card.querySelector('.nl-lead-sym').addEventListener('click', function () {
                if (typeof selectSymbol === 'function') selectSymbol(s.symbol);
            });
            // Bug fix: use .chart (not .chart_config)
            if (s.chart) { try { new Chart(card.querySelector('.nl-chart-canvas'), s.chart); } catch (_) {} }
            container.appendChild(card);
        });
    }

    // ── Card grid ─────────────────────────────────────────────
    function _renderCards(cards) {
        var grid = document.getElementById('nl-card-grid');
        if (!grid) return;
        grid.innerHTML = '';
        cards.forEach(function (c) {
            var scoreVal = c.score || 0;
            var regime   = _regime(c);
            var card = document.createElement('div');
            card.className = 'nl-card nl-card-' + (scoreVal > 0 ? 'bull' : scoreVal < 0 ? 'bear' : 'neut');
            card.innerHTML =
                '<div class="nl-card-header">' +
                  '<span class="nl-card-sym">' + c.symbol + '</span>' +
                  '<span class="nl-regime-pill nl-regime-' + regime.cls + '">' + regime.label + '</span>' +
                '</div>' +
                '<div class="nl-card-score-row">' +
                  '<span class="nl-score-badge ' + (scoreVal >= 0 ? 'nl-pos' : 'nl-neg') + '">' +
                    (scoreVal >= 0 ? '+' : '') + scoreVal.toFixed(2) +
                  '</span>' +
                  _scoreBarHtml(scoreVal) +
                '</div>' +
                '<div class="nl-card-subtitle">' + (c.subtitle || '') + '</div>';
            // Bug fix: use .chart (not .chart_config)
            if (c.chart) {
                var wrap = document.createElement('div');
                wrap.className = 'nl-card-chart';
                var canvas = document.createElement('canvas');
                wrap.appendChild(canvas);
                card.appendChild(wrap);
                try { new Chart(canvas, c.chart); } catch (_) {}
            }
            var metricsDiv = document.createElement('div');
            metricsDiv.className = 'nl-metrics-row';
            metricsDiv.innerHTML = _metricsHtml(c, false);
            card.appendChild(metricsDiv);
            card.querySelector('.nl-card-sym').addEventListener('click', function () {
                if (typeof selectSymbol === 'function') selectSymbol(c.symbol);
            });
            grid.appendChild(card);
        });
    }

    // ── Table view ───────────────────────────────────────────
    function _renderTable(items) {
        var tableEl = document.getElementById('nl-table-view');
        if (!tableEl) return;
        var cols = [
            { label: 'Symbol',  key: 'symbol'   },
            { label: 'Score',   key: '_score'   },
            { label: 'Regime',  key: '_regime'  },
            { label: 'RSI',     key: 'rsi'      },
            { label: 'ROC 5D',  key: 'roc_5d'  },
            { label: 'ROC 20D', key: 'roc_20d' },
            { label: 'Vol×',    key: 'vol_ratio'},
            { label: 'K10%',    key: 'k10pct'  },
            { label: 'Summary', key: 'subtitle' },
        ];
        var thead = '<thead><tr>' + cols.map(function (c) { return '<th>' + c.label + '</th>'; }).join('') + '</tr></thead>';
        var tbody = '<tbody>' + items.map(function (item) {
            var f        = item.features || {};
            var scoreVal = item.score || 0;
            var regime   = _regime(item);
            var k10pct   = (f.kama10 != null && f.price != null)
                ? (f.price >= f.kama10 ? '+' : '') + ((f.price - f.kama10) / f.kama10 * 100).toFixed(1) + '%' : '—';
            var cells = {
                symbol:    '<td class="nl-tbl-sym">' + item.symbol + '</td>',
                _score:    '<td class="' + (scoreVal >= 0 ? 'nl-pos' : 'nl-neg') + '">' + (scoreVal >= 0 ? '+' : '') + scoreVal.toFixed(2) + '</td>',
                _regime:   '<td><span class="nl-regime-pill nl-regime-' + regime.cls + '">' + regime.label + '</span></td>',
                rsi:       '<td>' + (f.rsi != null ? (+f.rsi).toFixed(1) : '—') + '</td>',
                // Bug fix: values are already in percent — no * 100
                roc_5d:    '<td class="' + (f.roc_5d >= 0 ? 'nl-pos' : 'nl-neg') + '">' + (f.roc_5d != null ? (f.roc_5d >= 0 ? '+' : '') + (+f.roc_5d).toFixed(1) + '%' : '—') + '</td>',
                roc_20d:   '<td class="' + (f.roc_20d >= 0 ? 'nl-pos' : 'nl-neg') + '">' + (f.roc_20d != null ? (f.roc_20d >= 0 ? '+' : '') + (+f.roc_20d).toFixed(1) + '%' : '—') + '</td>',
                vol_ratio: '<td>' + (f.vol_ratio != null ? (+f.vol_ratio).toFixed(2) + 'x' : '—') + '</td>',
                k10pct:    '<td>' + k10pct + '</td>',
                subtitle:  '<td class="nl-tbl-sub">' + (item.subtitle || '') + '</td>',
            };
            var rowCls = scoreVal > 1 ? 'nl-row-bull' : scoreVal < -1 ? 'nl-row-bear' : '';
            return '<tr class="' + rowCls + '">' + cols.map(function (c) { return cells[c.key]; }).join('') + '</tr>';
        }).join('') + '</tbody>';
        tableEl.innerHTML = '<table class="nl-table">' + thead + tbody + '</table>';
        tableEl.querySelectorAll('.nl-tbl-sym').forEach(function (td) {
            td.addEventListener('click', function () {
                if (typeof selectSymbol === 'function') selectSymbol(td.textContent.trim());
            });
        });
    }

    // ── Helpers ──────────────────────────────────────────────
    function _regime(item) {
        // Bug fix: trend_score is at the top level of the card object, not nested under .features
        var ts = item.trend_score;
        if (ts >  0) return { label: 'LONG',    cls: 'bull' };
        if (ts <  0) return { label: 'SHORT',   cls: 'bear' };
        return             { label: 'NEUTRAL',  cls: 'neut' };
    }

    function _scoreBarHtml(score) {
        var pct = Math.min(Math.abs(score || 0) * 10, 100);
        var cls = (score || 0) >= 0 ? 'nl-bar-pos' : 'nl-bar-neg';
        return '<div class="nl-score-bar"><div class="nl-bar-fill ' + cls + '" style="width:' + pct + '%"></div></div>';
    }

    function _metricsHtml(item, large) {
        var f   = item.features || {};
        var fmt = function (v, d) { return v != null ? (+v).toFixed(d != null ? d : 1) : '—'; };
        // Bug fix: values are already in percent — no * 100
        var pct = function (v) { return v != null ? (v >= 0 ? '+' : '') + (+v).toFixed(1) + '%' : '—'; };
        var cls = function (v) { return v != null && +v >= 0 ? 'nl-pos' : 'nl-neg'; };
        var rsiCls = function (v) { if (v == null) return ''; return v < 35 ? 'nl-pos' : v > 65 ? 'nl-neg' : ''; };
        var k10pct = (f.kama10 != null && f.price != null)
            ? (f.price >= f.kama10 ? '+' : '') + ((f.price - f.kama10) / f.kama10 * 100).toFixed(1) + '%' : '—';
        var k10cls = (f.kama10 != null && f.price != null) ? (f.price >= f.kama10 ? 'nl-pos' : 'nl-neg') : '';
        var fields = [
            ['RSI',    fmt(f.rsi, 1),                                       rsiCls(f.rsi)],
            ['ROC 5D', pct(f.roc_5d),                                       cls(f.roc_5d)],
            ['ROC 20D',pct(f.roc_20d),                                      cls(f.roc_20d)],
            ['Vol×',   f.vol_ratio != null ? fmt(f.vol_ratio, 2) + 'x' : '—', ''],
            ['K10%',   k10pct,                                              k10cls],
        ];
        if (large) fields.push(['Trend', item.trend_score != null ? fmt(item.trend_score, 2) : '—',
                                 item.trend_score > 0 ? 'nl-pos' : item.trend_score < 0 ? 'nl-neg' : '']);
        return fields.map(function (row) {
            return '<div class="nl-metric">' +
                   '<span class="nl-metric-label">' + row[0] + '</span>' +
                   '<span class="nl-metric-val ' + row[2] + '">' + row[1] + '</span>' +
                   '</div>';
        }).join('');
    }

    // ── Public API ───────────────────────────────────────────
    window.nlRefresh = function () {
        _loaded = false; _rawData = null;
        loadNewsletterData();
        _loaded = true;
    };
    window.nlApplyFilters = function () { _applyFilters(); };
    window.nlSetFilter = function (f) {
        _filter = f;
        document.querySelectorAll('.nl-filter-pill').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.filter === f);
        });
        _applyFilters();
    };
    window.nlSetView = function (v) {
        _view = v;
        document.querySelectorAll('.nl-view-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.view === v);
        });
        _applyFilters();
    };

})();
