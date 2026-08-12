/* 比目鱼（Bimuyu） · 财务视图图表（纯 SVG，无外部依赖）
 * - 环形图：收入构成（成本 / 利润），中心显示毛利率
 * - 折线图：毛利率按里程碑走势
 * - 导出 PNG (2x)：两张图合并为一张 2x 分辨率 PNG
 * 配色严格使用 halo.css 设计 token 对应十六进制，确保 SVG 序列化导出时颜色一致。
 */
(function () {
  "use strict";

  var pnl = window.__PNL__ || {};
  var curve = window.__CURVE__ || [];

  var C = {
    primary: "#9ACD32",
    success: "#2BE08C",
    error: "#FF3A5C",
    warning: "#F5D547",
    text: "#ECECEC",
    sub: "#9AA0AD",
    grid: "#2A2D38",
    surface: "#1C1E26",
  };

  function el(id) { return document.getElementById(id); }

  function emptyState(msg) {
    return (
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;' +
      "color:" + C.sub + ";font-size:13px;text-align:center;padding:24px;line-height:1.6\">" +
      msg + "</div>"
    );
  }

  /* ---------- 环形图：成本 vs 利润（= 收入 100%） ---------- */
  function renderDonut() {
    var svg = el("pnlDonut");
    if (!svg) return;
    var rev = pnl.revenue || 0;
    var cost = pnl.cost || 0;
    if (rev <= 0) {
      svg.innerHTML = emptyState("暂无收入数据<br>采纳报价后自动计算");
      return;
    }
    var W = 260, H = 260, cx = 130, cy = 130, r = 92, sw = 26;
    var circ = 2 * Math.PI * r;
    var costFrac = Math.min(cost / rev, 1);
    var profitFrac = Math.max(1 - costFrac, 0);
    var margin = pnl.margin_pct != null ? pnl.margin_pct.toFixed(1) + "%" : "—";

    function seg(frac, color, offsetFrac) {
      var len = circ * frac;
      var dash = len.toFixed(2) + " " + (circ - len).toFixed(2);
      var rot = offsetFrac * 360 - 90;
      return (
        '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' +
        color + '" stroke-width="' + sw + '" stroke-dasharray="' + dash +
        '" transform="rotate(' + rot + " " + cx + " " + cy + ')" stroke-linecap="butt"/>'
      );
    }

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.innerHTML =
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + C.grid + '" stroke-width="' + sw + '"/>' +
      seg(costFrac, C.error, 0) +
      seg(profitFrac, C.success, costFrac) +
      '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" fill="' + C.text + '" font-size="28" font-weight="700">' + margin + "</text>" +
      '<text x="' + cx + '" y="' + (cy + 18) + '" text-anchor="middle" fill="' + C.sub + '" font-size="12">毛利率</text>';
  }

  /* ---------- 折线图：毛利率按里程碑 ---------- */
  function renderLine() {
    var svg = el("pnlLine");
    if (!svg) return;
    if (!curve.length) {
      svg.innerHTML = emptyState("暂无里程碑数据<br>添加里程碑后展示毛利率走势");
      return;
    }
    var W = 440, H = 250, padL = 46, padR = 18, padT = 20, padB = 44;
    var n = curve.length;
    var ms = curve
      .map(function (p) { return p.margin_pct; })
      .filter(function (v) { return v != null; });
    var maxM = 100, minM = 0;
    if (ms.length) {
      maxM = Math.max(100, Math.ceil(Math.max.apply(null, ms) / 10) * 10);
      minM = Math.min(0, Math.floor(Math.min.apply(null, ms) / 10) * 10);
    }
    function X(i) { return padL + (W - padL - padR) * (n === 1 ? 0.5 : i / (n - 1)); }
    function Y(v) { return padT + (H - padT - padB) * (1 - (v - minM) / (maxM - minM)); }

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);

    var parts = [];
    // 网格 + y 轴标签
    var ticks = 4;
    for (var t = 0; t <= ticks; t++) {
      var val = minM + (maxM - minM) * (t / ticks);
      var yy = Y(val);
      parts.push(
        '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR) +
        '" y2="' + yy.toFixed(1) + '" stroke="' + C.grid + '" stroke-width="1"/>'
      );
      parts.push(
        '<text x="' + (padL - 8) + '" y="' + (yy + 4).toFixed(1) +
        '" text-anchor="end" fill="' + C.sub + '" font-size="10">' + val.toFixed(0) + "%</text>"
      );
    }
    // 折线点
    var linePts = [];
    for (var i = 0; i < n; i++) {
      var m = curve[i].margin_pct;
      if (m == null) continue;
      linePts.push([X(i), Y(m)]);
    }
    if (linePts.length) {
      var areaD = "M" + linePts[0][0].toFixed(1) + "," + Y(minM).toFixed(1);
      for (var k = 0; k < linePts.length; k++) {
        areaD += " L" + linePts[k][0].toFixed(1) + "," + linePts[k][1].toFixed(1);
      }
      areaD += " L" + linePts[linePts.length - 1][0].toFixed(1) + "," + Y(minM).toFixed(1) + " Z";
      parts.push('<path d="' + areaD + '" fill="' + C.success + '" fill-opacity="0.12"/>');
      var d = "";
      for (var j = 0; j < linePts.length; j++) {
        d += (j ? "L" : "M") + linePts[j][0].toFixed(1) + "," + linePts[j][1].toFixed(1) + " ";
      }
      parts.push(
        '<path d="' + d + '" fill="none" stroke="' + C.success + '" stroke-width="2.5" stroke-linejoin="round"/>'
      );
      for (var q = 0; q < linePts.length; q++) {
        parts.push(
          '<circle cx="' + linePts[q][0].toFixed(1) + '" cy="' + linePts[q][1].toFixed(1) +
          '" r="3.5" fill="' + C.surface + '" stroke="' + C.success + '" stroke-width="2"/>'
        );
      }
    }
    // x 轴标签
    for (var x = 0; x < n; x++) {
      var label = curve[x].name || ("M" + (x + 1));
      if (label.length > 8) label = label.slice(0, 7) + "…";
      parts.push(
        '<text x="' + X(x).toFixed(1) + '" y="' + (H - padB + 16) +
        '" text-anchor="middle" fill="' + C.sub + '" font-size="10">' + label + "</text>"
      );
      if (curve[x].date) {
        parts.push(
          '<text x="' + X(x).toFixed(1) + '" y="' + (H - padB + 28) +
          '" text-anchor="middle" fill="' + C.sub + '" font-size="9" opacity="0.7">' +
          curve[x].date + "</text>"
        );
      }
    }
    svg.innerHTML = parts.join("");
  }

  /* ---------- 导出 PNG (2x) ---------- */
  function svgToCanvas(svg, scale) {
    return new Promise(function (resolve, reject) {
      var xml = new XMLSerializer().serializeToString(svg);
      var img = new Image();
      img.onload = function () {
        var w = parseInt(svg.getAttribute("width"), 10) || svg.clientWidth || 260;
        var h = parseInt(svg.getAttribute("height"), 10) || svg.clientHeight || 260;
        var c = document.createElement("canvas");
        c.width = w * scale;
        c.height = h * scale;
        var ctx = c.getContext("2d");
        ctx.fillStyle = C.surface;
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        resolve(c);
      };
      img.onerror = reject;
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
    });
  }

  function exportPNG() {
    var donut = el("pnlDonut");
    var line = el("pnlLine");
    if (!donut || !line) return;
    Promise.all([svgToCanvas(donut, 2), svgToCanvas(line, 2)]).then(function (cs) {
      var c1 = cs[0], c2 = cs[1];
      var gap = 48;
      var out = document.createElement("canvas");
      out.width = c1.width + gap + c2.width;
      out.height = Math.max(c1.height, c2.height);
      var ctx = out.getContext("2d");
      ctx.fillStyle = C.surface;
      ctx.fillRect(0, 0, out.width, out.height);
      ctx.drawImage(c1, 0, 0);
      ctx.drawImage(c2, c1.width + gap, 0);
      var a = document.createElement("a");
      a.download = "PnL-" + (window.__PROJ_CODE__ || "chart") + "@2x.png";
      a.href = out.toDataURL("image/png");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });
  }

  /* ---------- 导出菜单 ---------- */
  function bindExport() {
    var btn = el("financeExportBtn");
    var menu = el("financeExportMenu");
    if (!btn || !menu) return;
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (menu.hasAttribute("hidden")) {
        menu.removeAttribute("hidden");
        btn.setAttribute("aria-expanded", "true");
      } else {
        menu.setAttribute("hidden", "");
        btn.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("click", function () {
      menu.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", "false");
    });
    menu.addEventListener("click", function (e) { e.stopPropagation(); });
    var pngBtn = menu.querySelector('[data-export="png"]');
    if (pngBtn) {
      pngBtn.addEventListener("click", function () {
        menu.setAttribute("hidden", "");
        btn.setAttribute("aria-expanded", "false");
        exportPNG();
      });
    }
  }

  function init() {
    renderDonut();
    renderLine();
    bindExport();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
