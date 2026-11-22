import {api, request} from './api.js';
import {escape} from './operations.js';

const attemptLabels = {effective: '已生效', rejected: '已拒绝（全场留原厅）'};
const tone = {effective: 'ok', rejected: 'warn'};

function panel(title, body, extra = '') {
  return `<section class="panel" style="margin-bottom:20px"><div class="panel-head"><h3>${title}</h3>${extra}</div>${body}</section>`;
}

function statusChip(row) {
  return `<span class="ops-status ${tone[row.status] || ''}">${attemptLabels[row.status] || row.status}</span>`;
}

function fmtTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-CN', {hour12: false});
}

function requestForm(state) {
  const canEdit = ['planner', 'admin'].includes(state.user.role)
    && state.selectedPlan?.status === 'live';
  if (!canEdit) return '';
  return panel('发起临时换厅', `<form class="ops-form" data-hall-op="request">
    <div class="ops-fields">
      <label>原厅名称<input name="origin_hall_name" minlength="1" maxlength="60" placeholder="IMAX-1" required></label>
      <label>目标厅名称<input name="target_hall_name" minlength="1" maxlength="60" placeholder="IMAX-3" required></label>
    </div>
    <label>目标厅容量（座）<input name="target_capacity" type="number" min="1" max="2000" required></label>
    <label>换厅原因<textarea name="reason" rows="2" minlength="3" maxlength="600" placeholder="设备故障 / 放映调整，说明临时换厅依据" required></textarea>
    <button class="button primary" type="submit">预检并整体换厅</button>
    <p class="ops-intro">同厅各实验单元一起生效；容量不足或座区冲突时全场留在原厅，请求记为已拒绝。</p>
  </form>`);
}

function attemptCards(state) {
  const rows = state.hallChanges || [];
  if (!rows.length) return '<p>暂无换厅请求。场次处于直播中时可由排片策划发起。</p>';
  const canEdit = ['planner', 'admin'].includes(state.user.role)
    && state.selectedPlan?.status === 'live';
  return rows.map(row => {
    const retry = canEdit && row.retryable ? `<details class="ops-history"><summary>重试该换厅（仅一次）</summary>
      <form class="ops-form" data-hall-op="retry" data-id="${row.id}">
        <label>重试说明<textarea name="reason" rows="2" minlength="3" maxlength="600" required
          placeholder="说明冲突已解除或目标厅已调整"></textarea></label>
        <button class="button secondary" type="submit">重试换厅</button>
      </form></details>` : (row.status === 'rejected' ? '<p class="ops-warning">同一次换厅已重试过，不能再次生效，请发起新的换厅请求。</p>' : '');
    return `<article class="ops-trial">
      <div class="ops-trial-head"><div><h4>${escape(row.origin_hall_name)} → ${escape(row.target_hall_name)}</h4>
        <p>目标容量 ${row.target_capacity} 座 · 请求 #${row.id} · 重试 ${row.retry_count} 次</p></div>${statusChip(row)}</div>
      <p>${escape(row.reason)}</p>
      ${row.failure_reason ? `<p class="ops-warning">${escape(row.failure_reason)}</p>` : ''}
      <p class="ops-intro">请求 ${fmtTime(row.requested_at)} · 生效 ${fmtTime(row.effective_at)}</p>
      ${retry}
    </article>`;
  }).join('');
}

function segmentBoard(state) {
  const rows = state.hallSegments || [];
  if (!rows.length) return '<p>暂无可查的厅次分段。</p>';
  return `<table class="ops-compare"><thead><tr>
      <th>实验单元 / 场次</th><th>实验组</th><th>实际厅次</th><th>座区</th><th>段内容量</th><th>归入座位</th><th>其中售出</th><th>时段</th>
    </tr></thead><tbody>
    ${rows.map(row => `<tr>
      <td>单元 #${row.unit_id}<small>${escape(row.session_code)}</small></td>
      <td><span class="group-label ${row.group_name}">${row.group_name}</span></td>
      <td><b>${escape(row.hall_name)}</b>${row.hall_change_id ? `<small>换厅 #${row.hall_change_id}</small>` : '<small>开场厅段</small>'}</td>
      <td>${escape(row.seat_zone)}</td>
      <td>${row.seat_capacity}</td>
      <td>${row.observed_seats}</td>
      <td>${row.sold_seats}</td>
      <td><small>${fmtTime(row.started_at)}<br>至 ${fmtTime(row.ended_at)}</small></td>
    </tr>`).join('')}
  </tbody></table>`;
}

export function hallPage(state) {
  const intro = '<p class="ops-intro">场次开场后可临时换厅：同厅各实验单元一起生效，实验组与座区保持不变；换厅前已入账座位留在原厅，迟到票务按发生时间归入当时的厅次。收益复盘按实际厅次分层。</p>';
  return `${intro}<div class="ops-layout">
    <div>${panel('厅次分段与归入座位', segmentBoard(state))}
      ${panel('换厅请求台账', attemptCards(state))}</div>
    ${requestForm(state)}
  </div>`;
}

export async function loadHall(state) {
  if (state.current !== 'hall') return;
  const id = state.selectedPlan?.id;
  if (!id) return;
  const [changes, segments] = await Promise.all([api.hallChanges(id), api.hallSegments(id)]);
  if (state.selectedPlan?.id === id && state.current === 'hall') {
    state.hallChanges = changes.items;
    state.hallSegments = segments.items;
  }
}

export function bindHall(state, render, run, notify) {
  if (state.current !== 'hall') return;
  document.querySelectorAll('form[data-hall-op]').forEach(form => form.onsubmit = event => {
    event.preventDefault();
    const key = form.dataset.hallOp;
    const fields = Object.fromEntries(new FormData(form));
    const submit = form.querySelector('button[type=submit]');
    submit.disabled = true;
    run(async () => {
      try {
        if (key === 'request') {
          fields.target_capacity = Number(fields.target_capacity);
          const result = await api.requestHallChange(state.selectedPlan.id, fields);
          notify(result.status === 'rejected' ? '换厅被拒，全场留在原厅。' : '换厅已整体生效。');
        } else {
          const result = await request(
            `/plans/${state.selectedPlan.id}/hall-changes/${form.dataset.id}/retry`,
            {method: 'POST', body: JSON.stringify({reason: fields.reason})});
          notify(result.status === 'rejected' ? '重试仍被拒，全场留在原厅。' : '重试成功，换厅已生效。');
        }
        await loadHall(state);
        render();
      } finally {
        submit.disabled = false;
      }
    });
  });
}
