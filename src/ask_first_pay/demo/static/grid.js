/* Upgrades each [data-grid] table to AG Grid Community 36 (vendored, MIT, no CDN).
   Used features, all Community: sorting (multi-column with shift), column text/number filters,
   external filters (the result / action / state buttons), quick filter (search box),
   custom cell renderers (status chips, hash links), single-row selection driving a detail panel
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
  function chip(tone) {
    return function (p) {
      if (!p.value) return '';
      var s = el('span', {'class': 'chip ' + (p.data.tone || tone || 'neutral')}, p.value);
      return s;
    };
  }
  function hashLink(p) {
    if (!p.value) return '';
    var a = el('a', {href: '/ledger/entry/' + p.data.n, title: 'Raw ledger row ' + p.data.n});
    a.appendChild(el('code', {}, p.value));
    return a;
  }
  function resultText(p) { return p.data.result + (p.data.reason ? ' · ' + p.data.reason : ''); }

  var specs = {
    mandates: {
      columns: [
        {field: 'short', headerName: 'Mandate', minWidth: 110, filter: 'agTextColumnFilter'},
        {field: 'state', headerName: 'State', minWidth: 120, cellRenderer: chip(), filter: 'agTextColumnFilter'},
        {field: 'action', headerName: 'Action', minWidth: 150, filter: 'agTextColumnFilter'},
        {field: 'resource', headerName: 'Resource', minWidth: 120, filter: 'agTextColumnFilter', initialHide: narrow},
        {field: 'cap', headerName: 'Cap (USD)', minWidth: 100, type: 'rightAligned', filter: 'agNumberColumnFilter',
         filterValueGetter: function (p) { return parseFloat(p.data.cap); },
         comparator: function (a, b) { return parseFloat(a) - parseFloat(b); }},
        {field: 'exp_text', headerName: 'Expires', minWidth: 120, initialHide: narrow}
      ],
      id: function (r) { return r.id; },
      detail: function (r) {
        return {title: 'Mandate ' + r.short + ' · ' + r.state, fields: [
          ['jti', r.id], ['action', r.action], ['recipient', r.resource], ['cap', 'USD ' + r.cap],
          ['created', r.created_text], ['expires', r.exp_text], ['plan_hash', r.plan_hash],
          ['ledger rows', (r.ledger && r.ledger.length) ? r.ledger.map(function (n) { return '#' + n; }).join(', ') : 'none yet']],
          links: (r.ledger || []).map(function (n) { return ['ledger row #' + n, '/ledger/entry/' + n]; }),
          raw: r.canonical, rawLabel: 'Exact bytes the owner signs (RFC 8785 canonical JSON)'};
      }
    },
    ledger: {
      columns: [
        {field: 'n', headerName: '#', minWidth: 64, maxWidth: 80, filter: 'agNumberColumnFilter', sort: 'desc'},
        {field: 'time', headerName: 'Time (UTC)', minWidth: 110, initialHide: narrow},
        {field: 'result', headerName: 'Result', minWidth: 170, cellRenderer: function (p) {
           return el('span', {'class': 'chip ' + p.data.tone}, resultText(p)); },
         getQuickFilterText: resultText, filter: 'agTextColumnFilter'},
        {field: 'action', headerName: 'Action', minWidth: 150, filter: 'agTextColumnFilter'},
        {field: 'resource', headerName: 'Resource', minWidth: 120, filter: 'agTextColumnFilter', initialHide: narrow},
        {field: 'amount', headerName: 'Amount', minWidth: 96, type: 'rightAligned', filter: 'agNumberColumnFilter',
         filterValueGetter: function (p) { return parseFloat(p.data.amount); },
         comparator: function (a, b) { return parseFloat(a || 0) - parseFloat(b || 0); }},
        {field: 'mandate', headerName: 'Mandate', minWidth: 100, filter: 'agTextColumnFilter', initialHide: narrow},
        {field: 'hash', headerName: 'Hash', minWidth: 160, cellRenderer: hashLink, filter: 'agTextColumnFilter', initialHide: narrow}
      ],
      id: function (r) { return String(r.n); },
      detail: function (r) {
        var s = r.signed || {};
        return {title: 'Ledger row #' + r.n + ' · ' + r.result + (r.reason ? ' · ' + r.reason : ''), fields: [
          ['time', r.ts_iso], ['result', r.result + (r.reason ? ' (' + r.reason + ')' : '')],
          ['mandate jti', r.mandate_id], ['action', r.action], ['recipient', r.resource],
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
      defaultColDef: {sortable: true, resizable: true, flex: 1, filter: false},
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

    /* "#latest" (after a replay) or "#n=3": open that row, so the newest attempt is explained */
    var want = location.hash === '#latest' ? String(rows[0] && spec.id(rows[0])) : (location.hash.match(/^#n=(\d+)$/) || [])[1];
    if (want) { var node = api.getRowNode(want); if (node) node.setSelected(true); }

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      api.setGridOption('theme', theme());
    });
    window.askFirstGrids = window.askFirstGrids || {};
    window.askFirstGrids[name] = api;
  });
})();
