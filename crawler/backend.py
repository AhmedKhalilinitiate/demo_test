from __future__ import annotations
import os, requests

class SupabaseStore:
    def __init__(self,url=None,key=None):
        self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/")
        self.key=key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self.headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json","Prefer":"return=representation"}
    def _endpoint(self,table): return f"{self.url}/rest/v1/{table}"
    def trackers(self):
        r=requests.get(self._endpoint("trackers"),headers=self.headers,params={"active":"eq.true","select":"*"},timeout=30); r.raise_for_status(); return r.json()
    def observations(self,tracker_id,limit=30):
        r=requests.get(self._endpoint("observations"),headers=self.headers,params={"tracker_id":f"eq.{tracker_id}","select":"*","order":"checked_at.desc","limit":str(limit)},timeout=30); r.raise_for_status(); return r.json()
    def insert_observation(self,row):
        r=requests.post(self._endpoint("observations"),headers=self.headers,json=row,timeout=30); r.raise_for_status(); data=r.json(); return data[0] if data else row
    def mark_checked(self,tracker_id,status,error=None):
        r=requests.patch(self._endpoint("trackers"),headers=self.headers,params={"id":f"eq.{tracker_id}"},json={"last_status":status,"last_error":error},timeout=30); r.raise_for_status()
