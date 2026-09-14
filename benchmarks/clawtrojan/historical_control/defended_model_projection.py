import copy,json,hashlib
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def project(role,body):
    assert role in {'actor','judge','defense'}
    assert body['model'] in {'glm-5','deepseek-v4-pro'} and body['temperature']==0
    assert body['max_tokens'] in ({4096,8192} if role=='actor' else {8192})
    if role=='actor':assert 'thinking' not in body
    else:
        assert body['thinking']=={'type':'disabled'}
        assert body['response_format']=={'type':'json_object'}
    wire=copy.deepcopy(body);wire['model']='deepseek-v4-pro';wire['max_tokens']=8192
    added_json_instruction=False
    if role=='defense' and not any('json' in str(m.get('content','')).lower() for m in wire['messages'] if m.get('role') in {'system','user'}):
        assert wire['messages'][0]['role']=='system' and isinstance(wire['messages'][0]['content'],str)
        wire['messages'][0]['content']+='\nReturn JSON.'
        added_json_instruction=True
    changed=[k for k in sorted(set(body)|set(wire)) if body.get(k)!=wire.get(k)]
    assert set(changed)<=({'model','max_tokens','messages'} if added_json_instruction else {'model','max_tokens'})
    proof={'role':role,'registered_changed_fields':changed,'source_request_sha256':hashlib.sha256(canonical(body).encode()).hexdigest(),'wire_request_sha256':hashlib.sha256(canonical(wire).encode()).hexdigest(),'all_other_fields_byte_equivalent_under_canonical_JSON':True,'json_format_instruction_added':added_json_instruction,'format_only_suffix':'\nReturn JSON.' if added_json_instruction else None}
    return wire,proof
