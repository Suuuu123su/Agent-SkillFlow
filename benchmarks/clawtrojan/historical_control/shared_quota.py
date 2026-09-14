"""Atomic cross-process request reservation. Contains no credentials or payloads."""
import sqlite3,time
from pathlib import Path
DB=Path(__file__).resolve().parent.parent/'ClawTrojan-dspro-shared-control'/'quota.sqlite3'
class SharedQuota:
 def __init__(self,path=DB):self.path=path
 def connect(self):return sqlite3.connect(self.path,timeout=30,isolation_level=None)
 def state(self):
  with self.connect() as c:
   row=c.execute('SELECT total,cap,stop_reason FROM quota WHERE id=1').fetchone();return {'total':row[0],'cap':row[1],'stop_reason':row[2]}
 def reserve(self,lane,unit,role):
  c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE');total,cap,stop=c.execute('SELECT total,cap,stop_reason FROM quota WHERE id=1').fetchone()
   if stop:raise RuntimeError('shared_provider_stopped:'+stop)
   if total>=cap:raise RuntimeError('shared_campaign_attempt_cap')
   idx=total+1;c.execute('UPDATE quota SET total=? WHERE id=1',(idx,));c.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(idx,lane,unit,role,time.time()));c.commit();return idx
  except BaseException:c.rollback();raise
  finally:c.close()
 def stop(self,reason):
  with self.connect() as c:c.execute('UPDATE quota SET stop_reason=COALESCE(stop_reason,?) WHERE id=1',(reason,))
