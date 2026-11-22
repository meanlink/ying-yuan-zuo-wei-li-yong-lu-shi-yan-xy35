import {request} from './api.js';

const closeoutLabels = {unsubmitted:'待对账', discrepancy:'有差异', stale:'观测更新，需补对', matched:'已对齐'};
const pilotLabels = {assigned:'待排片', scheduled:'已排片', withdrawn:'已撤回'};
const tone = {matched:'ok', discrepancy:'warn', stale:'warn', scheduled:'ok'};

export function escape(value) {
  const entities = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  return String(value ?? '').replace(/[&<>"']/g, char => entities[char]);
}

function chip(status, labels) {
  return `<span class="ops-status ${tone[status] || ''}">${labels[status]}</span>`;
}

function field(label,name,placeholder='') {
  return `<label>${label}<textarea name="${name}" rows="2" minlength="3" maxlength="600" required placeholder="${escape(placeholder)}"></textarea></label>`;
}

function panel(title,body,extra='') {
  return `<section class="panel"><div class="panel-head"><h3>${title}</h3>${extra}</div>${body}</section>`;
}

function currency(cents) {
  return `¥${(cents / 100).toFixed(2)}`;
}

function delta(value, format=String) {
  return `${value > 0 ? '+' : ''}${format(value)}`;
}

function compare(row, latest) {
  const values = [['观测座位','observed',String],['售出票数','sold',String],['实收金额','cents',currency]];
  return `<table class="ops-compare"><thead><tr><th>指标</th><th>当前观测</th><th>POS 回执</th><th>差异</th></tr></thead><tbody>
    ${values.map(([label,key,format]) => `<tr><td>${label}</td><td>${format(row.ledger[key])}</td>
      <td>${latest ? format(latest.reported[key]) : '—'}</td><td>${latest ? delta(latest.reported[key] - row.ledger[key],format) : '—'}</td></tr>`).join('')}</tbody></table>`;
}

export function closeoutsPage(state) {
  const rows = state.closeouts || [];
  const selected = rows.find(row => row.unit_id === state.closeoutUnit) || rows[0];
  const list = rows.map(row => `<button type="button" class="ops-unit ${row === selected ? 'chosen' : ''}" data-closeout-unit="${row.unit_id}" aria-pressed="${row === selected}">
    <span><b>${escape(row.hall_name)} · ${escape(row.seat_zone)}</b><small>${escape(row.session_code)} · ${escape(row.group_name)}</small></span>${chip(row.status,closeoutLabels)}</button>`).join('');
  const header = `<p class="ops-intro">按影厅、场次、座位区核对 POS 班结。登记首张回执后，所有单元对齐才能运行分析或审批。</p>`;
  if (!selected) return header + panel('实验单元','<p>暂无可核对的实验单元。</p>');
  const latest = selected.history[0];
  const canSubmit = ['boxoffice','admin'].includes(state.user.role) && ['live','review'].includes(state.selectedPlan.status) && selected.ledger.observed > 0 && selected.status !== 'matched';
  const editor = canSubmit ? `<form data-cinema-op="closeout" data-unit="${selected.unit_id}" data-expected="${latest?.id || 0}" class="ops-form">
    <label>POS 批次编号<input name="batch_ref" minlength="3" maxlength="60" placeholder="POS-IMAX-1930-R02" required></label>
    <div class="ops-fields triple"><label>POS 观测座位数<input name="observed" type="number" min="0" max="20000" required></label>
    <label>POS 售出票数<input name="sold" type="number" min="0" max="20000" required></label>
    <label>POS 实收金额（元）<input name="revenue" type="number" min="0" step="0.01" required></label></div>
    ${field('交接说明','note','记录对账来源或差异补正依据')}<button class="button primary" type="submit">登记班结回执</button></form>` : '';
  const history = selected.history.length ? `<details class="ops-history"><summary>班结回执历史 · ${selected.history.length} 次</summary>
    <ol>${selected.history.map(row => `<li><b>${escape(row.batch_ref)}</b> · ${closeoutLabels[row.status]}<p>${escape(row.note)}</p>
      <small>POS ${row.reported.observed} 座 / ${row.reported.sold} 售 / ${currency(row.reported.cents)} · 登记时观测 ${row.snapshot.observed} 座 / ${row.snapshot.sold} 售 / ${currency(row.snapshot.cents)}</small></li>`).join('')}</ol></details>` : '';
  const notice = selected.status === 'stale' ? '<p class="ops-warning">回执后有新增观测。请重新导出 POS 数字并登记。</p>' : '';
  const matched = rows.filter(row=>row.status === 'matched').length;
  return `${header}<div class="ops-layout queue">${panel(`实验单元 · ${matched}/${rows.length} 已对齐`,list)}
    ${panel(`${escape(selected.hall_name)} · ${escape(selected.seat_zone)}`,compare(selected,latest)+notice+history+editor,chip(selected.status,closeoutLabels))}</div>`;
}

export function pilotsPage(state) {
  const plan = state.selectedPlan;
  const trials = state.pilots || [];
  const approved = state.reviews.filter(review => review.analysis_status === 'approved');
  const units = state.units.filter(unit => unit.group_name === 'treatment');
  const canPublish = ['revenue','admin'].includes(state.user.role) && plan?.status === 'approved' && approved.length && units.length;
  const planForm = canPublish ? panel('派发试行工单',`<form class="ops-form" data-cinema-op="createPilot">
    <label>已审批复盘<select name="review_id" required>${approved.map(row=>`<option value="${row.id}">复盘 #${row.id} · ${row.sample_size} 个样本</option>`).join('')}</select></label>
    <label>试行座区<select name="unit_id" required>${units.map(unit=>`<option value="${unit.id}">${escape(unit.hall_name)} · ${escape(unit.seat_zone)}（${unit.seat_count} 座）</option>`).join('')}</select></label>
    <div class="ops-fields"><label>试行日期<input name="show_date" type="date" required></label><label>试行开场时间<input name="show_time" type="time" required></label></div>
    <label>计划投放座位<input name="pilot_seats" type="number" min="1" max="500" required></label>
    ${field('试行目标','objective','填写放量范围与排片执行要求')}<button class="button primary" type="submit">派发给排片策划</button></form>`) : '';
  const cards = trials.map(trial => {
    const canConfirm = trial.status === 'assigned' && ['planner','admin'].includes(state.user.role);
    const canWithdraw = trial.status === 'assigned' && ['revenue','admin'].includes(state.user.role);
    const confirm = canConfirm ? `<form class="ops-form" data-cinema-op="confirmPilot" data-id="${trial.id}">
      <div class="ops-fields"><label>排片回执编号<input name="booking_ref" minlength="3" maxlength="60" required></label>
      <label>实际投放座位<input name="actual_seats" type="number" min="1" max="${trial.pilot_seats}" required></label></div>
      ${field('执行说明','result_note','记录排片系统中的实际安排')}<button class="button primary" type="submit">确认排片</button></form>` : '';
    const withdraw = canWithdraw ? `<details class="ops-history"><summary>撤回工单</summary><form class="ops-form" data-cinema-op="withdrawPilot" data-id="${trial.id}">
      ${field('撤回说明','result_note','说明场次变更或资源冲突')}<button class="button secondary" type="submit">确认撤回</button></form></details>` : '';
    return `<article class="ops-trial"><div class="ops-trial-head"><div><h4>${escape(trial.hall_name)} · ${escape(trial.seat_zone)}</h4>
      <p>${escape(trial.show_date)} ${escape(trial.show_time)} · 已审批复盘 #${trial.review_id}</p></div>${chip(trial.status,pilotLabels)}</div>
      <p>计划 ${trial.pilot_seats} 座${trial.actual_seats ? ` · 实投 ${trial.actual_seats} 座` : ''}</p><p>${escape(trial.objective)}</p>
      ${trial.result_note ? `<div class="ops-receipt"><strong>${trial.booking_ref ? `回执 ${escape(trial.booking_ref)}` : '撤回说明'}</strong><p>${escape(trial.result_note)}</p></div>` : ''}
      ${confirm}${withdraw}</article>`;
  }).join('');
  return `<p class="ops-intro">从已审批的实验结果安排下一场 treatment 座区试行，排片策划录回正式排片编号和实投座数。</p>
    <div class="ops-layout">${panel('排片试行台账',cards || '<p>暂无试行工单。收益经理可在复盘审批完成后派发。</p>')}${planForm}</div>`;
}

export async function loadOperation(state) {
  const current = state.current;
  const id = state.selectedPlan?.id;
  if (!id) return;
  const endpoint = {closeouts:'pos-closeouts', pilots:'scheduling-pilots'}[current];
  if (!endpoint) return;
  const {items} = await request(`/plans/${id}/${endpoint}`);
  if (state.selectedPlan?.id === id && state.current === current) state[current] = items;
}

const paths = {
  closeout: () => '/pos-closeouts', createPilot: () => '/scheduling-pilots',
  confirmPilot: id => `/scheduling-pilots/${id}/confirm`, withdrawPilot: id => `/scheduling-pilots/${id}/withdraw`,
};

export function bindOperations(state, render, run, notify) {
  document.querySelectorAll('[data-closeout-unit]').forEach(node => node.onclick = () => {
    state.closeoutUnit = Number(node.dataset.closeoutUnit);
    render();
  });
  document.querySelectorAll('[data-cinema-op]').forEach(form => form.onsubmit = event => {
    event.preventDefault();
    const key = form.dataset.cinemaOp;
    const fields = Object.fromEntries(new FormData(form));
    for (const field of ['review_id','unit_id','pilot_seats','actual_seats','observed','sold']) {
      if (Object.hasOwn(fields,field)) fields[field] = Number(fields[field]);
    }
    if (key === 'closeout') Object.assign(fields,{unit_id:Number(form.dataset.unit),expected_closeout_id:Number(form.dataset.expected)});
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
    run(async () => {
      try {
        const result = await request(`/plans/${state.selectedPlan.id}${paths[key](form.dataset.id)}`, {method:'POST',body:JSON.stringify(fields)});
        await loadOperation(state);
        render();
        notify(result.status === 'discrepancy' ? '回执已登记，观测存在差异。' : '业务记录已保存。');
      } finally {
        submit.disabled = false;
      }
    });
  });
}
