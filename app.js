const cfg=window.PRICE_INTEL_CONFIG||{},$=id=>document.getElementById(id);
const configured=()=>cfg.supabaseUrl&&!cfg.supabaseUrl.includes('REPLACE_')&&cfg.supabaseAnonKey&&!cfg.supabaseAnonKey.includes('REPLACE_');
const headers=()=>({apikey:cfg.supabaseAnonKey,Authorization:`Bearer ${cfg.supabaseAnonKey}`,'Content-Type':'application/json'});
const api=(t,q='')=>`${cfg.supabaseUrl.replace(/\/$/,'')}/rest/v1/${t}${q}`;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>`SAR ${Number(n||0).toLocaleString(undefined,{maximumFractionDigits:2})}`;
async function getTrackers(){const r=await fetch(api('trackers','?active=eq.true&select=*&order=created_at.desc'),{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}
async function getObs(){const r=await fetch(api('observations','?select=*&order=checked_at.desc&limit=1000'),{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}
function setMsg(t,e=false){$('formMsg').textContent=t;$('formMsg').className=`msg ${e?'error':'ok'}`}
async function addTracker(){
  const name=$('itemName').value.trim(),url=$('itemUrl').value.trim();
  if(!configured())return setMsg('Backend is not configured yet. Add Supabase URL + anon key in config.js.',true);
  if(!name)return setMsg('Item name is required.',true);
  if(url){try{new URL(url)}catch{return setMsg('Enter a valid product URL, or leave it blank for automatic discovery.',true)}}
  const payload={name,country:'SA',currency:'SAR',url:url||null,urls:url?[url]:[],threshold_pct:Number($('threshold').value||15),target_price:Number($('targetPrice').value)||null,last_status:url?'queued':'discovery_queued',last_error:null};
  const r=await fetch(api('trackers'),{method:'POST',headers:{...headers(),Prefer:'return=representation'},body:JSON.stringify(payload)});
  if(!r.ok)return setMsg(`Could not create tracker: ${await r.text()}`,true);
  $('itemName').value='';$('itemUrl').value='';$('targetPrice').value='';
  setMsg(url?'Tracker saved. It will be checked by the next scheduled crawl.':'Tracker saved in discovery mode. Serper will find Saudi listings on the next crawl.');
  await render()
}
async function removeTracker(id){if(!confirm('Remove this tracker and its history?'))return;const r=await fetch(api('trackers',`?id=eq.${encodeURIComponent(id)}`),{method:'DELETE',headers:headers()});if(!r.ok)return alert(await r.text());render()}
function spark(rows){if(!rows.length)return'<div class="empty-spark">waiting for first crawl</div>';const vals=rows.map(x=>Number(x.delivered_price)),max=Math.max(...vals),min=Math.min(...vals),span=Math.max(1,max-min);return`<div class="history">${vals.slice(-20).map(v=>`<span class="bar" style="height:${12+((v-min)/span)*46}px" title="${money(v)}"></span>`).join('')}</div>`}
async function render(){if(!configured()){$('backendStatus').textContent='Needs Supabase config';$('backendDot').className='dot warn';$('trackerList').innerHTML='<p class="muted">Deploy the Supabase schema, then put the public project URL and anon key in <code>config.js</code>.</p>';return}$('backendStatus').textContent='Connected';$('backendDot').className='dot live';try{const[trackers,obs]=await Promise.all([getTrackers(),getObs()]),by={};for(const o of obs)(by[o.tracker_id]??=[]).push(o);let deals=0,best=0;$('trackerList').innerHTML=trackers.map(t=>{const rows=(by[t.id]||[]).sort((a,b)=>new Date(a.checked_at)-new Date(b.checked_at)),cur=rows.at(-1);if(cur?.is_deal)deals++;best=Math.max(best,Number(cur?.discount_pct||0));const sourceLink=t.url?`<a href="${esc(t.url)}" target="_blank" rel="noopener">Open product</a>`:'<span class="meta">Discovery mode</span>';return`<article class="card"><div class="cardtop"><div><h3>${esc(t.name)}</h3><p class="meta">${esc(cur?.retailer||'Pending first crawl')} · ${esc(t.last_status||'queued')}</p></div><span class="badge ${cur?.is_deal?'deal':'normal'}">${cur?.is_deal?'DEAL':'WATCHING'}</span></div><div class="price">${cur?money(cur.delivered_price):'—'}</div><p class="meta">${cur?`Baseline ${money(cur.baseline)} · ${Number(cur.discount_pct||0).toFixed(1)}% below`:'No observation yet'}</p>${spark(rows)}<div class="card-actions">${sourceLink}<button class="remove" onclick="removeTracker('${t.id}')">Remove</button></div>${t.last_error?`<p class="error small">${esc(t.last_error)}</p>`:''}</article>`}).join('')||'<p class="muted">No trackers yet.</p>';$('trackedCount').textContent=trackers.length;$('dealCount').textContent=deals;$('bestDiscount').textContent=`${best.toFixed(0)}%`}catch(e){$('backendStatus').textContent='Backend error';$('backendDot').className='dot warn';$('trackerList').innerHTML=`<p class="error">${esc(e.message)}</p>`}}
$('addTracker').addEventListener('click',addTracker);$('refresh').addEventListener('click',render);window.removeTracker=removeTracker;render();
