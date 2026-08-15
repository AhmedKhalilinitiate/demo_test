from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"

@dataclass
class ProductQuote:
    retailer: str
    title: str
    price: float
    currency: str
    in_stock: bool
    url: str
    shipping: float = 0.0
    source: str = "html"
    @property
    def delivered_price(self) -> float:
        return round(self.price + self.shipping, 2)

def _float(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace(",","").strip()
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)",s)
    return float(m.group(1)) if m else None

def _jsonld_product(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type":"application/ld+json"}):
        try: data=json.loads(tag.string or tag.get_text())
        except Exception: continue
        stack=data if isinstance(data,list) else [data]
        while stack:
            obj=stack.pop()
            if isinstance(obj,list): stack.extend(obj); continue
            if not isinstance(obj,dict): continue
            if obj.get("@type")=="Product" or "offers" in obj:
                offers=obj.get("offers") or {}
                if isinstance(offers,list): offers=offers[0] if offers else {}
                price=_float(offers.get("price") or offers.get("lowPrice"))
                if price:
                    availability=str(offers.get("availability","")).lower()
                    return {"title":obj.get("name") or "","price":price,
                            "currency":offers.get("priceCurrency") or "SAR",
                            "in_stock":("outofstock" not in availability) if availability else True}
            stack.extend(v for v in obj.values() if isinstance(v,(dict,list)))
    return None

def _selector_text(soup, selectors):
    for sel in selectors:
        el=soup.select_one(sel)
        if el:
            val=el.get("content") or el.get_text(" ",strip=True)
            if val: return val
    return None

def _recursive_price(obj):
    candidates=[]
    def walk(x):
        if isinstance(x,dict):
            lowered={str(k).lower():v for k,v in x.items()}
            for key in ("price","saleprice","specialprice","finalprice","currentprice"):
                if key in lowered:
                    val=_float(lowered[key])
                    if val and 5 <= val <= 1000000: candidates.append(val)
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(obj)
    return min(candidates) if candidates else None

class BaseAdapter:
    retailer="Generic"; domains=()
    price_selectors=("meta[property='product:price:amount']","meta[itemprop='price']",".price",".product-price")
    title_selectors=("h1","meta[property='og:title']")
    def matches(self,url):
        host=urlparse(url).netloc.lower()
        return any(d in host for d in self.domains)
    def parse(self,url,html):
        soup=BeautifulSoup(html,"html.parser")
        ld=_jsonld_product(soup)
        if ld:
            return ProductQuote(self.retailer,ld["title"] or _selector_text(soup,self.title_selectors) or self.retailer,
                                ld["price"],ld["currency"],ld["in_stock"],url,source="json-ld")
        price=_float(_selector_text(soup,self.price_selectors))
        if not price:
            for script_id in ("__NEXT_DATA__","__NUXT_DATA__"):
                el=soup.find("script",id=script_id)
                if el:
                    try: price=_recursive_price(json.loads(el.string or el.get_text()))
                    except Exception: pass
                if price: break
        if not price: raise ValueError(f"No price found for {url}")
        title=_selector_text(soup,self.title_selectors) or self.retailer
        return ProductQuote(self.retailer,title,price,"SAR",True,url,source="selector")

class AmazonSA(BaseAdapter):
    retailer="Amazon.sa"; domains=("amazon.sa",)
    price_selectors=("#corePrice_feature_div .a-offscreen",".a-price .a-offscreen","#priceblock_ourprice","#priceblock_dealprice","meta[itemprop='price']")
    title_selectors=("#productTitle","h1","meta[property='og:title']")
class Noon(BaseAdapter):
    retailer="Noon"; domains=("noon.com",)
    price_selectors=("[data-qa='product-price']",".priceNow",".price","meta[itemprop='price']")
class Jarir(BaseAdapter):
    retailer="Jarir"; domains=("jarir.com",)
    price_selectors=("[itemprop='price']",".price",".product-price",".price-box .price")
class Extra(BaseAdapter):
    retailer="eXtra"; domains=("extra.com",)
    price_selectors=("[itemprop='price']",".product-info-price .price",".price","meta[property='product:price:amount']")
class Namshi(BaseAdapter):
    retailer="Namshi"; domains=("namshi.com",)
    price_selectors=("[data-testid='price']",".price","meta[property='product:price:amount']")

ADAPTERS=[AmazonSA(),Noon(),Jarir(),Extra(),Namshi()]
GENERIC=BaseAdapter()
def adapter_for(url): return next((a for a in ADAPTERS if a.matches(url)),GENERIC)

def fetch_quote(url,timeout=25,session=None):
    sess=session or requests.Session()
    r=sess.get(url,headers={"User-Agent":UA,"Accept-Language":"en-SA,en;q=0.9,ar;q=0.8"},timeout=timeout)
    r.raise_for_status()
    return adapter_for(url).parse(url,r.text)
