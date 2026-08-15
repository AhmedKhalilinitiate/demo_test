from __future__ import annotations
import os, statistics, smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from crawler.adapters import fetch_quote
from crawler.backend import SupabaseStore
from crawler.discovery import discover

def baseline(prices):
    vals=[float(x) for x in prices if x is not None]
    return float(statistics.median(vals[-30:])) if vals else 0.0

def deal_status(current,base,threshold_pct,target_price=None):
    pct=((base-current)/base*100) if base else 0.0
    return (bool(base and current <= base*(1-float(threshold_pct)/100)) or
            bool(target_price is not None and current <= float(target_price))), round(pct,2)

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
    for t in store.trackers():
        tid=t["id"]
        try:
            urls=t.get("urls") or ([t["url"]] if t.get("url") else [])
            if not urls:
                rows=discoverer(t["name"],country="sa",limit=10)
                supported=[x.get("url") for x in rows if x.get("supported") and x.get("url")]
                fallback=[x.get("url") for x in rows if x.get("url")]
                urls=(supported or fallback)[:5]
                store.update_sources(tid,urls)
                if not urls:
                    store.mark_checked(tid,"needs_url","Serper discovery returned no product URLs"); continue
            previous=store.observations(tid,30)
            prior=[float(x["delivered_price"]) for x in reversed(previous) if x.get("delivered_price") is not None]
            quotes=[]
            for url in urls:
                try: quotes.append(quote_fetcher(url))
                except Exception: continue
            if not quotes: raise RuntimeError("Discovered/configured sources returned no valid price")
            quote=min(quotes,key=lambda q:q.delivered_price)
            base=baseline(prior) or quote.delivered_price
            is_deal,discount=deal_status(quote.delivered_price,base,t.get("threshold_pct",15),t.get("target_price"))
            row={"tracker_id":tid,"retailer":quote.retailer,"title":quote.title,"url":quote.url,
                 "price":quote.price,"shipping":quote.shipping,"delivered_price":quote.delivered_price,
                 "currency":quote.currency or t.get("currency","SAR"),"in_stock":quote.in_stock,
                 "baseline":base,"discount_pct":discount,"is_deal":is_deal,
                 "checked_at":datetime.now(timezone.utc).isoformat(),"source":quote.source}
            store.insert_observation(row); store.mark_checked(tid,"ok",None); checked+=1
            if is_deal: alerts.append(row)
        except Exception as e:
            store.mark_checked(tid,"error",str(e)[:500])
    if alerts:
        body="\n".join(f"{a['title']} — {a['currency']} {a['delivered_price']:.2f} vs {a['baseline']:.2f} ({a['discount_pct']}%)\n{a['url']}" for a in alerts)
        send_email(f"Price Intelligence: {len(alerts)} deal(s)",body)
    print(f"checked={checked} alerts={len(alerts)}")
    return {"checked":checked,"alerts":len(alerts)}
if __name__=="__main__": run()
