function toast(message,type="info",duration=3200){
  let host=$("toastHost");
  if(!host){host=document.createElement("div");host.id="toastHost";host.className="toast-host";document.body.appendChild(host);}
  const el=document.createElement("div");el.className="toast toast-"+type;el.textContent=message;host.appendChild(el);
  requestAnimationFrame(()=>el.classList.add("show"));
  setTimeout(()=>{el.classList.remove("show");setTimeout(()=>el.remove(),250)},duration);
}
function api(path,options={}){
  const notify=options.notify!==false, method=(options.method||"GET").toUpperCase();
  const fetchOptions={...options};delete fetchOptions.notify;
  if(notify&&method!=="GET")toast("Working…","loading",1500);
  return fetch(path,{...fetchOptions,headers:{"Content-Type":"application/json",...(fetchOptions.headers||{})}})
    .then(async r=>{
      if(!r.ok){let detail="Request failed.";try{detail=(await r.clone().json()).detail||detail}catch{}if(notify)toast(detail,"error");}
      else if(notify&&method!=="GET")toast("Operation completed.","success");
      return r;
    }).catch(err=>{if(notify)toast("Network error. Check the server.","error");throw err});
}
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c]));
function todayKey(){return new Date().toISOString().slice(0,10)}
function formatTime(s){return new Date(s*1000).toISOString().slice(11,19)}
let clientSeconds=0, serverSeconds=0;
function todayKey(){return new Date().toISOString().slice(0,10)}
function formatTime(s){return new Date(s*1000).toISOString().slice(11,19)}
function loadUsage(){try{const d=JSON.parse(localStorage.getItem("mpa_usage")||"{}");clientSeconds=d.date===todayKey()?Number(d.seconds||0):0}catch{clientSeconds=0}}
function saveUsage(){localStorage.setItem("mpa_usage",JSON.stringify({date:todayKey(),seconds:clientSeconds}))}
function updateClientUsage(){clientSeconds++;saveUsage()}
function renderServerUsage(d){serverSeconds=Number(d.server_runtime_seconds||0);const limit=Number(d.limit_seconds||28800),pct=Math.min(100,serverSeconds/limit*100);document.querySelectorAll("[data-usage-time]").forEach(e=>e.textContent=formatTime(serverSeconds));document.querySelectorAll("[data-usage-percent]").forEach(e=>e.textContent=Math.round(pct)+"%");document.querySelectorAll("[data-usage-bar]").forEach(e=>e.style.width=pct+"%");if($("serverUsageMeta"))$("serverUsageMeta").textContent="Server runtime: "+formatTime(serverSeconds)+" · "+d.percent+"% of 8-hour reference"}
async function loadServerUsage(){try{const r=await api("/api/usage",{notify:false});if(r.ok)renderServerUsage(await r.json())}catch{}}
async function loadSettings(){const r=await api("/api/settings",{notify:false});if(!r.ok)return;const c=await r.json();document.querySelectorAll("[data-brand-name]").forEach(e=>e.textContent=c.platform_name||"My Personal Assistant");document.querySelectorAll("[data-brand-logo]").forEach(e=>e.textContent=c.logo||"🤖");const favicon=document.querySelector("link[rel='icon']")||Object.assign(document.createElement("link"),{rel:"icon"});favicon.href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>"+encodeURIComponent(c.logo||"🤖")+"</text></svg>";if(!favicon.parentNode)document.head.appendChild(favicon);if($("platformName"))$("platformName").value=c.platform_name||"";if($("logo"))$("logo").value=c.logo||"";if($("geminiKey"))$("geminiKey").value="";if($("geminiModel"))$("geminiModel").value=c.gemini_model||"gemini-3.7-flash";if($("defaultMode"))$("defaultMode").value=c.default_storage_mode||"append";if($("dashMode"))$("dashMode").textContent=c.default_storage_mode==="new"?"New":"Append";if($("storageMode"))$("storageMode").value=c.default_storage_mode||"append"}
async function health(){try{const r=await api("/api/health",{notify:false});const d=await r.json();if($("serverStatus"))$("serverStatus").textContent=d.status;if($("dashServer"))$("dashServer").textContent="Online";if($("statusMessage"))$("statusMessage").textContent="API is responding normally."}catch{if($("serverStatus"))$("serverStatus").textContent="offline";if($("dashServer"))$("dashServer").textContent="Offline";if($("statusMessage"))$("statusMessage").textContent="Could not reach the API."}}
async function loadFiles(){const r=await api("/api/excel",{notify:false});if(!r.ok)return;const d=await r.json();if($("fileCount"))$("fileCount").textContent=d.files.length;if(!$("excelList"))return;$("excelList").innerHTML=d.files.length?d.files.map(f=>`<div class="panel p-4 flex flex-wrap items-center justify-between gap-3"><div><div class="font-semibold">${esc(f.file_name)}</div><div class="muted text-xs">${Math.max(1,Math.round(f.size_bytes/1024))} KB · ${new Date(f.modified).toLocaleString()}</div></div><a class="secondary inline-block" href="/api/download-excel/${encodeURIComponent(f.file_name)}">Download Excel</a></div>`).join(""):'<div class="panel p-5 muted">No Excel files yet.</div>'}
let logOffset=0, logSearchTimer=null;
const LOG_PAGE_SIZE=100;
async function loadLogs(reset=true){
  if(!$("logList"))return;
  if(reset)logOffset=0;
  const p=new URLSearchParams({q:($("logSearch")?.value||"").trim(),platform:$("logPlatform")?.value||"",date_from:$("logDateFrom")?.value||"",date_to:$("logDateTo")?.value||"",limit:String(LOG_PAGE_SIZE),offset:String(logOffset)});
  const r=await api("/api/logs/search?"+p.toString(),{notify:false});
  if(!r.ok)return;
  const d=await r.json();
  $("logList").innerHTML=d.records.length?d.records.map(x=>`<article class="bubble log-bubble"><div class="meta">${esc(x.Date)} · ${esc(x.Time)} · ${esc(x.Platform)}</div><div class="font-semibold">${esc(x["Prompt/Topic"])}</div><div class="muted text-sm mt-1">File: ${esc(x["File Name"])}</div><div class="text-sm mt-2">${esc(x["Message Bubble"])}</div></article>`).join(""):'<div class="panel p-6 muted">No matching records.</div>';
  const from=d.total?d.offset+1:0,to=Math.min(d.offset+d.limit,d.total);
  if($("logSummary"))$("logSummary").textContent=`Showing ${from}–${to} of ${d.total} records`;
  if($("logPrev"))$("logPrev").disabled=d.offset===0;
  if($("logNext"))$("logNext").disabled=d.offset+d.limit>=d.total;
}
function initLogFilters(){
  if(!$("logList"))return;
  const refresh=()=>{clearTimeout(logSearchTimer);logSearchTimer=setTimeout(()=>loadLogs(true),250)};
  ["logSearch","logPlatform","logDateFrom","logDateTo"].forEach(id=>$(id)?.addEventListener(id==="logSearch"?"input":"change",refresh));
  $("logPrev")?.addEventListener("click",()=>{logOffset=Math.max(0,logOffset-LOG_PAGE_SIZE);loadLogs(false)});
  $("logNext")?.addEventListener("click",()=>{logOffset+=LOG_PAGE_SIZE;loadLogs(false)});
  $("refreshLogs")?.addEventListener("click",()=>loadLogs(true));
  loadLogs(true);
}
function initScraper(){$("openScraper").onclick=()=>$("scrapeModal").classList.remove("hidden");$("closeScraper").onclick=()=>$("scrapeModal").classList.add("hidden");$("scrapeModal").onclick=e=>{if(e.target===$("scrapeModal"))$("scrapeModal").classList.add("hidden")};$("scrapeForm").onsubmit=async e=>{e.preventDefault();const btn=e.submitter;btn.disabled=true;try{const r=await api("/api/scrape",{method:"POST",body:JSON.stringify({topic:$("topic").value,platform:$("platform").value,storage_mode:$("storageMode").value,file_name:$("fileName").value})});const d=await r.json();$("scrapeModal").classList.add("hidden");$("scrapeResult").classList.remove("hidden");$("scrapeResult").textContent=r.ok?`Saved ${d.rows_added} record(s) to ${d.file_name}; total rows: ${d.total_rows}.`:(d.detail||"Scrape failed.");}finally{btn.disabled=false}}}
function initAdmin(){$("settingsForm").onsubmit=async e=>{e.preventDefault();const payload={platform_name:$("platformName").value,logo:$("logo").value,gemini_api_key:$("geminiKey").value,gemini_model:$("geminiModel").value,default_storage_mode:$("defaultMode").value};const r=await api("/api/settings",{method:"POST",body:JSON.stringify(payload)});const d=await r.json();$("settingsMessage").textContent=r.ok?"Saved successfully.":(d.detail||"Save failed.");if(r.ok){await loadSettings();$("settingsMessage").textContent="Saved successfully.";}}}
function bubble(text,type){const el=document.createElement("div");el.className="bubble "+type;el.innerHTML=esc(text).replace(/\n/g,"<br>");$("chatMessages").appendChild(el);$("chatMessages").scrollTop=$("chatMessages").scrollHeight;return el}
function initChat(){$("chatForm").onsubmit=async e=>{e.preventDefault();const input=$("chatInput"),msg=input.value.trim();if(!msg)return;input.value="";bubble(msg,"user");const pending=bubble("Thinking…","ai");try{const r=await api("/api/chat",{method:"POST",body:JSON.stringify({message:msg,include_logs:true})});const d=await r.json();pending.remove();bubble(r.ok?(d.answer||"No response."):(d.detail||"Chat request failed."),"ai")}catch{pending.remove();bubble("Request failed. Check the server.","ai")}}}
function initBackup(){$("backupBtn").onclick=async()=>{const btn=$("backupBtn");btn.disabled=true;btn.textContent="Creating…";try{const r=await api("/api/backup",{method:"POST"});if(!r.ok)throw new Error("Backup failed");const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="system_backup.zip";document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){alert(e.message)}finally{btn.disabled=false;btn.textContent="Create ZIP Backup"}}}
async function loadAutomation(){
  if(!$("automationScheduler"))return;
  try{
    const r=await api("/api/automation",{notify:false});if(!r.ok)return;
    const d=await r.json();
    $("automationScheduler").textContent=d.scheduler.enabled?"Running":"Disabled";
    $("automationTelegram").textContent=d.telegram.configured?"Configured":"Not configured";
    $("automationBackup").textContent=d.backup.latest?d.backup.latest:"No backup yet";
    $("automationJobs").textContent=(d.scheduler.jobs||[]).map(j=>j.id+" → "+(j.next_run||"not scheduled")).join(" · ")||"No scheduled jobs.";
  }catch{}
}
function navigation(){const items=[["index.html","📊","Dashboard"],["scraper.html","🔎","Scraper"],["logs.html","💬","Data Logs"],["chat.html","🧠","AI Chat"],["admin.html","⚙️","Admin Settings"],["backup.html","💾","Backups & Downloads"]];const current=location.pathname.split("/").pop()||"index.html";document.querySelectorAll("[data-navigation]").forEach(n=>n.innerHTML='<nav class="panel nav-panel">'+items.map(([href,icon,label])=>`<a class="nav-link ${current===href?"active":""}" href="/${href}"><span>${icon}</span><span>${label}</span></a>`).join("")+'</nav>')}
loadUsage();navigation();loadServerUsage();loadSettings();health();if($("fileCount")||$("excelList"))loadFiles();if($("logList"))initLogFilters()if($("openScraper"))initScraper();if($("settingsForm"))initAdmin();loadAutomation();if($("chatForm"))initChat();if($("backupBtn"))initBackup();if($("dashServer"))setInterval(health,30000);setInterval(updateClientUsage,1000);setInterval(loadServerUsage,30000);