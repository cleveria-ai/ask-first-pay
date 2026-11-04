/* Upgrades each [data-grid] table to AG Grid Community (vendored, MIT). The plain table stays as
   the no-JS fallback and is hidden only once the grid has been created. */
(function () {
  if (typeof agGrid === 'undefined') return;
  var specs = {
    mandates: [
      {field: 'short', headerName: 'Mandate', minWidth: 110},
      {field: 'state', headerName: 'State', minWidth: 100},
      {field: 'action', headerName: 'Action', minWidth: 150},
      {field: 'resource', headerName: 'Resource', minWidth: 120},
      {field: 'cap', headerName: 'Cap (USD)', minWidth: 100},
      {field: 'exp_text', headerName: 'Expires', minWidth: 120}
    ],
    ledger: [
      {field: 'n', headerName: '#', minWidth: 70, maxWidth: 80},
      {field: 'time', headerName: 'Time (UTC)', minWidth: 110},
      {field: 'result', headerName: 'Result', minWidth: 110,
       cellStyle: function (p) { return {fontWeight: 700, color: p.value === 'executed' ? '#0b6b3a' : '#9b1c1c'}; }},
      {field: 'reason', headerName: 'Reason', minWidth: 130},
      {field: 'mandate', headerName: 'Mandate', minWidth: 100},
      {field: 'action', headerName: 'Action', minWidth: 150},
      {field: 'resource', headerName: 'Resource', minWidth: 120},
      {field: 'amount', headerName: 'Amount', minWidth: 90},
      {field: 'hash', headerName: 'Hash', minWidth: 150}
    ]
  };
  document.querySelectorAll('[data-grid]').forEach(function (box) {
    var name = box.getAttribute('data-grid');
    var data = document.getElementById(name + '-data');
    if (!specs[name] || !data) return;
    var rows = JSON.parse(data.textContent);
    if (!rows.length) return;                       /* the table already says "none yet" */
    var el = document.createElement('div');
    el.style.minWidth = '640px';
    box.appendChild(el);
    agGrid.createGrid(el, {columnDefs: specs[name], rowData: rows, domLayout: 'autoHeight',
                           defaultColDef: {sortable: true, resizable: true, flex: 1}});
    box.classList.add('js-grid');
  });
})();
