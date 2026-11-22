from dataclasses import dataclass


@dataclass(frozen=True)
class PilotEconomics:
    contribution_cents: int
    breakeven_tickets: int | None


def calculate(tickets_sold, gross, commission, concessions, incremental_cost, subsidy):
    """Use actual unit yield, retaining zero-yield and no-sale runs in the ledger."""
    if commission > gross or (not tickets_sold and gross):
        raise ValueError('票务佣金不能超过实收，无售票场次的票务实收须为零')
    net_tickets = gross - commission
    cost_after_concessions = incremental_cost + subsidy - concessions
    if cost_after_concessions <= 0:
        breakeven = 0
    elif not tickets_sold or not net_tickets:
        breakeven = None
    else:
        breakeven = (cost_after_concessions * tickets_sold + net_tickets - 1) // net_tickets
    return PilotEconomics(net_tickets - cost_after_concessions, breakeven)
