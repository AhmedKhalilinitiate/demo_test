from __future__ import annotations
import os, statistics, smtplib, re
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlparse
from crawler.adapters import fetch_quote, ProductQuote
from crawler.backend import SupabaseStore
from crawler.discovery import discover
from crawler.product_match import evaluate_match


def baseline(prices):
    vals=[float(x) for x in prices if x is not None and float(x)>0]
    return float(statistics.median(vals[-30:])) if vals else 0.0


def deal_status(current,base,threshold_pct,target_price=None):
    pct=((base-current)/base*100) if base else 0.0
    return (
        bool(base and current <= base*(1-float(threshold_pct)/100)) or
        bool(target_price is not None and current <= float(target_price)),
        round(pct,2),
    )


def _price_number(value):
    if value is None:return None
    if isinstance(value,(int,float)):
        return float(value) if float(value)>0 else None
    text=str(value).strip()
    text=text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬","0123456789.,"))
    m=re.search(r"\d[\d.,]*",text)
    if not m:return None
    text=m.group(0).rstrip(".,")
    if "," in text and "." in text:
        if text.rfind(",")>text.rfind("."):
            text=text.replace(".","").replace(",",".")
        else:
            text=text.replace(",","")
    elif "," in text:
        tail=text.split(",")[-1]
        text=text.replace(",",".") if len(tail)==2 else text.replace(",","")
    try:
        n=float(text)
        return n if n>0 else None
    except ValueError:
        return None


def _is_direct_merchant_url(url):
    host=urlparse(url or "").netloc.lower()
    return bool(host) and not (host=="google.com" or host=="www.google.com" or host.endswith(".google.com"))


def _serper_quotes(rows,query):
    quotes=[];rejected=[]
    for x in rows:
        price=_price_number(x.get("price"))
        if not price:continue
        source=(x.get("source") or "Google Shopping").strip()
        title=x.get("title") or source
        match=evaluate_match(query,title)
        if not match.accepted:
            rejected.append((title,match.reason))
            continue
        quotes.append(ProductQuote(
            retailer=source,title=title,price=price,currency="SAR",in_stock=True,
            url=x.get("url") or "",source="serper-shopping",
        ))
    return quotes,rejected


def _filter_fetched_quotes(query,quotes):
    accepted=[];rejected=[]
    for q in quotes:
        match=evaluate_match(query,q.title)
        if match.accepted:accepted.append(q)
        else:rejected.append((q.title,match.reason))
    return accepted,rejected


def _drop_price_outliers(quotes):
    """Protect the best-price decision from obvious accessory/parse outliers."""
    if len(quotes)<4:return quotes,0
    vals=[float(q.delivered_price) for q in quotes if q.delivered_price>0]
    if len(vals)<4:return quotes,0
    med=float(statistics.median(vals));lo,hi=med*0.30,med*3.5
    kept=[q for q in quotes if lo<=float(q.delivered_price)<=hi]
    if len(kept)<2:return quotes,0
    return kept,len(quotes)-len(kept)


def _offer_rows(tracker_id,quotes,checked_at):
    ordered=sorted(quotes,key=lambda x:x.delivered_price)
    seen=set();out=[]
    for q in ordered:
        direct=_is_direct_merchant_url(q.url)
        key=(q.retailer.lower().strip(),(q.title or "").lower().strip(),round(float(q.delivered_price),2))
        if key in seen:continue
        seen.add(key)
        out.append({
            "tracker_id":tracker_id,"retailer":q.retailer,"title":q.title,
            "url":q.url if direct else "","price":q.price,"shipping":q.shipping,
            "delivered_price":q.delivered_price,"currency":q.currency or "SAR",
            "in_stock":q.in_stock,"source":q.source,"checked_at":checked_at,
        })
    out.sort(key=lambda r:(0 if r["url"] else 1,float(r["delivered_price"])))
    return out[:20]


def _should_alert(is_deal,previous,current_price):
    if not is_deal:return False
    if not previous:return True
    prev=previous[0]
    if not bool(prev.get("is_deal")):return True
    try:
        prev_price=float(prev.get("delivered_price"))
        return current_price <= prev_price*0.98
    except Exception:
        return False


def send_email(subject,body):
    host=os.getenv("SMTP_HOST");user=os.getenv("SMTP_USER");password=os.getenv("SMTP_PASSWORD")
    recipient=os.getenv("ALERT_EMAIL_TO");sender=os.getenv("ALERT_EMAIL_FROM",user)
    if not all([host,user,password,recipient,sender]):return False
    msg=EmailMessage();msg["Subject"]=subject;msg["From"]=sender;msg["To"]=recipient;msg.set_content(body)
    with smtplib.SMTP_SSL(host,int(os.getenv("SMTP_PORT","465"))) as smtp:
        smtp.login(user,password);smtp.send_message(msg)
    return True


def _unique_direct_urls(urls):
    seen=set();out=[]
    for u in urls:
        if not u or not _is_direct_merchant_url(u):continue
        key=u.split("#",1)[0]
        if key in seen:continue
        seen.add(key);out.append(u)
    return out


def run(store=None,quote_fetcher=fetch_quote,discoverer=discover):
    store=store or SupabaseStore();alerts=[];checked=0
    tracker_filter=os.getenv("TRACKER_ID") or None
    trackers=store.trackers(tracker_filter)
    try:project_host=urlparse(store.url).netloc
    except Exception:project_host="unknown"
    print(f"supabase_host={project_host} trackers_loaded={len(trackers)} targeted={bool(tracker_filter)}")
    if trackers:print("tracker_names="+" | ".join(str(t.get("name","") or "")[:80] for t in trackers))

    for t in trackers:
        tid=t["id"];name=(t.get("name") or "").strip()
        try:
            known_urls=t.get("urls") or ([t["url"]] if t.get("url") else [])
            discovery_rows=[];discovery_quotes=[];rejected=[];discovery_error=None
            try:
                discovery_rows=discoverer(name,country="sa",limit=16)
                discovery_quotes,rejected=_serper_quotes(discovery_rows,name)
            except Exception as exc:
                discovery_error=str(exc)[:180]

            discovered_urls=[x.get("url") for x in discovery_rows if x.get("url") and _is_direct_merchant_url(x.get("url"))]
            supported_urls=[x.get("url") for x in discovery_rows if x.get("supported") and x.get("url") and _is_direct_merchant_url(x.get("url"))]
            urls=_unique_direct_urls(list(known_urls)+(supported_urls or discovered_urls))[:8]
            print(
                f"tracker={name} discovery_results={len(discovery_rows)} direct_urls={len(urls)} "
                f"relevant_serper={len(discovery_quotes)} rejected_serper={len(rejected)}"
                + (f" discovery_error={discovery_error}" if discovery_error else "")
            )

            if not urls and not discovery_quotes:
                detail=rejected[0][1] if rejected else (discovery_error or "no shopping results")
                store.mark_checked(tid,"no_match",f"No sufficiently relevant product offers found ({detail})")
                continue

            previous=store.observations(tid,30)
            prior=[float(x["delivered_price"]) for x in reversed(previous) if x.get("delivered_price") is not None]

            fetched=[];quote_errors=[]
            for url in urls:
                try:fetched.append(quote_fetcher(url))
                except Exception as exc:quote_errors.append(str(exc)[:160])
            fetched_ok,fetched_rejected=_filter_fetched_quotes(name,fetched)
            quotes=list(discovery_quotes)+fetched_ok
            rejected.extend(fetched_rejected)

            if not quotes:
                detail=(rejected[0][1] if rejected else "; ".join(quote_errors[:2])) or "no valid relevant price"
                store.mark_checked(tid,"no_match",f"Offers found but none safely matched this product: {detail}")
                print(f"tracker={name} status=no_match detail={detail[:180]}")
                continue

            quotes,outlier_count=_drop_price_outliers(quotes)
            now=datetime.now(timezone.utc).isoformat()
            try:
                saved=store.replace_offers(tid,_offer_rows(tid,quotes,now))
                if not saved:print("offers_table=missing; apply supabase/offers_migration.sql")
            except Exception as exc:
                print(f"offers_store_warning={str(exc)[:180]}")

            quote=min(quotes,key=lambda q:q.delivered_price)
            base=baseline(prior) or quote.delivered_price
            is_deal,discount=deal_status(quote.delivered_price,base,t.get("threshold_pct",15),t.get("target_price"))
            row={
                "tracker_id":tid,"retailer":quote.retailer,"title":quote.title,"url":quote.url,
                "price":quote.price,"shipping":quote.shipping,"delivered_price":quote.delivered_price,
                "currency":quote.currency or t.get("currency","SAR"),"in_stock":quote.in_stock,
                "baseline":base,"discount_pct":discount,"is_deal":is_deal,
                "checked_at":now,"source":quote.source,
            }
            store.insert_observation(row);store.mark_checked(tid,"ok",None);checked+=1
            print(
                f"tracker={name} retailer={quote.retailer} price={quote.delivered_price} "
                f"relevant_offers={len(quotes)} rejected={len(rejected)} outliers_removed={outlier_count} status=ok"
            )
            if _should_alert(is_deal,previous,quote.delivered_price):alerts.append(row)
        except Exception as e:
            print(f"tracker={name} status=error error={str(e)[:300]}")
            store.mark_checked(tid,"error",str(e)[:500])

    if alerts:
        body="\n".join(
            f"{a['title']} — {a['currency']} {a['delivered_price']:.2f} vs {a['baseline']:.2f} ({a['discount_pct']}%)\n{a['url']}"
            for a in alerts
        )
        send_email(f"Price Intelligence: {len(alerts)} new/stronger deal(s)",body)
    print(f"checked={checked} alerts={len(alerts)}")
    return {"checked":checked,"alerts":len(alerts)}


if __name__=="__main__":run()
