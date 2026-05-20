// ─────────────────────────────────────────────────────────────────────────────
// 3 Lakes Logistics — Universal TimeKeeper (TK)
// Single source of truth for all date/time logic across every platform:
//   website · Eagle Eye · driver PWA · execution engine UI
//
// Include once per page:  <script src="/shared/tk.js"></script>
//                         <script src="../shared/tk.js"></script>
//
// Exposes window.TK immediately so downstream scripts can use it.
// Stamps .tk-* elements automatically on DOMContentLoaded.
// ─────────────────────────────────────────────────────────────────────────────
(function () {
  if (window.TK) return; // already loaded — skip re-init

  var now = new Date();
  var y   = now.getFullYear();
  var m   = now.getMonth();   // 0-11
  var d   = now.getDate();
  var q   = Math.floor(m / 3) + 1; // IFTA quarter 1-4

  var Q_META = [
    { n: 'Q1', start: 'Jan', end: 'Mar', dlMonth: 'Apr', dlDay: 30, dlM: 3 },
    { n: 'Q2', start: 'Apr', end: 'Jun', dlMonth: 'Jul', dlDay: 31, dlM: 6 },
    { n: 'Q3', start: 'Jul', end: 'Sep', dlMonth: 'Oct', dlDay: 31, dlM: 9 },
    { n: 'Q4', start: 'Oct', end: 'Dec', dlMonth: 'Jan', dlDay: 31, dlM: 0, nextYear: true },
  ];

  function iftaDeadline(quarter, year) {
    var meta = Q_META[quarter - 1];
    var dlYear = meta.nextYear ? year + 1 : year;
    var date = new Date(dlYear, meta.dlM, meta.dlDay);
    var daysLeft = Math.ceil((date - now) / 86400000);
    return {
      label: meta.dlMonth + ' ' + meta.dlDay + ', ' + dlYear,
      short: meta.dlMonth + ' ' + meta.dlDay,
      date: date,
      daysLeft: daysLeft,
      past: now > date,
      year: dlYear,
    };
  }

  function iftaStatus(quarter, year) {
    var dl = iftaDeadline(quarter, year);
    if (dl.past) return { label: 'Filed', cls: 'badge-green' };
    if (quarter === q && year === y) return { label: 'In Progress', cls: 'badge-orange' };
    return { label: 'Upcoming', cls: 'badge-ghost' };
  }

  // Returns rolling window: 2 prior quarters, current, 1 future
  function allQuarters() {
    var rows = [];
    for (var i = -2; i <= 1; i++) {
      var qn = q + i, yn = y;
      if (qn < 1) { qn += 4; yn -= 1; }
      if (qn > 4) { qn -= 4; yn += 1; }
      rows.push({
        q: qn, y: yn,
        meta: Q_META[qn - 1],
        dl: iftaDeadline(qn, yn),
        st: iftaStatus(qn, yn),
        isCurrent: (qn === q && yn === y),
      });
    }
    return rows;
  }

  // 2290 HVUT — due Aug 31 every year
  function hvut() {
    var thisYearDue = new Date(y, 7, 31);
    var filingYear  = now > thisYearDue ? y + 1 : y;
    var dueDate     = new Date(filingYear, 7, 31);
    var daysLeft    = Math.ceil((dueDate - now) / 86400000);
    if (daysLeft < 0)   return { desc: 'Annual IRS filing · Filed ' + y + ' · Next due Aug 31, ' + (y + 1), badge: 'badge-green',  label: 'Filed ' + y };
    if (daysLeft <= 90) return { desc: 'Annual IRS filing · Due Aug 31, ' + filingYear + ' (' + daysLeft + ' days)', badge: 'badge-orange', label: 'Due Soon' };
    return { desc: 'Annual IRS filing · Due Aug 31, ' + filingYear, badge: 'badge-ghost', label: 'Upcoming', year: filingYear };
  }

  // UCR — renewal window opens Oct 1 for following calendar year
  function ucr() {
    var renewOpen = new Date(y, 9, 1);
    if (now >= renewOpen) return { desc: 'UCR · $76 · Renew now for ' + (y + 1), badge: 'badge-orange', label: 'Renew Now' };
    return { desc: 'UCR · $76 · Current through ' + y, badge: 'badge-green', label: 'Current' };
  }

  // Insurance expiry — pass "MM/DD/YY" or "MM/DD/YYYY"
  function insStatus(dateStr) {
    if (!dateStr) return { cls: 'badge-ghost', label: 'Unknown' };
    var p = dateStr.split('/');
    var yr = p[2].length === 2 ? 2000 + parseInt(p[2], 10) : parseInt(p[2], 10);
    var exp = new Date(yr, parseInt(p[0], 10) - 1, parseInt(p[1], 10));
    var days = Math.ceil((exp - now) / 86400000);
    if (days < 0)   return { cls: 'badge-red',    label: 'Expired' };
    if (days <= 60) return { cls: 'badge-orange',  label: 'Expiring Soon' };
    return { cls: 'badge-green', label: 'Active' };
  }

  // CDL / medical card expiry — pass ISO date string "YYYY-MM-DD"
  function licenseStatus(isoDate) {
    if (!isoDate) return { cls: 'badge-ghost', label: 'Unknown', daysLeft: null };
    var exp = new Date(isoDate);
    var days = Math.ceil((exp - now) / 86400000);
    if (days < 0)    return { cls: 'badge-red',    label: 'Expired',         daysLeft: days };
    if (days <= 30)  return { cls: 'badge-red',    label: 'Expires in ' + days + 'd', daysLeft: days };
    if (days <= 90)  return { cls: 'badge-orange',  label: 'Expires in ' + days + 'd', daysLeft: days };
    return { cls: 'badge-green', label: 'Valid', daysLeft: days };
  }

  // Current fiscal/calendar year helpers
  var cur = Q_META[q - 1];
  var currentDeadline = iftaDeadline(q, y);

  window.TK = {
    now:  now,
    y:    y,
    m:    m,
    d:    d,
    q:    q,
    qLabel:          'Q' + q,
    qYear:           y,
    qRange:          cur.start + '–' + cur.end + ' ' + y,
    currentDeadline: currentDeadline,
    prevQ:           q === 1 ? 4 : q - 1,
    prevY:           q === 1 ? y - 1 : y,
    // Methods
    iftaDeadline:  iftaDeadline,
    iftaStatus:    iftaStatus,
    allQuarters:   allQuarters,
    hvut:          hvut,
    ucr:           ucr,
    insStatus:     insStatus,
    licenseStatus: licenseStatus,
    // Stamp all .tk-* elements in the DOM
    stampDOM: function () {
      var hv = hvut();
      var hvYear = hv.year || y;
      var map = {
        '.tk-year':          y,
        '.tk-copyright-year': y,
        '.tk-next-year':     y + 1,
        '.tk-qLabel':        'Q' + q + ' ' + y,
        '.tk-iftaDue':       currentDeadline.label,
        '.tk-hvutYear':      hvYear,
        '.tk-qRange':        cur.start + '–' + cur.end + ' ' + y,
      };
      Object.keys(map).forEach(function (sel) {
        document.querySelectorAll(sel).forEach(function (el) {
          el.textContent = map[sel];
        });
      });
    },
  };

  // Auto-stamp on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.TK.stampDOM);
  } else {
    window.TK.stampDOM();
  }
})();
