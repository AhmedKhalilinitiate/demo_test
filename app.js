const KEY = 'price-intel-trackers-v1';
const $ = (id) => document.getElementById(id);
const load = () => JSON.parse(localStorage.getItem(KEY) || '[]');
const save = (items) => localStorage.setItem(KEY, JSON.stringify(items));
const median = (arr) => { const s=[...arr].sort((a,b)=>a-b); const m=Math.floor(s.length/2); return s.length%2?s[m]:(s[m-1]+s[m])/2; };
const fmt = (n,c) => `${c} ${Number(n).toLocaleString(undefined,{maximumFractionDigits:0})}`;
function sampleHistory(target){
  const base = target || 650;
  return Array.from({length:10},(_,i)=>Math.round(base*(0.9+Math.random()*0.25)-(i===9?base*0.14:0)));
}
function addTracker(){
  const name=$('itemName').value.trim();
  if(!name){ alert('Enter an item name first.'); return; }
  const target=Number($('targetPrice').value||0);
  const history=sampleHistory(target||650);
  const tracker={id:crypto.randomUUID(),name,url:$('itemUrl').value.trim(),country:$('country').value,currency:$('currency').value,threshold:Number($('threshold').value||15),targetPrice:target||null,history,createdAt:new Date().toISOString()};
  save([tracker,...load()]);
  $('itemName').value=''; $('itemUrl').value=''; $('targetPrice').value='';
  render();
}
function loadDemo(){
  save([
    {id:crypto.randomUUID(),name:'Nike Air Max 90',url:'https://example.com/nike-air-max-90',country:'SA',currency:'SAR',threshold:15,targetPrice:500,history:[699,679,649,655,629,610,590,570,540,479],createdAt:new Date().toISOString()},
    {id:crypto.randomUUID(),name:'Sony WH-1000XM6',url:'https://example.com/sony-wh-1000xm6',country:'SA',currency:'SAR',threshold:12,targetPrice:1250,history:[1599,1520,1499,1480,1465,1450,1399,1329,1288,1249],createdAt:new Date().toISOString()},
    {id:crypto.randomUUID(),name:'MacBook Air M3 13 inch',url:'',country:'SA',currency:'SAR',threshold:10,targetPrice:null,history:[4299,4299,4199,4150,4100,4099,4050,3999,3979,3999],createdAt:new Date().toISOString()}
  ]); render();
}
function removeTracker(id){ save(load().filter(x=>x.id!==id)); render(); }
function render(){
  const items=load();
  $('trackedCount').textContent=items.length;
  let deals=0,best=0;
  $('trackerList').innerHTML=items.map(t=>{
    const current=t.history.at(-1); const base=median(t.history.slice(0,-1));
    const discount=Math.max(0,((base-current)/base)*100); const isDeal=discount>=t.threshold || (t.targetPrice && current<=t.targetPrice);
    if(isDeal) deals++; best=Math.max(best,discount);
    const max=Math.max(...t.history);
    return `<article class="card"><h3>${t.name}</h3><div class="meta">Deliver to ${t.country} ${t.url?`• <a href="${t.url}" target="_blank">source</a>`:'• discovery mode'}</div><div class="price">${fmt(current,t.currency)}</div><div class="meta">Baseline: ${fmt(base,t.currency)} • Discount: ${discount.toFixed(1)}%</div><span class="badge ${isDeal?'deal':'normal'}">${isDeal?'DEAL ALERT':'NORMAL PRICE'}</span><div class="history">${t.history.map(v=>`<span class="bar" style="height:${Math.max(10,(v/max)*58)}px"></span>`).join('')}</div><button class="remove" onclick="removeTracker('${t.id}')">Remove</button></article>`;
  }).join('') || '<p class="meta">No trackers yet. Add one or load demo data.</p>';
  $('dealCount').textContent=deals;
  $('avgDiscount').textContent=`${best.toFixed(0)}%`;
}
$('addTracker').addEventListener('click',addTracker);
$('demoData').addEventListener('click',loadDemo);
render();
