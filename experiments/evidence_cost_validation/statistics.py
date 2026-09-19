"""Pure common statistics for candidate selection, result reporting and gates."""
from collections import defaultdict
import statistics


COUNTS=('observations','reference_point','reference_unknown','reference_not_applicable',
        'correct','wrong','wrong_safe','point','unknown','infeasible','not_applicable')


def auc(values, grid):
    if any(values.get(x) is None for x in grid):return None
    return sum((b-a)*(values[a]+values[b])/2 for a,b in zip(grid,grid[1:]))/(grid[-1]-grid[0])


def curves(records, truth, grid):
    """Average seeds at query/condition/rho, then sum within families, then equal families."""
    repeated=defaultdict(list)
    for r in records:
        t=truth[r['query_id']];qualified=t['status']=='point';point=r['status']=='point'
        good=qualified and point and r['value']==t['value'];bad=qualified and point and not good
        v=dict(observations=1,reference_point=int(qualified),
               reference_unknown=int(t['status'] not in ('point','not_applicable')),
               reference_not_applicable=int(t['status']=='not_applicable'),correct=int(good),wrong=int(bad),
               wrong_safe=int(bad and r['metric']=='UEA' and r['value'] in (False,0)),
               point=int(point),unknown=int(r['status']=='unknown'),infeasible=int(r['status']=='infeasible'),
               not_applicable=int(r['status']=='not_applicable'))
        repeated[(r['family_id'],r['query_id'],r['condition'],r['rho'])].append(v)
    buckets=defaultdict(lambda:{k:0.0 for k in COUNTS})
    for (family,query,condition,rho),items in repeated.items():
        for k in COUNTS:buckets[family,rho][k]+=statistics.mean(v[k] for v in items)
    families=[]
    for (family,rho),v in sorted(buckets.items()):
        den=v['reference_point'];n=v['observations']
        families.append(dict(family_id=family,rho=rho,**v,
            correct_coverage=v['correct']/den if den else None,
            wrong_rate=v['wrong']/den if den else None,wrong_safe_rate=v['wrong_safe']/den if den else None,
            unknown_rate=v['unknown']/n,infeasible_rate=v['infeasible']/n,
            reference_coverage=den/n,reference_unknown_rate=v['reference_unknown']/n,
            reference_not_applicable_rate=v['reference_not_applicable']/n))
    aggregate=[]
    rates=('correct_coverage','wrong_rate','wrong_safe_rate','unknown_rate','infeasible_rate',
           'reference_coverage','reference_unknown_rate','reference_not_applicable_rate')
    for rho in grid:
        rr=[r for r in families if r['rho']==rho];item=dict(rho=rho,families=len(rr))
        for k in COUNTS:item[k]=sum(r[k] for r in rr)
        for k in rates:
            vv=[r[k] for r in rr if r[k] is not None];item[k]=statistics.mean(vv) if vv else None
        aggregate.append(item)
    areas=[]
    for f in sorted({r['family_id'] for r in families}):
        areas.append(dict(family_id=f,auc=auc({r['rho']:r['correct_coverage'] for r in families if r['family_id']==f},grid)))
    return dict(aggregate=aggregate,families=families,areas=areas,
                auc=auc({r['rho']:r['correct_coverage'] for r in aggregate},grid))


def compare(dynamic, static, grid):
    ds={r['family_id']:r['auc'] for r in dynamic['areas']};ss={r['family_id']:r['auc'] for r in static['areas']}
    paired=[dict(family_id=f,dynamic_auc=ds[f],static_auc=ss[f],difference=None if ds[f] is None or ss[f] is None else ds[f]-ss[f]) for f in sorted(ds)]
    valid=[r for r in paired if r['difference'] is not None]
    leave=[dict(excluded=r['family_id'],difference=statistics.mean(x['difference'] for x in valid if x!=r)) for r in valid if len(valid)>1]
    dc={r['rho']:r for r in dynamic['aggregate']};sc={r['rho']:r for r in static['aggregate']}
    curve=[dict(rho=x,coverage_difference=None if dc[x]['correct_coverage'] is None or sc[x]['correct_coverage'] is None else dc[x]['correct_coverage']-sc[x]['correct_coverage'],
                dynamic_wrong=dc[x]['wrong'],static_wrong=sc[x]['wrong'],dynamic_wrong_safe=dc[x]['wrong_safe'],static_wrong_safe=sc[x]['wrong_safe']) for x in grid]
    return dict(dynamic_auc=dynamic['auc'],static_auc=static['auc'],difference=None if dynamic['auc'] is None or static['auc'] is None else dynamic['auc']-static['auc'],
                paired=paired,leave_one_out=leave,curve=curve,
                positive_families=sum(r['difference']>1e-12 for r in valid),
                positive_interior_points=sum(r['coverage_difference'] is not None and r['coverage_difference']>1e-12 and 0<r['rho']<1 for r in curve))
