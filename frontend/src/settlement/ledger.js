import {escape} from '../operations.js';

const currency = new Intl.NumberFormat('zh-CN', {style:'currency', currency:'CNY'});
const money = cents => currency.format(cents / 100);
const status = {submitted:'待收益复核', approved:'已确认收益', rejected:'已驳回'};
const amounts = [
  ['gross_tickets_cents','票务实收（分）'], ['ticket_commission_cents','票务分账（分）'],
  ['concession_margin_cents','卖品毛利（分）'], ['incremental_cost_cents','增量成本（分）'], ['subsidy_cents','活动补贴（分）'],
];
const field = (name, label, attrs = '') => `<label>${label}<input name="${name}" ${attrs} required></label>`;

function input(item) {
  return `<form class="settlement-form" data-settlement="${item.pilot_id}" data-action="submit">
    ${field('pos_reference','结算凭证号','maxlength="80"')}
    ${field('tickets_sold','正式排片售出座位',`type="number" min="0" max="${item.seats}" step="1"`)}
    ${amounts.map(([name,label]) => field(name,label,'type="number" min="0" max="10000000" step="1"')).join('')}
    ${field('notes','票房和成本口径','minlength="5" maxlength="400"')}
    <button class="button primary" type="submit">登记场次结算</button></form>`;
}

function review(item) {
  return `<form class="settlement-form" data-settlement="${item.pilot_id}" data-action="review">
    <label>收益复核决定<select name="decision"><option value="approved">确认收益</option><option value="rejected">驳回结算</option></select></label>
    ${field('note','复核意见','minlength="5" maxlength="400"')}
    <button class="button ink" type="submit">提交复核</button></form>`;
}

export function settlementPage(state) {
  const {role} = state.user;
  const options = state.pilotSettlements ?? [];
  const cards = options.map(item => {
    const row = item.settlement;
    let details = item.can_submit ? '<p>已开场，可由票房岗位登记实际结算。</p>' : '<p>等待正式排片开场。</p>';
    if (!row && item.can_submit && ['boxoffice','admin'].includes(role)) details += input(item);
    if (row) {
      details = `<div class="settlement-metrics">
        <div><small>实际售出</small><strong>${row.tickets_sold} / ${row.seats_offered}</strong></div>
        <div><small>场次净贡献</small><strong>${money(row.contribution_cents)}</strong></div>
        <div><small>盈亏平衡门槛</small><strong>${row.breakeven_tickets ?? '票务净额为零'}</strong></div></div>
        <dl class="settlement-breakdown">${amounts.map(([name,label]) => `<div><dt>${label.replace('（分）','')}</dt><dd>${money(row[name])}</dd></div>`).join('')}</dl>
        <p>${escape(row.pos_reference)} · ${escape(row.notes)}</p><p><b>${status[row.state]}</b> ${escape(row.review_note ?? '')}</p>`;
      if (row.state === 'submitted' && ['revenue','admin'].includes(role) && Number(state.user.id) !== row.submitted_by) details += review(item);
    }
    return `<article class="panel pilot-settlement"><h3>${escape(item.hall)} · ${escape(item.receipt)}</h3>
      <p>${escape(item.show_date)} ${escape(item.show_time)} · 可售 ${item.seats} 座</p>${details}</article>`;
  });
  return `<section class="settlement-board">${cards.join('') || '<p class="panel">此排片版本暂无已确认的试行场次。</p>'}</section>`;
}
