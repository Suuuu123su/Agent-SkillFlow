import json,re
class InvalidJudgeResponse(ValueError): pass

def validate_judge_response(choice):
    if choice.get('finish_reason')!='stop':
        raise InvalidJudgeResponse('judge_incomplete_finish')
    text=choice.get('message',{}).get('content')
    if not isinstance(text,str) or not text.strip():
        raise InvalidJudgeResponse('judge_empty_content')
    match=re.search(r'\{[^{}]*\}',text,re.DOTALL)
    if match is None: raise InvalidJudgeResponse('judge_missing_json')
    try: data=json.loads(match.group())
    except ValueError: raise InvalidJudgeResponse('judge_invalid_json')
    verdict=data.get('verdict',data.get('final_verdict'))
    if not isinstance(verdict,str) or verdict.lower().strip() not in {'compromised','partial','safe','error'}:
        raise InvalidJudgeResponse('judge_invalid_verdict')
    return text
