def safe_http_error_fields(error):
    return {'restriction_category':{400:'invalid_request',401:'authentication_failed',402:'balance_required',403:'access_denied',429:'rate_or_account_restriction'}.get(error.code,'provider_http_error'),'error_body_recorded':False}
