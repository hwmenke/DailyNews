(function () {
    'use strict';

    const NL_N = 20;
    let _loaded = false;

    // ── Patch switchTab ──────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        const _orig = window.switchTab;
        window.switchTab = async function (tabId) {
            // Always hide the daily-edge area before delegating
            const area = document.getElementById('daily-edge-area');
            if (area) area.style.display = 'none';

            if (tabId === 'daily-edge') {
                // Update active tab button
                document.querySelectorAll('.tab-btn').forEach(function (btn) {
                    btn.classList.toggle('active', btn.id === 'tab-daily-edge');
                });
                // Hide all other content areas
                ['empty-state', 'chart-area', 'stats-area', 'knn-area',
                 'backtest-area', 'trend-area', 'scanner-area', 'data-manager-area'
                ].forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                });
                var tabBar = document.querySelector('.tab-bar');
                if (tabBar) tabBar.style.display = 'none';
                // Show daily-edge area
                if (area) area.style.display = 'flex';
                // Load on first visit
                if (!_loaded) {
                    _loaded = true;
                    loadNewsletterData();
                }
            } else {
                if (typeof _orig === 'function') await _orig(tabId);
            }
        };
    });

    // ── Data fetch ───────────────────────────────────────────
    async function loadNewsletterData() {
        var loadEl = document.getElementById('nl-loading');
        var errEl  = document.getElementById('nl-error');
        if (loadEl) loadEl.style.display = 'flex';
        if (errEl)  errEl.style.display  = 'none';

        try {
            var res = await fetch('/api/newsletter/data?n=' + NL_N);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var data = await res.json();
            renderLeadStories(data.lead_stories || []);
            renderCards(data.cards || []);
            var meta = document.getElementById('nl-meta');
            if (meta) {
                meta.textContent =
                    (data.symbol_count || 0) + ' symbols · generated ' + (data.generated_at || '');
            }
        } catch (e) {
            if (errEl) {
                errEl.textContent = 'Failed to load newsletter: ' + e.message;
                errEl.style.display = 'block';
            }
        } finally {
            if (loadEl) loadEl.style.display = 'none';
        }
    }

    // ── Lead stories ─────────────────────────────────────────
    function renderLeadStories(stories) {
        var container = document.getElementById('nl-lead-stories');
        if (!container) return;
        container.innerHTML = '';

        stories.forEach(function (s) {
            var card = document.createElement('div');
            card.className = 'nl-lead-card';

            var header = document.createElement('div');
            header.className = 'nl-lead-header';

            var sym = document.createElement('span');
            sym.className   = 'nl-lead-sym';
            sym.textContent = s.symbol;
            sym.addEventListener('click', function () {
                if (typeof selectSymbol === 'function') selectSymbol(s.symbol);
            });

            var badge = document.createElement('span');
            badge.className   = 'nl-score-badge ' + ((s.score || 0) >= 0 ? 'nl-pos' : 'nl-neg');
            badge.textContent = ((s.score || 0) >= 0 ? '+' : '') + (s.score || 0).toFixed(2);

            header.appendChild(sym);
            header.appendChild(badge);
            card.appendChild(header);

            var subtitle = document.createElement('div');
            subtitle.className   = 'nl-lead-subtitle';
            subtitle.textContent = s.subtitle || '';
            card.appendChild(subtitle);

            if (s.chart_config) {
                var wrap   = document.createElement('div');
                wrap.className = 'nl-lead-chart';
                var canvas = document.createElement('canvas');
                wrap.appendChild(canvas);
                card.appendChild(wrap);
                try { new Chart(canvas, s.chart_config); } catch (_) {}
            }

            var metrics = document.createElement('div');
            metrics.className = 'nl-card-metrics';
            metrics.innerHTML = _metricsHtml(s);
            card.appendChild(metrics);

            container.appendChild(card);
        });
    }

    // ── Cards grid ───────────────────────────────────────────
    function renderCards(cards) {
        var grid = document.getElementById('nl-card-grid');
        if (!grid) return;
        grid.innerHTML = '';

        cards.forEach(function (c) {
            var card = document.createElement('div');
            card.className = 'nl-card';

            var header = document.createElement('div');
            header.className = 'nl-card-header';

            var sym = document.createElement('span');
            sym.className   = 'nl-card-sym';
            sym.textContent = c.symbol;
            sym.addEventListener('click', function () {
                if (typeof selectSymbol === 'function') selectSymbol(c.symbol);
            });

            var badge = document.createElement('span');
            badge.className   = 'nl-score-badge ' + ((c.score || 0) >= 0 ? 'nl-pos' : 'nl-neg');
            badge.textContent = ((c.score || 0) >= 0 ? '+' : '') + (c.score || 0).toFixed(2);

            header.appendChild(sym);
            header.appendChild(badge);
            card.appendChild(header);

            var subtitle = document.createElement('div');
            subtitle.className   = 'nl-card-subtitle';
            subtitle.textContent = c.subtitle || '';
            card.appendChild(subtitle);

            var barWrap = document.createElement('div');
            barWrap.innerHTML = _scoreBar(c.score);
            card.appendChild(barWrap);

            if (c.chart_config) {
                var wrap   = document.createElement('div');
                wrap.className = 'nl-card-chart';
                var canvas = document.createElement('canvas');
                wrap.appendChild(canvas);
                card.appendChild(wrap);
                try { new Chart(canvas, c.chart_config); } catch (_) {}
            }

            var metrics = document.createElement('div');
            metrics.className = 'nl-card-metrics';
            metrics.innerHTML = _metricsHtml(c);
            card.appendChild(metrics);

            grid.appendChild(card);
        });
    }

    // ── Score bar ────────────────────────────────────────────
    function _scoreBar(score) {
        var pct = Math.min(Math.abs(score || 0) * 10, 100);
        var cls = (score || 0) >= 0 ? 'nl-bar-pos' : 'nl-bar-neg';
        return '<div class="nl-score-bar"><div class="nl-bar-fill ' + cls +
               '" style="width:' + pct + '%"></div></div>';
    }

    // ── Metrics row ──────────────────────────────────────────
    function _metricsHtml(item) {
        var f   = item.features || {};
        var fmt = function (v, dec) { return v != null ? (+v).toFixed(dec != null ? dec : 1) : '—'; };
        var pct = function (v) {
            return v != null ? (v >= 0 ? '+' : '') + (+v * 100).toFixed(1) + '%' : '—';
        };
        var cls = function (v) { return v != null && +v >= 0 ? 'nl-pos' : 'nl-neg'; };
        var k10pct = (f.kama10 != null && f.price != null)
            ? pct((f.price - f.kama10) / f.kama10) : '—';
        var fields = [
            ['RSI',    fmt(f.rsi, 1),                      ''],
            ['ROC 5D', pct(f.roc_5d),                      cls(f.roc_5d)],
            ['ROC 20D',pct(f.roc_20d),                     cls(f.roc_20d)],
            ['Vol×', f.vol_ratio != null ? fmt(f.vol_ratio, 2) + 'x' : '—', ''],
            ['K10%',   k10pct,                             ''],
        ];
        return fields.map(function (row) {
            return '<span class="nl-metric">' +
                   '<span class="nl-metric-label">' + row[0] + '</span>' +
                   '<span class="nl-metric-val ' + row[2] + '">' + row[1] + '</span>' +
                   '</span>';
        }).join('');
    }

    // ── Expose refresh ───────────────────────────────────────
    window.nlRefresh = function () {
        _loaded = false;
        loadNewsletterData();
        _loaded = true;
    };

})();
