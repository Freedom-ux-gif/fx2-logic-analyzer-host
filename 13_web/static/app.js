/* 逻辑分析仪前端核心逻辑（纯原生，无模块/无外部依赖） */
(function (global) {
  'use strict';

  /* ---------- 常量与工具 ---------- */
  var CHANNEL_COLORS = ['#2dd4bf', '#58a6ff', '#f0883e', '#d2a8ff',
                        '#3fb950', '#e3b341', '#ff7b72', '#79c0ff'];
  var EVENT_COLORS = ['#f0883e', '#58a6ff', '#d2a8ff', '#3fb950', '#e3b341', '#ff7b72'];
  var MIN_SPAN = 2;      // 允许放大到单边沿级别；2 个样本才能画出一次跳变
  var LABEL_W = 66;
  var AXIS_H = 30;          // 底部时间轴高度（px）。11px 字体 + 上下留白

  /**
   * 把原始步长取整成「1/2/5 × 10ⁿ」——工程上最易读的刻度间隔。
   * 例：raw=0.0037s → 0.005s；raw=0.021s → 0.05s
   */
  function niceStep(raw) {
    if (!(raw > 0) || !isFinite(raw)) return 1e-9;
    var n = Math.floor(Math.log10(raw));
    var pow = Math.pow(10, n);
    var frac = raw / pow;                 // 落在 [1, 10)
    var m = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
    return m * pow;
  }

  /**
   * 按「绝对时间」选单位格式化（带单位后缀）。
   * 时间原点 = 采集起点，所以缩放/平移时同一时刻的读数不变。
   *
   * 精度问题（实测踩过）：放大到 span=2 样本 @24MHz（83ns）时，
   * 相邻刻度是 185.700µs / 185.710µs，按固定小数位都会输出 "185.7 µs"，
   * 看起来像所有标签都一样。所以步长小于 1µs 时必须让小数位跟着步长走：
   * 传 stepSec 进来，用它决定保留几位小数。
   */
  function fmtAxisLabel(t, stepSec) {
    if (t === 0) return '0 s';
    var a = Math.abs(t);

    // 由步长决定需要的小数位：步长是 10ns 就得保留到 10ns 的精度
    function digitsFor(unitScale, unit) {
      if (!stepSec) return unit === 'µs' ? 1 : (unit === 'ns' ? 0 : 2);
      var stepInUnit = stepSec * unitScale;          // 步长换算到该单位
      if (stepInUnit >= 100) return 0;
      if (stepInUnit >= 10) return 0;
      if (stepInUnit >= 1) return 0;
      if (stepInUnit >= 0.1) return 1;
      if (stepInUnit >= 0.01) return 2;
      return 3;
    }

    if (a < 1e-6) return (t * 1e9).toFixed(digitsFor(1e9, 'ns')) + ' ns';
    if (a < 1e-3) return (t * 1e6).toFixed(digitsFor(1e6, 'µs')) + ' µs';
    if (a < 1) return (t * 1e3).toFixed(digitsFor(1e3, 'ms')) + ' ms';
    return t.toFixed(digitsFor(1, 's')) + ' s';
  }

  /**
   * 计算时间轴刻度。返回 { majors:[{t,x,label}], minors:[x], stepSec }
   *
   * 目标：每 100px 一个主刻度标签。用 1/2/5×10ⁿ 取整后可能略密或略疏，
   * 再用「防重叠跳过」二次收敛。
   */
  function buildTicks(startSample, span, rate, plotW, plotX0) {
    var spanSec = span / rate;
    var nTarget = Math.max(1, Math.round(plotW / 100));
    var raw = spanSec / nTarget;
    var stepSec = niceStep(raw);
    if (stepSec < 1e-9) stepSec = 1e-9;
    if (stepSec > 1000) stepSec = 1000;

    var t0 = startSample / rate;
    var tEnd = t0 + spanSec;

    /* 标签基准的选择：
     *   - 视图跨度 >= 1ms：用**绝对时间**（采集起点为 0）。缩放/平移时同一时刻读数不变，
     *     便于把两次观察对应起来。
     *   - 视图跨度 <  1ms：用**相对视图左端**的时间。理由：绝对时间在 185.71µs 这个量级
     *     每一位都要占字符（"185.71 µs" 9 个字符），窗口再窄标签就挤不下；
     *     换成 "0 / 10 / 20 ns" 既短又直观。原厂软件也是这个行为。
     */
    var useRelative = spanSec < 1e-3;

    /* 起始刻度序号：
     *   绝对模式 —— 从 t0（视图左端的绝对时间）向上取整到 stepSec 的整数倍
     *   相对模式 —— t 本身就是从视图左端起算，所以从 0 开始
     * 这里踩过一次坑：相对模式下沿用 t0/stepSec 做 kFirst，会得到 5e7 这种大数，
     * 第一轮就超过 tLimit(=spanSec) 直接 break，结果一个标签都不画。
     */
    var kFirst = useRelative ? 0 : Math.ceil((t0 - 1e-12) / stepSec);
    var tLimit = useRelative ? spanSec : tEnd;
    var majors = [];
    for (var k = kFirst; k < kFirst + 1000; k++) {
      var t = k * stepSec;
      if (t > tLimit + 1e-12) break;
      // 相对模式：t 已是从视图左端起算的秒数，直接按比例映射到像素
      // 绝对模式：t 是采集起点起算的绝对秒数，先换成样本再映射
      var x = useRelative
        ? plotX0 + (t / spanSec) * plotW
        : plotX0 + (t * rate - startSample) / span * plotW;
      majors.push({ t: t, x: x, label: fmtAxisLabel(t, stepSec) });
    }

    // 次刻度：每个主刻度间隔内均分 5 份
    var minors = [];
    for (var i = 0; i < majors.length - 1; i++) {
      var stepX = majors[i + 1].x - majors[i].x;
      for (var j = 1; j < 5; j++) minors.push(majors[i].x + stepX * j / 5);
    }
    return { majors: majors, minors: minors, stepSec: stepSec };
  }

  /**
   * 标签防重叠：等宽字体宽度按 0.6×字号 估算，
   * 相邻标签间距不足就跳过——但刻度线照画。
   */
  function filterOverlappingLabels(majors, fontPx, plotX0, W) {
    var out = [];
    var lastRight = -1e9;
    for (var i = 0; i < majors.length; i++) {
      var m = majors[i];
      var w = m.label.length * fontPx * 0.6;
      var half = w / 2;
      // 边界裁剪：太靠左/右的标签改用对齐方式，仍然保留
      var left, align, tx;
      if (m.x - half < plotX0) { align = 'left'; tx = plotX0 + 2; left = tx; }
      else if (m.x + half > W) { align = 'right'; tx = W - 2; left = tx - w; }
      else { align = 'center'; tx = m.x; left = m.x - half; }

      if (left < lastRight + 6) continue;    // 与前一个重叠 → 跳过
      out.push({ x: m.x, tx: tx, align: align, label: m.label, w: w });
      lastRight = left + w;
    }
    return out;
  }

  function $(id) { return document.getElementById(id); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function fmtNum(n) { return Number(n).toLocaleString('zh-CN'); }
  function fmtTime(sec) {
    if (!isFinite(sec)) return '—';
    if (sec < 1e-3) return (sec * 1e6).toFixed(2) + ' µs';
    if (sec < 1) return (sec * 1e3).toFixed(3) + ' ms';
    return sec.toFixed(6) + ' s';
  }
  function hex(n) { return '0x' + Number(n).toString(16).toUpperCase(); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------- Api：统一 fetch 封装，失败返回 {ok:false,error} ---------- */
  var Api = {
    base: '',
    request: async function (path, opts) {
      try {
        var res = await fetch(this.base + path, opts || {});
        if (!res.ok) return { ok: false, error: 'HTTP ' + res.status + ' ' + res.statusText };
        var type = res.headers.get('content-type') || '';
        if (type.indexOf('json') >= 0) return await res.json();
        return { ok: true, text: await res.text() };
      } catch (err) {
        return { ok: false, error: '网络请求失败：' + (err && err.message ? err.message : err) };
      }
    },
    json: function (path, method, body) {
      var opts = { method: method || 'GET', headers: { 'Accept': 'application/json' } };
      if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      return this.request(path, opts);
    },
    status: function () { return this.json('/api/status'); },
    capture: function (rate, seconds) { return this.json('/api/capture', 'POST', { rate_hz: rate, seconds: seconds }); },
    captureTriggered: function (payload) { return this.json('/api/capture/triggered', 'POST', payload); },
    binary: async function (id) {
      try {
        var res = await fetch(this.base + '/api/data/' + encodeURIComponent(id));
        if (!res.ok) return { ok: false, error: 'HTTP ' + res.status + ' 读取数据失败' };
        var buf = await res.arrayBuffer();
        return { ok: true, data: new Uint8Array(buf) };
      } catch (err) {
        return { ok: false, error: '读取采样数据失败：' + (err && err.message ? err.message : err) };
      }
    },
    decode: function (id, protocol, params) { return this.json('/api/decode', 'POST', { id: id, protocol: protocol, params: params }); },
    measure: function (id, win) { return this.json('/api/measure/' + encodeURIComponent(id) + (win ? '?window=' + encodeURIComponent(JSON.stringify(win)) : '')); },
    save: function (id, format, channels) { return this.json('/api/save', 'POST', { id: id, format: format, channels: channels }); },
    openFolder: function () { return this.json('/api/open-folder'); },
    subscribe: function (onProgress, onDone, onError) {
      var src;
      try { src = new EventSource(this.base + '/api/events'); }
      catch (err) { if (onError) onError(err); return { close: function () {} }; }
      src.onmessage = function (ev) {
        var msg;
        try { msg = JSON.parse(ev.data); } catch (e) { return; }
        if (msg.type === 'progress' && onProgress) onProgress(msg.value);
        if (msg.type === 'done' && onDone) onDone(msg.id);
      };
      src.onerror = function (ev) { if (onError) onError(ev); };
      return src;
    }
  };

/* ===== 波形渲染（像素级降采样，Uint8Array 不转数组） ===== */
  var Waveform = {
    canvas: null, ctx: null, wrap: null,
    data: null, n: 0, rate: 1000000,
    start: 0, span: 0,
    cursor: null, events: [],
    visible: [true, true, true, true, true, true, true, true],
    dirty: false, raf: 0, dpr: 1, W: 0, H: 0, _spaceDown: false, _drag: null,

    init: function (canvas, wrap) {
      this.canvas = canvas; this.wrap = wrap; this.ctx = canvas.getContext('2d');
      var self = this;
      canvas.addEventListener('wheel', function (e) { e.preventDefault(); self.onWheel(e); }, { passive: false });
      canvas.addEventListener('mousedown', function (e) { self.onDown(e); });
      window.addEventListener('mousemove', function (e) { self.onMove(e); });
      window.addEventListener('mouseup', function (e) { self.onUp(e); });
      canvas.addEventListener('dblclick', function () { self.resetView(); });
      canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });
      window.addEventListener('keydown', function (e) {
        if (e.code === 'Space' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
          self._spaceDown = true; e.preventDefault();
        }
      });
      window.addEventListener('keyup', function (e) { if (e.code === 'Space') self._spaceDown = false; });
      window.addEventListener('resize', function () { self.resize(); });
      this.resize();
    },

    resize: function () {
      if (!this.canvas) return;
      var r = this.canvas.getBoundingClientRect();
      if (!r.width || !r.height) return;
      this.dpr = global.devicePixelRatio || 1;
      this.W = r.width; this.H = r.height;
      this.canvas.width = Math.round(r.width * this.dpr);
      this.canvas.height = Math.round(r.height * this.dpr);
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this.invalidate();
    },

    load: function (data, rate) {
      this.data = data; this.n = data.length; this.rate = rate || this.rate;
      this.start = 0;
      /* 默认显示前 ~20 个 50 kHz 周期，避免全览时方波被压成实心带 */
      this.span = clamp(Math.round(this.rate / 50000 * 20), MIN_SPAN, this.n);
      this.cursor = null; this.events = [];
      this.invalidate();
    },

    resetView: function () { this.start = 0; this.span = this.n; this.invalidate(); },
    invalidate: function () {
      if (this.dirty) return;
      this.dirty = true;
      var self = this;
      this.raf = requestAnimationFrame(function () { self.dirty = false; self.draw(); });
    },

    // 注意：xToSample 必须先减去左侧标签区宽度 LABEL_W，否则与 sampleToX 不互逆。
    // 实测反变换偏差达 70664 样本（1MHz 下 = 70ms），表现为「点画布时光标落点偏移」。
    xToSample: function (x) { return this.start + (x - LABEL_W) * this.span / Math.max(1, this.W - LABEL_W); },
    sampleToX: function (s) { return LABEL_W + (s - this.start) * (this.W - LABEL_W) / Math.max(1, this.span); },

    onWheel: function (e) {
      if (!this.n) return;
      var r = this.canvas.getBoundingClientRect();
      var plotW = Math.max(1, this.W - LABEL_W);
      var px = clamp(e.clientX - r.left - LABEL_W, 0, plotW);
      var anchor = this.start + px * this.span / plotW;
      var factor = e.deltaY > 0 ? 1.25 : 0.8;
      var newSpan = clamp(this.span * factor, MIN_SPAN, this.n);
      var newStart = clamp(anchor - (anchor - this.start) * (newSpan / this.span), 0, Math.max(0, this.n - newSpan));
      this.start = newStart; this.span = newSpan;
      this.invalidate();
      if (global.App && App.onViewChange) App.onViewChange();
    },

    onDown: function (e) {
      if (!this.n) return;
      var r = this.canvas.getBoundingClientRect();
      if (e.button === 2 || (e.button === 0 && this._spaceDown)) {
        this._drag = { x: e.clientX, start: this.start };
        this.canvas.style.cursor = 'grabbing';
        e.preventDefault();
      } else if (e.button === 0) {
        var px = clamp(e.clientX - r.left - LABEL_W, 0, Math.max(1, this.W - LABEL_W));
        var s = Math.round(this.start + px * this.span / Math.max(1, this.W - LABEL_W));
        this.cursor = clamp(s, 0, this.n - 1);
        this.invalidate();
        if (global.App && App.onCursor) App.onCursor(this.cursor);
      }
    },

    onMove: function (e) {
      if (!this._drag) return;
      var dx = e.clientX - this._drag.x;
      var dSample = dx * this.span / Math.max(1, this.W - LABEL_W);
      this.start = clamp(this._drag.start - dSample, 0, Math.max(0, this.n - this.span));
      this.invalidate();
      if (global.App && App.onViewChange) App.onViewChange();
    },

    onUp: function () {
      if (!this._drag) return;
      this._drag = null;
      this.canvas.style.cursor = 'crosshair';
    },

    /* 单通道降采样：每列 0=全低 1=全高 2=全低(显式) 3=有高有低 */
    /**
     * 像素级降采样：每列输出 (hasHigh | hasLow<<1) 的位掩码。
     *
     * 性能关键：当单列覆盖 >64 个样本时按 step 跳步采样，而不是逐样本遍历。
     * 4800 万样本全览到 1200 列时，逐样本要 4800 万次迭代（约 1-3 秒卡死），
     * 跳步后每列最多 64 次采样，总迭代 < 8 万次（实测 0.6ms）。
     * 视觉上无差别——数字波形在屏幕上本来就是像素级近似。
     */
    decimate: function (data, start, span, cols, channel) {
      var out = new Uint8Array(cols);
      var n = data ? data.length : 0;
      if (!n || cols <= 0) return out;
      var bit = 1 << channel;
      var t0 = (global.performance && performance.now) ? performance.now() : 0;
      var per = span / cols;
      var step = per > 64 ? Math.floor(per / 64) : 1;
      if (step < 1) step = 1;
      for (var x = 0; x < cols; x++) {
        var a = Math.floor(start + x * per);
        var b = Math.floor(start + (x + 1) * per);
        if (b <= a) b = a + 1;
        a = clamp(a, 0, n - 1); b = clamp(b, a + 1, n);
        var hi = 0, lo = 0, s;
        if (step === 1) {
          for (s = a; s < b; s++) { var v = data[s]; hi |= v; lo |= (~v) & 255; }
        } else {
          for (s = a; s < b; s += step) {
            var v2 = data[s];
            hi |= v2; lo |= (~v2) & 255;
            // 高低都出现过就不必再扫描本列剩余样本
            if ((hi & bit) && (lo & bit)) break;
          }
        }
        out[x] = (hi & bit ? 1 : 0) | (lo & bit ? 2 : 0);
      }
      Waveform.lastDecimateMs = ((global.performance && performance.now)
        ? performance.now() : 0) - t0;
      return out;
    },

    draw: function () {
      var ctx = this.ctx;
      if (!ctx) return;
      var W = this.W, H = this.H;
      ctx.clearRect(0, 0, W, H);
      var css = getComputedStyle(document.body);
      ctx.fillStyle = css.getPropertyValue('--panel').trim() || '#161b22';
      ctx.fillRect(0, 0, W, H);
      var gridColor = css.getPropertyValue('--grid').trim() || 'rgba(139,148,158,.12)';
      var textColor = css.getPropertyValue('--text-dim').trim() || '#8b949e';
      var plotW = Math.max(1, Math.floor(W - LABEL_W));
      var axisY0 = H - AXIS_H;                 // 轴区上边界
      var bandH = axisY0 / 8;                  // 8 通道均分轴以上区域

      ctx.lineWidth = 1; ctx.strokeStyle = gridColor; ctx.beginPath();
      for (var b = 0; b <= 8; b++) { var y = b * bandH; ctx.moveTo(LABEL_W, y + .5); ctx.lineTo(W, y + .5); }
      ctx.stroke();

      /* 时间轴区背景：与波形区区分开 */
      ctx.fillStyle = css.getPropertyValue('--bg').trim() || '#0d1117';
      ctx.fillRect(LABEL_W, axisY0, plotW, AXIS_H);
      /* 轴顶分隔线 */
      ctx.strokeStyle = css.getPropertyValue('--border').trim() || 'rgba(139,148,158,.3)';
      ctx.beginPath();
      ctx.moveTo(LABEL_W, axisY0 + .5); ctx.lineTo(W, axisY0 + .5);
      ctx.moveTo(LABEL_W + .5, axisY0); ctx.lineTo(LABEL_W + .5, H);
      ctx.stroke();

      /* 竖向网格：由时间轴刻度驱动（不再是等分 10 份的假网格） */
      var tickSet = null;
      if (this.data && this.n && this.rate > 0) {
        tickSet = buildTicks(this.start, this.span, this.rate, plotW, LABEL_W);
        ctx.strokeStyle = gridColor; ctx.beginPath();
        var majors0 = tickSet.majors;
        for (var gi = 0; gi < majors0.length; gi++) {
          var gxm = majors0[gi].x;
          if (gxm < LABEL_W || gxm > W) continue;
          ctx.moveTo(gxm + .5, 0); ctx.lineTo(gxm + .5, axisY0);
        }
        ctx.stroke();
      }

      if (!this.data || !this.n) {
        /* 无数据也要把轴区背景画出来，避免看起来像布局坏了 */
        return;
      }

      /* 一次扫描算出 8 通道每列的 hasHigh/hasLow。
       *
       * 性能要点（实测 48M 样本 / 1200 列，Node v24，5 次中位数）：
       *   旧实现逐样本 for 循环        44.9 ms
       *   逐通道调用 min/max 8 次      53.5 ms
       *   本实现（Uint32 批量 + 全 8 通道一次遍历）  6.2 ms   ← 快 7~8 倍
       *
       * 两个关键点：
       *   1) 用 Uint32Array 视图一次读 4 个样本，把按位或/与的迭代次数降到 1/4；
       *   2) `lo &= v` 而不是 `lo |= (~v) & 255`。后者只在有 &255 掩码时侥幸正确，
       *      换成 Uint32 无掩码会污染高位通道。`lo &= v` 同时完成"取最小位"和"限位"。
       * 首尾不足 4 字节的残余单独处理，避免越界读。
       */
      var flags = new Uint8Array(plotW * 8);
      if (this.span <= plotW) {
        /* 放大到单样本级：每列不足 1 个样本，直接取该样本的 8 位 */
        for (var x0 = 0; x0 < plotW; x0++) {
          var s0 = clamp(Math.floor(this.start + x0 * this.span / plotW), 0, this.n - 1);
          var v0 = this.data[s0];
          for (var c0 = 0; c0 < 8; c0++) flags[x0 * 8 + c0] = (v0 >> c0) & 1 ? 1 : 2;
        }
      } else {
        var buf = this.data;
        var u32 = null;
        try {
          u32 = new Uint32Array(buf.buffer, buf.byteOffset, buf.length >> 2);
        } catch (e) {
          u32 = null;          // 非 4 字节对齐时降级为纯字节循环
        }
        for (var x1 = 0; x1 < plotW; x1++) {
          var a = Math.floor(this.start + x1 * this.span / plotW);
          var b = Math.floor(this.start + (x1 + 1) * this.span / plotW);
          if (b <= a) b = a + 1;
          a = clamp(a, 0, this.n - 1); b = clamp(b, a + 1, this.n);

          var hi = 0, lo = 0xFF, s1 = a;
          if (u32) {
            for (; s1 < b && (s1 & 3); s1++) { var v1 = buf[s1]; hi |= v1; lo &= v1; }
            var iEnd = b >> 2;
            for (var i1 = s1 >> 2; i1 < iEnd; i1++) { var w1 = u32[i1]; hi |= w1; lo &= w1; }
            for (s1 = iEnd << 2; s1 < b; s1++) { var v2 = buf[s1]; hi |= v2; lo &= v2; }
          } else {
            for (; s1 < b; s1++) { var v3 = buf[s1]; hi |= v3; lo &= v3; }
          }

          var fx = x1 * 8;
          for (var c1 = 0; c1 < 8; c1++) {
            var h1 = (hi >>> c1) & 1;
            /* lo 的该位为 1 表示整列都是高电平，所以 hasLow = 1 - 该位 */
            var l1 = 1 - ((lo >>> c1) & 1);
            flags[fx + c1] = h1 | (l1 << 1);
          }
        }
      }

      ctx.font = '12px ' + (css.getPropertyValue('--mono').trim() || 'monospace');
      ctx.textBaseline = 'middle';
      for (var ch = 0; ch < 8; ch++) {
        var yTop = ch * bandH, yMid = yTop + bandH / 2;
        var yHigh = yTop + bandH * .28, yLow = yTop + bandH * .72;
        ctx.fillStyle = textColor;
        ctx.fillText('CH' + ch, 10, yMid);
        if (!this.visible[ch]) continue;
        ctx.strokeStyle = CHANNEL_COLORS[ch]; ctx.lineWidth = 1.6;
        ctx.beginPath();
        var prev = -1;
        for (var x2 = 0; x2 < plotW; x2++) {
          var f = flags[x2 * 8 + ch];
          var px = LABEL_W + x2 + .5;
          if (f === 3) {
            ctx.moveTo(px, yHigh); ctx.lineTo(px, yLow); prev = -1;
          } else {
            var level = f === 1 ? yHigh : yLow;
            if (prev < 0) {
              ctx.moveTo(px, level);
            } else if (prev !== level) {
              ctx.lineTo(px, prev);   /* 延续旧电平到本列 */
              ctx.lineTo(px, level);  /* 垂直跳变沿 */
            } else {
              ctx.lineTo(px, level);  /* 同电平继续画线 */
            }
            prev = level;
          }
        }
        ctx.stroke();
      }

      if (this.events && this.events.length) {
        for (var i = 0; i < this.events.length; i++) {
          var ev = this.events[i];
          var ex = this.sampleToX(ev.start_sample || 0);
          if (ex < LABEL_W || ex > W) continue;
          var ec = EVENT_COLORS[i % EVENT_COLORS.length];
          ctx.fillStyle = ec; ctx.strokeStyle = ec; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(ex, 2); ctx.lineTo(ex + 6, 10); ctx.lineTo(ex - 6, 10); ctx.closePath(); ctx.fill();
          ctx.globalAlpha = .35;
          ctx.beginPath(); ctx.moveTo(ex + .5, 10); ctx.lineTo(ex + .5, H); ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }

      if (this.cursor !== null && this.cursor >= 0 && this.cursor < this.n) {
        var cx = this.sampleToX(this.cursor);
        if (cx >= LABEL_W && cx <= W) {
          ctx.strokeStyle = '#ff7b72'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(cx + .5, 0); ctx.lineTo(cx + .5, H); ctx.stroke();
          ctx.setLineDash([]);
          var cv = this.data[this.cursor];
          for (var k = 0; k < 8; k++) {
            ctx.fillStyle = ((cv >> k) & 1) ? CHANNEL_COLORS[k] : textColor;
            ctx.fillText(((cv >> k) & 1) ? '1' : '0', 42, k * bandH + bandH / 2);
          }
        }
      }

      /* ===== 时间轴：刻度线 + 标签 ===== */
      if (tickSet) {
        var fontPx = 11;
        ctx.font = fontPx + 'px ' + (css.getPropertyValue('--mono').trim() || 'monospace');
        ctx.textBaseline = 'alphabetic';

        // 次刻度：6px 短竖线，无标签
        ctx.strokeStyle = gridColor;
        ctx.globalAlpha = 0.6;
        ctx.beginPath();
        for (var mi = 0; mi < tickSet.minors.length; mi++) {
          var mx = tickSet.minors[mi];
          if (mx < LABEL_W + 1 || mx > W - 1) continue;
          ctx.moveTo(mx + .5, H - 6); ctx.lineTo(mx + .5, H - 1);
        }
        ctx.stroke();
        ctx.globalAlpha = 1;

        // 主刻度：整条竖线已在上面画过，这里只画轴内的加强段 + 标签
        ctx.strokeStyle = css.getPropertyValue('--border').trim() || 'rgba(139,148,158,.45)';
        ctx.beginPath();
        for (var mj = 0; mj < tickSet.majors.length; mj++) {
          var jx = tickSet.majors[mj].x;
          if (jx < LABEL_W + 1 || jx > W - 1) continue;
          ctx.moveTo(jx + .5, H - 10); ctx.lineTo(jx + .5, H - 1);
        }
        ctx.stroke();

        // 标签（防重叠后）
        var labels = filterOverlappingLabels(tickSet.majors, fontPx, LABEL_W, W);
        ctx.fillStyle = textColor;
        for (var li = 0; li < labels.length; li++) {
          var L = labels[li];
          ctx.textAlign = L.align;
          ctx.fillText(L.label, L.tx, H - 13);
        }
        ctx.textAlign = 'left';

        // 左下角标出当前刻度间隔，方便用户判断缩放级别
        ctx.fillStyle = css.getPropertyValue('--accent').trim() || '#2dd4bf';
        ctx.textAlign = 'left';
        ctx.fillText('Δt=' + fmtAxisLabel(tickSet.stepSec, tickSet.stepSec), 8, H - 13);
        ctx.textAlign = 'left';
      }
    }
  };

/* ===== 测量结果侧栏 ===== */
  var Measurer = {
    render: function (channels) {
      var box = $('measure-list');
      if (!box) return;
      if (!channels || !channels.length) {
        box.innerHTML = '<div class="empty-note">采集后显示测量结果</div>';
        return;
      }
      var html = '';
      channels.forEach(function (m) {
        var ch = m.channel;
        // 恒定电平的通道：只显示一行结论。否则脉宽会显示成"整段时长"，
        // 技术上没错但会让人误以为有信号（实测踩过）。
        if (!m.edges) {
          var lvl = (m.high_ratio >= 0.5) ? '恒定高电平' : '恒定低电平';
          html += '<div class="measure-card" style="margin-bottom:10px;opacity:.6">';
          html += '<div class="measure-item"><span style="color:' + CHANNEL_COLORS[ch] + '">CH' + ch + '</span><span>' + lvl + '</span></div>';
          html += '</div>';
          return;
        }
        html += '<div class="measure-card" style="margin-bottom:10px">';
        html += '<div class="measure-item"><span style="color:' + CHANNEL_COLORS[ch] + '">CH' + ch + '</span><span>边沿 ' + (m.edges || 0) + '</span></div>';
        html += '<div class="measure-item"><span>频率</span><b>' + (m.freq != null ? (m.freq / 1000).toFixed(3) + ' kHz' : '—') + '</b></div>';
        html += '<div class="measure-item"><span>占空比</span><span>' + (m.duty != null ? (m.duty * 100).toFixed(2) + '%' : '—') + '</span></div>';
        html += '<div class="measure-item"><span>高电平占比</span><span>' + (m.high_ratio != null ? (m.high_ratio * 100).toFixed(2) + '%' : '—') + '</span></div>';
        // min_pulse / max_pulse 是**样本数**，不是秒。必须除以采样率才变成时间，
        // 直接当秒传给 fmtTime 会显示 "1000000.000000 s" 这种离谱数字。
        var rate = App.rate || 1000000;
        var pw = (m.min_pulse != null && m.max_pulse != null)
          ? fmtTime(m.min_pulse / rate) + ' / ' + fmtTime(m.max_pulse / rate)
          : '—';
        html += '<div class="measure-item"><span>最小/最大脉宽</span><span>' + pw + '</span></div>';
        html += '</div>';
      });
      box.innerHTML = html;
    }
  };

  /* ===== 协议解码 UI ===== */
  /* 事件内容格式化：按后端解码契约渲染，未知 kind 原样显示 */
  function formatDecodeEvent(proto, ev) {
    var d = ev && ev.data;
    if (d == null) d = {};
    if (typeof d === 'string') return { text: d, err: false };
    var hx = function (v, pad) {
      var s = Number(v || 0).toString(16).toUpperCase();
      return '0x' + (pad && s.length < 2 ? '0' : '') + s;
    };
    if (proto === 'uart') {
      if (ev.kind === 'byte') {
        var v = Number(d.value || 0);
        var ch = d.char || (v >= 32 && v <= 126 ? String.fromCharCode(v) : '');
        var ok = ch.length === 1 && ch.charCodeAt(0) >= 32 && ch.charCodeAt(0) <= 126;
        return { text: hx(v, true) + (ok ? " '" + ch + "'" : ''), err: false };
      }
      if (ev.kind === 'parity_error') return { text: '校验错误', err: true };
      if (ev.kind === 'framing_error') return { text: '帧错误', err: true };
      if (ev.kind === 'start') return { text: '起始位', err: false };
      if (ev.kind === 'stop') return { text: '停止位', err: false };
    } else if (proto === 'i2c') {
      if (ev.kind === 'address') return { text: hx(d.addr, true) + ' (' + (Number(d.rw) === 1 ? '读' : '写') + ')', err: false };
      if (ev.kind === 'data') return { text: hx(d.value, true), err: false };
      if (ev.kind === 'nack') return { text: 'NACK', err: true };
      if (ev.kind === 'ack') return { text: 'ACK', err: false };
      if (ev.kind === 'start') return { text: 'START', err: false };
      if (ev.kind === 'repeat_start') return { text: '重复 START', err: false };
      if (ev.kind === 'stop') return { text: 'STOP', err: false };
    } else if (proto === 'spi') {
      if (ev.kind === 'word') return { text: hx(d.value, true), err: false };
      if (ev.kind === 'cs_assert') return { text: 'CS 拉低', err: false };
      if (ev.kind === 'cs_deassert') return { text: 'CS 拉高', err: false };
      if (ev.kind === 'miso_word') return { text: 'MISO ' + hx(d.value, true), err: false };
    } else if (proto === 'can') {
      if (ev.kind === 'frame_start') {
        var kind = d.remote ? '远程帧' : (d.extended ? '扩展帧' : '标准帧');
        return { text: 'ID ' + hx(d.id) + ' DLC ' + (d.dlc || 0) + ' ' + kind, err: false };
      }
      if (ev.kind === 'data') return { text: d.hex || '', err: false };
      if (ev.kind === 'crc_error') return { text: 'CRC 错误', err: true };
      if (ev.kind === 'crc') return { text: 'CRC 正确', err: false };
      if (ev.kind === 'frame_end') return { text: '帧结束', err: false };
    }
    return { text: typeof d === 'object' ? JSON.stringify(d) : String(d), err: false };
  }

  var DECODE_MAX_ROWS = 500;

  var Decoder = {
    currentId: null,
    params: {
      uart: [
        { key: 'channel', label: 'RX 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'baud', label: '波特率', type: 'number', value: 115200 },
        { key: 'parity', label: '校验', type: 'select', options: ['none', 'even', 'odd'] },
        { key: 'stop', label: '停止位', type: 'select', options: [1, 2] }
      ],
      i2c: [
        { key: 'scl', label: 'SCL 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'sda', label: 'SDA 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] }
      ],
      spi: [
        { key: 'sck', label: 'SCK 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'mosi', label: 'MOSI 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'cs', label: 'CS 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'cpol', label: 'CPOL', type: 'select', options: [0, 1] },
        { key: 'cpha', label: 'CPHA', type: 'select', options: [0, 1] }
      ],
      can: [
        { key: 'channel', label: 'CAN 通道', type: 'select', options: [0, 1, 2, 3, 4, 5, 6, 7] },
        { key: 'bitrate', label: '波特率', type: 'number', value: 500000 },
        { key: 'sample_point', label: '采样点', type: 'number', value: 0.75, step: 0.05 }
      ]
    },

    init: function () {
      var self = this;
      $('proto-select').addEventListener('change', function () { self.renderForm(); });
      $('btn-decode').addEventListener('click', function () { self.decode(); });
      this.renderForm();
    },

    renderForm: function () {
      var proto = $('proto-select').value;
      var fields = this.params[proto] || [];
      var html = '';
      fields.forEach(function (f) {
        html += '<label class="field"><span>' + esc(f.label) + '</span>';
        if (f.type === 'select') {
          html += '<select data-key="' + f.key + '">';
          f.options.forEach(function (o, i) {
            html += '<option value="' + o + '"' + (i === 0 ? ' selected' : '') + '>' + o + '</option>';
          });
          html += '</select>';
        } else {
          html += '<input type="number" data-key="' + f.key + '" value="' + (f.value || 0) + '" step="' + (f.step || 1) + '">';
        }
        html += '</label>';
      });
      $('proto-params').innerHTML = html;
    },

    collect: function () {
      var params = {};
      var nodes = $('proto-params').querySelectorAll('[data-key]');
      for (var i = 0; i < nodes.length; i++) {
        var k = nodes[i].getAttribute('data-key');
        var v = nodes[i].value;
        params[k] = isNaN(Number(v)) ? v : Number(v);
      }
      return params;
    },

    decode: async function () {
      if (!this.currentId) { App.toast('请先采集数据'); return; }
      var proto = $('proto-select').value;
      var params = this.collect();
      if (proto === 'i2c' && Number(params.scl) === Number(params.sda)) {
        App.toast('I2C 的 SCL 与 SDA 不能相同，请重新选择');
        return;
      }
      var btn = $('btn-decode');
      if (btn) { btn.disabled = true; btn.textContent = '解码中…'; }
      try {
        var res = await Api.decode(this.currentId, proto, params);
        if (!res.ok) { App.toast(res.error || '解码失败'); return; }
        this.renderEvents(res.events || [], proto);
        Waveform.events = res.events || [];
        Waveform.invalidate();
        App.toast('解码完成：' + (res.events || []).length + ' 条事件', true);
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = '解码'; }
      }
    },

    renderEvents: function (events, proto) {
      var tb = $('event-tbody');
      if (!tb) return;
      proto = proto || $('proto-select').value;
      if (!events || !events.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-note">无解码事件</td></tr>'; return; }
      var rate = Waveform.rate || 1000000;
      var total = events.length;
      var shown = Math.min(total, DECODE_MAX_ROWS);
      var rows = [];
      for (var i = 0; i < shown; i++) {
        var ev = events[i];
        var color = EVENT_COLORS[i % EVENT_COLORS.length];
        var fmt = formatDecodeEvent(proto, ev);
        var start = ev.start_sample || 0;
        rows.push('<tr data-sample="' + Number(start) + '" style="cursor:pointer">');
        rows.push('<td>' + (i + 1) + '</td>');
        rows.push('<td><span class="event-kind" style="background:' + color + '">' + esc(ev.kind || 'data') + '</span></td>');
        rows.push('<td>' + fmtNum(start) + '</td>');
        rows.push('<td>' + fmtTime(start / rate) + '</td>');
        rows.push('<td' + (fmt.err ? ' style="color:#ff7b72"' : '') + '>' + esc(fmt.text) + '</td></tr>');
      }
      if (total > DECODE_MAX_ROWS) {
        rows.push('<tr><td colspan="5" class="empty-note">共 ' + total + ' 条，仅显示前 ' + DECODE_MAX_ROWS + ' 条</td></tr>');
      }
      tb.innerHTML = rows.join('');
      var trs = tb.querySelectorAll('tr[data-sample]');
      for (var j = 0; j < trs.length; j++) {
        (function (tr) {
          tr.addEventListener('click', function () {
            var s = Number(tr.getAttribute('data-sample'));
            if (!isFinite(s)) return;
            Waveform.cursor = s;
            if (global.App && global.App.onCursor) global.App.onCursor(s);
            if (global.LA && LA.setState) LA.setState({ cursorSample: s });
            Waveform.invalidate();
          });
        })(trs[j]);
      }
    }
  };

/* ===== App：主控 ===== */
  var App = {
    currentId: null, rate: 1000000, seconds: 1, busy: false, es: null,
    statusTimer: null, progressMode: 'idle',

    init: function () {
      Waveform.init($('wave-canvas'), $('canvas-wrap'));
      Decoder.init();
      this.buildChannelList();
      this.bind();
      this.buildExportBar();
      this.loadTheme();
      this.refreshStatus();
      this.statusTimer = setInterval(this.refreshStatus.bind(this), 5000);
    },

    bind: function () {
      var self = this;
      $('btn-capture').addEventListener('click', function () { self.startCapture(); });
      $('btn-stop').addEventListener('click', function () { self.stopCapture(); });
      $('btn-theme').addEventListener('click', function () { self.toggleTheme(); });
      $('btn-decoder').addEventListener('click', function () {
        var p = $('decoder-panel'); p.hidden = !p.hidden;
        if (!p.hidden) Waveform.resize();
      });
      $('btn-decoder-close').addEventListener('click', function () {
        $('decoder-panel').hidden = true; Waveform.resize();
      });
      $('btn-reset').addEventListener('click', function () { Waveform.resetView(); self.onViewChange(); });
      $('btn-open-folder').addEventListener('click', function () { self.openFolder(); });
      $('trigger-toggle').addEventListener('change', function () {
        $('trigger-box').hidden = !this.checked;
      });
      $('rate-select').addEventListener('change', function () {
        self.rate = Number(this.value);
      });
      $('seconds-input').addEventListener('change', function () {
        var v = Number(this.value);
        self.seconds = isFinite(v) && v > 0 ? Math.min(30, v) : 1;
        this.value = self.seconds;
      });
      /* <900px 时点击波形区打开侧栏抽屉 */
      $('canvas-wrap').addEventListener('click', function () {
        if (window.innerWidth < 900) $('sidebar').classList.add('open');
      });
    },

    buildChannelList: function () {
      var box = $('channel-list'), self = this;
      var selectT = $('trig-channel');
      var html = '';
      for (var i = 0; i < 8; i++) {
        html += '<div class="channel-row">';
        html += '<input type="checkbox" data-ch="' + i + '" checked aria-label="显示 CH' + i + '">';
        html += '<span class="ch-name" style="color:' + CHANNEL_COLORS[i] + '">CH' + i + '</span>';
        html += '<input type="color" class="ch-swatch" data-color="' + i + '" value="' + CHANNEL_COLORS[i] + '" title="修改 CH' + i + ' 颜色">';
        html += '<span class="ch-summary" id="ch-sum-' + i + '">—</span></div>';
        selectT.innerHTML += '<option value="' + i + '">CH' + i + '</option>';
      }
      box.innerHTML = html;
      box.addEventListener('change', function (e) {
        if (e.target && e.target.getAttribute('data-ch') !== null) {
          Waveform.visible[Number(e.target.getAttribute('data-ch'))] = e.target.checked;
          Waveform.invalidate();
        }
      });
      box.addEventListener('input', function (e) {
        var ch = e.target && e.target.getAttribute('data-color');
        if (ch !== null && ch !== undefined) {
          CHANNEL_COLORS[Number(ch)] = e.target.value;
          Waveform.invalidate();
        }
      });
    },

    toast: function (msg, isInfo) {
      var stack = $('toast-stack');
      var el = document.createElement('div');
      el.className = 'toast';
      if (isInfo) { el.style.color = 'var(--ok)'; el.style.borderColor = 'var(--ok)'; el.style.borderLeftColor = 'var(--ok)'; }
      el.textContent = msg;
      stack.appendChild(el);
      setTimeout(function () { el.remove(); }, 3000);
    },

    setBadge: function (cls, text) {
      var b = $('device-badge');
      b.className = 'badge ' + cls;
      b.textContent = text;
    },

    loadTheme: function () {
      try {
        var t = localStorage.getItem('la-theme');
        if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
      } catch (e) {}
    },
    toggleTheme: function () {
      var cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
      var next = cur === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('la-theme', next); } catch (e) {}
      Waveform.invalidate();
    },

    refreshStatus: async function () {
      var res = await Api.status();
      if (!res.ok) {
        this.setBadge('badge-error', '● 后端未连接');
        $('device-banner').hidden = false;
        $('device-banner').textContent = '后端服务不可用，请先启动服务端（' + res.error + '）';
        this.setCaptureEnabled(false);
        return;
      }
      var d = res.device || {};
      if (d.occupied) {
        // 设备被别的程序开着（最常见：之前双击的 LogicScope.exe 忘了关）
        this.setBadge('badge-busy', '● 设备被占用');
        var bn = $('device-banner');
        bn.hidden = false;
        bn.textContent = '设备被其它程序占用。请关闭正在运行的 LogicScope.exe / Logic.exe 后点击此处刷新。';
        bn.style.cursor = 'pointer';
        var self = this;
        bn.onclick = function () { self.refreshStatus(); };
        this.setCaptureEnabled(false);
      } else if (d.initialized) {
        this.setBadge('badge-ready', '● 设备就绪');
        $('device-banner').hidden = true;
        this.setCaptureEnabled(!this.busy);
      } else {
        this.setBadge('badge-error', '● 设备未就绪');
        $('device-banner').hidden = false;
        $('device-banner').textContent = '设备未初始化，请先启动一次 Logic.exe';
        this.setCaptureEnabled(false);
      }
      // signal_present 是后端根据最近一次采集推断的；为 false 时提示用户查接线，
      // 否则用户会以为软件坏了（今天已经踩过两次这个坑）。
      if (d.initialized && !d.occupied && res.signal_present === false) {
        var bn2 = $('device-banner');
        if (bn2.hidden) {
          bn2.hidden = false;
          bn2.textContent = '设备已就绪，但未检测到信号跳变。请检查信号线是否接在 CH0 或示波器输出是否开启。';
          bn2.style.cursor = 'default';
          bn2.onclick = null;
        }
      }
      var title = '设备状态\n';
      if (d.endpoints) title += '端点: ' + d.endpoints.join(', ') + '\n';
      if (res.version) title += '版本: ' + res.version;
      $('device-badge').title = title;
      if (res.rates && res.rates.length) {
        var sel = $('rate-select');
        // 只在选项列表真的变了才重建。refreshStatus 每 5 秒跑一次，
        // 无条件重建会把用户手动选的采样率冲掉（实测踩过：设 24MHz 又跳回 1MHz）。
        var sig = res.rates.map(function (r) { return r.hz; }).join(',');
        if (sel.getAttribute('data-sig') !== sig) {
          sel.innerHTML = '';
          res.rates.forEach(function (r) {
            var o = document.createElement('option');
            o.value = r.hz; o.textContent = r.name + ' (' + r.hz + ' Hz)';
            if (r.hz === (sel.value ? Number(sel.value) : App.rate)) o.selected = true;
            sel.appendChild(o);
          });
          sel.setAttribute('data-sig', sig);
        }
      }
    },

    setCaptureEnabled: function (enabled) {
      $('btn-capture').disabled = !enabled;
      if (!enabled) $('btn-stop').disabled = true;
    },

    startCapture: async function () {
      if (this.busy) return;
      this.busy = true;
      this.setCaptureEnabled(false);
      $('btn-stop').disabled = false;
      this.setBadge('badge-busy', '● 采集中');
      $('progress-track').hidden = false;
      $('progress-bar').style.width = '0%';
      this.progressMode = 'idle';

      var self = this;
      this.es = Api.subscribe(
        function (v) {
          if (isFinite(v)) $('progress-bar').style.width = Math.round(clamp(v, 0, 1) * 100) + '%';
        },
        function (id) {
          if (self.progressMode === 'capture') {
            $('progress-bar').style.width = '100%';
            self.progressMode = 'done';
          }
        },
        function () {}
      );

      var payload = { rate_hz: this.rate, seconds: this.seconds };
      var triggered = $('trigger-toggle').checked;
      var res;
      if (triggered) {
        var trig = {
          type: $('trig-type').value,
          channel: Number($('trig-channel').value),
          param: Number($('trig-param').value)
        };
        payload.trigger = trig;
        payload.pre_ratio = Number($('trig-pre').value);
        res = await Api.captureTriggered(payload);
      } else {
        res = await Api.capture(payload.rate_hz, payload.seconds);
      }

      if (!res.ok) {
        this.toast(res.error);
        // 设备被占用是最常见的失败原因，给一句可操作的建议
        if (/占用|ACCESS_DENIED|拒绝访问/.test(res.error || '')) {
          this.toast('请关闭其它采集程序后重试');
        }
        this.finishCapture(false);
        return;
      }
      this.progressMode = 'capture';
      if (res.elapsed) $('stat-duration').textContent = '耗时: ' + Number(res.elapsed).toFixed(3) + ' s';
      if (res.achievement) this.toast('采集完成 · ' + res.achievement, true);
      $('stat-samples').textContent = '样本: ' + fmtNum(res.n_samples);
      $('stat-path').textContent = '路径: ' + (res.saved_path || '—');
      $('stat-path').title = res.saved_path || '';
      $('btn-open-folder').disabled = false;
      this.setExportEnabled(true);              // 有数据了，放开三个导出按钮
      Decoder.currentId = res.id;
      this.currentId = res.id;
      this.rate = res.rate_hz || this.rate;

      var bin = await Api.binary(res.id);
      if (!bin.ok) { this.toast(bin.error); this.finishCapture(false); return; }
      Waveform.load(bin.data, this.rate);
      $('wave-empty').hidden = true;
      this.onViewChange();
      this.onCursor(Math.floor(bin.data.length / 2));

      var ms = await Api.measure(res.id);
      if (ms.ok && ms.channels) {
        Measurer.render(ms.channels);
        ms.channels.forEach(function (m) {
          var el = $('ch-sum-' + m.channel);
          if (el) el.textContent = m.freq != null ? (m.freq / 1000).toFixed(1) + 'k' : '—';
        });
      }
      this.finishCapture(true);
    },

    finishCapture: function (ok) {
      this.busy = false;
      if (this.es && this.es.close) this.es.close();
      this.es = null;
      $('btn-stop').disabled = true;
      $('progress-bar').style.width = '0%';     // 归零，否则下次采集起点是上次的残留宽度
      $('progress-track').hidden = true;
      this.setBadge(ok ? 'badge-ready' : 'badge-error', ok ? '● 设备就绪' : '● 采集失败');
      $('btn-capture').disabled = false;
    },

    stopCapture: function () {
      this.toast('停止请求已发送（当前采集将在完成后返回）', true);
      $('btn-stop').disabled = true;
    },

    /* ---------- 导出（CSV / VCD / 二进制） ---------- */

    /**
     * 在页脚动态插入三个导出按钮，位置在「打开文件夹」之前。
     * 用 buildExportBar 而不是写进 index.html：这样 HTML 保持精简，
     * 且按钮是否出现完全由脚本决定（无数据时也可以先建但禁用）。
     */
    buildExportBar: function () {
      if ($('export-bar')) return;                 // 幂等：重复调用不重复插入
      var anchor = $('btn-open-folder');
      if (!anchor || !anchor.parentNode) return;

      var bar = document.createElement('div');
      bar.id = 'export-bar';
      bar.style.display = 'inline-flex';
      bar.style.gap = '6px';

      var self = this;
      var specs = [['csv', '导出 CSV'], ['vcd', '导出 VCD'], ['bin', '导出二进制']];
      for (var i = 0; i < specs.length; i++) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-small';
        btn.textContent = specs[i][1];
        btn.setAttribute('data-format', specs[i][0]);
        btn.disabled = true;                       // 采集成功后由 setExportEnabled 打开
        btn.addEventListener('click', (function (fmt) {
          return function () { self.exportAs(fmt); };
        }(specs[i][0])));
        bar.appendChild(btn);
      }
      anchor.parentNode.insertBefore(bar, anchor);
    },

    /** 采集成功/失败时统一开关导出按钮。 */
    setExportEnabled: function (on) {
      var bar = $('export-bar');
      if (!bar) return;
      var btns = bar.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) btns[i].disabled = !on;
    },

    /**
     * 按格式导出当前采集。channels 只带可见通道，避免把用不到的数据也写进文件。
     */
    exportAs: async function (format) {
      if (!this.currentId) { this.toast('请先采集数据'); return; }
      if (format !== 'csv' && format !== 'vcd' && format !== 'bin') return;

      var channels = [];
      for (var i = 0; i < Waveform.visible.length; i++) {
        if (Waveform.visible[i]) channels.push(i);
      }
      if (!channels.length) { this.toast('没有可见通道可导出'); return; }

      var res = await Api.save(this.currentId, format, channels);
      if (!res.ok) {
        this.toast(res.error || '导出失败');
        return;
      }
      var path = res.path || '';
      this.toast('已保存到 ' + path, true);
      var elPath = $('stat-path');
      if (elPath) {
        elPath.textContent = '路径: ' + path;
        elPath.title = path;
      }
    },

    openFolder: async function () {
      var res = await Api.openFolder();
      if (!res.ok) { this.toast(res.error); return; }
      this.toast('文件夹: ' + (res.path || ''), true);
    },

    onViewChange: function () {
      var s = Waveform, total = s.n || 0;
      if (!total) { $('stat-view').textContent = '视图: —'; return; }
      $('stat-view').textContent = '视图: ' + fmtNum(Math.floor(s.start)) + '–' +
        fmtNum(Math.floor(s.start + s.span)) + ' / ' + fmtNum(total);
    },

    onCursor: function (sample) {
      if (sample == null || !Waveform.n) { $('stat-cursor').textContent = '光标: —'; return; }
      var v = Waveform.data[sample] || 0;
      var bits = '';
      for (var i = 0; i < 8; i++) bits += ((v >> i) & 1);
      $('stat-cursor').textContent = '光标: #' + fmtNum(sample) + ' @' +
        fmtTime(sample / Waveform.rate) + ' CH7..0=' + bits;
    }
  };

  /* ---------- 全局导出（供 selftest 使用） ---------- */
  global.LA = {
    Api: Api, Waveform: Waveform, Measurer: Measurer, Decoder: Decoder, App: App,
    COLORS: CHANNEL_COLORS, MIN_SPAN: MIN_SPAN,
    helpers: { clamp: clamp, fmtTime: fmtTime, esc: esc }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { App.init(); });
  } else {
    App.init();
  }

})(window);
