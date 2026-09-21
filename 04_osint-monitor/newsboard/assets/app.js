/* ============================================================
   뉴스 스크랩 대시보드 · 검색/필터/모달
   데이터: data/news.json  { updated, total, site, groups, items:[{t,u,d,s,g,c,y}] }
     t=제목 u=원문URL d=보도일 s=매체 g=키워드그룹 c=주제 y=요약
   ============================================================ */
(function () {
  "use strict";

  var PAGE = 24;
  /* 그룹 이름은 data/news.json 의 groups(설정에서 옴)로 덮어쓴다 */
  var GROUP_LABEL = { org: "기관", site: "사업지", both: "공통" };
  var GROUP_FULL = { org: "기관", site: "사업지" };
  var GROUP_CLASS = { org: "badge-org", site: "badge-site", both: "badge-both" };
  var PERIODS = [
    { id: "all", label: "전체" },
    { id: "7", label: "최근 7일" },
    { id: "30", label: "최근 30일" },
    { id: "90", label: "최근 90일" },
    { id: "year", label: "올해" }
  ];

  var DATA = [];
  var state = { q: "", kw: "all", topic: "all", period: "all", source: "", sort: "new", shown: PAGE };
  var view = [];
  var lastFocus = null;

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var days = function (dstr) {
    if (!dstr) return 99999;
    var t = new Date(dstr + "T00:00:00+09:00").getTime();
    return isNaN(t) ? 99999 : Math.floor((Date.now() - t) / 86400000);
  };
  var fmtDate = function (d) { return d ? d.replace(/-/g, ".") : "날짜 미상"; };

  /* ── 검색어 하이라이트 ─────────────────────────────── */
  function hl(text, q) {
    var safe = esc(text);
    if (!q) return safe;
    var terms = q.split(/\s+/).filter(function (x) { return x.length > 0; });
    terms.forEach(function (term) {
      var re = new RegExp("(" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
      safe = safe.replace(re, "<mark>$1</mark>");
    });
    return safe;
  }

  /* ── 필터링 ────────────────────────────────────────── */
  function applyFilters() {
    var q = state.q.trim().toLowerCase();
    var terms = q ? q.split(/\s+/).filter(Boolean) : [];

    view = DATA.filter(function (it) {
      if (state.kw !== "all") {
        if (state.kw === "org" && it.g === "site") return false;
        if (state.kw === "site" && it.g === "org") return false;
      }
      if (state.topic !== "all" && it.c !== state.topic) return false;
      if (state.source && it.s !== state.source) return false;
      if (state.period !== "all") {
        if (state.period === "year") {
          if (it.d.slice(0, 4) !== String(new Date().getFullYear())) return false;
        } else if (days(it.d) > parseInt(state.period, 10)) return false;
      }
      if (terms.length) {
        var hay = (it.t + " " + it.y + " " + it.s + " " + it.c).toLowerCase();
        for (var i = 0; i < terms.length; i++) {
          if (hay.indexOf(terms[i]) === -1) return false;
        }
      }
      return true;
    });

    if (state.sort === "old") view.sort(function (a, b) { return a.d < b.d ? -1 : a.d > b.d ? 1 : 0; });
    else if (state.sort === "src") view.sort(function (a, b) { return a.s.localeCompare(b.s, "ko") || (a.d < b.d ? 1 : -1); });
    else view.sort(function (a, b) { return a.d > b.d ? -1 : a.d < b.d ? 1 : 0; });

    state.shown = PAGE;
    render();
  }

  /* ── 카드 렌더 ─────────────────────────────────────── */
  function render() {
    var box = $("cards");
    $("cnt").textContent = view.length.toLocaleString("ko-KR");

    if (!view.length) {
      box.innerHTML =
        '<div class="empty"><div class="empty-icon" aria-hidden="true">🔍</div>' +
        "<p>조건에 맞는 기사가 없습니다</p>" +
        "<span>검색어를 줄이거나 필터를 초기화해 보세요.</span></div>";
      $("moreWrap").hidden = true;
      renderActiveTags();
      return;
    }

    var list = view.slice(0, state.shown);
    var q = state.q.trim();
    box.innerHTML = list.map(function (it, i) {
      var fresh = days(it.d) <= 7;
      return '<button type="button" class="card" data-i="' + i + '">' +
        '<span class="card-top">' +
          '<span class="badge ' + GROUP_CLASS[it.g] + '">' + GROUP_LABEL[it.g] + "</span>" +
          (fresh ? '<span class="badge badge-new">NEW</span>' : "") +
          '<span class="card-date">' + fmtDate(it.d) + "</span>" +
        "</span>" +
        '<span class="card-title">' + hl(it.t, q) + "</span>" +
        (it.y ? '<span class="card-summary">' + hl(it.y, q) + "</span>" : "") +
        '<span class="card-foot">' +
          '<span class="card-source">' + esc(it.s) + " · " + esc(it.c) + "</span>" +
          '<span class="card-more">바로보기 →</span>' +
        "</span>" +
      "</button>";
    }).join("");

    var rest = view.length - list.length;
    $("moreWrap").hidden = rest <= 0;
    if (rest > 0) $("moreBtn").textContent = "기사 더 보기 (" + rest.toLocaleString("ko-KR") + "건 남음)";

    renderActiveTags();
  }

  /* ── 적용 중 필터 태그 ─────────────────────────────── */
  function renderActiveTags() {
    var tags = [];
    if (state.q.trim()) tags.push({ k: "q", t: '"' + state.q.trim() + '"' });
    if (state.kw !== "all") tags.push({ k: "kw", t: GROUP_LABEL[state.kw] });
    if (state.topic !== "all") tags.push({ k: "topic", t: state.topic });
    if (state.period !== "all") {
      var p = PERIODS.filter(function (x) { return x.id === state.period; })[0];
      tags.push({ k: "period", t: p ? p.label : state.period });
    }
    if (state.source) tags.push({ k: "source", t: state.source });

    $("activeTags").innerHTML = tags.map(function (x) {
      return '<span class="active-tag">' + esc(x.t) +
        '<button type="button" data-clear="' + x.k + '" aria-label="' + esc(x.t) + ' 필터 해제">✕</button></span>';
    }).join("");
  }

  /* ── 칩(버튼형 필터) 생성 ──────────────────────────── */
  function chips(containerId, list, stateKey) {
    var el = $(containerId);
    el.innerHTML = list.map(function (o) {
      return '<button type="button" class="chip" role="button" aria-pressed="' +
        (state[stateKey] === o.id) + '" data-v="' + esc(o.id) + '">' + esc(o.label) +
        (o.count != null ? '<span class="cnt">' + o.count + "</span>" : "") + "</button>";
    }).join("");
    el.addEventListener("click", function (e) {
      var b = e.target.closest(".chip");
      if (!b) return;
      state[stateKey] = b.dataset.v;
      Array.prototype.forEach.call(el.querySelectorAll(".chip"), function (c) {
        c.setAttribute("aria-pressed", String(c === b));
      });
      applyFilters();
    });
  }

  /* ── 모달 ──────────────────────────────────────────── */
  function openModal(it) {
    lastFocus = document.activeElement;
    $("modalBadges").innerHTML =
      '<span class="badge ' + GROUP_CLASS[it.g] + '">' + GROUP_LABEL[it.g] + "</span>" +
      (days(it.d) <= 7 ? '<span class="badge badge-new">NEW</span>' : "");
    $("modalTitle").textContent = it.t;
    $("modalSource").textContent = it.s;
    $("modalDate").textContent = fmtDate(it.d);
    $("modalTopic").textContent = it.c;
    var sm = $("modalSummary");
    if (it.y) { sm.textContent = it.y; sm.className = "modal-summary"; }
    else { sm.textContent = "이 기사는 요약 정보를 제공하지 않습니다. 원문 보기로 확인하세요."; sm.className = "modal-summary none"; }
    $("modalLink").href = it.u;
    var cb = $("copyBtn");
    cb.textContent = "링크 복사"; cb.className = "btn btn-ghost"; cb.dataset.url = it.u;

    var bg = $("modalBg");
    bg.hidden = false;
    requestAnimationFrame(function () { bg.classList.add("open"); });
    document.body.style.overflow = "hidden";
    $("modalClose").focus();
  }

  function closeModal() {
    var bg = $("modalBg");
    bg.classList.remove("open");
    bg.hidden = true;
    document.body.style.overflow = "";
    if (lastFocus) lastFocus.focus();
  }

  /* ── 초기화 ────────────────────────────────────────── */
  function init(payload) {
    DATA = payload.items || [];
    var G = payload.groups || {};
    ["org", "site"].forEach(function (k) {
      if (G[k]) { GROUP_LABEL[k] = G[k].short || GROUP_LABEL[k]; GROUP_FULL[k] = G[k].label || GROUP_FULL[k]; }
    });
    var site = payload.site || {};
    if (site.title) { $("siteTitle").textContent = site.title; document.title = site.title; }
    if (site.subtitle) { $("siteSub").textContent = site.subtitle; }
    $("l-org").textContent = GROUP_FULL.org;
    $("l-site").textContent = GROUP_FULL.site;
    $("f-groups").textContent = GROUP_FULL.org + ", " + GROUP_FULL.site;
    $("updated").textContent = "· " + payload.updated + " 기준";
    $("updated2").textContent = payload.updated;

    var nK = DATA.filter(function (x) { return x.g !== "site"; }).length;
    var nA = DATA.filter(function (x) { return x.g !== "org"; }).length;
    $("s-total").innerHTML = DATA.length.toLocaleString("ko-KR") + "<small>건</small>";
    $("s-org").innerHTML = nK.toLocaleString("ko-KR") + "<small>건</small>";
    $("s-site").innerHTML = nA.toLocaleString("ko-KR") + "<small>건</small>";
    $("s-recent").innerHTML = DATA.filter(function (x) { return days(x.d) <= 7; }).length + "<small>건</small>";

    chips("f-keyword", [
      { id: "all", label: "전체", count: DATA.length },
      { id: "org", label: GROUP_FULL.org, count: nK },
      { id: "site", label: GROUP_FULL.site, count: nA }
    ], "kw");

    var byTopic = {};
    DATA.forEach(function (x) { byTopic[x.c] = (byTopic[x.c] || 0) + 1; });
    var topics = Object.keys(byTopic).sort(function (a, b) { return byTopic[b] - byTopic[a]; });
    chips("f-topic", [{ id: "all", label: "전체", count: DATA.length }].concat(
      topics.map(function (t) { return { id: t, label: t, count: byTopic[t] }; })), "topic");

    chips("f-period", PERIODS.map(function (p) {
      var c = p.id === "all" ? DATA.length
        : p.id === "year" ? DATA.filter(function (x) { return x.d.slice(0, 4) === String(new Date().getFullYear()); }).length
        : DATA.filter(function (x) { return days(x.d) <= parseInt(p.id, 10); }).length;
      return { id: p.id, label: p.label, count: c };
    }), "period");

    var bySrc = {};
    DATA.forEach(function (x) { bySrc[x.s] = (bySrc[x.s] || 0) + 1; });
    var sel = $("f-source");
    Object.keys(bySrc).sort(function (a, b) { return bySrc[b] - bySrc[a] || a.localeCompare(b, "ko"); })
      .forEach(function (s) {
        var o = document.createElement("option");
        o.value = s; o.textContent = s + " (" + bySrc[s] + ")";
        sel.appendChild(o);
      });

    /* 이벤트 */
    var qi = $("q"), tmr = null;
    qi.addEventListener("input", function () {
      $("searchWrap").classList.toggle("has-value", qi.value.length > 0);
      clearTimeout(tmr);
      tmr = setTimeout(function () { state.q = qi.value; applyFilters(); }, 180);
    });
    qi.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { qi.value = ""; state.q = ""; $("searchWrap").classList.remove("has-value"); applyFilters(); }
    });
    $("clearBtn").addEventListener("click", function () {
      qi.value = ""; state.q = ""; $("searchWrap").classList.remove("has-value"); applyFilters(); qi.focus();
    });
    sel.addEventListener("change", function () { state.source = sel.value; applyFilters(); });
    $("f-sort").addEventListener("change", function () { state.sort = this.value; applyFilters(); });

    $("resetBtn").addEventListener("click", function () {
      state = { q: "", kw: "all", topic: "all", period: "all", source: "", sort: "new", shown: PAGE };
      qi.value = ""; sel.value = ""; $("f-sort").value = "new";
      $("searchWrap").classList.remove("has-value");
      ["f-keyword", "f-topic", "f-period"].forEach(function (id) {
        Array.prototype.forEach.call($(id).querySelectorAll(".chip"), function (c, i) {
          c.setAttribute("aria-pressed", String(i === 0));
        });
      });
      applyFilters();
    });

    $("activeTags").addEventListener("click", function (e) {
      var b = e.target.closest("[data-clear]");
      if (!b) return;
      var k = b.dataset.clear;
      if (k === "q") { qi.value = ""; state.q = ""; $("searchWrap").classList.remove("has-value"); }
      else if (k === "source") { state.source = ""; sel.value = ""; }
      else {
        state[k] = "all";
        var box = $(k === "kw" ? "f-keyword" : k === "topic" ? "f-topic" : "f-period");
        Array.prototype.forEach.call(box.querySelectorAll(".chip"), function (c, i) {
          c.setAttribute("aria-pressed", String(i === 0));
        });
      }
      applyFilters();
    });

    $("moreBtn").addEventListener("click", function () { state.shown += PAGE; render(); });

    $("cards").addEventListener("click", function (e) {
      var c = e.target.closest(".card");
      if (c) openModal(view[parseInt(c.dataset.i, 10)]);
    });

    $("modalClose").addEventListener("click", closeModal);
    $("modalBg").addEventListener("click", function (e) { if (e.target === this) closeModal(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !$("modalBg").hidden) closeModal();
      if (e.key === "/" && document.activeElement !== qi) { e.preventDefault(); qi.focus(); }
    });
    $("copyBtn").addEventListener("click", function () {
      var self = this, url = this.dataset.url;
      var done = function () { self.textContent = "복사 완료"; self.className = "btn btn-ghost copied";
        setTimeout(function () { self.textContent = "링크 복사"; self.className = "btn btn-ghost"; }, 1600); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url).then(done).catch(function () {});
      } else {
        var ta = document.createElement("textarea");
        ta.value = url; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); done(); } catch (err) {}
        document.body.removeChild(ta);
      }
    });

    applyFilters();
  }

  fetch("data/news.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(init)
    .catch(function (err) {
      $("cards").innerHTML =
        '<div class="empty"><div class="empty-icon" aria-hidden="true">⚠️</div>' +
        "<p>데이터를 불러오지 못했습니다</p><span>" + esc(err.message) +
        " · 로컬에서 열 때는 파일 직접 열기 대신 <code>python3 -m http.server</code> 로 실행하세요.</span></div>";
    });
})();
