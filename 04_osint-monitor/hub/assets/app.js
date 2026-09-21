/* 각 화면이 배포해 둔 status.json(수백 바이트)만 읽어 숫자를 채운다.
   원본 데이터는 수백 KB라 허브에서 통째로 받지 않는다. 사이트 목록은 sites.js.
   못 받아도 타일은 그대로 뜨고 링크는 살아 있다. */

(function () {
  "use strict";

  var CFG = window.HUB_CONFIG || { sites: [] };
  var SITES = CFG.sites || [];
  /* 주소에 ?sample 을 붙이면 각 사이트의 로컬 예시 status 파일을 읽는다 */
  var SAMPLE = /[?&]sample\b/.test(location.search);

  function setText(id, v) { var el = document.getElementById(id); if (el && v) el.textContent = v; }
  setText("h-title", CFG.title);
  setText("h-eyebrow", CFG.eyebrow);
  setText("h-wordmark", CFG.wordmark);
  setText("h-footer", CFG.footer);
  if (CFG.eyebrow && CFG.title) document.title = CFG.eyebrow + " " + CFG.title;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* "2026-08-28T09:19:44+09:00" 과 "2026-08-28 08:47" 두 표기를 모두 받는다 */
  function parseWhen(s) {
    if (!s) return null;
    var d = new Date(/T/.test(s) ? s : s.replace(" ", "T") + "+09:00");
    return isNaN(d.getTime()) ? null : d;
  }
  function fmtWhen(d) {
    var p = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "." + p(d.getMonth() + 1) + "." + p(d.getDate()) +
           " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  document.getElementById("tiles").innerHTML = SITES.map(function (s) {
    return '<a class="tile" id="t-' + s.key + '" href="' + esc(s.url) + '" ' +
      'target="_blank" rel="noopener">' +
      '<span class="no">' + esc(s.no) + "</span>" +
      '<span class="val">' + (s.fixed
        ? esc(Number(s.fixed.value).toLocaleString("ko-KR")) +
          '<span class="unit">' + esc(s.fixed.unit) + "</span>"
        : "—") + "</span>" +
      '<span class="cap">' + esc(s.cap) + "</span>" +
      '<span class="name">' + esc(s.name) + "</span>" +
      '<span class="cta">열기</span></a>';
  }).join("");

  var jobs = SITES.filter(function (s) { return s.status; }).map(function (s) {
    var src = SAMPLE && s.sample ? s.sample : s.status;
    return fetch(src, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) {
        var tile = document.getElementById("t-" + s.key);
        var m = (j.metrics || []).filter(function (x) { return x.label === s.pick; })[0]
                || (j.metrics || [])[0];
        if (tile && m) {
          tile.querySelector(".val").innerHTML =
            esc(Number(m.value).toLocaleString("ko-KR")) +
            (m.unit ? '<span class="unit">' + esc(m.unit) + "</span>" : "");
          tile.querySelector(".cap").textContent = s.cap;
          tile.title = m.label + " " + Number(m.value).toLocaleString("ko-KR") + (m.unit || "");
        }
        var when = parseWhen(j.updated);
        if (when && tile) tile.title = (tile.title ? tile.title + " · " : "") + fmtWhen(when) + " 기준";
        return { when: when, stale: when ? (Date.now() - when.getTime()) / 36e5 > s.staleHours : true };
      })
      .catch(function () { return { when: null, stale: true }; });
  });

  Promise.all(jobs).then(function (res) {
    var stale = res.filter(function (r) { return r.stale; }).length;
    var newest = res.reduce(function (a, r) {
      return r.when && (!a || r.when > a) ? r.when : a;
    }, null);
    document.getElementById("nav-meta").innerHTML = newest
      ? (stale ? "지연 " + stale : '<span class="on">최신</span>') + " · " + esc(fmtWhen(newest))
      : "";
  });
})();
