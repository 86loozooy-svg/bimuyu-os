(function () {
  const match = location.pathname.match(/\/app\/projects\/(\d+)/);
  if (!match) return;
  const pid = match[1];
  const API = `/api/projects/${pid}`;
  const CATS = ['主材', '辅材', '设备', '软装', '人工', '其他'];
  const STATUSES = ['pending', 'ordered', 'arrived', 'installed'];
  const ST_LABEL = { pending: '待采购', ordered: '已下单', arrived: '已到货', installed: '已安装' };

  const fmt = (n) =>
    '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) =>
    String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  async function load() {
    const r = await fetch(API + '/materials');
    if (!r.ok) {
      document.getElementById('bomBody').innerHTML =
        '<tr><td colspan="11" style="color:#ff6b6b">加载失败</td></tr>';
      return;
    }
    const d = await r.json();
    const tb = document.getElementById('bomBody');
    if (!d.materials.length) {
      tb.innerHTML =
        '<tr><td colspan="11" style="color:var(--color-text-tertiary)">暂无物料，点击「+ 物料」或「从造价生成草稿」。</td></tr>';
      return;
    }
    tb.innerHTML = d.materials
      .map((m) => {
        const qty = parseFloat(m.quantity || 0);
        const price = parseFloat(m.unit_price || 0);
        const line = qty * price;
        return `<tr data-id="${m.id}">
          <td>${esc(m.name)}</td><td>${esc(m.brand)}</td><td>${esc(m.spec)}</td>
          <td>${qty}</td><td>${esc(m.unit)}</td><td>${fmt(price)}</td><td>${fmt(line)}</td>
          <td>${esc(m.category)}</td><td>${esc(m.purchase_stage)}</td>
          <td>${ST_LABEL[m.status] || m.status || ''}</td>
          <td style="white-space:nowrap">
            <button class="bc-btn" data-act="edit">编辑</button>
            <button class="bc-btn bc-del" data-act="del">✕</button>
          </td></tr>`;
      })
      .join('');
    tb.querySelectorAll('button[data-act]').forEach(
      (b) =>
        (b.onclick = () => {
          const id = b.closest('tr').dataset.id;
          if (b.dataset.act === 'edit') openEdit(id);
          else delMaterial(id);
        })
    );
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

  function materialFormHtml(v) {
    v = v || {};
    const catOpts = CATS.map((c) => `<option ${v.category === c ? 'selected' : ''}>${c}</option>`).join('');
    const stOpts = STATUSES.map(
      (s) => `<option value="${s}" ${v.status === s ? 'selected' : ''}>${ST_LABEL[s]}</option>`
    ).join('');
    return `
      <div class="form-group"><label>名称</label><input id="mName" value="${esc(v.name || '')}"></div>
      <div class="form-group"><label>品牌</label><input id="mBrand" value="${esc(v.brand || '')}"></div>
      <div class="form-group"><label>规格</label><input id="mSpec" value="${esc(v.spec || '')}"></div>
      <div class="form-group"><label>数量</label><input id="mQty" type="number" step="0.01" value="${v.quantity != null ? v.quantity : 1}"></div>
      <div class="form-group"><label>单位</label><input id="mUnit" value="${esc(v.unit || '')}"></div>
      <div class="form-group"><label>单价(¥)</label><input id="mPrice" type="number" step="0.01" value="${v.unit_price || 0}"></div>
      <div class="form-group"><label>分类</label><select id="mCat">${catOpts}</select></div>
      <div class="form-group"><label>购买节点</label><input id="mStage" value="${esc(v.purchase_stage || '')}" placeholder="前期/中期/尾期"></div>
      <div class="form-group"><label>状态</label><select id="mStatus">${stOpts}</select></div>`;
  }

  document.getElementById('addMaterialBtn').onclick = () => {
    const m = openModal('新增物料', materialFormHtml(''));
    m.querySelector('#bmOk').onclick = () => submitMaterial(m, null);
  };

  async function openEdit(id) {
    const r = await fetch(API + '/materials');
    const d = await r.json();
    const mat = (d.materials || []).find((x) => String(x.id) === String(id));
    if (!mat) return;
    const m = openModal('编辑物料', materialFormHtml(mat));
    m.querySelector('#bmOk').onclick = () => submitMaterial(m, id);
  }

  async function submitMaterial(m, id) {
    const name = m.querySelector('#mName').value.trim();
    if (!name) {
      alert('请填写名称');
      return;
    }
    const body = {
      name,
      brand: m.querySelector('#mBrand').value,
      spec: m.querySelector('#mSpec').value,
      quantity: parseFloat(m.querySelector('#mQty').value || 1),
      unit: m.querySelector('#mUnit').value,
      unit_price: parseFloat(m.querySelector('#mPrice').value || 0),
      category: m.querySelector('#mCat').value,
      purchase_stage: m.querySelector('#mStage').value,
      status: m.querySelector('#mStatus').value,
    };
    const url = id ? `${API}/materials/${id}` : API + '/materials';
    const method = id ? 'PUT' : 'POST';
    const r = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (r.ok) {
      m.style.display = 'none';
      load();
    } else {
      alert('保存失败');
    }
  }

  async function delMaterial(id) {
    if (!confirm('删除该物料？')) return;
    const r = await fetch(`${API}/materials/${id}`, { method: 'DELETE' });
    if (r.ok) load();
  }

  document.getElementById('genFromCostBtn').onclick = async () => {
    if (!confirm('将读取造价库所有材质分类，生成草稿物料清单（不覆盖已有）？')) return;
    const r = await fetch(API + '/materials/generate-from-cost', { method: 'POST' });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      alert(`已生成 ${d.count} 条草稿`);
      load();
    } else {
      alert('生成失败：' + (d.error || r.status));
    }
  };

  document.getElementById('exportExcelBtn').onclick = () => {
    window.location = API + '/materials/export/excel';
  };
  document.getElementById('exportPdfBtn').onclick = () => {
    window.location = API + '/materials/export/pdf';
  };

  load();
})();
