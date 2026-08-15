from __future__ import annotations
import os, statistics, smtplib, re
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlparse
from crawler.adapters import fetch_quote, ProductQuote
from crawler.backend import SupabaseStore
from crawler.discovery import discover

def baseline(prices):
    vals=[float(x) for x in prices if x is not None]
    return float(statistics.median(vals[-30:])) if vals else 0.0

def deal_status(current,base,threshold_pct,target_price=None):
    pct=((base-current)/base*100) if base else 0.0
    return (bool(base and current <= base*(1-float(threshold_pct)/100)) or
            bool(target_price is not None and current <= float(target_price))), round(pct,2)

def _price_number(value):
    if value is None: return None
    if isinstance(value,(int,float)): return float(value)
    text=str(value).replace(",","")
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)",text)
    return float(m.group(1)) if m else None

def _is_direct_merchant_url(url):
    host=urlparse(url or "").netloc.lower()
    return bool(host) and not (host=="google.com" or host.endswith(".google.com") or host=="www.google.com")

def _serper_quotes(rows):
    quotes=[]
    for x in rows:
        price=_price_number(x.get("price"))
        if not price: continue
        source=(x.get("source") or "Google Shopping").strip()
        quotes.append(ProductQuote(retailer=source,title=x.get("title") or source,price=price,currency="SAR",in_stock=True,url=x.get("url") or "",source="serper-shopping"))
    return quotes

def _offer_rows(tracker_id,quotes,checked_at):
    seen=set(); out=[]
    for q in sorted(quotes,key=lambda x:x.delivered_price):
        key=(q.retailer,q.url,round(float(q.delivered_price),2))
        if key in seen: continue
        seen.add(key)
        out.append({"tracker_id":tracker_id,"retailer":q.retailer,"title":q.title,"url":q.url,"price":q.price,"shipping":q.shipping,"delivered_price":q.delivered_price,"currency":q.currency or "SAR","in_stock":q.in_stock,"source":q.source,"checked_at":checked_at})
    return out[:20]

def send_email(subject,body):
    host=os.getenv("SMTP_HOST"); user=os.getenv("SMTP_USER"); password=os.getenv("SMTP_PASSWORD")
    recipient=os.getenv("ALERT_EMAIL_TO"); sender=os.getenv("ALERT_EMAIL_FROM",user)
    if not all([host,user,password,recipient,sender]): return False
    msg=EmailMessage(); msg["Subject"]=subject; msg["From"]=sender; msg["To"]=recipient; msg.set_content(body)
    with smtplib.SMTP_SSL(host,int(os.getenv("SMTP_PORT","465"))) as smtp:
        smtp.login(user,password); smtp.send_message(msg)
    return True

def run(store=None,quote_fetcher=fetch_quote,discoverer=discover):
    store=store or SupabaseStore(); alerts=[]; checked=0
    tracker_filter=os.getenv("TRACKER_ID") or None
    trackers=store.trackers(tracker_filter)
    try: project_host=urlparse(store.url).netloc
    except Exception: project_host="unknown"
    print(f"supabase_host={project_host} trackers_loaded={len(trackers)} targeted={bool(tracker_filter)}")
    if trackers: print("tracker_names=" + " | ".join(str(t.get("name",""))[:80] for t in trackers))
    for t in trackers:
        tid=t["id"]
        try:
            urls=t.get("urls") or ([t["url"]] if t.get("url") else [])
            discovery_rows=[]; discovery_quotes=[]
            if not urls:
                discovery_rows=discoverer(t["name"],country="sa",limit=10)
                direct=[x.get("url") for x in discovery_rows if x.get("url") and _is_direct_merchant_url(x.get("url"))]
                supported=[x.get("url") for x in discovery_rows if x.get("supported") and x.get("url") and _is_direct_merchant_url(x.get("url"))]
                urls=(supported or direct)[:5]
                discovery_quotes=_serper_quotes(discovery_rows)
                print(f"tracker={t.get('name','')} discovery_results={len(discovery_rows)} direct_urls={len(urls)} serper_quotes={len(discovery_quotes)}")
                if urls: store.update_sources(tid,urls)
                if not urls and not discovery_quotes:
                    store.mark_checked(tid,"needs_url","Serper discovery returned no usable product URLs or prices"); continue
            previous=store.observations(tid,30)
            prior=[float(x["delivered_price"]) for x in reversed(previous) if x.get("delivered_price") is not None]
            quotes=list(discovery_quotes); quote_errors=[]
            for url in urls:
                try: quotes.append(quote_fetcher(url))
                except Exception as exc: quote_errors.append(str(exc)[:160])
            if not quotes:
                detail="; ".join(quote_errors[:3]); raise RuntimeError("Discovered/configured sources returned no valid price" + (f": {detail}" if detail else ""))
            now=datetime.now(timezone.utc).isoformat()
            try:
                saved=store.replace_offers(tid,_offer_rows(tid,quotes,now))
                if not saved: print("offers_table=missing; apply supabase/offers_migration.sql")
            except Exception as exc:
                print(f"offers_store_warning={str(exc)[:180]}")
            quote=min(quotes,key=lambda q:q.delivered_price)
            base=baseline(prior) or quote.delivered_price
            is_deal,discount=deal_status(quote.delivered_price,base,t.get("threshold_pct",15),t.get("target_price"))
            row={"tracker_id":tid,"retailer":quote.retailer,"title":quote.title,"url":quote.url,"price":quote.price,"shipping":quote.shipping,"delivered_price":quote.delivered_price,"currency":quote.currency or t.get("currency","SAR"),"in_stock":quote.in_stock,"baseline":base,"discount_pct":discount,"is_deal":is_deal,"checked_at":now,"source":quote.source}
            store.insert_observation(row); store.mark_checked(tid,"ok",None); checked+=1
            print(f"tracker={t.get('name','')} retailer={quote.retailer} price={quote.delivered_price} source={quote.source} offers={len(quotes)} status=ok")
            if is_deal: alerts.append(row)
        except Exception as e:
            print(f"tracker={t.get('name','')} status=error error={str(e)[:300]}")
            store.mark_checked(tid,"error",str(e)[:500])
    if alerts:
        body="\n".join(f"{a['title']} — {a['currency']} {a['delivered_price']:.2f} vs {a['baseline']:.2f} ({a['discount_pct']}%)\n{a['url']}" for a in alerts)
        send_email(f"Price Intelligence: {len(alerts)} deal(s)",body)
    print(f"checked={checked} alerts={len(alerts)}")
    return {"checked":checked,"alerts":len(alerts)}
if __name__=="__main__": run()
