from __future__ import annotations
import os, re, requests
from urllib.parse import urlparse
from crawler.product_match import evaluate_match

SAUDI_DOMAINS=("amazon.sa","noon.com","jarir.com","extra.com","namshi.com")
HEADERS=lambda key:{"X-API-KEY":key,"Content-Type":"application/json"}


def _is_google(url):
    host=urlparse(url or "").netloc.lower()
    return host=="google.com" or host=="www.google.com" or host.endswith(".google.com")


def _source_domain(source):
    s=(source or "").strip().lower()
    aliases={
        "amazon.sa":"amazon.sa","amazon sa":"amazon.sa","amazon":"amazon.sa",
        "noon":"noon.com","noon.com":"noon.com","jarir":"jarir.com","jarir bookstore":"jarir.com",
        "extra":"extra.com","extra stores":"extra.com","namshi":"namshi.com",
    }
    if s in aliases:return aliases[s]
    m=re.search(r"(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})",s)
    return m.group(1) if m else None


def _shopping(key,q,country,limit):
    r=requests.post("https://google.serper.dev/shopping",headers=HEADERS(key),json={"q":q,"gl":country,"num":limit},timeout=30)
    r.raise_for_status();return r.json().get("shopping",[])


def _organic(key,q,country,limit=5):
    r=requests.post("https://google.serper.dev/search",headers=HEADERS(key),json={"q":q,"gl":country,"num":limit},timeout=20)
    r.raise_for_status();return r.json().get("organic",[])


def _resolve_direct(key,row,query,country):
    """Return (url, verified) for a Shopping result.

    Direct merchant links are preserved. Google Shopping intermediary links are
    resolved through strict organic-title matching. If Serper's source does not
    expose a domain (common for smaller shops), a source-name search is used.
    """
    link=row.get("link") or ""
    if link and not _is_google(link):
        return link,False

    source=(row.get("source") or "").strip()
    domain=_source_domain(source);title=(row.get("title") or "").strip()
    searches=[]
    if domain:
        if query:searches.append(f'site:{domain} "{query[:120]}"')
        if title:searches.append(f'site:{domain} "{title[:120]}"')
        if query and title:searches.append(f"site:{domain} {query[:90]} {title[:90]}")
    else:
        if source and query:searches.append(f'"{source[:70]}" "{query[:120]}" Saudi Arabia')
        if source and title:searches.append(f'"{source[:70]}" "{title[:120]}"')

    best=None;best_score=-1.0
    for search_q in searches:
        try:
            for item in _organic(key,search_q,country,5):
                u=item.get("link") or "";host=urlparse(u).netloc.lower()
                if not u or _is_google(u):continue
                if domain and not (host==domain or host.endswith("."+domain)):continue
                candidate_title=item.get("title") or title
                result=evaluate_match(query,candidate_title) if query else None
                if result and result.accepted and result.score>best_score:
                    best=u;best_score=result.score
                if result and result.accepted and result.score>=80:return u,True
        except Exception:
            continue
    return (best,True) if best else (link,False)


def _row_key(x):
    return (
        str(x.get("source") or "").strip().lower(),
        str(x.get("title") or "").strip().lower(),
        str(x.get("price") or "").strip().lower(),
        str(x.get("link") or "").split("#",1)[0],
    )


def discover(query,country="sa",limit=10):
    key=os.getenv("SERPER_API_KEY")
    if not key:raise RuntimeError("SERPER_API_KEY is required for discovery mode")

    # Merge several Shopping searches instead of stopping at the first result set.
    # This intentionally broadens coverage so smaller/cheaper merchants are not
    # hidden simply because Amazon/large retailers dominate the first query.
    attempts=[
        f"{query} Saudi Arabia buy price",
        f'"{query}" Saudi Arabia',
        f"{query} KSA price",
    ]
    raw=[];seen=set()
    per_query=max(10,min(int(limit),18))
    for q in attempts:
        try:batch=_shopping(key,q,country,per_query)
        except Exception:continue
        for x in batch:
            k=_row_key(x)
            if k in seen:continue
            seen.add(k);raw.append(x)
        if len(raw)>=36:break

    rows=[]
    for i,x in enumerate(raw[:36]):
        original=x.get("link") or ""
        # Resolve more candidates than before, prioritising breadth while keeping
        # organic-resolution API use bounded.
        if i<12:link,verified=_resolve_direct(key,x,query,country)
        else:link,verified=original,False
        host=urlparse(link).netloc.lower()
        rows.append({
            "title":x.get("title"),"price":x.get("price"),"source":x.get("source"),"url":link,
            "shopping_url":original,"supported":any(d in host for d in SAUDI_DOMAINS),
            "direct":bool(link and not _is_google(link)),"verified_direct":verified,
        })
    return rows
