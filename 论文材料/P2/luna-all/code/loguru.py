"""Local logging compatibility only; no model or business behavior."""
import logging
class Logger:
 def remove(self,*a,**k): pass
 def __getattr__(self,name):
  def log(message,*args,**kwargs):
   if name in ('error','exception','critical'): logging.getLogger('native').error(str(message))
  return log
logger=Logger()
