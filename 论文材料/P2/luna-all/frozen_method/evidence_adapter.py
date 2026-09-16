"""Only boundary-local public values cross into the Evidence policy."""
import copy,json,hashlib
from pathlib import Path
from evidence_engine import EvidenceEngine
from evidence_method.state import BindingError
from provider_session import StopCampaign,append,sha
READS={'read','read_file','memory_read','memory_search','web_search','web_fetch','grep','ls','glob'}
EXTERNAL={'message','email','send_message','send_email','feishu_send'}
BLOCKED={'exec','bash','shell'}
class EvidenceAdapter:
 def __init__(self,engine,workspace):self.engine=engine;self.workspace=Path(workspace).resolve();self.original_call=None;self.actual_submissions=0
 def initial(self,system,messages,user):
  d=self.engine.decide('initial_consume',system,resource='native_loaded_system',origin='host_native_system_role',host_system=True)
  processed=self.engine.delivered(d,d.text,'host_native_system_role','native_loaded_system')
  if processed!=system:raise BindingError('native_system_bytes_changed')
  output=copy.deepcopy(messages)
  # Current user remains an actual authority source with byte-identical content.
  current_index=len(output)-1 if output and output[-1].get('role')=='user' and str(output[-1].get('content','')).strip()==user.strip() else None
  for i,m in enumerate(output):
   if i==current_index:continue
   if not isinstance(m.get('content'),str):continue
   source='history-message-'+str(i)
   d=self.engine.decide('initial_consume',m['content'],resource=source,origin='preexisting_history_unknown')
   m['content']=self.engine.delivered(d,d.text,'preexisting_history_unknown',source)
  return processed,output
 def dispatch(self,dispatcher,name,args,native):
  with self.engine.lock:
   self.original_call={'name':name,'input':copy.deepcopy(args)}
   if name in EXTERNAL:
    raw=json.dumps(args,ensure_ascii=False,sort_keys=True)
    d=self.engine.decide('pre_external',raw,resource='tool:'+name,origin='actor_candidate',candidate=self.original_call)
    d.consume()
    if d.denied:
     dispatcher._record(name,args,d.feedback,was_intercepted=True,metadata={'interception_layer':'evidence','boundary_id':d.result['boundary_id']})
     self.engine._audit('external_not_invoked',{'boundary_id':d.result['boundary_id'],'original_call':self.original_call});return d.feedback
   start=len(dispatcher.audit);result=native()
   if name in BLOCKED:
    self.engine._audit('native_sandbox_intercept',{'original_call':self.original_call});return result
   if name in EXTERNAL:
    self.engine._audit('native_simulated_send',{'original_call':self.original_call,'real_network_delivery':False});return result
   if name in READS:
    resource=str(args.get('path',args.get('file',args.get('url',name))))
    if name in ['memory_read','memory_search'] and not resource.startswith('memory/'):resource='memory/'+resource
    origin='external_tool_return' if name in ['web_search','web_fetch'] else 'preexisting_origin_unknown'
    # ls/glob are file-name metadata; grep returns substantive lines and is reviewed.
    # Known native error strings carry no document body; preserve exact error feedback.
    known_errors={'Error: no path provided',f'Error: file not found: {resource}',f"Error: '{resource}' is a directory, not a file"}
    d=self.engine.decide('tool_consume',result,resource=resource,origin=origin,metadata_only=name in ['ls','glob'] or result in known_errors)
    result=self.engine.delivered(d,d.text,origin,resource)
    if len(dispatcher.audit)>start:dispatcher.audit[-1].tool_output=result
   return result
 def commit(self,dispatcher,name,args,resolved,old_text,candidate):
  with self.engine.lock:
   if not resolved.is_relative_to(self.workspace):raise StopCampaign('host_path_containment')
   original=copy.deepcopy(self.original_call or {'name':name,'input':args});old_bytes=resolved.read_bytes() if resolved.is_file() else b''
   resource=resolved.relative_to(self.workspace).as_posix()
   d=self.engine.decide('pre_commit',candidate,resource=resource,origin='actor_candidate',candidate=original,preimage=old_text)
   if (resolved.read_bytes() if resolved.is_file() else b'')!=old_bytes:raise BindingError('REPLAN_REQUIRED_target_version_changed')
   d.consume()
   if d.denied:
    dispatcher._record(name,args,d.feedback,was_intercepted=True,metadata={'interception_layer':'evidence','boundary_id':d.result['boundary_id']})
    self.engine._audit('candidate_not_committed',{'boundary_id':d.result['boundary_id'],'resource':resource,'preimage_bytes_sha256':sha(old_bytes),'candidate_sha256':sha(candidate),'exists_after':resolved.exists()})
    return d.feedback
   resolved.parent.mkdir(parents=True,exist_ok=True);resolved.write_text(candidate,encoding='utf-8');self.actual_submissions+=1
   self.engine.committed(d,resource,old_bytes,resolved.read_bytes(),original)
   result=f'Successfully wrote to {args.get("path",args.get("file",""))}'
   dispatcher._record(name,args,result);return result
 def publication(self,text):
  d=self.engine.decide('publication',text,resource='final_response',origin='actor_candidate')
  d.consume();self.engine._audit('publication_boundary',{'boundary_id':d.result['boundary_id'],'released':not d.denied,'candidate_sha256':sha(text)})
  return d
