from responses_transport import StopCampaign,sha,canonical
class DefenseTechError(StopCampaign):pass
def append(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(canonical(value)+'\n')
