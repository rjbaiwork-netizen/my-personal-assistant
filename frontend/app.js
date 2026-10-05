const $ = (id) => document.getElementById(id);
const api = (path, options={}) => fetch(path, {headers: {"Content-Type":"application/json", ...(options.headers||{})}, ...options});

let config = {};
let activeSeconds = 0;

function todayKey(){ return new Date().toISOString().slice(0,10); }
function loadUsage(){
  const raw = localStorage.getItem("mpa_usage");
  const data = raw ? JSON.parse(raw) : {};
  if(data.date !== todayKey()){ activeSeconds = 0; localStorage.setItem("mpa_usage", JSON.stringify({date:todayKey(), seconds:0})); }
  else activeSeconds = Number(data.seconds||0);
}
function saveUsage(){ localStorage.setItem("mpa_usage", JSON.stringify({date:todayKey(), seconds:activeSeconds})); }
function formatTime(s){ return new Date(s*1000).toISOString().slice(11,19); }
function updateUsage(){
  activeSeconds += 1; saveUsage();
  const pct = Math.min(100, activeSeconds/(8*3600)*100);
  $("usageTimer").textContent = formatTime(activeSeconds);
  $("usagePercent").textContent = Math.round(pct) + "%";
  $("usageBar").style.width = pct + "%";
}

async function health(){
  try{
    const r = await api("/api/health"); const d = await r.json();
    $("serverStatus").textContent = d.status; $("dashServer").textContent = "Online"; $("statusMessage").textContent = "API is responding normally.";
  }catch(e){
    $("serverStatus").textContent = "offline"; $("dashServer").textContent = "Offline"; $("statusMessage").textContent = "Could not reach the API.";
  }
}
async function loadSettings(){
  const r = await api("/api/settings"); config = await r.json();
  $("brandName").textContent = config.platform_name || "My Personal Assistant";
  $("brandLogo").textContent = config.logo || "🤖";
  $("platformName").value = config.platform_name || "";
  $("logo").value = config.logo || "";
  $("geminiKey").value = config.gemini_api_key || "";
  $("geminiModel").value = config.gemini_model || "gemini-2.5-flash";
  $("defaultMode").value = config.default_storage_mode || "append";
  $("storageMode").value = config.default_storage_mode || "append";
  $("dashMode").textContent = (config.default_storage_mode || "append") === "append" ? "Append" : "New";
}
async function loadFiles(){
  const r = await api("/api/excel"); const d = await r.json();
  $("fileCount").textContent = d.files.length;
  $("excelList").innerHTML = d.files.length ? d.files.map(f =>
    `<div class="panel p-4 flex items-center justify-between gap-3"><div><div class="font-semibold">${escapeHtml(f.file_name)}</div><div class="text-xs text-slate-400">${Math.round(f.size_bytes/1024)} KB · ${new Date(f.modified).toLocaleString()}</div></div><a class="secondary" href="/api/download-excel/${encodeURIComponent(f.file_name)}">Download</a></div>`
  ).join("") : '<div class="panel p-5 text-slate-400">No Excel files yet.</div>';
}
async function loadLogs(){
  const r = await api("/api/logs?limit=200"); const d = await r.json();
  $("logList").innerHTML = d.records.length ? d.records.map(x =>
    `<div class="panel log-card p-4"><div class="meta">${escapeHtml(x.Date)} · ${escapeHtml(x.Time)} · ${escapeHtml(x["File Name"])} · ${escapeHtml(x.Platform)}</div><div class="font-medium">${escapeHtml(x["Prompt/Topic"])}</div><div class="text-sm text-slate-400 mt-1">${escapeHtml(x["Message Bubble"])}</div></div>`
  ).join("") : '<div class="panel p-5 text-slate-400">No records yet. Run your first scrape.</div>';
}
function escapeHtml(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}

document.querySelectorAll(".nav-btn").forEach(btn => btn.addEventListener("click", () => {
  document.querySelectorAll(".nav-btn").forEach(b=>b.classList.remove("active")); btn.classList.add("active");
  document.querySelectorAll(".tab").forEach(s=>s.classList.add("hidden")); $(btn.dataset.tab).classList.remove("hidden");
  if(btn.dataset.tab==="logs") loadLogs();
  if(btn.dataset.tab==="backup") loadFiles();
}));

$("openScraper").onclick=()=> $("scrapeModal").classList.remove("hidden");
$("closeScraper").onclick=()=> $("scrapeModal").classList.add("hidden");
$("scrapeModal").onclick=e=>{if(e.target===$("scrapeModal")) $("scrapeModal").classList.add("hidden")};
$("refreshLogs").onclick=loadLogs;

$("scrapeForm").onsubmit=async e=>{
  e.preventDefault();
  const r=await api("/api/scrape",{method:"POST",body:JSON.stringify({
    topic:$("topic").value,platform:$("platform").value,storage_mode:$("storageMode").value,file_name:$("fileName").value
  })});
  const d=await r.json();
  $("scrapeModal").classList.add("hidden"); $("scrapeResult").classList.remove("hidden");
  $("scrapeResult").textContent = r.ok ? `Saved ${d.rows_added} records to ${d.file_name} (total ${d.total_rows}).` : (d.detail||"Scrape failed.");
  await loadFiles(); await loadLogs();
};

$("settingsForm").onsubmit=async e=>{
  e.preventDefault();
  const r=await api("/api/settings",{method:"POST",body:JSON.stringify({
    platform_name:$("platformName").value,logo:$("logo").value,gemini_api_key:$("geminiKey").value,
    gemini_model:$("geminiModel").value,default_storage_mode:$("defaultMode").value
  })});
  const d=await r.json(); $("settingsMessage").textContent=r.ok?"Saved.":"Save failed: "+(d.detail||"unknown error");
  if(r.ok) await loadSettings();
};

function addBubble(text,type){
  const el=document.createElement("div"); el.className="bubble "+type;
  el.innerHTML=escapeHtml(text).replace(/\n/g,"<br>"); $("chatMessages").appendChild(el);
  $("chatMessages").scrollTop=$("chatMessages").scrollHeight;
}
$("chatForm").onsubmit=async e=>{
  e.preventDefault(); const input=$("chatInput"); const msg=input.value.trim(); if(!msg)return;
  addBubble(msg,"user"); input.value="";
  addBubble("Thinking…","ai");
  const last=$("chatMessages").lastElementChild;
  try{
    const r=await api("/api/chat",{method:"POST",body:JSON.stringify({message:msg,include_logs:true})});
    const d=await r.json(); last.remove(); addBubble(d.answer||"No response.","ai");
  }catch(err){last.remove();addBubble("Request failed.","ai")}
};

$("backupBtn").onclick=async()=>{
  $("backupBtn").disabled=true; $("backupBtn").textContent="Creating…";
  try{
    const r=await api("/api/backup",{method:"POST"}); const blob=await r.blob();
    const url=URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url; a.download="system_backup.zip"; a.click(); URL.revokeObjectURL(url);
  }finally{$("backupBtn").disabled=false;$("backupBtn").textContent="Create & Download ZIP Backup";}
};

loadUsage(); loadSettings(); health(); loadFiles(); loadLogs(); setInterval(updateUsage,1000); setInterval(health,30000);
