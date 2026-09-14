"""Run only the remaining27 after explicit quota admission; retain the other12."""
import json,os
import parallel_provider as control
from run_defended_stage import run
from credential_store import load_credential
ROOT=control.ROOT

def main():
    authorization=control.read(ROOT/'LIVE_AUTHORIZATION.json')
    if authorization.get('status')!='confirmed' or authorization['new_targets']!=27:raise control.StopCampaign('quota_authorization_missing')
    admission=control.read(ROOT/'PARALLEL_ADMISSION.json')
    for name,h in admission['files'].items():
        if control.sha((ROOT/name).read_bytes())!=h:raise control.StopCampaign('runtime_changed')
    if control.read(ROOT/'COMPLEMENT_OFFLINE_CHECK.json')['status']!='verified':raise control.StopCampaign('offline_checks_missing')
    for sibling in ['ClawTrojan-dspro-three39','ClawTrojan-dspro-evidence-diagnostic12']:
        if control.read(ROOT.parent/sibling/'THREE_ARM_STATUS.json')['state']!='complete':raise control.StopCampaign('previous_campaign_not_complete')
    with (ROOT/'CONTROLLER_START.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'time':control.utc(),'targets':27},f)
    state={'state':'starting','pid':os.getpid(),'planned_new':27,'retained':12,'planned_combined':39,'method':'same Evidence v3','model':'deepseek-v4-pro'}
    def save():state['updated_at']=control.utc();control.write(ROOT/'CAMPAIGN_STATUS.json',state)
    save();p=None;key=''
    try:
        key=load_credential();p=control.Provider(key);key=''
        if p.quota.state()['cap']!=authorization['shared_cap']:raise control.StopCampaign('authorized_quota_mismatch')
        state['state']='running';save();p.progress(inflight=False);run(p,'evidence');state['state']='judgments_complete';save()
    except BaseException as e:
        state['state']='stopped';state['reason']=str(e) if isinstance(e,(control.StopCampaign,control.UnitUnknown,control.DefenseTechError,control.PauseCampaign)) else type(e).__name__;save();raise
    finally:
        key=''
        if p is not None:p.clear()
        save()
    from finalize_full39 import main as finalize
    try:
        finalize();state['state']='complete';save()
    except BaseException as e:
        state['state']='postprocessing_error';state['reason']=type(e).__name__;save();raise
if __name__=='__main__':main()
