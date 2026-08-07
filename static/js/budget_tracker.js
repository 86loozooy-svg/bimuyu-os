(function () {
  const card = document.getElementById('budgetTracker');
  if (!card) return;
  const pid = card.dataset.projectId;
  const API = `/api/projects/${pid}`;
  let chart = null;

  const fmt = (n) =>
    '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) =>
    String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  async function load() {
    const res = await fetch(API + '/budget');
    if (!res.ok) {
      document.getElementById('budgetCards').innerHTML = '<p style="color:#ff6b6b">加载失败</p>';
      return;
    }
    const data = await res.json();
    renderSummary(data);
    renderCards(data.items);
    renderChart(data.chart);
  }

  function renderSummary(d) {
    const el = document.getElementById('budgetSummary');
    el.innerHTML =
      `<div><span style="color:var(--color-text-secondary)">总预算：</span><b>${fmt(d.total_planned)}</b></div>` +
      `<div><span style="color:var(--color-text-secondary)">总已花：</span><b>${fmt(d.total_spent)}</b></div>` +
      `<div><span style="color:var(--color-text-secondary)">总剩余：</span><b style="color:${d.total_remaining < 0 ? '#ff6b6b' : 'var(--color-accent)'}">${fmt(d.total_remaining)}</b></div>`;
  }

  function renderCards(items) {
    const el = document.getElementById('budgetCards');
    if (!items.length) {
      el.innerHTML = '<p style="color:var(--color-text-tertiary)">暂无预算分项，点击「+ 预算分项」添加。</p>';
      return;
    }
    el.innerHTML = items
      .map(
        (it) => `
      <div class="budget-card ${it.over ? 'over' : ''}">
        <div class="budget-card__head">
          <div>
            <div class="budget-card__name">${esc(it.name)}</div>
            <div class="budget-card__cat">${esc(it.category)}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="bc-btn" data-act="expense" data-id="${it.id}">记一笔</button>
            <button class="bc-btn bc-del" data-act="del" data-id="${it.id}">✕</button>
          </div>
        </div>
        <div class="budget-card__row"><span>预算</span><b>${fmt(it.planned)}</b></div>
        <div class="budget-card__row"><span>已花</span><b>${fmt(it.spent)}</b></div>
        <div class="budget-card__row"><span>剩余</span><b style="color:${it.remaining < 0 ? '#ff6b6b' : 'inherit'}">${fmt(it.remaining)}</b></div>
        <div class="budget-card__bar"><div class="budget-card__fill" style="width:${Math.min(100, it.pct)}%"></div></div>
        <div class="budget-card__pct ${it.over ? 'over' : ''}">${it.pct}% ${it.over ? '· 超支' : ''}</div>
      </div>`
      )
      .join('');
    el.querySelectorAll('button[data-act]').forEach((b) =>
      (b.onclick = () => {
        const id = b.dataset.id;
        if (b.dataset.act === 'expense') openExpenseModal(id);
        else if (b.dataset.act === 'del') delItem(id);
      })
    );
  }

  function renderChart(chartData) {
    const cv = document.getElementById('budgetChart');
    if (!cv || !chartData || !chartData.labels.length) {
      if (cv) cv.style.display = 'none';
      return;
    }
    if (chart) chart.destroy();
    chart = new Chart(cv, {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: '累计预算',
            data: chartData.cum_budget,
            borderColor: '#9aa0a6',
            backgroundColor: 'rgba(154,160,166,.10)',
            fill: true,
            tension: 0.3,
          },
          {
            label: '累计实际',
            data: chartData.cum_actual,
            borderColor: '#c8ff00',
            backgroundColor: 'rgba(200,255,0,.12)',
            fill: true,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: '#cfcabf' } } },
        scales: {
          x: { ticks: { color: '#cfcabf' }, grid: { color: 'rgba(99,97,90,.3)' } },
          y: { ticks: { color: '#cfcabf' }, grid: { color: 'rgba(99,97,90,.3)' } },
        },
      },
    });
  }

  function openModal(title, html) {
    let m = document.getElementById('bmModal');
    if (!m) {
      m = document.createElement('div');
      m.id = 'bmModal';
      m.className = 'bm-modal';
      m.innerHTML =
        '<div class="bm-modal__box"><div class="bm-modal__title"></div><div class="bm-modal__body"></div><div class="bm-modal__foot"></div></div>';
      document.body.appendChild(m);
    }
    m.querySelector('.bm-modal__title').textContent = title;
    m.querySelector('.bm-modal__body').innerHTML = html;
    m.querySelector('.bm-modal__foot').innerHTML =
      '<button class="btn" id="bmOk">保存</button><button class="btn btn-outline" id="bmCancel">取消</button>';
    m.style.display = 'flex';
    m.querySelector('#bmCancel').onclick = () => (m.style.display = 'none');
    m.onclick = (e) => {
      if (e.target === m) m.style.display = 'none';
    };
    return m;
  }

  document.getElementById('addBudgetItemBtn').onclick = () => {
    const m = openModal(
      '新增预算分项',
      `<div class="form-group"><label>分项名称</label><input id="biName" placeholder="如：硬装基础"></div>
       <div class="form-group"><label>分类</label><input id="biCat" value="其他" placeholder="主材/人工/设备…"></div>
       <div class="form-group"><label>预算金额 (¥)</label><input id="biAmt" type="number" step="0.01" value="0"></div>`
    );
    m.querySelector('#bmOk').onclick = async () => {
      const name = m.querySelector('#biName').value.trim();
      if (!name) {
        alert('请填写分项名称');
        return;
      }
      const body = {
        name,
        category: m.querySelector('#biCat').value.trim() || '其他',
        planned_amount: parseFloat(m.querySelector('#biAmt').value || 0),
      };
      const r = await fetch(API + '/budget-items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        m.style.display = 'none';
        load();
      } else {
        alert('保存失败');
      }
    };
  };

  async function delItem(id) {
    if (!confirm('删除该预算分项？关联开销将不再归属此项。')) return;
    const r = await fetch(`${API}/budget-items/${id}`, { method: 'DELETE' });
    if (r.ok) load();
  }

  async function openExpenseModal(itemId) {
    const m = openModal(
      '记一笔开销',
      `<div class="form-group"><label>归属分项</label><input id="exItem" value="${itemId || ''}" disabled></div>
       <div class="form-group"><label>金额 (¥)</label><input id="exAmt" type="number" step="0.01" required></div>
       <div class="form-group"><label>收款方</label><input id="exPayee" placeholder="如：XX材料商"></div>
       <div class="form-group"><label>发生日期</label><input id="exDate" type="date"></div>
       <div class="form-group"><label>备注</label><input id="exNote"></div>
       <div class="form-group"><label>附件（PDF/图片，≤10MB）</label><input id="exFile" type="file"></div>`
    );
    m.querySelector('#bmOk').onclick = async () => {
      const amt = parseFloat(m.querySelector('#exAmt').value || 0);
      if (!amt || amt <= 0) {
        alert('请填写有效金额');
        return;
      }
      const fd = new FormData();
      if (itemId) fd.append('budget_item_id', itemId);
      fd.append('amount', amt);
      fd.append('payee', m.querySelector('#exPayee').value);
      fd.append('occurred_date', m.querySelector('#exDate').value);
      fd.append('note', m.querySelector('#exNote').value);
      const file = m.querySelector('#exFile').files[0];
      if (file) fd.append('attachment', file);
      const r = await fetch(API + '/expenses', { method: 'POST', body: fd });
      if (r.ok) {
        m.style.display = 'none';
        load();
      } else {
        const e = await r.json().catch(() => ({}));
        alert('保存失败：' + (e.error || r.status));
      }
    };
  }

  load();
})();
