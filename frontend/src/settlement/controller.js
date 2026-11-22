import {request} from '../api.js';

const section = id => `/plans/${id}/pilot-settlements`;

export async function loadSettlements(state) {
  if (state.current !== 'settlements') return;
  const id = state.selectedPlan?.id;
  state.pilotSettlements = id ? (await request(section(id))).items : [];
}

export function bindSettlement(state, render, run, setMessage) {
  if (state.current !== 'settlements') return;
  for (const form of document.querySelectorAll('form[data-settlement]')) {
    form.addEventListener('submit', event => {
      event.preventDefault();
      run(async () => {
        const button = form.querySelector('button');
        button.disabled = true;
        try {
          const review = form.dataset.action === 'review';
          const body = Object.fromEntries(new FormData(form));
          if (!review) {
            for (const name of Object.keys(body)) {
              if (name.endsWith('_cents') || name === 'tickets_sold') body[name] = Number(body[name]);
            }
          }
          const route = `${section(state.selectedPlan.id)}/${form.dataset.settlement}${review ? '/review' : ''}`;
          await request(route, {method:'POST', body:JSON.stringify(body)});
          await loadSettlements(state);
          render();
          setMessage(review ? '收益复核已记录' : '票房结算已登记');
        } finally {
          button.disabled = false;
        }
      });
    });
  }
}
