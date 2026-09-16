"""Explicit host projection from frozen v3 ChatCompletion requests to Luna Responses."""
from responses_transport import base_body,convert_messages,output_text,sha,canonical
class DefenseProvider:
    def __init__(self,provider):self.provider=provider
    def create(self,unit,role,body,boundary=None):
        assert role=='defense' and body['max_tokens']==8192
        assert body.get('response_format')=={'type':'json_object'}
        wire=base_body(convert_messages(body['messages']))
        wire['input'].insert(0,{'role':'system','content':'Return the requested output as a JSON object.'})
        wire['text']={'format':{'type':'json_object'}}
        self.provider.append('defense_projection.jsonl',{'unit':unit,'boundary':boundary,'source_request':body,'wire_sha256':sha(canonical(wire)),'projection':{'model':'gpt-5.6-luna','temperature':'omitted','thinking':'reasoning.medium','max_output_tokens':8192,'format_only_instruction':'Return the requested output as a JSON object.'}})
        response=self.provider.create(unit,role,wire)
        return {'model':response['model'],'choices':[{'finish_reason':'stop' if response['status']=='completed' else 'length','message':{'role':'assistant','content':output_text(response)}}],'usage':response.get('usage',{})}
