const cfg=window.PRICE_INTEL_CONFIG||{},$=id=>document.getElementById(id);
const configured=()=>cfg.supabaseUrl&&!cfg.supabaseUrl.includes('REPLACE_')&&cfg.supabaseAnonKey&&!cfg.supabaseAnonKey.includes('REPLACE_');
const headers=()=>({apikey:cfg.supabaseAnonKey,Authorization:`Bearer ${cfg.supabaseAnonKey}`,'Content-Type':'application/json'});
const api=(t,q='')=>`${cfg.supabaseUrl.replace(/\/$/,'')}/rest/v1/${t}${q}`;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
const money=n=>`SAR ${Number(n||0).toLocaleString(undefined,{maximumFractionDigits:2})}`;
const fmtTime=v=>v?new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
const pct=n=>`${Number(n||0).toFixed(1)}%`;
const normName=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim().replace(/\s+/g,' ');
const normUrl=s=>{try{const u=new URL(s);return `${u.hostname.replace(/^www\./,'')}${u.pathname}`.replace(/\/$/,'')}catch{return String(s||'').trim().toLowerCase()}};
const isDirectUrl=v=>{try{const h=new URL(v).hostname.toLowerCase();return !!h&&!(/^google\./.test(h)||h==='google.com'||h==='www.google.com'||h.endsWith('.google.com'))}catch{return false}};
const isStale=v=>v&&(Date.now()-new Date(v).getTime())>12*60*60*1000;

async function getTrackers(){const r=await fetch(api('trackers','?active=eq.true&select=*&order=created_at.desc'),{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}
async function getObs(){const r=await fetch(api('observations','?select=*&order=checked_at.desc&limit=1000'),{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}
async function getOffers(){const r=await fetch(api('offers','?select=*&order=delivered_price.asc&limit=1000'),{headers:headers()});if(r.status===404)return[];if(!r.ok){const text=await r.text();if(text.includes('offers'))return[];throw new Error(text)}return r.json()}
async function triggerInstantCrawl(trackerId){
  const url=`${cfg.supabaseUrl.replace(/\/$/,'')}/functions/v1/trigger-price-check`;
  let lastError;
  for(let attempt=1;attempt<=3;attempt++){
    try{
      const r=await fetch(url,{method:'POST',headers:headers(),body:JSON.stringify({tracker_id:trackerId})});
      const text=await r.text();
      if(r.ok){try{return JSON.parse(text)}catch{return{ok:true}}}
      let detail=text;try{const j=JSON.parse(text);detail=j.detail||j.error||text}catch{}
      const hint=r.status===404?'Edge Function is not deployed.'
        :[401,403].includes(r.status)?'Edge Function authentication rejected the request.'
        :r.status===500?'Edge Function server configuration failed (usually a missing secret).'
        :r.status===502?'GitHub rejected the workflow dispatch (usually token/Actions permission).'
        :`HTTP ${r.status}.`;
      lastError=new Error(`${hint} ${String(detail||'').slice(0,300)}`.trim());
      if(![429,500,502,503,504].includes(r.status))break;
    }catch(e){lastError=e}
    if(attempt<3)await new Promise(res=>setTimeout(res,attempt*1000));
  }
  throw lastError||new Error('Instant crawl trigger failed.');
}
function setMsg(t,e=false){$('formMsg').textContent=t;$('formMsg').className=`msg ${e?'error':'ok'}`}
function pollAfterCreate(){[6000,12000,22000,36000].forEach(ms=>setTimeout(render,ms))}

async function addTracker(){
  const btn=$('addTracker'),name=$('itemName').value.trim(),url=$('itemUrl').value.trim();
  if(!configured())return setMsg('Backend is not configured yet. Add Supabase URL + anon key in config.js.',true);
  if(name.length<3)return setMsg('Enter a more specific item name (at least 3 characters).',true);
  if(url){try{new URL(url)}catch{return setMsg('Enter a valid product URL, or leave it blank for automatic discovery.',true)}}
  const threshold=Number($('threshold').value||15),target=Number($('targetPrice').value)||null;
  if(!Number.isFinite(threshold)||threshold<1||threshold>90)return setMsg('Discount threshold must be between 1% and 90%.',true);
  if(target!==null&&(!Number.isFinite(target)||target<=0))return setMsg('Target price must be greater than zero.',true);
  btn.disabled=true;
  try{
    const existing=await getTrackers();
    const duplicate=existing.find(t=>normName(t.name)===normName(name)&&((!url&&!t.url)||(url&&t.url&&normUrl(t.url)===normUrl(url))));
    if(duplicate)return setMsg('This product is already being tracked. Remove the existing tracker first if you want to recreate it.',true);
    const payload={name,country:'SA',currency:'SAR',url:url||null,urls:url?[url]:[],threshold_pct:threshold,target_price:target,last_status:url?'queued':'discovery_queued',last_error:null};
    const r=await fetch(api('trackers'),{method:'POST',headers:{...headers(),Prefer:'return=representation'},body:JSON.stringify(payload)});
    if(!r.ok)return setMsg(`Could not create tracker: ${await r.text()}`,true);
    const created=await r.json(),tracker=created?.[0];
    $('itemName').value='';$('itemUrl').value='';$('targetPrice').value='';
    if(tracker?.id){
      try{await triggerInstantCrawl(tracker.id);setMsg('Tracker saved. First crawl queued automatically; this card will refresh as results arrive.');pollAfterCreate()}
      catch(e){setMsg(`Tracker saved, but the instant crawl trigger failed: ${e.message||e} Scheduled tracking will still continue.`,true)}
    }else setMsg('Tracker saved.');
    await render();
  }catch(e){setMsg(`Could not start tracking: ${e.message||e}`,true)}finally{btn.disabled=false}
}

async function removeTracker(id){if(!confirm('Remove this tracker and its history?'))return;const r=await fetch(api('trackers',`?id=eq.${encodeURIComponent(id)}`),{method:'DELETE',headers:headers()});if(!r.ok)return alert(await r.text());render()}

function sparkSvg(rows){if(!rows.length)return'<div class="muted">Waiting for first crawl</div>';const vals=rows.slice(-30).map(x=>Number(x.delivered_price));if(vals.length===1)return`<svg class="spark-svg" viewBox="0 0 300 92"><line class="spark-bg" x1="0" y1="78" x2="300" y2="78"/><circle class="spark-dot" cx="150" cy="46" r="4"/></svg>`;const min=Math.min(...vals),max=Math.max(...vals),span=Math.max(1,max-min),pts=vals.map((v,i)=>{const x=8+i*(284/(vals.length-1)),y=78-((v-min)/span)*62;return`${x.toFixed(1)},${y.toFixed(1)}`}).join(' '),last=pts.split(' ').at(-1).split(',');return`<svg class="spark-svg" viewBox="0 0 300 92"><line class="spark-bg" x1="0" y1="78" x2="300" y2="78"/><polyline class="spark-line" points="${pts}"/><circle class="spark-dot" cx="${last[0]}" cy="${last[1]}" r="4"/></svg>`}

function statusBadge(t,cur){
  if(t.last_status==='error')return'<span class="badge error">ERROR</span>';
  if(t.last_status==='no_match'||t.last_status==='needs_url')return'<span class="badge warn">CHECK MATCH</span>';
  if(!cur||['queued','discovery_queued','discovered'].includes(t.last_status))return'<span class="badge normal">QUEUED</span>';
  if(isStale(cur.checked_at))return'<span class="badge warn">STALE</span>';
  if(cur?.is_deal)return'<span class="badge deal">DEAL</span>';
  return'<span class="badge normal">WATCHING</span>';
}
function dealReason(t,cur){if(!cur)return'Waiting for market data';if(t.target_price&&Number(cur.delivered_price)<=Number(t.target_price))return`Target met: ${money(t.target_price)}`;if(Number(cur.discount_pct)>0)return`${pct(cur.discount_pct)} below baseline`;return'No baseline discount yet'}

function offerTable(offers,cur){
  const rows=offers?.length?offers:(cur?[cur]:[]);
  if(!rows.length)return'<div class="offer-empty">No sufficiently relevant retailer offers captured yet.</div>';
  const sorted=[...rows].sort((a,b)=>Number(a.delivered_price??a.price)-Number(b.delivered_price??b.price));
  return`<div class="offers"><div class="offers-title">Current relevant offers</div>${sorted.slice(0,12).map((o,i)=>{
    const direct=isDirectUrl(o.url);
    return`<div class="offer-row"><div><strong>${esc(o.retailer||'Unknown seller')}</strong><span>${esc(o.title||'')}</span></div><div class="offer-price">${money(o.delivered_price??o.price)}</div><div>${direct?`<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">Open seller ↗</a>`:'<span class="offer-source-note">Price source only</span>'}</div>${i===0?'<span class="best-offer">BEST</span>':''}</div>`
  }).join('')}</div>`;
}

function trackerCard(t,rows,offers){
  const cur=rows.at(-1),vals=rows.map(r=>Number(r.delivered_price)).filter(Number.isFinite),low=vals.length?Math.min(...vals):null,high=vals.length?Math.max(...vals):null,avg=vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null,delta=cur&&cur.baseline?((Number(cur.delivered_price)-Number(cur.baseline))/Number(cur.baseline))*100:0,deltaClass=delta<0?'good':delta>0?'bad':'flat',directOffers=(offers||[]).filter(o=>isDirectUrl(o.url)).length;
  return`<article class="card"><div class="cardtop"><div><h3>${esc(t.name)}</h3><p class="meta">${esc(cur?.retailer||'Pending first crawl')} · ${esc(t.last_status||'queued')}</p></div>${statusBadge(t,cur)}</div><div class="price-row"><div><div class="price">${cur?money(cur.delivered_price):'—'}</div><div class="delta ${deltaClass}">${cur?dealReason(t,cur):'No observation yet'}</div></div><div class="meta">${cur?`Last checked ${fmtTime(cur.checked_at)}`:'Awaiting automatic first check'}</div></div><div class="metrics"><div class="metric"><span>Baseline</span><strong>${cur?money(cur.baseline):'—'}</strong></div><div class="metric"><span>Target</span><strong>${t.target_price?money(t.target_price):'—'}</strong></div><div class="metric"><span>Observed low</span><strong>${low!=null?money(low):'—'}</strong></div><div class="metric"><span>Observed high</span><strong>${high!=null?money(high):'—'}</strong></div><div class="metric"><span>Average</span><strong>${avg!=null?money(avg):'—'}</strong></div><div class="metric"><span>Observations</span><strong>${rows.length}</strong></div><div class="metric"><span>Threshold</span><strong>${pct(t.threshold_pct)}</strong></div><div class="metric"><span>Seller pages</span><strong>${directOffers}/${offers?.length||0}</strong></div></div>${offerTable(offers,cur)}<div class="chart-wrap">${sparkSvg(rows)}</div><div class="card-actions"><span class="meta">Automatic first crawl + scheduled 3× / day</span><button class="remove" onclick="removeTracker('${t.id}')">Remove</button></div>${t.last_error&&t.last_status!=='ok'?`<p class="error small">${esc(t.last_error)}</p>`:''}</article>`
}

function renderSnapshot(trackers,obs,offers){const latest=trackers.map(t=>{const rs=obs.filter(o=>o.tracker_id===t.id).sort((a,b)=>new Date(a.checked_at)-new Date(b.checked_at));return rs.at(-1)}).filter(Boolean),prices=latest.map(x=>Number(x.delivered_price)).filter(Number.isFinite),retailers=new Set((offers||[]).map(x=>x.retailer).filter(Boolean)),healthy=trackers.filter(t=>t.last_status==='ok').length;$('portfolioSnapshot').innerHTML=`<div class="snapshot-item"><span>Tracked value</span><strong>${prices.length?money(prices.reduce((a,b)=>a+b,0)):'—'}</strong></div><div class="snapshot-item"><span>Retailers seen</span><strong>${retailers.size}</strong></div><div class="snapshot-item"><span>Healthy trackers</span><strong>${healthy}/${trackers.length}</strong></div>`}
function renderActivity(obs){const rows=[...obs].sort((a,b)=>new Date(b.checked_at)-new Date(a.checked_at)).slice(0,6);$('recentActivity').innerHTML=rows.length?rows.map(o=>`<div class="activity-row"><div><strong>${esc(o.title||o.retailer||'Observation')}</strong><br><span>${esc(o.retailer||'Unknown source')} · ${money(o.delivered_price)}</span></div><span>${fmtTime(o.checked_at)}</span></div>`).join(''):'<p class="muted">No crawl history yet.</p>'}

async function render(){
  if(!configured()){$('backendStatus').textContent='Needs Supabase config';$('backendDot').className='dot warn';$('trackerList').innerHTML='<p class="muted">Deploy the Supabase schema, then put the public project URL and anon key in <code>config.js</code>.</p>';return}
  $('backendStatus').textContent='Connected';$('backendDot').className='dot live';$('lastRefresh').textContent=`refreshed ${fmtTime(new Date())}`;
  try{
    const[trackers,obs,offers]=await Promise.all([getTrackers(),getObs(),getOffers()]),by={},offersBy={};
    for(const o of obs)(by[o.tracker_id]??=[]).push(o);for(const o of offers)(offersBy[o.tracker_id]??=[]).push(o);
    for(const id in by)by[id].sort((a,b)=>new Date(a.checked_at)-new Date(b.checked_at));
    for(const id in offersBy)offersBy[id].sort((a,b)=>Number(a.delivered_price)-Number(b.delivered_price));
    let deals=0,best=0;for(const t of trackers){const cur=(by[t.id]||[]).at(-1);if(cur?.is_deal)deals++;best=Math.max(best,Number(cur?.discount_pct||0))}
    $('trackerList').innerHTML=trackers.map(t=>trackerCard(t,by[t.id]||[],offersBy[t.id]||[])).join('')||'<p class="muted">No trackers yet.</p>';
    $('trackedCount').textContent=trackers.length;$('dealCount').textContent=deals;$('bestDiscount').textContent=`${best.toFixed(1)}%`;$('observationCount').textContent=obs.length;
    $('trackedDetail').textContent=`${trackers.filter(t=>t.last_status==='ok').length} healthy`;$('dealDetail').textContent=deals?`${deals} target/baseline trigger${deals===1?'':'s'}`:'No active deal triggers';$('bestSavingDetail').textContent='vs recent median baseline';$('observationDetail').textContent=obs.length?`latest ${fmtTime(obs[0]?.checked_at)}`:'3 checks / day';$('productSummary').textContent=`${trackers.length} product${trackers.length===1?'':'s'}`;
    renderSnapshot(trackers,obs,offers);renderActivity(obs);
  }catch(e){$('backendStatus').textContent='Backend error';$('backendDot').className='dot warn';$('trackerList').innerHTML=`<p class="error">${esc(e.message)}</p>`}
}

$('addTracker').addEventListener('click',addTracker);$('refresh').addEventListener('click',render);window.removeTracker=removeTracker;render();
