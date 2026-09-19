"""Plot sealed result curves; optional matplotlib, zero experiment execution."""
import argparse
import json
from pathlib import Path


def draw(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    old=json.loads((out/'COST_ROBUSTNESS.json').read_text('utf-8'))
    fresh=json.loads((out/'FRESH_RESULTS.json').read_text('utf-8'))
    fig,axs=plt.subplots(1,2,figsize=(10,4.2),sharey=True)
    for ax,cost in zip(axs,('C1','C2')):
        for label,curve in [('Old disclosed heldout',old['results'][cost]['heldout']['curve']),
                            ('New 24 controlled instances',fresh['results'][cost]['curve'])]:
            ax.plot([r['rho'] for r in curve],[100*r['coverage_difference'] for r in curve],marker='o',markersize=3,label=label)
        if cost=='C1':
            ax.axhline(.5,color='grey',linestyle='--',linewidth=1,label='Preregistered 0.5 pp threshold')
        ax.axhline(0,color='black',linewidth=.6)
        ax.set(title=cost,xlabel='Normalized proxy budget');ax.grid(alpha=.2)
    axs[0].set_ylabel('Coverage gain (percentage points)')
    handles,labels=axs[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=1,fontsize=8)
    fig.tight_layout(rect=(0,.19,1,1))
    fig.savefig(out/'COVERAGE_GAIN.png',dpi=200,bbox_inches='tight')
    fig.savefig(out/'COVERAGE_GAIN.pdf',bbox_inches='tight');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();draw(a.out.resolve())
