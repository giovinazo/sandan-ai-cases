/* 배경 입자.
   SpaceX 화면에서 그 자리를 차지하는 것은 사진이다. 쓸 사진이 없으니 흑백 점으로 대신한다.
   색은 흰색 하나, 도형은 점 하나뿐이다(명세: 강조색·장식 도형 금지).

   깊이를 세 겹으로 나눠 먼 겹은 어둡고 느리게, 가까운 겹은 밝고 빠르게 흐른다.
   마우스를 움직이면 겹마다 다른 폭으로 따라와 시차가 생긴다. */

(function () {
  "use strict";

  var cv = document.getElementById("stars");
  if (!cv || !cv.getContext) return;
  var ctx = cv.getContext("2d", { alpha: false });

  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;

  var LAYERS = [
    { n: 0.45, r: [0.4, 0.9], a: [0.18, 0.34], v: 0.010, par: 6 },   // 먼 겹
    { n: 0.35, r: [0.7, 1.3], a: [0.34, 0.58], v: 0.020, par: 14 },
    { n: 0.20, r: [1.0, 1.9], a: [0.55, 0.92], v: 0.034, par: 26 }   // 가까운 겹
  ];

  var W = 0, H = 0, dpr = 1, stars = [], last = 0;
  var mx = 0, my = 0, tx = 0, ty = 0;                 // 마우스 시차: 목표값과 현재값

  function rand(a, b) { return a + Math.random() * (b - a); }

  function build() {
    var area = (W * H) / (1920 * 1080);
    var total = Math.round(Math.min(Math.max(area * 260, 90), 340));
    stars = [];
    LAYERS.forEach(function (L, li) {
      for (var i = 0; i < Math.round(total * L.n); i++) {
        stars.push({
          x: Math.random() * W, y: Math.random() * H,
          r: rand(L.r[0], L.r[1]) * dpr,
          a: rand(L.a[0], L.a[1]),
          v: L.v * dpr * rand(0.7, 1.35),
          tw: Math.random() * Math.PI * 2,            // 깜빡임 위상
          li: li
        });
      }
    });
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = cv.width = Math.floor(window.innerWidth * dpr);
    H = cv.height = Math.floor(window.innerHeight * dpr);
    build();
    draw(0);
  }

  function draw(dt) {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);

    // 시차는 부드럽게 따라온다
    mx += (tx - mx) * 0.055;
    my += (ty - my) * 0.055;

    for (var i = 0; i < stars.length; i++) {
      var s = stars[i], L = LAYERS[s.li];
      if (!still) {
        s.y -= s.v * dt;                              // 위로 아주 천천히 흐른다
        if (s.y < -2) { s.y = H + 2; s.x = Math.random() * W; }
        s.tw += 0.0012 * dt;
      }
      var a = still ? s.a : s.a * (0.78 + 0.22 * Math.sin(s.tw));
      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(s.x + mx * L.par * dpr, s.y + my * L.par * dpr, s.r, 0, 6.2832);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function loop(t) {
    var dt = Math.min(t - last, 50);
    last = t;
    draw(dt);
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", resize, { passive: true });
  if (!coarse && !still) {
    window.addEventListener("mousemove", function (e) {
      tx = (e.clientX / window.innerWidth - 0.5) * 2;   // -1 ~ 1
      ty = (e.clientY / window.innerHeight - 0.5) * 2;
    }, { passive: true });
  }

  resize();
  if (still) draw(0); else requestAnimationFrame(loop);
})();
