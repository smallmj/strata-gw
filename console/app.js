(function(){
"use strict";
var root=document.documentElement;
var saved=null;try{saved=localStorage.getItem("stratagw.theme")}catch(e){}
var theme=saved||(window.matchMedia&&matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");
function applyTheme(t){root.dataset.theme=t;try{localStorage.setItem("stratagw.theme",t)}catch(e){}}
applyTheme(theme);
document.getElementById("theme").onclick=function(){applyTheme(root.dataset.theme==="dark"?"light":"dark")};

var META={
  "qwen3.8-flash-next-iq3_s":{ac:"q",nick:"qwen 酱",who:"银灰长直 · 清冷图书管理员",
    sub:"ISTA 官方原版权重 · Qwen-Sharp 模板",tags:["官方原版","完整思考链","工具调用忠实","agent 主力"],
    specs:[["量化档","IQ3_S · GSQ-RCO"],["权重","54.8 GB GGUF"],["专家","46.85G 内存 + 14.4G 显存"],["上下文","512 K · YaRN×2 · K8V4"],["投机解码","MTP + n-gram 共享分片"],["图像输入","strata-vision"]],
    style:"官方复刻档：思考链完整、工具调用忠实——agent、编码与长文主力。",
    notes:["与 sc117 互斥，内存只驻得下其一","冷加载 1.5-3 分钟 · 热重载秒级","思考默认 medium，全关会掉质量"],
    art:"router/assets/qwen-chan.png"},
  "sc117-qwen3.8-flash-next-abliterated-iq3_s":{ac:"s",nick:"sc117 酱",who:"粉挑染 · 元气小恶魔",
    sub:"SC117 · abliterated 去拒绝版",tags:["去拒绝","角色扮演","小说写作","酒馆 RP"],
    specs:[["量化档","IQ3_S · SC117 消融"],["权重","55.1 GB GGUF"],["专家","46.85G 内存 + 14.4G 显存"],["上下文","512 K · YaRN×2 · K8V4"],["投机解码","MTP + n-gram（同分片）"],["图像输入","mmproj-Swift"]],
    style:"去拒绝变体：敏感剧情、角色扮演不说教不拒答——酒馆 RP 与创作首选。",
    notes:["与官方档互斥，换档 = 卸载 + 冷加载","独立学一份路由画像，越用越热","两档质量同级，只差安全微调"],
    art:"router/assets/sc117-chan.png"}
};
function metaFor(n){
  var m=META[n];
  if(m)return m;
  return {ac:"q",nick:n,who:"网关新发现的模型",sub:"自动挂载",tags:["自动挂载"],
    specs:[["配置文件","strata-…json"]],
    style:"网关扫描到了一份新的 strata-*.json。在网关文件 GATEWAY_HTML 的 META 里为它补一份介绍和立绘路径，这张卡片就会变成和另外两张一样的详细档案。",
    notes:["与其它模型互斥加载"],art:""};
}

var keyEl=document.getElementById("key"),msg=document.getElementById("msg");
try{keyEl.value=localStorage.getItem("stratagw.key")||""}catch(e){}
document.getElementById("save").onclick=function(){
  try{localStorage.setItem("stratagw.key",keyEl.value.trim())}catch(e){}
  say("key 已保存在本浏览器。","");
};
function say(t,cls){msg.textContent=t;msg.className=cls||""}
function hdrs(needJson){var h={};var k=keyEl.value.trim();if(k)h.Authorization="Bearer "+k;
  if(needJson)h["Content-Type"]="application/json";return h}
function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML}
function tstr(t){var d=new Date(t*1000);return ("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2)+":"+("0"+d.getSeconds()).slice(-2)}
function num(v){if(v==null)return "–";var s=""+Math.round(v);
  return s.replace(/([0-9])(?=([0-9]{3})+$)/g,"$1,")}
function fnum(v,d2){if(v==null||isNaN(v))return "–";var f=Math.pow(10,d2||0);return Math.round(v*f)/f}
function qs(url,cb){fetch(url,{headers:hdrs(false)}).then(function(r){return r.ok?r.json():Promise.reject(r.status)}).then(cb).catch(function(){})}
function postj(url,obj,cb){fetch(url,{method:"POST",headers:hdrs(true),body:JSON.stringify(obj)})
  .then(function(r){return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})}).then(cb)
  .catch(function(e){say("请求失败: "+e,"err")})}

var ops={};      // 本页乐观进行态（服务端 busy 一到就以服务端为准）
var prev={};    // 上次轮询的 loaded 状态（发现加载完成）
var sig="";
var cardsEl=document.getElementById("cards");
var modelsList=[];
var selName=null;
var mon={data:null};

function cardHTML(name,meta){
  var artHtml='<div class="art"><img alt="'+esc(meta.nick)+'立绘" src="'+meta.art+'" '+
    'onerror="this.remove()" onload="this.classList.add(&quot;landed&quot;);var p=this.parentNode&&this.parentNode.querySelector(&quot;.art-ph&quot;);if(p)p.remove()">'+
    '<div class="art-ph"><span class="nick">'+esc(meta.nick)+'</span><i></i>'+
    '<span class="who">'+esc(meta.who)+'</span><span class="pend">立绘待入</span></div></div>';
  return artHtml+'<div class="cbody">'+
    '<div class="mhead"><div><h3 title="'+esc(name)+'">'+esc(name)+'</h3><div class="sub">'+esc(meta.sub)+'</div></div></div>'+
    (meta.specs.length?'<h4 class="mod">技术档案</h4><dl class="specs">'+meta.specs.map(function(p){
      return '<div class="srow"><dt>'+esc(p[0])+'</dt><dd>'+esc(p[1])+'</dd></div>'}).join("")+'</dl>':"")+
    '<h4 class="mod">风格与适用场景</h4><div class="tags">'+meta.tags.map(function(t){return '<span>'+esc(t)+'</span>'}).join("")+'</div>'+
    '<p class="prose">'+esc(meta.style)+'</p>'+
    '<h4 class="mod">使用提醒</h4><ul class="notes">'+meta.notes.map(function(n){return '<li>'+esc(n)+'</li>'}).join("")+'</ul>'+
    '<div class="acts"><button class="load" data-r="toggle">载入</button>'+
    '<span class="statechip" data-r="live">待加载</span>'+
    '<span class="ring" data-r="ring"><svg viewBox="0 0 36 36"><circle class="trk" cx="18" cy="18" r="14.5"/>'+
    '<circle class="arc" cx="18" cy="18" r="14.5"/></svg><span data-r="elapsed">0s</span></span></div>';
}
function build(names){
  cardsEl.innerHTML="";
  names.forEach(function(n){
    var meta=metaFor(n);
    var card=document.createElement("div");
    card.className="card";card.dataset.accent=meta.ac;card.dataset.model=n;
    card.innerHTML=cardHTML(n,meta);
    card.querySelector('[data-r=toggle]').onclick=function(){
      act(card.dataset.st==="loaded"?"unload":"load",n);
    };
    cardsEl.appendChild(card);
  });
}
function paint(list){
  var busyNow=false;
  list.forEach(function(b){
    if(b.busy)delete ops[b.model];
    else if(b.loaded&&ops[b.model]&&ops[b.model].op==="load")delete ops[b.model];
    else if(b.alive&&!b.loaded&&ops[b.model]&&ops[b.model].op==="unload")delete ops[b.model];
    if(b.busy||ops[b.model])busyNow=true;
  });
  list.forEach(function(b){
    var card=cardsEl.querySelector('[data-model="'+b.model+'"]');
    if(!card)return;
    var st=!b.alive?"down":(b.loaded?"loaded":"unloaded");
    var act2=b.busy?{op:b.busy.op,t0:Date.now()-b.busy.elapsed_s*1000}:ops[b.model];
    card.dataset.st=st;
    var tg=card.querySelector('[data-r=toggle]'),
        ring=card.querySelector('[data-r=ring]'),el=card.querySelector('[data-r=elapsed]'),
        live=card.querySelector('[data-r=live]');
    var willUnload=(st==="loaded");
    tg.textContent=act2?(act2.op==="load"?"载入中…":"卸载中…"):(willUnload?"卸载":"载入");
    tg.className=act2?(act2.op==="load"?"load":"warnbtn"):(willUnload?"warnbtn":"load");
    tg.disabled=(st==="down"||busyNow);
    if(act2){ring.classList.add("on");
      var e0=Math.round((Date.now()-act2.t0)/1000);
      el.textContent=e0<100?(e0+"s"):(Math.floor(e0/60)+"m"+("0"+(e0%60)).slice(-2)+"s");}
    else ring.classList.remove("on");
    var lv=mon.data&&mon.data.live?mon.data.live:null;
    if(st==="down")live.textContent="离线";
    else if(act2)live.textContent=(act2.op==="load"?"请上卡":"让卡中");
    else if(st==="loaded")live.textContent=(lv&&lv.state==="generating")?(fnum(lv.tok_s,1)+" tok/s"):
      ((lv&&lv.state==="reading")?"读提示词":"静驻");
    else live.textContent="待加载";
  });
}
function refresh(){
  fetch("router/backends").then(function(r){return r.json()}).then(function(d){
    var list=d.backends||[];modelsList=list;
    var names=list.map(function(b){return b.model});
    if(names.join("|")!==sig){sig=names.join("|");build(names);buildSeg()}
    list.forEach(function(b){
      var was=prev[b.model];
      if(was===false&&b.loaded===true){
        say(b.model+" 已载入 —— monitor 已就绪，页面见下方。","busy");
        var sec=document.getElementById("sec-monitor");
        sec.classList.remove("flash");void sec.offsetWidth;sec.classList.add("flash");
        sec.scrollIntoView({behavior:"smooth",block:"start"});
      }else if(was===true&&b.loaded===false&&!b.busy){
        say(b.model+" 已卸载，显存已让出。","");
      }
      prev[b.model]=b.loaded;
    });
    var anyLoaded=list.some(function(b){return b.loaded});
    var loadedNow=list.filter(function(b){return b.loaded});
    if(!selName||!list.some(function(b){return b.model===selName})){
      if(loadedNow[0]||list[0])selectModel((loadedNow[0]||list[0]).model,true);
    }else if(selName&&loadedNow.length&&loadedNow.every(function(b){return b.model!==selName})){
      selectModel(loadedNow[0].model,true);
    }
    paint(list);
  }).catch(function(e){say("读后端列表失败: "+e,"err")});
  fetchComfy();
}
function act(op,name){
  if(ops[name])return;
  ops[name]={op:op,t0:Date.now()};
  refresh();
  fetch(op,{method:"POST",headers:hdrs(true),body:JSON.stringify({model:name})})
    .then(function(r){return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
    .then(function(rj){
      if(rj[0]>=400){delete ops[name];
        say(op+" "+name+" 失败 HTTP "+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");
        refresh()}
    })
    .catch(function(e){delete ops[name];say(op+" "+name+" 失败: "+e,"err");refresh()});
}

/* ---------------- monitor ---------------- */
var TILES=[
  {key:"decode",label:"解码速度",unit:"tok/s",series:"tok_s",dec:1},
  {key:"prefill",label:"预填速度",unit:"tok/s",series:"prefill_tok_s_mean"},
  {key:"gpu",label:"GPU 负载",unit:"%",series:"gpu_util"},
  {key:"vram",label:"显存占用",unit:"GB",series:"gpu_mem_used"},
  {key:"temp",label:"GPU 温度",unit:"°C",series:"gpu_temp"},
  {key:"power",label:"GPU 功耗",unit:"W",series:"gpu_power"},
  {key:"pcie",label:"PCIe→显存",unit:"MB/s",series:"gpu_pcie_rx_mb"},
  {key:"cpu",label:"CPU",unit:"%",series:"cpu",alt:true},
  {key:"disk",label:"磁盘读取",unit:"MB/s",series:"disk_read_mb"}
];
function gbf(v,d){if(v==null||isNaN(v))return "–";var x=v/1073741824;return d?x.toFixed(d):""+(Math.round(x*10)/10)}
function kfmt(v){if(v==null)return "–";if(v>=1000000)return (v/1000000).toFixed(2)+"M";if(v>=1000)return (v/1000).toFixed(1)+"K";return ""+v}
function flatSpark(){return '<svg viewBox="0 0 100 32" preserveAspectRatio="none"><path class="line" d="M0,30L100,30" style="stroke-dasharray:3 3;opacity:.55"/></svg>'}
function spark(arr,max){
  if(!arr||arr.length<2)return flatSpark();
  var mx=0,i;for(i=0;i<arr.length;i++){if(arr[i]>mx)mx=arr[i]}
  if(max)mx=Math.max(mx,max);if(!(mx>0))mx=1;
  var n=arr.length,pts=[];
  for(i=0;i<n;i++){pts.push((i*100/(n-1)).toFixed(1)+","+(30-(arr[i]/mx)*26).toFixed(1))}
  var line="M"+pts.join("L");
  return '<svg viewBox="0 0 100 32" preserveAspectRatio="none"><path class="area" d="M0,32L'+pts.join("L")+'L100,32Z"/><path class="line" d="'+line+'"/></svg>';
}
function phTiles(){
  document.getElementById("mon").innerHTML=
    TILES.map(function(m){
      return '<div class="tile ph'+(m.alt?" alt":"")+'"><div class="lab">'+m.label+'</div>'+
        '<div class="val">–<small>'+m.unit+'</small></div><div class="sub">载入后点亮</div>'+flatSpark()+'</div>';
    }).join("")+
    '<div class="tile ph"><div class="lab">上下文填充</div><div class="val">–<small>%</small></div><div class="sub">最近请求占窗口比</div><div class="pbar"><i style="width:0"></i></div></div>'+
    '<div class="tile ph"><div class="lab">显存专家缓存</div><div class="val">–<small>槽</small></div><div class="sub">热专家占显存比</div><div class="pbar"><i style="width:0"></i></div></div>'+
    '<div class="tile ph"><div class="lab">系统内存</div><div class="val">–<small>GB</small></div><div class="sub">引擎常驻水位</div><div class="pbar ram"><i style="width:0"></i></div></div>';
}
var FIN={stop:["ok","已完成"],length:["len","触上限"],cancel:["stop","已停止"],disconnect:["stop","已断开"],error:["err","错误"],timeout:["stop","超时"]};
var TROWS=10;
function phRow(){return '<tr class="phr"><td>–</td><td><span class="fin">–</span></td><td>–</td><td>–</td><td>–</td><td>–</td><td>–</td><td>–</td><td>–</td></tr>'}
function renderMonitor(){
  var bar=document.getElementById("mon-bar");
  var chip=document.getElementById("mon-chip");
  var det=document.getElementById("mon-detail");
  var who=document.getElementById("mon-who");
  var prog=document.querySelector("#mon-prog i");
  var strip=document.getElementById("mon-strip");
  var tb=document.getElementById("mon-tb");
  var hint=document.getElementById("mon-hint");
  var meta=metaFor(selName||"");
  bar.style.setProperty("--ac","var(--"+(meta.ac==="s"?"s":"q")+")");
  chip.className="";det.textContent="";who.textContent=selName?"· "+selName:"";prog.style.width="0";
  var d=mon.data;
  if(!d){
    chip.textContent="待载入";
    det.textContent="拿不到 /metrics——多半是页脚 api key 没填，或该后端进程未起";
    phTiles();strip.textContent="";
    tb.innerHTML=phRow().repeat(TROWS);
    hint.textContent="尚无请求记录——统计从引擎启动起累计";
    return;
  }
  var eng=d.engine||{},lv=d.live||{},hw=d.hardware||{},st=d.hardware_static||{},
      h=d.history||{},t=d.totals||{};
  var requests=d.requests||[],last=requests[0]||null;
  var loaded=modelsList.some(function(b){return b.model===selName&&b.loaded});
  var state=lv.state||"unloaded";
  if(loaded&&lv.queued>0&&state!=="generating"&&state!=="reading")state="queued";
  var STATE={idle:"待机",reading:"读提示词",generating:"生成中",queued:"排队中",unloaded:"已卸载",error:"异常"};
  if(!loaded)state="unloaded";
  chip.textContent=STATE[state]||state;
  if(state==="generating"){
    chip.className="gen";
    det.textContent=num(lv.generated)+" tok · "+fnum(lv.tok_s,1)+" tok/s"+(lv.phase?" · "+lv.phase:"");
    if(lv.max_tokens)prog.style.width=Math.min(100,(100*(lv.generated||0))/lv.max_tokens)+"%";
  }else if(state==="reading"){
    chip.className="reading";
    if(lv.prompt_total){det.textContent=num(lv.prompt_read)+" / "+num(lv.prompt_total)+" tok · "+Math.round(100*(lv.prompt_read||0)/lv.prompt_total)+"%";
      prog.style.width=Math.min(100,100*(lv.prompt_read||0)/lv.prompt_total)+"%";}
    else det.textContent=num(lv.prompt_tokens)+" tok";
  }else if(state==="queued"){
    chip.className="reading";
    det.textContent=(lv.queued||0)+" 个请求排队 · 先让上一个说完";
  }else if(state==="idle"){
    chip.className="idle";
    det.textContent=last?("上次: "+num(last.output_tokens)+" tok · "+fnum(last.decode_tok_s,1)+" tok/s"):"等待请求";
  }else{
    det.textContent="引擎未驻留——下方硬件读数仍是实时的（画布出图也在同一块卡上）";
  }
  var decodeAvg=(t.decode_ms&&t.output_tokens)?t.output_tokens/(t.decode_ms/1000):null;
  var readTok=(t.prompt_tokens||0)-(t.reused||0);
  var avgPrefill=(t.prompt_ms>0&&readTok>0)?readTok/(t.prompt_ms/1000):null;
  var decodeV=(state==="generating")?lv.tok_s:(decodeAvg!=null?decodeAvg:(last?last.decode_tok_s:null));
  var prefillV=(lv.state&&lv.state!=="idle"&&lv.prefill_tok_s_mean!=null)?lv.prefill_tok_s_mean
              :(avgPrefill!=null?avgPrefill
              :(last&&last.prompt_ms>0?Math.max(0,(last.prompt_tokens||0)-(last.reused||0))/(last.prompt_ms/1000):null));
  var speedSub=state==="generating"?"当前 decode":(decodeAvg!=null?"decode · 运行均值":(last?"上次请求":"等待首次"));
  var preSub=state==="reading"?"当前 prefill":(avgPrefill!=null?"prefill · 运行均值":(last?"上次请求":"等待首次"));
  function std(m,val,unit,sub,amax){
    return '<div class="tile'+(m.alt?" alt":"")+'"><div class="lab">'+m.label+'</div>'+
      '<div class="val">'+val+(unit?'<small>'+unit+'</small>':"")+'</div>'+
      '<div class="sub">'+(sub||"")+'</div>'+spark(h[m.series],amax)+'</div>';
  }
  var tiles=[],amax,sub2;
  TILES.forEach(function(m){
    var val;
    if(m.key==="decode"){val=fnum(decodeV,1);sub2=speedSub;amax=null}
    else if(m.key==="prefill"){val=fnum(prefillV,0);sub2=preSub;amax=null}
    else if(m.key==="gpu"){val=fnum(hw.gpu_util,0);sub2=st.gpu_name?esc(st.gpu_name):"利用率";amax=100}
    else if(m.key==="vram"){val=gbf(hw.gpu_mem_used,1);
      sub2=eng.expert_slots?(num(eng.expert_slots)+" experts cached"):(hw.gpu_mem_total?("共 "+gbf(hw.gpu_mem_total,0)+" GB"):"");amax=hw.gpu_mem_total}
    else if(m.key==="temp"){val=fnum(hw.gpu_temp,0);sub2="阈值 90°C";amax=90}
    else if(m.key==="power"){val=fnum(hw.gpu_power,0);sub2=hw.gpu_power_limit?("上限 "+fnum(hw.gpu_power_limit,0)+" W"):"";amax=hw.gpu_power_limit}
    else if(m.key==="pcie"){val=fnum(hw.gpu_pcie_rx_mb,(hw.gpu_pcie_rx_mb!=null&&hw.gpu_pcie_rx_mb<10)?1:0);
      sub2="Gen"+(hw.gpu_pcie_gen_max||hw.gpu_pcie_gen||"?")+(hw.gpu_pcie_width?(" x"+hw.gpu_pcie_width):"")}
    else if(m.key==="cpu"){val=fnum(hw.cpu,0);sub2=st.threads?((st.cores?st.cores+" 核 · ":"")+st.threads+" 线程"):"负载";amax=100}
    else{var rd=hw.disk_read_mb;val=rd==null?"–":fnum(rd,rd<10?1:0);
      sub2=hw.disk_write_mb==null?(st.psutil?"":"需 psutil"):("写 "+fnum(hw.disk_write_mb,1)+" MB/s")}
    tiles.push(std(m,val,m.unit,sub2,amax));
  });
  var ctx=eng.max_context||0,usedNow=0;
  if(state==="reading"||state==="generating")usedNow=(lv.prompt_tokens||0)+(lv.generated||0);
  else if(last)usedNow=(last.prompt_tokens||0)+(last.output_tokens||0);
  var frac=ctx?Math.min(1,usedNow/ctx):0;
  tiles.push('<div class="tile"><div class="lab">上下文填充</div><div class="val">'+Math.round(frac*100)+
    '<small>%</small></div><div class="sub">'+(ctx?(kfmt(usedNow)+" / "+Math.round(ctx/1024)+"K tok"):"–")+'</div>'+
    '<div class="pbar"><i style="width:'+(frac*100).toFixed(1)+'%"></i></div></div>');
  var cacheBytes=(eng.expert_cache_mib||0)*1048576;
  var cacheFrac=(hw.gpu_mem_total&&cacheBytes)?Math.min(1,cacheBytes/hw.gpu_mem_total):0;
  tiles.push('<div class="tile alt"><div class="lab">显存专家缓存</div><div class="val">'+
    (eng.expert_slots!=null?num(eng.expert_slots):"–")+'<small>槽</small></div><div class="sub">'+
    (cacheBytes?(gbf(cacheBytes,1)+" GB · "+Math.round(cacheFrac*100)+"% 显存"):"–")+'</div>'+
    '<div class="pbar warm"><i style="width:'+(cacheFrac*100).toFixed(1)+'%"></i></div></div>');
  var rp=(hw.ram_total&&hw.ram_used!=null)?Math.min(100,100*hw.ram_used/hw.ram_total):0;
  tiles.push('<div class="tile"><div class="lab">系统内存</div><div class="val">'+
    (hw.ram_used!=null?gbf(hw.ram_used,1):"–")+'<small>GB</small></div><div class="sub">'+
    (hw.ram_total?("共 "+gbf(hw.ram_total,0)+" GB · 水位 "+Math.round(rp)+"%"):"–")+'</div>'+
    '<div class="pbar ram'+(rp>92?" hot":"")+'"><i style="width:'+rp.toFixed(1)+'%"></i></div></div>');
  document.getElementById("mon").innerHTML=tiles.join("");
  var dg=document.getElementById("dg-ram"),gg=document.getElementById("dg-gpu");
  if(dg&&hw.ram_total)dg.textContent="DDR4 · "+gbf(hw.ram_total,0)+" GB";
  if(gg){var g0=String(st.gpu_name||"");g0=g0.replace("NVIDIA GeForce ","").replace("NVIDIA ","").replace("GeForce ","");var gn=g0||"GPU";
    gg.textContent=gn+(hw.gpu_mem_total?(" · "+gbf(hw.gpu_mem_total,0)+" GB"):"");}
  
  if(t.requests){
    var pS=t.prompt_ms>0&&readTok>0?(" @ "+fnum(readTok/(t.prompt_ms/1000),0)+" tok/s"):"";
    var oS=t.decode_ms>0&&t.output_tokens>0?(" @ "+fnum(t.output_tokens/(t.decode_ms/1000),1)+" tok/s"):"";
    var since=t.since?new Date(t.since*1000):null;
    var stime=(since&&since.getFullYear()>2020)?((since.getMonth()+1)+"月"+since.getDate()+"日 "+("0"+since.getHours()).slice(-2)+":"+("0"+since.getMinutes()).slice(-2)):"启动";
    strip.innerHTML="自 "+stime+" 起：<b>"+num(t.requests)+"</b> 次请求 · 读取 prompt <b>"+num(readTok)+"</b> tok"+pS+
      "（复用 <b>"+num(t.reused)+"</b>） · 生成 <b>"+num(t.output_tokens)+"</b> tok"+oS;
  }else strip.textContent="本次会话尚无请求——统计从引擎启动起累计";
  var rows=[];
  for(var ri=0;ri<TROWS;ri++){
    var r=requests[ri];
    if(!r){rows.push(phRow());continue}
    var f=FIN[r.finish]||["",r.finish||"–"];
    var hit=r.hit_rate==null?"–":((r.hit_rate*100).toFixed(1)+"%"+
      (r.pcie_share?(' <span style="color:var(--dim)">+'+(r.pcie_share*100).toFixed(1)+"% PCIe</span>"):""));
    var fresh=Math.max(0,(r.prompt_tokens||0)-(r.reused||0));
    var pr=(fresh>0&&r.prompt_ms>0)?fresh/(r.prompt_ms/1000):null;
    rows.push('<tr><td>'+tstr(r.time)+'</td><td><span class="fin '+f[0]+'">'+f[1]+'</span></td>'+
      '<td>'+num(r.prompt_tokens)+'</td><td>'+num(r.reused)+'</td><td>'+num(r.output_tokens)+'</td>'+
      '<td>'+fnum(pr,0)+'</td><td>'+fnum(r.decode_tok_s,1)+'</td><td>'+hit+'</td><td>'+fnum(r.duration_s,1)+"s</td></tr>");
  }
  tb.innerHTML=rows.join("");
  hint.textContent=(d.requests_kept>TROWS)?("留存 "+d.requests_kept+" 条 · 表内显示最近 "+TROWS+" 条"):(requests.length?"":"尚无请求记录——统计从引擎启动起累计");
}
function pollMetrics(){
  if(!selName)return;
  fetch("router/metrics?model="+encodeURIComponent(selName),{headers:hdrs(false)})
    .then(function(r){return r.ok?r.json():Promise.reject(r.status)})
    .then(function(m){mon.data=m;renderMonitor()})
    .catch(function(){mon.data=null;renderMonitor()});
}
[["drawer-sampling","sampling"],["drawer-config","config"]].forEach(function(p){
  var d=document.getElementById(p[0]);if(!d)return;
  try{if(localStorage.getItem("stratagw.drawer."+p[1])==="1")d.open=true}catch(e){}
  d.addEventListener("toggle",function(){
    try{localStorage.setItem("stratagw.drawer."+p[1],d.open?"1":"0")}catch(e){}
  });
});

/* ---------------- settings ---------------- */
var SAMP=[["temperature","stemp","ostemp",1],["top_p","stop_p","os-top_p",2],["top_k","stop_k","os-top_k",0],
          ["reasoning_effort","seffort",null,0],["reasoning_budget_tokens","sbudget",null,0],
          ["seed","sseed",null,0],["max_tokens","smax",null,0],["experimental_speed_projection","sesp",null,0]];
function buildSeg(){
  var seg=document.getElementById("seg-models");seg.innerHTML="";
  modelsList.forEach(function(b){
    var btn=document.createElement("button");
    btn.textContent=metaFor(b.model).nick;
    btn.dataset.model=b.model;
    if(b.model===selName)btn.className="on";
    btn.onclick=function(){selectModel(b.model)};
    seg.appendChild(btn);
  });
}
function selectModel(name,quiet){
  if(selName===name)return;
  selName=name;
  buildSeg();
  mon.data=null;pollMetrics();
  loadSettings();loadConfig();
}
function loadSettings(){
  if(!selName)return;
  qs("router/settings?model="+encodeURIComponent(selName),function(d){
    var def=d.defaults||{};
    SAMP.forEach(function(f){
      var el=document.getElementById(f[1]);var v=def[f[0]];
      if(el.type==="checkbox"){el.checked=!!v}
      else if(el.tagName==="SELECT"){el.value=v==null?"":v}
      else if(el.type==="range"){el.value=(v==null?(f[0]==="temperature"?1:el.value):v);showOut(f)}
      else{el.value=(v==null||v===""?"":v)}
      if(el.type==="range")showOut(f);
    });
  });
}
function showOut(f){var o=f[2];if(!o)return;
  var el=document.getElementById(f[1]);var out=document.getElementById(o);
  if(out)out.textContent=el.value}
document.querySelectorAll(".fgrid input[type=range]").forEach(function(el){
  el.addEventListener("input",function(){
    SAMP.forEach(function(f){if(f[1]===el.id)showOut(f)});
  });
});
document.getElementById("s-save").onclick=function(){
  if(!selName)return;
  var def={};
  SAMP.forEach(function(f){
    var el=document.getElementById(f[1]);var v;
    if(el.type==="checkbox"){if(el.checked)def[f[0]]=true;return}
    v=el.value;
    if(v===""||v==null)return;
    if(el.type==="range"||el.tagName!=="SELECT"&&el.id!=="seffort")v=+v;
    def[f[0]]=v;
  });
  postj("router/settings?model="+encodeURIComponent(selName),{defaults:def},function(rj){
    if(rj[0]>=400){say("保存采样失败 HTTP "+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    say("采样默认已保存到 "+selName+"（即时生效）。","");
    if(rj[1].defaults){/* server may normalize; leave form as is */}
  });
};
document.getElementById("s-clear").onclick=function(){
  if(!selName)return;
  postj("router/settings?model="+encodeURIComponent(selName),{defaults:null},function(rj){
    if(rj[0]>=400){say("清除失败 HTTP "+rj[0],"err");return}
    say("已清除："+selName+" 交回各客户端自带的参数。","");
    loadSettings();
  });
};
var cfgKeys=[];
var CFGNOTE="后端 /config 白名单键。保存时 Strata 官方会自动备份配置 json；改动从该模型下次启动起生效。留空 = 删除该键（回默认）。";
function loadConfig(){
  if(!selName)return;
  qs("router/config?model="+encodeURIComponent(selName),function(d){
    cfgKeys=d.keys||[];
    document.getElementById("cfg-note").textContent=(d.note||CFGNOTE)+(d.file?("（文件: "+d.file+"）"):"");
    var wrap=document.getElementById("cfg-list");wrap.innerHTML="";
    cfgKeys.forEach(function(k){
      var row=document.createElement("div");row.className="crow";
      var inputHtml="";
      if(k.kind==="bool"){
        inputHtml='<span class="chk"><input type="checkbox" data-ck="'+esc(k.key)+'"'+(k.value?" checked":"")+'>'+
          '<span>'+(k.value==null?"默认":"")+'</span></span>';
      }else if(k.kind==="enum"){
        inputHtml='<select data-ck="'+esc(k.key)+'"><option value="">默认</option>'+
          (k.choices||[]).map(function(c){return '<option value="'+esc(c)+'"'+(k.value===c?" selected":"")+'>'+esc(c)+'</option>'}).join("")+'</select>';
      }else{
        inputHtml='<input type="text" inputmode="'+(k.kind==="number"?"decimal":"text")+'" data-ck="'+esc(k.key)+'" value="'+(k.value==null?"":esc(String(k.value)))+'" placeholder="默认">';
      }
      row.innerHTML='<span class="ck">'+esc(k.key)+'</span>'+inputHtml+
        '<div class="ch">'+esc(k.help||"")+'</div>';
      wrap.appendChild(row);
    });
  });
}
document.getElementById("c-save").onclick=function(){
  if(!selName)return;
  var set={};
  document.querySelectorAll("#cfg-list [data-ck]").forEach(function(el){
    var key=el.dataset.ck;var v;
    if(el.type==="checkbox"){v=el.checked}
    else if(el.value===""){v=null}
    else if(el.tagName==="SELECT"){v=el.value}
    else{v=/^[0-9.]+$/.test(el.value.trim())?+el.value.trim():el.value.trim()}
    set[key]=v;
  });
  postj("router/config?model="+encodeURIComponent(selName),{set:set},function(rj){
    if(rj[0]>=400){say("保存 Model settings 失败 HTTP "+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    var ch=(rj[1].changed||[]);
    say("Model settings 已写入 "+selName+"（"+(ch.length?("改动: "+ch.join(", ")):"无改动")+"）— 下次启动该模型时生效。","busy");
    loadConfig();
  });
};

/* ---------------- about / engine info ---------------- */
function loadInfo(){
  qs("router/info",function(d){
    var b=d.build||{},a=d.app||{},rows=[];
    rows.push(["Strata 本体","v"+String(a.version||"?").replace(/^v/,"")+(a.commit?(" @"+String(a.commit).slice(0,8)):"")]);
    rows.push(["引擎版本",b.version?"v"+b.version:"—"]);
    rows.push(["构建",(b.source||"—")+(b.commit?(" @"+String(b.commit).slice(0,8)):"")]);
    rows.push(["CUDA",(b.cuda||"?")+(b.vision?(" · vision "+b.vision):"")]);
    rows.push(["预编架构",(b.archs||[]).join("/")+" 本机 sm_"+((b.archs||[]).indexOf(86)>=0?"86":"?")]);
    var ms=d.models||{};
    Object.keys(ms).forEach(function(n){
      var m=ms[n];
      rows.push([metaFor(n).nick,m.alive?("上下文 "+Math.round((m.max_context||0)/1024)+"K · vision "+(m.images?"有":"无")+(m.loaded?" · 在位":" · 待命")):"后端离线"]);
    });
    rows.push(["让卡水位",(d.comfy_free_target_mib||0)+" MiB"]);
    document.getElementById("eng-kv").innerHTML=rows.map(function(r){
      return '<span class="kvchip">'+esc(r[0])+'<b>'+esc(String(r[1]))+'</b></span>'}).join("");
  });
}
/* ---------------- dyn ---------------- */
var KIND={load:"载入",unload:"让位",comfy:"显存",switch:"切换",backend:"后端",error:"异常"};
var evOpen=false;
function loadEvents(){
  qs("router/events",function(d){
    var box=document.getElementById("events");
    var raw=(d.events||[]).slice(0,120),evs=[];
    raw.forEach(function(e){var m=evs[evs.length-1];
      if(m&&m.kind===e.kind&&m.text===e.text){m.n++;m.t=e.t}
      else evs.push({kind:e.kind,text:e.text,t:e.t,n:1})});
    var sig=(evOpen?"O":"C")+evs.map(function(e){return e.kind+e.text+e.n+Math.round(e.t)}).join(";");
    if(box.getAttribute("data-sig")===sig)return;
    box.setAttribute("data-sig",sig);
    box.className=evOpen?"open":"";
    box.innerHTML=evs.length?"":"<p style='color:var(--muted);font-size:.8rem'>还没有事件——加载、卸载、让卡都会出现在这里（网关重启前的记录不留存）。</p>";
    (evOpen?evs:evs.slice(0,5)).forEach(function(e,i){
      var p=document.createElement("p");
      p.className="ev "+e.kind;
      p.style.animationDelay=(Math.min(i,10)*0.03)+"s";
      p.innerHTML='<span class="kind">'+(KIND[e.kind]||esc(e.kind))+'</span><time>'+tstr(e.t)+(e.n>1?(' \u00d7'+e.n):"")+'</time><p>'+esc(e.text)+'</p>';
      box.appendChild(p);
    });
    if(evs.length>5){
      var b=document.createElement("button");
      b.className="evbtn";
      b.textContent=evOpen?("收起 · 只留最近 5 条"):("展开其余 "+(evs.length-5)+" 条 ▾");
      b.onclick=function(){evOpen=!evOpen;loadEvents()};
      box.appendChild(b);
    }
  });
}

/* ---------------- comfyui 状态条 + 清理 ---------------- */
var cfree=document.getElementById("cfree"),cforce=document.getElementById("cforce");
var cfreeBusy=null,cfSeen=null;
function sayFree(res){
  var line="显存释放 "+(res.freed_vram_mib/1024).toFixed(1)+" GB · 内存释放 "+(res.freed_ram_mib/1024).toFixed(1)+" GB · 用时 "+res.waited_s+" 秒";
  if(res.force){
    if(res.gave_card)say("强制清理完成，显卡已让出（清掉任务 "+res.tasks_cleared+" 个）。"+line,"");
    else say("强制清理：等了 "+res.waited_s+" 秒显卡还没让出来（任务被打断后可能还在收尾）。"+line,"busy");
  }else{
    if(res.freed_vram_mib>=256)say("温和清理："+line,"");
    else say("温和清理：显存没降——出图任务正在跑不让卡。等它跑完再点，或用强制清理。","busy");
  }
}
function doComfyFree(force){
  if(cfreeBusy)return;
  cfreeBusy={op:force?"force":"gentle"};
  fetch("router/comfy/free",{method:"POST",headers:hdrs(true),body:JSON.stringify({force:force})})
    .then(function(r){return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
    .then(function(rj){
      cfreeBusy=null;
      if(rj[0]>=400||!rj[1].ok){say("清理失败 HTTP "+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");fetchComfy();return}
      sayFree(rj[1]);
      refresh();
    })
    .catch(function(e){cfreeBusy=null;say("清理请求失败: "+e,"err");fetchComfy()});
}
cfree.onclick=function(){doComfyFree(false)};
cforce.onclick=function(){
  if(confirm("强制清理：会打断正在执行的出图任务并清空排队，然后释放显存。继续吗？"))doComfyFree(true);
};
function fetchComfy(){
  fetch("router/comfy").then(function(r){return r.json()}).then(function(c){
    var el=document.getElementById("comfy"),bar=el.querySelector(".bar i"),lab=el.querySelector("b");
    var fr=null;
    if(cfreeBusy||c.freeing){
      if(!cfSeen)cfSeen=Date.now();
      var extra=Math.floor((Date.now()-cfSeen)/1000);
      if(c.freeing)fr={op:c.freeing.op,elapsed_s:c.freeing.elapsed_s+extra};
      else fr={op:cfreeBusy.op,elapsed_s:extra};
    }else cfSeen=null;
    var busy=!!fr;
    cfree.disabled=!c.running||busy;
    cforce.disabled=!c.running||busy;
    cfree.textContent=(busy&&fr.op==="gentle")?("清理中… "+fr.elapsed_s+"s"):"清理显存";
    cforce.textContent=(busy&&fr.op==="force")?("强清中… "+fr.elapsed_s+"s"):"强制清理";
    cfree.classList.toggle("busy",busy&&fr.op==="gentle");
    cforce.classList.toggle("busy",busy&&fr.op==="force");
    if(!c.running){lab.textContent="未运行";bar.style.width="100%";return}
    var total=c.vram_total_mib||0,free=c.vram_free_mib||0;
    if(total)bar.style.width=Math.round(free/total*100)+"%";
    function g(v){return(v/1024).toFixed(1)+" GiB 空"}
    var st=free>=(c.free_target_mib||0)?"空闲 · ":(busy?"清理中 · ":"出图占用 · ");
    lab.textContent=st+g(free);
  }).catch(function(){});
}

/* ---------------- 本页循环视频：关闭 / 背景 / 单独 ---------------- */
var bgmode="off",bgsound=false,gestured=false;
try{bgmode=localStorage.getItem("stratagw.bgmode")||"off"}catch(e){}
try{bgsound=localStorage.getItem("stratagw.bgsound")==="1"}catch(e){}
if(bgmode!=="bg"&&bgmode!=="solo")bgmode="off";
var stage=document.getElementById("bgstage"),vid=document.getElementById("bgvid"),
    segbg=document.getElementById("seg-bg"),svBtn=document.getElementById("vid-sound");
function playVid(){var p=vid.play();if(p&&p.catch)p.catch(function(){vid.muted=true;
  var q=vid.play();if(q&&q.catch)q.catch(function(){})})}
function paintBg(){
  segbg.querySelectorAll("button").forEach(function(b){b.className=b.dataset.bg===bgmode?"on":""});
  if(bgmode==="off"){vid.pause();stage.className="";stage.setAttribute("aria-hidden","true");
    svBtn.disabled=true;svBtn.textContent="声音: —";return}
  stage.className="on "+bgmode;
  stage.setAttribute("aria-hidden",bgmode==="bg"?"true":"false");
  vid.controls=(bgmode==="solo");
  vid.muted=!(bgsound&&gestured);
  svBtn.disabled=false;svBtn.textContent=bgsound?"声音: 开":"声音: 关";
  playVid()
}
function setBg(m){bgmode=m;try{localStorage.setItem("stratagw.bgmode",m)}catch(e){}paintBg()}
segbg.querySelectorAll("button").forEach(function(b){b.onclick=function(){setBg(b.dataset.bg)}});
svBtn.onclick=function(){if(bgmode==="off")return;bgsound=!bgsound;gestured=true;
  try{localStorage.setItem("stratagw.bgsound",bgsound?"1":"0")}catch(e){}
  vid.muted=!bgsound;svBtn.textContent=bgsound?"声音: 开":"声音: 关"};
stage.addEventListener("click",function(e){if(bgmode==="solo"&&e.target===stage)setBg("off")});
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&bgmode==="solo")setBg("off")});
["pointerdown","keydown"].forEach(function(ev){document.addEventListener(ev,function(){
  if(!gestured){gestured=true;if(bgsound&&bgmode!=="off")vid.muted=false}})});
paintBg();

refresh();setInterval(refresh,2000);
setInterval(pollMetrics,2500);
setInterval(loadEvents,5000);loadEvents();
setInterval(loadInfo,10000);loadInfo();

if(!(window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches)){
  var cv=document.getElementById("fx"),cx=cv.getContext("2d"),P=[],W=0,H=0,DPR=Math.min(window.devicePixelRatio||1,2);
  function size(){W=cv.width=innerWidth*DPR;H=cv.height=innerHeight*DPR;P=[];
    var n=Math.min(70,Math.floor(innerWidth*innerHeight/26000));
    for(var i=0;i<n;i++)P.push({x:Math.random()*W,y:Math.random()*H,
      vx:(Math.random()-.5)*.16*DPR,vy:(Math.random()-.5)*.16*DPR,r:Math.random()*1.6+.5})}
  size();addEventListener("resize",size);
  (function tick(){
    cx.clearRect(0,0,W,H);
    var acc=root.dataset.theme==="light"?"14,116,144":"94,234,212";
    for(var i=0;i<P.length;i++){
      var p=P[i];p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x+=W;if(p.x>W)p.x-=W;if(p.y<0)p.y+=H;if(p.y>H)p.y-=H;
      cx.beginPath();cx.arc(p.x,p.y,p.r*DPR,0,7);
      cx.fillStyle="rgba("+acc+",.5)";cx.fill();
      for(var j=i+1;j<P.length;j++){
        var q=P[j],dx=p.x-q.x,dy=p.y-q.y,d2=dx*dx+dy*dy,L=110*DPR;
        if(d2<L*L){cx.beginPath();cx.moveTo(p.x,p.y);cx.lineTo(q.x,q.y);
          cx.strokeStyle="rgba("+acc+","+(.14*(1-Math.sqrt(d2)/L)).toFixed(3)+")";
          cx.lineWidth=DPR*.6;cx.stroke()}
      }
    }
    requestAnimationFrame(tick);
  })();
}
})();
