from __future__ import annotations
import os, requests
from urllib.parse import urlparse

SAUDI_DOMAINS=("amazon.sa","noon.com","jarir.com","extra.com","namshi.com")

def discover(query,country="sa",limit=10):
    key=os.getenv("SERPER_API_KEY")
    if not key:
        raise RuntimeError("SERPER_API_KEY is required for discovery mode")
    r=requests.post("https://google.serper.dev/shopping",
        headers={"X-API-KEY":key,"Content-Type":"application/json"},
        json={"q":f"{query} Saudi Arabia buy price","gl":country,"num":limit},timeout=30)
    r.raise_for_status(); rows=[]
    for x in r.json().get("shopping",[]):
        link=x.get("link") or ""; host=urlparse(link).netloc.lower()
        rows.append({"title":x.get("title"),"price":x.get("price"),"source":x.get("source"),"url":link,
                     "supported":any(d in host for d in SAUDI_DOMAINS)})
    return rows
