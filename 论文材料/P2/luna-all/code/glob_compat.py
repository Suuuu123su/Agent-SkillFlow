"""Return an ordinary tool error for invalid glob syntax; retain native valid semantics."""
def install(dispatcher):
    native=dispatcher._do_glob
    def guarded(self,tool_name,tool_input,pattern):
        try:
            return native(self,tool_name,tool_input,pattern)
        except ValueError as error:
            result='Error: invalid glob pattern: '+str(error)
            self._record(tool_name,tool_input,result,
                         metadata={'runtime_compatibility':'invalid_glob_returns_tool_error'})
            return result
    dispatcher._do_glob=guarded
