"""Offline metrics. This module is NEVER imported by a search engine."""
import math

def tolerance(reference):
    return max(1e-9, abs(reference['optimal_cost'])*1e-12)

def root_regret(root, reference):
    if root is None:
        return None
    value = reference['root_costs'][root] - reference['optimal_cost']
    if value < -tolerance(reference):
        raise ValueError('Invalid offline root reference')
    return max(0., value)

def events_for(stats, reference, visibility='observed'):
    if visibility == 'api_available' and stats.get('original_return_is_blocking'):
        if stats.get('selected_root') is None:
            return []
        raw = [dict(elapsed=stats['total_optimizer_time'], root=stats['selected_root'], cost=stats['selected_cost'])]
    else:
        raw = stats.get('incumbent_trace', [])
    out=[]
    last=-1.
    denominator=max(abs(reference['optimal_cost']),1e-9)
    for e in raw:
        t=float(e['elapsed'])
        if t < last or t < 0:
            raise ValueError('Non-monotonic observation timestamps')
        last=t
        regret=root_regret(e['root'], reference)
        out.append(dict(e, root_regret=regret, normalized_root_regret=regret/denominator,
                        configuration_regret=max(0.,e['cost']-reference['optimal_cost'])))
    return out

def at_time(events, deadline):
    found=None
    for e in events:
        if e['elapsed']>deadline:
            break
        found=e
    return found

def integrate(events, horizon):
    """Exact step integral, without imputing regret before first feasibility.

    Full AURC is undefined if any interval is unobserved. Conditional AURC
    and coverage are separate statistics, not a weighted composite score.
    """
    if horizon<=0:
        raise ValueError('Positive horizon required')
    active=[e for e in events if e['elapsed']<=horizon]
    if not active:
        return dict(unavailable_seconds=horizon, feasible_seconds=0., unavailable_fraction=1.,
                    aurc_raw=None, aurc_normalized=None, conditional_aurc_raw=None,
                    conditional_aurc_normalized=None, observed_integral_raw=0., observed_integral_normalized=0.)
    missing=min(horizon,active[0]['elapsed']); area=normarea=0.
    for i,e in enumerate(active):
        end=active[i+1]['elapsed'] if i+1<len(active) else horizon
        width=max(0.,end-e['elapsed'])
        area+=width*e['root_regret'];normarea+=width*e['normalized_root_regret']
    known=horizon-missing
    return dict(unavailable_seconds=missing,feasible_seconds=known,unavailable_fraction=missing/horizon,
        aurc_raw=area/horizon if missing==0 else None,
        aurc_normalized=normarea/horizon if missing==0 else None,
        conditional_aurc_raw=area/known if known>0 else None,
        conditional_aurc_normalized=normarea/known if known>0 else None,
        observed_integral_raw=area,observed_integral_normalized=normarea)

def targets(events, stats, reference, horizon):
    conditions=[('first_feasible',lambda e: True),
      ('optimal_root',lambda e:e['root_regret']<=tolerance(reference)),
      ('near_1pct',lambda e:e['normalized_root_regret']<=.01),
      ('root_le_10',lambda e:e['root_regret']<=10),
      ('root_le_5',lambda e:e['root_regret']<=5),
      ('root_le_1',lambda e:e['root_regret']<=1)]
    rows=[]
    for name,test in conditions:
        hits=[e for e in events if e['elapsed']<=horizon and test(e)]
        e=hits[0] if hits else None
        rows.append(dict(target=name,event_observed=e is not None,
          time_to_target=e['elapsed'] if e else None,followup_time=e['elapsed'] if e else horizon,
          censor_time=horizon,exact_evaluations_at_target=e.get('exact_evaluations') if e else None,
          terminal_evaluations_at_target=e.get('terminal_evaluations') if e else None,
          memory_rss_mib_at_target=e.get('rss_mib') if e else None))
    cert=stats.get('proof_time');hit=cert is not None and cert<=horizon
    rows.append(dict(target='certified_configuration_optimality',event_observed=hit,
      time_to_target=cert if hit else None,followup_time=cert if hit else horizon,censor_time=horizon,
      exact_evaluations_at_target=None,terminal_evaluations_at_target=None,memory_rss_mib_at_target=None))
    return rows

def regression_count(events, tol=1e-9):
    return sum(b['root_regret']>a['root_regret']+tol for a,b in zip(events,events[1:]))
