/* Upgrades each [data-grid] table to AG Grid Community 36 (vendored, MIT, no CDN).
   Used features, all Community: sorting (multi-column with shift), column text/number filters,
   external filters (the result / action / state buttons), quick filter (search box),
   status cells styled by cellClass (no renderers: values stay text), single-row selection driving a detail panel
   (signed fields, chain link), CSV export, the Theming API fed from app.css tokens, and
   keyboard navigation with DOM order kept for screen readers.
   The plain table stays as the no-JS fallback and is hidden only once the grid exists. */
(function () {
  if (typeof agGrid === 'undefined') return;
  var narrow = window.matchMedia('(max-width: 640px)').matches;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function theme() {
    return agGrid.themeQuartz.withParams({
      fontFamily: 'inherit', fontSize: 14, headerFontSize: 13, headerFontWeight: 700,
      backgroundColor: css('--surface'), foregroundColor: css('--fg'), textColor: css('--fg'),
      headerBackgroundColor: css('--surface-2'), headerTextColor: css('--fg'),
      borderColor: css('--line'), accentColor: css('--accent'), chromeBackgroundColor: css('--surface-2'),
      rowHoverColor: css('--accent-soft'), selectedRowBackgroundColor: css('--accent-soft'),
      oddRowBackgroundColor: css('--surface'), wrapperBorderRadius: 12, rowHeight: 44, headerHeight: 44,
      spacing: 6, cellHorizontalPadding: 12
    });
  }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text !== undefined) n.textContent = text;
    return n;
  }
  /* No cell renderers: AG Grid writes every cell value as text (tests/security forbids
     renderers, HTML strings and formatters). Status cells only get a CSS class from the row's
     server-computed tone, which is one of a fixed set of words. */
  var TONES = {ok: 1, bad: 1, warn: 1, info: 1, neutral: 1};
  function toneClass(p) { return 'cell-chip tone-' + (TONES[p.data.tone] ? p.data.tone : 'neutral'); }
  function resultText(p) { return p.data.result + (p.data.reason ? ' · ' + p.data.reason : ''); }

  var specs = {
    mandates: {
      columns: [
        {field: 'short', headerName: 'Mandate', minWidth: 100, filter: 'agTextColumnFilter'},
        {field: 'state', headerName: 'State', minWidth: 110, cellClass: toneClass, filter: 'agTextColumnFilter'},
        {field: 'action', headerName: 'Action', minWidth: 140, filter: 'agTextColumnFilter'},
        {field: 'resource', headerName: 'Resource', minWidth: 120, filter: 'agTextColumnFilter', initialHide: true},
        {field: 'cap', headerName: 'Cap (USD)', minWidth: 96, type: 'rightAligned', filter: 'agNumberColumnFilter',
         filterValueGetter: function (p) { return parseFloat(p.data.cap); },
         comparator: function (a, b) { return parseFloat(a) - parseFloat(b); }},
        {field: 'exp_text', headerName: 'Expires', minWidth: 120, initialHide: true}
      ],
      id: function (r) { return r.id; },
      detail: function (r) {
        return {title: 'Mandate ' + r.short + ' · ' + r.state, fields: [
          ['jti', r.id], ['action', r.action], ['recipient', r.resource], ['cap', 'USD ' + r.cap],
          ['asked', r.created_text], ['expires', r.exp_text], ['plan_hash', r.plan_hash],
          ['sent to PayPal as', r.state === 'used' ? 'PayPal-Request-Id: ' + r.id : 'not sent (never executed)'],
          ['PayPal returned', r.paypal || '—'],
          ['ledger rows', (r.ledger && r.ledger.length) ? r.ledger.map(function (n) { return '#' + n; }).join(', ') : 'none yet']],
          links: (r.ledger || []).map(function (n) { return ['ledger row #' + n, '/ledger/entry/' + n]; }),
          raw: r.canonical, rawLabel: 'Exact bytes the owner signs (RFC 8785 canonical JSON)'};
      }
    },
    ledger: {
      columns: [
        {field: 'n', headerName: '#', minWidth: narrow ? 56 : 64, maxWidth: 80, filter: 'agNumberColumnFilter', sort: 'desc'},
        {field: 'time', headerName: 'Time (UTC)', minWidth: 100, initialHide: true},   /* in the row detail */
        {colId: 'result', headerName: 'Result', minWidth: narrow ? 150 : 170, valueGetter: resultText,
         cellClass: toneClass, filter: 'agTextColumnFilter'},
        {field: 'result', colId: 'result_raw', headerName: 'Result (raw)', hide: true},
        {field: 'reason', headerName: 'Reason', hide: true},          /* shown in the Result chip; exported to CSV */
        {field: 'action', headerName: 'Action', minWidth: narrow ? 130 : 150, filter: 'agTextColumnFilter'},
        {field: 'resource', headerName: 'Resource', minWidth: 120, filter: 'agTextColumnFilter', initialHide: narrow},
        {field: 'amount', headerName: 'Amount', minWidth: narrow ? 84 : 96, type: 'rightAligned', filter: 'agNumberColumnFilter',
         filterValueGetter: function (p) { return parseFloat(p.data.amount); },
         comparator: function (a, b) { return parseFloat(a || 0) - parseFloat(b || 0); }},
        {field: 'mandate', headerName: 'Mandate', minWidth: 100, filter: 'agTextColumnFilter', initialHide: true},
        {field: 'hash', headerName: 'Hash', minWidth: 160, cellClass: 'cell-mono', filter: 'agTextColumnFilter', initialHide: narrow}   /* link: row detail */
      ],
      id: function (r) { return String(r.n); },
      detail: function (r) {
        var s = r.signed || {};
        return {title: 'Ledger row #' + r.n + ' · ' + r.result + (r.reason ? ' · ' + r.reason : ''), fields: [
          ['time', r.ts_iso], ['result', r.result + (r.reason ? ' (' + r.reason + ')' : '')],
          ['mandate jti', r.mandate_id],
          ['sent to PayPal as', r.request_id ? 'PayPal-Request-Id: ' + r.request_id : 'not sent: the gate refused it before PayPal'],
          ['PayPal returned', r.paypal_id || '—'],
          ['action', r.action], ['recipient', r.resource],
          ['amount', r.amount ? 'USD ' + r.amount : '—'],
          ['signed cap', s.cap !== undefined ? 'USD ' + Number(s.cap).toFixed(2) : '—'],
          ['signed by', (s.iss || '?') + ' for ' + (s.sub || '?')],
          ['signed expiry', s.exp ? new Date(s.exp * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC' : '—'],
          ['plan_hash', r.plan_hash], ['hash', r.hash], ['prev', r.prev || '(first row)']],
          links: [['this row as written', '/ledger/entry/' + r.n]].concat(r.prev ? [['previous row #' + (r.n - 1), '/ledger/entry/' + (r.n - 1)]] : []),
          raw: null};
      }
    }
  };

  function renderDetail(box, d) {
    box.textContent = '';
    box.appendChild(el('h3', {}, d.title));
    var dl = el('dl');
    d.fields.forEach(function (f) { dl.appendChild(el('dt', {}, f[0])); dl.appendChild(el('dd', {}, f[1] === undefined ? '' : String(f[1]))); });
    box.appendChild(dl);
    if (d.links.length) {
      var p = el('p', {'class': 'hint'});
      d.links.forEach(function (l, i) { if (i) p.appendChild(document.createTextNode(' · ')); p.appendChild(el('a', {href: l[1]}, l[0])); });
      box.appendChild(p);
    }
    if (d.raw) { box.appendChild(el('p', {'class': 'hint'}, d.rawLabel)); box.appendChild(el('pre', {}, d.raw)); }
    box.hidden = false;
  }

  document.querySelectorAll('[data-grid]').forEach(function (wrap) {
    var name = wrap.getAttribute('data-grid'), spec = specs[name];
    var data = document.getElementById(name + '-data');
    if (!spec || !data) return;
    var rows = JSON.parse(data.textContent);
    if (!rows.length) return;                       /* the page already shows its empty state */
    var bar = document.querySelector('[data-toolbar="' + name + '"]');
    var detail = document.getElementById(name + '-detail');
    var filters = {};                               /* field -> value from the filter buttons */

    var host = el('div', {'class': 'grid-host', 'aria-label': name === 'ledger' ? 'Ledger rows' : 'Mandates'});
    wrap.appendChild(host);
    var api = agGrid.createGrid(host, {
      theme: theme(), columnDefs: spec.columns, rowData: rows, domLayout: 'autoHeight',
      /* on a phone the filter buttons above the grid replace the header filter icons */
      defaultColDef: {sortable: true, resizable: true, flex: 1, filter: false, suppressHeaderFilterButton: narrow},
      getRowId: function (p) { return spec.id(p.data); },
      rowSelection: {mode: 'singleRow', checkboxes: false, enableClickSelection: true},
      ensureDomOrder: true, animateRows: true, suppressDragLeaveHidesColumns: true,
      isExternalFilterPresent: function () { return Object.keys(filters).some(function (k) { return filters[k]; }); },
      doesExternalFilterPass: function (node) {
        return Object.keys(filters).every(function (k) { return !filters[k] || node.data[k] === filters[k]; });
      },
      onSelectionChanged: function () {
        var sel = api.getSelectedRows();
        if (detail && sel.length) renderDetail(detail, spec.detail(sel[0]));
        else if (detail) detail.hidden = true;
      },
      onCellKeyDown: function (e) {
        if (e.event && e.event.key === 'Enter') e.node.setSelected(true, true);
      }
    });
    wrap.classList.add('js-grid');

    if (bar) {
      bar.hidden = false;
      bar.querySelectorAll('[data-filter]').forEach(function (seg) {
        var field = seg.getAttribute('data-filter');
        seg.querySelectorAll('button').forEach(function (b) {
          b.addEventListener('click', function () {
            seg.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
            filters[field] = b.getAttribute('data-value');
            api.onFilterChanged();
          });
        });
      });
      var search = bar.querySelector('[data-search]');
      if (search) search.addEventListener('input', function () { api.setGridOption('quickFilterText', search.value); });
      var csv = bar.querySelector('[data-csv]');
      if (csv) csv.addEventListener('click', function () {
        api.exportDataAsCsv({fileName: 'ask-first-pay-' + name + '.csv', allColumns: true});
      });
    }

    /* the ledger opens on its newest row (the attempt that just happened); "#n=3" opens row 3 */
    var want = (location.hash.match(/^#n=(\d+)$/) || [])[1] || (name === 'ledger' || location.hash === '#latest' ? spec.id(rows[0]) : null);
    if (want) { var node = api.getRowNode(want); if (node) node.setSelected(true); }

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      api.setGridOption('theme', theme());
    });
    window.askFirstGrids = window.askFirstGrids || {};
    window.askFirstGrids[name] = api;
  });
})();
