/* 通用工具函数 - 所有页面共享 */

const API = window.location.origin;

// ── 在浏览器中打开当前页面（PyWebView 调用系统默认浏览器）──
function openInBrowser() {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.open_in_browser();
  } else {
    window.open(window.location.href, '_blank');
  }
}

// ── 全局 F5 刷新支持（PyWebView 默认不支持）────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
    e.preventDefault();
    location.reload();
  }
});

/**
 * 带重试的 JSON fetch
 */
async function fetchJson(url, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(url);
      if (!r.ok && r.status >= 500 && i < retries - 1) {
        await new Promise(res => setTimeout(res, 500));
        continue;
      }
      return await r.json();
    } catch(e) {
      if (i < retries - 1) {
        await new Promise(res => setTimeout(res, 500));
        continue;
      }
      throw e;
    }
  }
}

/**
 * Toast 提示
 */
function toast(msg, type='success') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast show ' + type;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = 'toast', 2800);
}

// ── 平滑曲线图工具 ──────────────────────────────────────

/**
 * 简单折线 - 直接用直线连接各点
 * @param {Array<{x:number,y:number}>} pts 数据点
 * @returns {string} SVG path d 属性
 */
function simpleLinePath(pts) {
  if (!pts || pts.length < 1) return '';
  // 单点：画一个小圆点
  if (pts.length === 1) {
    const r = 3;
    const x = pts[0].x, y = pts[0].y;
    return `M ${x-r} ${y} A ${r} ${r} 0 1 0 ${x+r} ${y} A ${r} ${r} 0 1 0 ${x-r} ${y}`;
  }
  // 用直线连接各点
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    d += ` L ${pts[i].x} ${pts[i].y}`;
  }
  return d;
}


/**
 * 绘制记忆趋势曲线
 * - 紫色：累计总数（added-deleted 的实时总数）
 * - 绿色：每时段新增量（该小时/天实际新增的记忆数）
 * - 橙色：每时段更新量（该小时/天实际更新的记忆数）
 */
function drawChartCurve(data, range) {
  const svgW = 700, svgH = 120, padTop = 8, padBottom = 4, padX = 10;
  const lineTotal = document.getElementById('curveLineTotal');
  const lineAdded = document.getElementById('curveLineAdded');
  const lineUpdated = document.getElementById('curveLineUpdated');
  const svg = document.getElementById('chartSvg');

  if (!lineTotal) return;

  if (!data || data.length < 1) {
    lineTotal.setAttribute('d', '');
    if (lineAdded) lineAdded.setAttribute('d', '');
    if (lineUpdated) lineUpdated.setAttribute('d', '');
    _clearChartDots();
    _updateYAxis(0);
    return;
  }

  const usableW = svgW - padX * 2;
  const stepX = usableW / Math.max(data.length - 1, 1);

  // 累计总数线（紫）— 实际记忆数趋势
  const maxTotal = Math.max(...data.map(d => d.total), 1);
  const totalPts = data.map((d, i) => ({
    x: padX + stepX * i,
    y: padTop + (svgH - padTop - padBottom) * (1 - d.total / maxTotal),
  }));
  lineTotal.setAttribute('d', simpleLinePath(totalPts));

  // 新增线（绿）— 每个时间点的实际新增量
  if (lineAdded) {
    const maxAdded = Math.max(...data.map(d => d.added || 0), 1);
    const addedPts = data.map((d, i) => ({
      x: padX + stepX * i,
      y: padTop + (svgH - padTop - padBottom) * (1 - (d.added || 0) / maxAdded),
    }));
    lineAdded.setAttribute('d', simpleLinePath(addedPts));
  }

  // 更新线（橙）— 每个时间点的实际更新量
  if (lineUpdated) {
    const maxUpdated = Math.max(...data.map(d => d.updated || 0), 1);
    const updatedPts = data.map((d, i) => ({
      x: padX + stepX * i,
      y: padTop + (svgH - padTop - padBottom) * (1 - (d.updated || 0) / maxUpdated),
    }));
    lineUpdated.setAttribute('d', simpleLinePath(updatedPts));
  }

  // 绘制端点圆点
  _drawChartDots(totalPts, addedPts, updatedPts, data);

  _updateYAxis(maxTotal);
}

/**
 * 清除图表端点
 */
function _clearChartDots() {
  const existing = document.querySelectorAll('.chart-dot');
  existing.forEach(el => el.remove());
}

/**
 * 绘制图表端点并绑定悬浮窗
 * @param {Array<{x:number,y:number}>} totalPts 累计线的端点坐标
 * @param {Array} data 对应的数据
 */
function _drawChartDots(totalPts, data) {
  const svg = document.getElementById('chartSvg');
  const tooltip = document.getElementById('chartTooltip');
  const tooltipDate = document.getElementById('tooltipDate');
  const tooltipTotal = document.getElementById('tooltipTotal');
  const tooltipAdded = document.getElementById('tooltipAdded');
  const tooltipUpdated = document.getElementById('tooltipUpdated');
  if (!svg || !tooltip || !totalPts || !data) return;

  // 清除旧端点
  _clearChartDots();

  // 直接用 totalPts 的坐标绘制端点（与曲线端点一致）
  totalPts.forEach((pt, i) => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('class', 'chart-dot');
    circle.setAttribute('cx', pt.x);
    circle.setAttribute('cy', pt.y);
    circle.setAttribute('r', '3');
    circle.setAttribute('fill', '#7c3aed');
    circle.setAttribute('data-index', i);
    svg.appendChild(circle);

    const d = data[i];

    // 鼠标事件
    circle.addEventListener('mouseenter', (e) => {
      tooltipDate.textContent = d.date;
      tooltipTotal.textContent = d.total ?? '-';
      tooltipAdded.textContent = d.added ?? '-';
      tooltipUpdated.textContent = d.updated ?? '-';

      // 计算像素位置
      const svgRect = svg.getBoundingClientRect();
      const wrapRect = svg.parentElement.getBoundingClientRect();
      const scaleX = svgRect.width / 700;
      const scaleY = svgRect.height / 120;
      const dotX = pt.x * scaleX;
      const dotY = pt.y * scaleY;

      let left = dotX + 10;
      let top = dotY - 40;

      // 边界检测
      if (left + 130 > wrapRect.width) left = dotX - 140;
      if (top < 0) top = dotY + 10;

      tooltip.style.left = left + 'px';
      tooltip.style.top = top + 'px';
      tooltip.classList.add('visible');
    });

    circle.addEventListener('mouseleave', () => {
      tooltip.classList.remove('visible');
    });
  });
}

/**
 * 更新Y轴刻度（4个刻度）
 * @param {number} max 最大值
 */
function _updateYAxis(max) {
  const yMax = document.getElementById('yMax');
  const yMid2 = document.getElementById('yMid2');
  const yMid1 = document.getElementById('yMid1');
  const yMin = document.getElementById('yMin');

  if (!yMax || !yMid2 || !yMid1 || !yMin) return;

  const maxVal = Math.max(max, 1);
  yMax.textContent = Math.round(maxVal);
  yMid2.textContent = Math.round(maxVal * 0.67);
  yMid1.textContent = Math.round(maxVal * 0.33);
  yMin.textContent = '0';
}
