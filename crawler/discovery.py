from __future__ import annotations
import os, re, requests
from urllib.parse import urlparse

SAUDI_DOMAINS=("amazon.sa","noon.com","jarir.com","extra.com","namshi.com")
HEADERS=lambda key:{"X-API-KEY":key,"Content-Type":"application/json"}

def _is_google(url):
    host=urlparse(url or "").netloc.lower()
    return host=="google.com" or host=="www.google.com" or host.endswith(".google.com")

def _source_domain(source):
    s=(source or "").strip().lower()
    aliases={"amazon.sa":"amazon.sa","amazon sa":"amazon.sa","noon":"noon.com","jarir":"jarir.com","extra":"extra.com","extra stores":"extra.com","namshi":"namshi.com"}
    if s in aliases:return aliases[s]
    m=re.search(r"(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})",s)
    return m.group(1) if m else None

def _shopping(key,q,country,limit):
    r=requests.post("https://google.serper.dev/shopping",headers=HEADERS(key),json={"q":q,"gl":country,"num":limit},timeout=30)
    r.raise_for_status(); return r.json().get("shopping",[])

def _resolve_direct(key,row,country):
    link=row.get("link") or ""
    if link and not _is_google(link): return link
    domain=_source_domain(row.get("source"))
    title=(row.get("title") or "").strip()
    if not domain or not title:return link
    try:
        r=requests.post("https://google.serper.dev/search",headers=HEADERS(key),json={"q":f'site:{domain} "{title[:120]}"',"gl":country,"num":3},timeout=20)
        r.raise_for_status()
        for item in r.json().get("organic",[]):
            u=item.get("link") or ""; host=urlparse(u).netloc.lower()
            if host==domain or host.endswith("."+domain): return u
    except Exception:
        pass
    return link

def discover(query,country="sa",limit=10):
    key=os.getenv("SERPER_API_KEY")
    if not key: raise RuntimeError("SERPER_API_KEY is required for discovery mode")
    raw=_shopping(key,f"{query} Saudi Arabia buy price",country,limit)
    if not raw:
        raw=_shopping(key,f"{query} Saudi Arabia",country,limit)
    rows=[]
    for i,x in enumerate(raw):
        original=x.get("link") or ""
        link=_resolve_direct(key,x,country) if i<6 else original
        host=urlparse(link).netloc.lower()
        rows.append({"title":x.get("title"),"price":x.get("price"),"source":x.get("source"),"url":link,
                     "shopping_url":original,"supported":any(d in host for d in SAUDI_DOMAINS),
                     "direct":bool(link and not _is_google(link))})
    return rows
