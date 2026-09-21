// 정책·현안 SNS 모아보기: 화면 로직 (무빌드, data.js 를 그대로 읽는다)
(function () {
  "use strict";
  var POSTS = window.POSTS || [];
  var META = window.META || {};

  var state = { platform: "전체", person: "전체", group: "전체", onlyhit: false, q: "" };

  var PLAT_LABEL = { rss: "RSS", blog: "BLOG", youtube: "YOUTUBE", custom: "기타", x: "X", facebook: "FACEBOOK" };
  var PLATFORMS = ["전체"].concat(META.platforms || []);

  function esc(s) { return (s || "").replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function fmtUpdated(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return iso.slice(0, 16).replace("T", " ");
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  // ── 필터 버튼 만들기 ──
  // 계정 순서: targets.json 의 accounts 에 적은 순서(META.persons). 없으면 가나다순
  var ORDER = META.persons || [];
  function personRank(author) {
    var i = ORDER.indexOf(author);
    return i < 0 ? 999 : i;
  }
  function uniquePersons() {
    var seen = {}, list = [];
    POSTS.forEach(function (p) { if (!seen[p.author]) { seen[p.author] = 1; list.push(p.author); } });
    list.sort(function (a, b) { return (personRank(a) - personRank(b)) || a.localeCompare(b, "ko"); });
    return list;
  }

  function makePills(hostId, key, values, counts) {
    var host = document.getElementById(hostId);
    host.innerHTML = "";
    values.forEach(function (v) {
      var b = document.createElement("button");
      b.className = "pill" + (state[key] === v ? " on" : "");
      var n = counts && counts[v] != null ? ' <span class="n">' + counts[v] + "</span>" : "";
      var label = v;
      if (key === "platform" && PLAT_LABEL[v]) label = PLAT_LABEL[v];
      b.innerHTML = esc(label) + n;
      b.onclick = function () { state[key] = v; render(); };
      host.appendChild(b);
    });
  }

  function countBy(fn) {
    var c = { "전체": POSTS.length };
    POSTS.forEach(function (p) { var k = fn(p); if (k) c[k] = (c[k] || 0) + 1; });
    return c;
  }

  function siteText() {
    var st = META.site || {};
    if (st.title) { document.getElementById("siteTitle").textContent = st.title; document.title = st.title; }
    if (st.eyebrow) document.getElementById("eyebrow").textContent = st.eyebrow;
    if (st.hub_url) {
      ["hubLink", "hubLink2"].forEach(function (id) { document.getElementById(id).href = st.hub_url; });
    }
    if (st.hub_name) document.getElementById("hubLink").textContent = "◂ " + st.hub_name;
  }

  function buildFilters() {
    siteText();
    document.getElementById("upd").textContent = fmtUpdated(META.updated);
    document.getElementById("s-total").textContent = META.total || POSTS.length;
    document.getElementById("s-hit").textContent = META.detected || 0;
    var accs = {}; POSTS.forEach(function (p) { accs[p.account || p.author] = 1; });
    document.getElementById("s-acc").textContent = Object.keys(accs).length;

    makePills("f-platform", "platform", PLATFORMS, countBy(function (p) { return p.platform; }));
    makePills("f-person", "person", ["전체"].concat(uniquePersons()), countBy(function (p) { return p.author; }));
    var gcounts = { "전체": POSTS.length };
    (META.groups || []).forEach(function (g) { gcounts[g] = POSTS.filter(function (p) { return p.groups.indexOf(g) >= 0; }).length; });
    makePills("f-group", "group", ["전체"].concat(META.groups || []), gcounts);

    var oh = document.getElementById("f-onlyhit");
    oh.onclick = function () { state.onlyhit = !state.onlyhit; oh.classList.toggle("on", state.onlyhit); render(); };
    document.getElementById("q").oninput = function (e) { state.q = e.target.value.trim(); render(); };
  }

  // ── 걸러내기 ──
  function match(p) {
    if (state.platform !== "전체" && p.platform !== state.platform) return false;
    if (state.person !== "전체" && p.author !== state.person) return false;
    if (state.group !== "전체" && p.groups.indexOf(state.group) < 0) return false;
    if (state.onlyhit && !p.hit) return false;
    if (state.q && p.text.toLowerCase().indexOf(state.q.toLowerCase()) < 0) return false;
    return true;
  }

  // ── 검색어 하이라이트 ──
  function highlight(text) {
    var h = esc(text);
    if (state.q) {
      var re = new RegExp("(" + state.q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      h = h.replace(re, "<mark style='background:#fff;color:#000'>$1</mark>");
    }
    return h;
  }

  function card(p) {
    var chips = (p.groups || []).map(function (g) { return '<span class="chip grp">' + esc(g) + "</span>"; }).join("");
    var kw = (p.kw || []).slice(0, 4).map(function (w) { return '<span class="chip">' + esc(w) + "</span>"; }).join("");
    var orig = p.url ? '<a class="orig" href="' + esc(p.url) + '" target="_blank" rel="noopener">원문 ↗</a>' : "";
    var thumb = p.thumb
      ? '<a class="thumb" href="' + esc(p.url || p.thumb) + '" target="_blank" rel="noopener">' +
        '<img loading="lazy" src="' + esc(p.thumb) + '" alt=""></a>'
      : "";
    return '<article class="card' + (p.priority ? " pri" : "") + '">' +
      '<div class="who"><span class="nm">' + esc(p.author) + "</span>" +
      '<span class="rl">' + esc(p.role) + "</span>" +
      '<span class="pf' + (p.platform === "facebook" ? " fb" : "") + '">' + (PLAT_LABEL[p.platform] || p.platform) + "</span></div>" +
      '<div class="body">' + thumb + '<div class="txt">' + highlight(p.text) + "</div>" +
      '<div class="meta"><span class="date">' + esc(p.date || "") + "</span>" +
      chips + kw + orig + "</div></div></article>";
  }

  function render() {
    document.querySelectorAll(".filters .pill").forEach(function (b) { /* rebuilt below */ });
    // 활성 표시 갱신
    makePills("f-platform", "platform", PLATFORMS, countBy(function (p) { return p.platform; }));
    makePills("f-person", "person", ["전체"].concat(uniquePersons()), countBy(function (p) { return p.author; }));
    var gcounts = { "전체": POSTS.length };
    (META.groups || []).forEach(function (g) { gcounts[g] = POSTS.filter(function (p) { return p.groups.indexOf(g) >= 0; }).length; });
    makePills("f-group", "group", ["전체"].concat(META.groups || []), gcounts);
    document.getElementById("f-onlyhit").classList.toggle("on", state.onlyhit);

    var rows = POSTS.filter(match);
    var feed = document.getElementById("feed");
    document.getElementById("countline").textContent = rows.length + "건 표시" + (state.onlyhit ? " · 감지만" : "");
    if (!rows.length) { feed.innerHTML = '<div class="empty">조건에 맞는 게시물이 없습니다.</div>'; return; }
    feed.innerHTML = rows.map(card).join("");
  }

  buildFilters();
  render();
})();
