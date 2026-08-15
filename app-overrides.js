// Runtime UX hardening layered over app.js.

window.lastInstantTriggerError='';
triggerInstantCrawl = async function triggerInstantCrawlWithRetry(trackerId){
  const url=`${cfg.supabaseUrl.replace(/\/$/,'')}/functions/v1/trigger-price-check`;
  let lastErr;
  window.lastInstantTriggerError='';
  for(let attempt=1;attempt<=3;attempt++){
    try{
      const r=await fetch(url,{method:'POST',headers:headers(),body:JSON.stringify({tracker_id:trackerId})});
      const text=await r.text();
      if(r.ok){window.lastInstantTriggerError='';try{return JSON.parse(text)}catch{return {ok:true}}}
      let detail=text;
      try{const j=JSON.parse(text);detail=j.detail||j.error||text}catch{}
      const hint=r.status===404?'Edge Function is not deployed.'
        :r.status===401||r.status===403?'Edge Function authentication/JWT configuration rejected the request.'
        :r.status===500?'Edge Function is deployed but a required server secret may be missing.'
        :r.status===502?'GitHub workflow dispatch was rejected; check the GitHub token and Actions permission.'
        :`HTTP ${r.status}`;
      lastErr=new Error(`${hint} ${String(detail||'').slice(0,220)}`.trim());
      if(![429,500,502,503,504].includes(r.status))break;
    }catch(e){lastErr=e}
    if(attempt<3)await new Promise(res=>setTimeout(res,attempt*900));
  }
  window.lastInstantTriggerError=String(lastErr?.message||lastErr||'Instant crawl trigger failed.');
  throw lastErr||new Error('Instant crawl trigger failed.');
};

// Replace the offer renderer so cheaper variant-ambiguous results are visible
// as leads without being confused with the verified price used for history/alerts.
offerTable = function offerTableWithConfidence(offers,cur){
  const rows=offers?.length?offers:(cur?[cur]:[]);
  if(!rows.length)return'<div class="offer-empty">No market offers captured yet.</div>';
  const sorted=[...rows].sort((a,b)=>Number(a.delivered_price??a.price)-Number(b.delivered_price??b.price));
  const firstSafe=sorted.findIndex(o=>o.source!=='serper-shopping-possible');
  return`<div class="offers"><div class="offers-title">Market offers · verified + possible matches</div>${sorted.slice(0,16).map((o,i)=>{
    const direct=isDirectUrl(o.url),possible=o.source==='serper-shopping-possible';
    const tag=possible?'<span class="confidence-tag possible">POSSIBLE MATCH</span>'
      :(i===firstSafe?'<span class="confidence-tag tracked">BEST TRACKED</span>':'');
    return`<div class="offer-row ${possible?'offer-possible':''}"><div><strong>${esc(o.retailer||'Unknown seller')}</strong><span>${esc(o.title||'')}</span>${tag}</div><div class="offer-price">${money(o.delivered_price??o.price)}</div><div>${direct?`<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">Open seller ↗</a>`:'<span class="offer-source-note">Price source only</span>'}</div></div>`
  }).join('')}</div>`;
};

// The original addTracker intentionally keeps scheduled tracking alive when the
// instant dispatch fails; add the concrete server-side cause to that message.
const _oldSetMsg=setMsg;
setMsg=function(t,e=false){
  if(e&&t==='Tracker saved, but the instant crawl trigger failed. Scheduled tracking will still continue.'){
    const detail=window.lastInstantTriggerError;
    t+=detail?` ${detail}`:' Check the trigger-price-check Edge Function deployment and its GITHUB_WORKFLOW_TOKEN secret.';
  }
  _oldSetMsg(t,e);
};

render();
