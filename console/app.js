(function(){
"use strict";
var root=document.documentElement;
var saved=null;try{saved=localStorage.getItem("stratagw.theme")}catch(e){}
var theme=saved||(window.matchMedia&&matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");
function applyTheme(t){root.dataset.theme=t;try{localStorage.setItem("stratagw.theme",t)}catch(e){}}
applyTheme(theme);
document.getElementById("theme").onclick=function(){applyTheme(root.dataset.theme==="dark"?"light":"dark")};

/* dossier data lives in cards/cards.json (via router/cards) - never hardcoded here.
   The 技术档案 rows are assembled live from router/backends + router/info + engine
   metrics, so a card always mirrors the user's real setup and settings. */
var CARDS={},INFO={};
var LANG=(navigator.language||"zh").toLowerCase().indexOf("zh")===0?"zh":"en";
try{var _lg=localStorage.getItem("stratagw.lang");if(_lg==="zh"||_lg==="en")LANG=_lg}catch(e){}
document.getElementById("langbtn").onclick=function(){LANG=LANG==="zh"?"en":"zh";try{localStorage.setItem("stratagw.lang",LANG)}catch(e){}applyLang();renderHero();syncLangBtn();sig="";refresh()};
function syncLangBtn(){var b=document.getElementById("langbtn");if(b)b.textContent=LANG==="zh"?"中 / EN":"EN / 中"}
document.getElementById("gwver").onclick=function(){fetch("router/info").then(function(r){return r.json()}).then(function(j){var b=j.build||j.engine||{};var mv=document.querySelector('meta[name="strata-gw-version"]');var lines=[tt("网关版本","gateway version")+" "+(j.version||(mv&&mv.content)||"?")];if(b.commit){var sh=String(b.commit);if(sh.length>12)sh=sh.substring(0,12);lines.push(tt("引擎构建","engine build")+" "+sh)}if(b.version)lines.push(tt("引擎版本","engine version")+" "+b.version);if(b.built_at||b.built)lines.push(tt("构建时间","built")+" "+(b.built_at||b.built));alert(lines.join("\n"))}).catch(function(){alert(tt("拿不到引擎构建信息（引擎可能没在跑）","cannot read engine build (engine may be offline)"))})};
var setpop=document.getElementById("setpop");
document.getElementById("setgear").onclick=function(e){e.stopPropagation();setpop.style.display=setpop.style.display==="none"?"block":"none"};
document.addEventListener("click",function(e){if(setpop.style.display!=="none"&&!setpop.contains(e.target))setpop.style.display="none"});
var petOn=false,petSize=120;
try{petOn=localStorage.getItem("stratagw.pet")==="1";petSize=parseInt(localStorage.getItem("stratagw.petsize"),10)||120}catch(e){}
var petT=document.getElementById("pet-toggle"),petS=document.getElementById("pet-size"),petO=document.getElementById("pet-size-out");
petT.checked=petOn;petS.value=petSize;petO.textContent=petSize+"px";
function petChanged(){petOn=petT.checked;petSize=Math.min(220,Math.max(80,parseInt(petS.value,10)||120));try{localStorage.setItem("stratagw.pet",petOn?"1":"0");localStorage.setItem("stratagw.petsize",String(petSize))}catch(e){}petO.textContent=petSize+"px";if(window.STRATA_PET&&window.STRATA_PET.apply)window.STRATA_PET.apply(petOn,petSize)}
petT.onchange=petChanged;petS.oninput=petChanged;
function tt(zh,en){return LANG==="zh"?zh:en}
function pick(v){if(v==null)return "";if(typeof v==="string")return v;
  if(Array.isArray(v))return v;
  var o=(v[LANG]!=null?v[LANG]:(v.zh!=null?v.zh:""));return o==null?"":o;}
function pickarr(v){var o=pick(v);return Array.isArray(o)?o:[];}
function cardMeta(n){var m=CARDS[n];return (m&&typeof m==="object")?m:null;}
function cardNick(n){var m=cardMeta(n);var p=pick(m&&m.nick);
  return (typeof p==="string"&&p)?p:n;}
function accentFor(n){var m=cardMeta(n),a=(m&&m.accent)||"";
  if(a==="s")return "var(--s)";
  if(/^#[0-9a-fA-F]{3,8}$/.test(a))return a;
  return "var(--q)";}
function backendOf(n){for(var i=0;i<modelsList.length;i++){if(modelsList[i].model===n)return modelsList[i]}return null;}
function cardNameList(){var names=modelsList.map(function(b){return b.model});
  Object.keys(CARDS).forEach(function(k){if(k.charAt(0)!=="_"&&names.indexOf(k)<0)names.push(k)});
  return names;}
function renderHero(){
  var box=document.getElementById("herochips");if(!box)return;
  var els=box.querySelectorAll("span");
  var chips=(CARDS._hero&&CARDS._hero.chips&&CARDS._hero.chips[LANG])||[];
  for(var i=0;i<els.length;i++){
    if(chips.length&&chips[i]!=null){els[i].style.display="";els[i].removeAttribute("data-i18n");els[i].textContent=chips[i];}
    else if(chips.length){els[i].style.display="none"}
  }
}
function fetchCards(cb){qs("router/cards",function(d){CARDS=(d&&typeof d==="object")?d:{};if(window.PETUI)window.PETUI.art();renderHero();if(cb)cb()})}

var keyEl=document.getElementById("key"),msg=document.getElementById("msg");
try{keyEl.value=localStorage.getItem("stratagw.key")||""}catch(e){}
document.getElementById("save").onclick=function(){
  try{localStorage.setItem("stratagw.key",keyEl.value.trim())}catch(e){}
  say(tt("key 已保存在本浏览器。","key saved in this browser."),"");
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
  .catch(function(e){say(tt("请求失败: ","request failed: ")+e,"err")})}

var ops={};      // 本页乐观进行态（服务端 busy 一到就以服务端为准）
var prev={};    // 上次轮询的 loaded 状态（发现加载完成）
var sig="";
var cardsEl=document.getElementById("cards");
var modelsList=[];
var selName=null;
var mon={data:null};

function artHtml(name){
  var m=cardMeta(name),nick=cardNick(name);
  var ph='<div class="art-ph"><span class="nick">'+esc(nick)+'</span><i></i>'+
    '<span class="who">'+esc(pick(m&&m.who))+'</span><span class="pend">'+tt("立绘待入","portrait pending")+'</span></div>';
  var art=m?String(m.art||""):"";
  var tools='<div class="art-tools"><button data-r="uploadart">'+tt("上传立绘","upload art")+'</button>'+
    '<button data-r="rmart" style="display:none">'+tt("移除","remove")+'</button></div>';
  if(!art)return '<div class="art">'+ph+tools+'</div>';
  return '<div class="art"><img alt="'+esc(nick)+tt("立绘","portrait")+'" src="'+esc(art)+'" '+
    'onerror="this.remove()" onload="this.classList.add(&quot;landed&quot;);var p=this.parentNode&&this.parentNode.querySelector(&quot;.art-ph&quot;);if(p)p.remove()">'+ph+tools+'</div>';
}
function cardHTML(name){
  var m=cardMeta(name);
  var tags=m?pickarr(m.tags):[],notes=m?pickarr(m.notes):[];
  var lore=m?pick(m.lore):"";
  var h='<div class="page"><div class="card" style="--ac:'+accentFor(name)+'" data-model="'+esc(name)+'">';
  h+=artHtml(name);
  h+='<div class="cbody">'+
    '<div class="mhead"><div><h3 title="'+esc(name)+'">'+esc(name)+'</h3>'+
    '<div class="sub">'+esc(m?pick(m.sub):tt("点「自定义」设昵称 / 配色 / 立绘","customize to set nickname · palette · portrait"))+'</div></div></div>'+
    '<h4 class="mod">'+tt("技术档案","technical dossier")+'</h4><dl class="specs" data-r="liverows"></dl>';
  if(tags.length)h+='<div class="tags">'+tags.map(function(x){return '<span>'+esc(x)+'</span>'}).join("")+'</div>';
  if(m&&pick(m.style))h+='<p class="prose">'+esc(pick(m.style))+'</p>';
  if(notes.length)h+='<h4 class="mod">'+tt("使用提醒","field notes")+'</h4><ul class="notes">'+notes.map(function(x){return '<li>'+esc(x)+'</li>'}).join("")+'</ul>';
  if(lore)h+='<h4 class="mod">'+tt("档案","dossier")+'</h4><p class="prose">'+esc(lore)+'</p>';
  h+='<div class="acts"><button class="load" data-r="toggle">'+tt("载入","Load")+'</button>'+
    '<span class="statechip" data-r="live">'+tt("待加载","idle")+'</span>'+
    '<button class="ghostbtn" data-r="editdossier" style="display:none">'+tt("自定义","customize")+'</button>'+
    '<button class="warnbtn" data-r="delcard" style="display:none">'+tt("删除卡片","delete card")+'</button>'+
    '<span class="ring" data-r="ring"><svg viewBox="0 0 36 36"><circle class="trk" cx="18" cy="18" r="14.5"/>'+
    '<circle class="arc" cx="18" cy="18" r="14.5"/></svg><span data-r="elapsed">0s</span></span></div>'+
    '</div></div>';
  return h;
}
var pageIdx=0,cardNames=[];
var trainName=null;
function closeTrain(){}
function build(names){
  cardNames=names.slice();
  var remember=null;try{remember=localStorage.getItem("stratagw.cardidx")}catch(e){}
  if(remember){var k=names.indexOf(remember);if(k>=0)pageIdx=k}
  if(pageIdx>=names.length)pageIdx=Math.max(0,names.length-1);
  cardsEl.innerHTML=names.map(cardHTML).join("");
  names.forEach(function(n){
    var card=cardsEl.querySelector('[data-model="'+n+'"]');if(!card)return;
    card.querySelector('[data-r=toggle]').onclick=function(){
      if(!backendOf(n))return;
      act(card.dataset.st==="loaded"?"unload":"load",n);
    };
    card.querySelector('[data-r=editdossier]').onclick=function(){openEdit(n)};
    var ua=card.querySelector('[data-r=uploadart]');
    if(ua)ua.onclick=function(){artTarget=n;artInput.click()};
    var rm=card.querySelector('[data-r=rmart]');
    if(rm)rm.onclick=function(){
      postj("router/cards",{model:n,card:{art:""}},function(q){
        if(q[0]>=400){say(tt("移除立绘失败 HTTP ","art remove failed HTTP ")+q[0],"err");return}
        say(tt("立绘已移除。","art removed."),"");
        fetchCards(function(){sig="";refresh()});
      });
    };
    var del=card.querySelector('[data-r=delcard]');
    del.onclick=function(){
      if(del.dataset.armed==="1"){delCard(n);return}
      del.dataset.armed="1";del.textContent=tt("再点一次确认","tap again to confirm");
      setTimeout(function(){if(del.isConnected){del.dataset.armed="";del.textContent=tt("删除卡片","delete card")}},4000);
    };
  });
  setPage(pageIdx);
}
function setPage(i){
  if(trainName)closeTrain();
  if(!cardNames.length){paintDots();return}
  pageIdx=((i%cardNames.length)+cardNames.length)%cardNames.length;
  var pages=cardsEl.querySelectorAll(".page");var np=pages.length;
  for(var j=0;j<np;j++){var rel=(j-pageIdx+np)%np;
    pages[j].className=rel===0?"page on":rel===1?"page pr":rel===np-1?"page pl":"page";
    if(np>1&&(rel===1||rel===np-1))pages[j].onclick=(function(k){return function(){setPage(k)}})(j);
    else if(rel!==0)pages[j].onclick=null;}
  deckHeight();
  try{localStorage.setItem("stratagw.cardidx",cardNames[pageIdx])}catch(e){}
  paintDots();
}
function deckHeight(){
  var mx=0,ps=cardsEl.querySelectorAll(".page .card");
  for(var i=0;i<ps.length;i++){var h=ps[i].offsetHeight;if(h>mx)mx=h}
  if(mx)cardsEl.style.height=mx+"px";
}
function paintDots(){
  var pd=document.getElementById("pdots");if(!pd)return;
  pd.innerHTML=cardNames.map(function(n,i){return '<button class="dot'+(i===pageIdx?" on":"")+'" data-i="'+i+'" title="'+esc(n)+'"></button>'}).join("");
  Array.prototype.forEach.call(pd.children,function(b){b.onclick=function(){setPage(+b.getAttribute("data-i"))}});
  var nav=document.getElementById("cardnav");
  if(nav)nav.style.display=cardNames.length>1?"":"none";
}
var artTarget=null;
var artInput=document.createElement("input");
artInput.type="file";artInput.accept=".png,.jpg,.jpeg,.webp";artInput.style.display="none";
document.body.appendChild(artInput);
artInput.onchange=function(){
  var f=artInput.files&&artInput.files[0];artInput.value="";
  if(!f||!artTarget)return;
  if(f.size>5*1024*1024){say(tt("图片超过 5 MB 上限","image over the 5 MB cap"),"err");return}
  var fd=new FormData();fd.append("file",f);
  say(tt("立绘上传中…","uploading art…"),"busy");
  fetch("router/upload",{method:"POST",body:fd}).then(function(r){
    return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
  .then(function(rj){
    if(rj[0]>=400){say(tt("上传失败 HTTP ","upload failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    postj("router/cards",{model:artTarget,card:{art:rj[1].art}},function(q){
      if(q[0]>=400){say(tt("立绘路径保存失败 HTTP ","art path save failed HTTP ")+q[0],"err");return}
      say(tt("立绘已保存并持久化。","art saved and persisted."),"");
      fetchCards(function(){sig="";refresh()});
    });
  })
  .catch(function(e){say(tt("上传失败: ","upload failed: ")+e,"err")});
};
(function wireNav(){
  var pb=document.getElementById("cprev"),nb=document.getElementById("cnext");
  if(pb)pb.onclick=function(){setPage(pageIdx-1)};
  if(nb)nb.onclick=function(){setPage(pageIdx+1)};
  document.addEventListener("keydown",function(e){
    if(e.target&&/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;
    if(e.key==="ArrowLeft"){setPage(pageIdx-1)}else if(e.key==="ArrowRight"){setPage(pageIdx+1)}
  });
  var tX=null;
  cardsEl.addEventListener("touchstart",function(e){tX=e.touches[0].clientX},{passive:true});
  cardsEl.addEventListener("touchend",function(e){
    if(tX==null)return;var dx=e.changedTouches[0].clientX-tX;tX=null;
    if(dx<-40)setPage(pageIdx+1);else if(dx>40)setPage(pageIdx-1);
  },{passive:true});
/* ---------- Phase 7: desktop pet + chat window ---------- */
var petStage=document.getElementById("petstage"),petImg=document.getElementById("petimg"),
    petChat=document.getElementById("petchat"),ptf=document.getElementById("ptf"),
    pcNote=document.getElementById("pc-note"),petMenu=document.getElementById("petmenu"),
    petBreath=document.getElementById("petbreath"),pcLoad=document.getElementById("pc-load"),
    petPos=null;
try{petPos=JSON.parse(localStorage.getItem("stratagw.petpos"))||null}catch(e){petPos=null}
function closeChat(){petChat.style.display="none";ptf.src="about:blank"}
window.STRATA_PET={apply:function(on,size){petStage.style.display=on?"block":"none";petImg.style.height=size+"px";if(!on)closeChat();if(on)placePet()}};
window.PETUI={art:function(){if(CARDS&&CARDS._pet&&CARDS._pet.art)petImg.src=CARDS._pet.art},
  state:function(resident){petStage.classList[resident?"add":"remove"]("resident")}};
function placePet(){var w=innerWidth,h=innerHeight;
  if(!petPos)petPos={x:w-40-petSize*0.8,y:h-40-petSize};
  petPos.x=Math.max(8,Math.min(w-56,petPos.x));petPos.y=Math.max(76,Math.min(h-56,petPos.y));
  petStage.style.left=Math.round(petPos.x)+"px";petStage.style.top=Math.round(petPos.y)+"px";
  petStage.style.right="auto";petStage.style.bottom="auto"}
window.addEventListener("resize",placePet);
var pd=null;
petImg.addEventListener("pointerdown",function(e){if(e.button===2)return;pd={x0:e.clientX,y0:e.clientY,ox:petPos?petPos.x:0,oy:petPos?petPos.y:0,moved:false};try{petImg.setPointerCapture(e.pointerId)}catch(err){}});
petImg.addEventListener("pointermove",function(e){if(!pd)return;var dx=e.clientX-pd.x0,dy=e.clientY-pd.y0;
  if(!pd.moved&&Math.abs(dx)+Math.abs(dy)>8)pd.moved=true;
  if(pd.moved){petPos.x=pd.ox+dx;petPos.y=pd.oy+dy;placePet()}});
petImg.addEventListener("pointerup",function(){if(!pd)return;var moved=pd.moved;pd=null;
  if(moved){try{localStorage.setItem("stratagw.petpos",JSON.stringify(petPos))}catch(e){}}
  else toggleChat()});
petImg.addEventListener("contextmenu",function(e){e.preventDefault();petMenu.style.display=petMenu.style.display==="none"?"flex":"none"});
document.addEventListener("click",function(e){if(petMenu.style.display!=="none"&&!petStage.contains(e.target))petMenu.style.display="none"});
document.getElementById("pm-hide").onclick=function(){petOn=false;petT.checked=false;
  try{localStorage.setItem("stratagw.pet","0")}catch(e){}window.STRATA_PET.apply(false,petSize)};
document.getElementById("pm-art").onclick=function(){artTarget="_pet";artInput.click()};
function petAnchor(){var w=Math.min(420,Math.round(innerWidth*0.92)),h=Math.min(600,Math.round(innerHeight*0.72));
  var cx=petPos?petPos.x:innerWidth-w,cy=petPos?petPos.y:innerHeight-160;
  var L=Math.max(8,Math.min(innerWidth-w-8,cx-w*0.25)),T=Math.max(70,Math.min(innerHeight-h-8,cy-h-12));
  petChat.style.left=Math.round(L)+"px";petChat.style.top=Math.round(T)+"px";
  petChat.style.width=w+"px";petChat.style.height=h+"px"}
function toggleChat(){if(petChat.style.display==="flex"){closeChat();return}openChat()}
function openChat(){petAnchor();petChat.style.display="flex";
  var loadedNow=null;
  for(var i=0;i<modelsList.length;i++){if(modelsList[i].loaded){loadedNow=modelsList[i].model;break}}
  if(loadedNow){pcNote.style.display="none";ptf.src="/"}
  else{pcNote.style.display="flex";ptf.src="about:blank"}}
pcLoad.onclick=function(){if(modelsList.length)act("load",modelsList[0].model);closeChat()};
document.getElementById("pc-close").onclick=closeChat;
ptf.addEventListener("load",function(){if(ptf.src.indexOf("about:blank")>=0)return;
  try{var pth=ptf.contentWindow.location.pathname;
    if(pth==="/gateway"){ptf.src="about:blank";pcNote.style.display="flex"}}catch(e){}});
window.STRATA_PET.apply(petOn,petSize);

})();
function paintSpecials(){
  cardNames.forEach(function(n){
    var card=cardsEl.querySelector('[data-model="'+n+'"]');if(!card)return;
    var b=backendOf(n),m=cardMeta(n);
    var ed=card.querySelector('[data-r=editdossier]'),del=card.querySelector('[data-r=delcard]'),
        tg=card.querySelector('[data-r=toggle]'),live=card.querySelector('[data-r=live]');
    if(ed)ed.style.display=(b&&!m)?"":"none";
    if(del)del.style.display=(!b&&m)?"":"none";
    var rm2=card.querySelector('[data-r=rmart]');
    if(rm2)rm2.style.display=(m&&String(m.art||""))?"":"none";
    if(!b){card.dataset.st="orphan";card.classList.add("orphan");
      if(tg){tg.disabled=true}
      if(live)live.textContent=tt("未安装","not installed")}
  });
}
function updateLiveAll(){cardNames.forEach(function(n){
  var c=cardsEl.querySelector('[data-model="'+n+'"]');if(c)updateLive(c,n)});deckHeight()}
function updateLive(card,name){
  var dl=card.querySelector('[data-r=liverows]');if(!dl)return;
  var b=backendOf(name),info=INFO[name]||{},rows=[];
  function row(a,c){rows.push('<div class="srow"><dt>'+esc(a)+'</dt><dd>'+esc(c)+'</dd></div>')}
  if(!b){row(tt("状态","status"),tt("未安装 · 本机没有这个后端","not installed on this machine"))}
  else{row(tt("端口","port"),":"+b.port);
    row(tt("进程","process"),b.alive?tt("在线","up"):tt("待冷启动","cold-start pending"));
    row(tt("驻留","resident"),b.loaded?tt("在位","on GPU"):tt("待载入","not loaded"))}
  if(info.alive===false)row(tt("健康检查","health"),tt("后端离线","offline"));
  if(info.max_context)row(tt("最大上下文","max context"),Math.round(info.max_context/1024)+"K");
  if(info.images!=null)row(tt("图像输入","vision"),info.images?tt("有","yes"):tt("无","no"));
  var eng=(name===selName&&mon.data&&mon.data.engine)?mon.data.engine:null;
  if(eng){if(eng.version!=null)row(tt("引擎版本","engine"),String(eng.version));
    if(eng.expert_slots!=null&&eng.expert_cache_mib!=null)row(tt("专家缓存","expert cache"),num(eng.expert_slots)+tt(" 槽 · "," slots · ")+gbf(eng.expert_cache_mib*1048576,1)+" GB");
    if(eng.kv!=null)row(tt("KV 量化","KV quant"),String(eng.kv))}
  if(name===selName&&mon.data&&mon.data.hardware){var hw=mon.data.hardware;
    if(hw.gpu_mem_total!=null)row(tt("显存驻留","VRAM"),gbf(hw.gpu_mem_used,1)+" / "+gbf(hw.gpu_mem_total,0)+" GB");
    if(hw.ram_total!=null)row(tt("系统内存","RAM"),gbf(hw.ram_used,1)+" / "+gbf(hw.ram_total,0)+" GB")}
  dl.innerHTML=rows.length?rows.join(""):'<div class="srow"><dt>'+esc(tt("实时档案","live dossier"))+'</dt><dd>'+esc(tt("等待该后端报告…","awaiting backend report…"))+'</dd></div>';
}
var ED_PALETTE=["#48c6d8","#f0679a","#8f7bff","#3ba55d","#f5a623","#e05252","#2f80ed","#a0a6b3"];
var edAccent="";
function renderSwatches(){var w=document.getElementById("ed-swatches");if(!w)return;
  w.innerHTML=ED_PALETTE.map(function(c){return '<span class="sw'+(c.toLowerCase()===edAccent?" sel":"")+'" data-c="'+c+'" style="background:'+c+'"></span>'}).join("");
  var i2;for(i2=0;i2<w.children.length;i2++)w.children[i2].onclick=function(){edSetAccent(this.dataset.c)};}
function edSetAccent(c){edAccent=String(c||"").toLowerCase();
  var ci=document.getElementById("ed_accentc");
  if(ci&&/^#[0-9a-f]{6}$/.test(edAccent))ci.value=edAccent;
  renderSwatches();}
function openEdit(name){
  var d=document.getElementById("dossier-edit");if(!d)return;
  d.dataset.model=name;d.style.display="flex";
  var whoEl=document.getElementById("ed-who");if(whoEl)whoEl.textContent=name;
  var m=cardMeta(name)||{};
  var nk=document.getElementById("ed_nick");
  if(nk)nk.value=(m.nick&&(m.nick[LANG]||m.nick.zh||m.nick.en))||"";
  edSetAccent(m.accent&&/^#[0-9a-fA-F]{6}$/.test(m.accent)?m.accent:"");
  var an=document.getElementById("ed-artname");
  if(an)an.textContent=m.art?String(m.art).split("/").pop():"";
}
function saveEdit(){
  var d=document.getElementById("dossier-edit");var name=d&&d.dataset.model;if(!name)return;
  var nk=document.getElementById("ed_nick");var v=nk?nk.value.trim():"";
  var card={nick:{zh:v||name,en:v||name}};
  if(edAccent)card.accent=edAccent;
  postj("router/cards",{model:name,card:card},function(rj){
    if(rj[0]>=400){say(tt("保存卡片失败 HTTP ","card save failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    say(tt("卡片已保存。","card saved."),"");
    d.style.display="none";
    fetchCards(function(){sig="";refresh()});
  });
}
(function(){var ci=document.getElementById("ed_accentc");
  if(ci)ci.oninput=function(){edSetAccent(ci.value)};
  var up=document.getElementById("ed-artup");
  if(up)up.onclick=function(){var d=document.getElementById("dossier-edit");artTarget=d&&d.dataset.model;artInput.click()};})();
function delCard(name){
  fetch("router/cards/"+encodeURIComponent(name),{method:"DELETE"}).then(function(r){
    return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
    .then(function(rj){
      if(rj[0]>=400){say(tt("删除卡片失败 HTTP ","card delete failed HTTP ")+rj[0],"err");return}
      say(tt("卡片已删除（写回 cards.json，重启不回潮）。","card deleted (persisted to cards.json)."),"");
      fetchCards(function(){sig="";refresh()});
    })
    .catch(function(e){say(tt("删除失败: ","delete failed: ")+e,"err")});
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
    tg.textContent=act2?(act2.op==="load"?tt("载入中…","loading…"):tt("卸载中…","unloading…")):(willUnload?tt("卸载","Unload"):tt("载入","Load"));
    tg.className=act2?(act2.op==="load"?"load":"warnbtn"):(willUnload?"warnbtn":"load");
    tg.disabled=(st==="down"||busyNow);
    if(act2){ring.classList.add("on");
      var e0=Math.round((Date.now()-act2.t0)/1000);
      el.textContent=e0<100?(e0+"s"):(Math.floor(e0/60)+"m"+("0"+(e0%60)).slice(-2)+"s");}
    else ring.classList.remove("on");
    var lv=mon.data&&mon.data.live?mon.data.live:null;
    if(st==="down")live.textContent=tt("离线","offline");
    else if(act2)live.textContent=(act2.op==="load"?tt("请上卡","yield ask"):tt("让卡中","yielding"));
    else if(st==="loaded")live.textContent=(lv&&lv.state==="generating")?(fnum(lv.tok_s,1)+" tok/s"):
      ((lv&&lv.state==="reading")?tt("读提示词","prompt decode"):tt("静驻","idle resident"));
    else live.textContent=tt("待加载","not loaded");
  });
}
function refresh(){
  fetch("router/backends").then(function(r){return r.json()}).then(function(d){
    var list=d.backends||[];modelsList=list;
    applyLang();syncLangBtn();
    var names=cardNameList();
    if(names.join("|")!==sig){sig=names.join("|");build(names);buildSeg()}
    list.forEach(function(b){
      var was=prev[b.model];
      if(was===false&&b.loaded===true){
        say(b.model+tt(" 已载入 —— monitor 已就绪，页面见下方。"," loaded — monitor ready below."),"busy");
        var sec=document.getElementById("sec-monitor");
        sec.classList.remove("flash");void sec.offsetWidth;sec.classList.add("flash");
        sec.scrollIntoView({behavior:"smooth",block:"start"});
      }else if(was===true&&b.loaded===false&&!b.busy){
        say(b.model+tt(" 已卸载，显存已让出。"," unloaded, VRAM released."),"");
      }
      prev[b.model]=b.loaded;
    });
    var anyLoaded=list.some(function(b){return b.loaded});
    var loadedNow=list.filter(function(b){return b.loaded});
    if(window.PETUI)window.PETUI.state(anyLoaded);
    if(!selName||!list.some(function(b){return b.model===selName})){
      if(loadedNow[0]||list[0])selectModel((loadedNow[0]||list[0]).model,true);
    }else if(selName&&loadedNow.length&&loadedNow.every(function(b){return b.model!==selName})){
      selectModel(loadedNow[0].model,true);
    }
    paint(list);paintSpecials();updateLiveAll();renderArch(list);
  }).catch(function(e){say(tt("读后端列表失败: ","backend list read failed: ")+e,"err")});
  fetchGpu();
}
function act(op,name){
  if(ops[name])return;
  ops[name]={op:op,t0:Date.now()};
  refresh();
  fetch(op,{method:"POST",headers:hdrs(true),body:JSON.stringify({model:name})})
    .then(function(r){return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
    .then(function(rj){
      if(rj[0]>=400){delete ops[name];
        say(op+" "+name+tt(" 失败 HTTP "," failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");
        refresh()}
    })
    .catch(function(e){delete ops[name];say(op+" "+name+tt(" 失败: "," failed: ")+e,"err");refresh()});
}

/* ---------------- monitor ---------------- */
var TILES=[
  {key:"decode",label:tt("解码速度","decode speed"),unit:"tok/s",series:"tok_s",dec:1},
  {key:"prefill",label:tt("预填速度","prefill speed"),unit:"tok/s",series:"prefill_tok_s_mean"},
  {key:"gpu",label:tt("GPU 负载","GPU load"),unit:"%",series:"gpu_util"},
  {key:"vram",label:tt("显存占用","VRAM use"),unit:"GB",series:"gpu_mem_used"},
  {key:"temp",label:tt("GPU 温度","GPU temp"),unit:"°C",series:"gpu_temp"},
  {key:"power",label:tt("GPU 功耗","GPU power"),unit:"W",series:"gpu_power"},
  {key:"pcie",label:tt("PCIe→显存","PCIe→VRAM"),unit:"MB/s",series:"gpu_pcie_rx_mb"},
  {key:"cpu",label:"CPU",unit:"%",series:"cpu",alt:true},
  {key:"disk",label:tt("磁盘读取","disk read"),unit:"MB/s",series:"disk_read_mb"}
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
        '<div class="val">–<small>'+m.unit+'</small></div><div class="sub">'+tt("载入后点亮","lights up once loaded")+'</div>'+flatSpark()+'</div>';
    }).join("")+
    '<div class="tile ph"><div class="lab">'+tt("上下文填充","ctx fill")+'</div><div class="val">–<small>%</small></div><div class="sub">'+tt("最近请求占窗口比","recent req / window")+'</div><div class="pbar"><i style="width:0"></i></div></div>'+
    '<div class="tile ph"><div class="lab">'+tt("显存专家缓存","expert cache")+'</div><div class="val">–<small>'+tt("槽","slots")+'</small></div><div class="sub">'+tt("热专家占显存比","hot experts / VRAM")+'</div><div class="pbar"><i style="width:0"></i></div></div>'+
    '<div class="tile ph"><div class="lab">'+tt("系统内存","system RAM")+'</div><div class="val">–<small>GB</small></div><div class="sub">'+tt("引擎常驻水位","engine floor")+'</div><div class="pbar ram"><i style="width:0"></i></div></div>';
}
var FIN={stop:["ok",tt("已完成","done")],length:["len",tt("触上限","limit")],cancel:["stop",tt("已停止","stopped")],disconnect:["stop",tt("已断开","gone")],error:["err",tt("错误","error")],timeout:["stop",tt("超时","timeout")]};
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
  bar.style.setProperty("--ac",accentFor(selName||""));
  chip.className="";det.textContent="";who.textContent=selName?"· "+selName:"";prog.style.width="0";
  var d=mon.data;
  if(!d){
    chip.textContent=tt("待载入","pending");
    det.textContent=tt("拿不到 /metrics——多半是页脚 api key 没填，或该后端进程未起","/metrics unavailable — set the footer api key, or check that the backend is running");
    phTiles();strip.textContent="";
    tb.innerHTML=phRow().repeat(TROWS);
    hint.textContent=tt("尚无请求记录——统计从引擎启动起累计","no requests yet — counters run since engine start");
    return;
  }
  var eng=d.engine||{},lv=d.live||{},hw=d.hardware||{},st=d.hardware_static||{},
      h=d.history||{},t=d.totals||{};
  var requests=d.requests||[],last=requests[0]||null;
  var loaded=modelsList.some(function(b){return b.model===selName&&b.loaded});
  var state=lv.state||"unloaded";
  if(loaded&&lv.queued>0&&state!=="generating"&&state!=="reading")state="queued";
  var STATE={idle:tt("待机","standby"),reading:tt("读提示词","prompt decode"),generating:tt("生成中","generating"),queued:tt("排队中","queued"),unloaded:tt("已卸载","offloaded"),error:tt("异常","stale")};
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
    det.textContent=(lv.queued||0)+tt(" 个请求排队 · 先让上一个说完"," queued · let the previous one finish");
  }else if(state==="idle"){
    chip.className="idle";
    det.textContent=last?(tt("上次: ","last: ")+num(last.output_tokens)+" tok · "+fnum(last.decode_tok_s,1)+" tok/s"):tt("等待请求","idle");
  }else{
    det.textContent=tt("引擎未驻留——下方硬件读数仍是实时的（画布出图也在同一块卡上）","engine not resident — the hardware readings below stay live (canvas output shares the same GPU)");
  }
  var decodeAvg=(t.decode_ms&&t.output_tokens)?t.output_tokens/(t.decode_ms/1000):null;
  var readTok=(t.prompt_tokens||0)-(t.reused||0);
  var avgPrefill=(t.prompt_ms>0&&readTok>0)?readTok/(t.prompt_ms/1000):null;
  var decodeV=(state==="generating")?lv.tok_s:(decodeAvg!=null?decodeAvg:(last?last.decode_tok_s:null));
  var prefillV=(lv.state&&lv.state!=="idle"&&lv.prefill_tok_s_mean!=null)?lv.prefill_tok_s_mean
              :(avgPrefill!=null?avgPrefill
              :(last&&last.prompt_ms>0?Math.max(0,(last.prompt_tokens||0)-(last.reused||0))/(last.prompt_ms/1000):null));
  var speedSub=state==="generating"?tt("当前 decode","current decode"):(decodeAvg!=null?tt("decode · 运行均值","decode · run mean"):(last?tt("上次请求","last req"):tt("等待首次","awaiting first")));
  var preSub=state==="reading"?tt("当前 prefill","current prefill"):(avgPrefill!=null?tt("prefill · 运行均值","prefill · run mean"):(last?tt("上次请求","last req"):tt("等待首次","awaiting first")));
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
    else if(m.key==="gpu"){val=fnum(hw.gpu_util,0);sub2=st.gpu_name?esc(st.gpu_name):tt("利用率","util");amax=100}
    else if(m.key==="vram"){val=gbf(hw.gpu_mem_used,1);
      sub2=eng.expert_slots?(num(eng.expert_slots)+" experts cached"):(hw.gpu_mem_total?(tt("共 ","total ")+gbf(hw.gpu_mem_total,0)+" GB"):"");amax=hw.gpu_mem_total}
    else if(m.key==="temp"){val=fnum(hw.gpu_temp,0);sub2=tt("阈值 90°C","thresh 90°C");amax=90}
    else if(m.key==="power"){val=fnum(hw.gpu_power,0);sub2=hw.gpu_power_limit?(tt("上限 ","cap ")+fnum(hw.gpu_power_limit,0)+" W"):"";amax=hw.gpu_power_limit}
    else if(m.key==="pcie"){val=fnum(hw.gpu_pcie_rx_mb,(hw.gpu_pcie_rx_mb!=null&&hw.gpu_pcie_rx_mb<10)?1:0);
      sub2="Gen"+(hw.gpu_pcie_gen_max||hw.gpu_pcie_gen||"?")+(hw.gpu_pcie_width?(" x"+hw.gpu_pcie_width):"")}
    else if(m.key==="cpu"){val=fnum(hw.cpu,0);sub2=st.threads?((st.cores?st.cores+tt(" 核 · "," cores · "):"")+st.threads+tt(" 线程"," threads")):tt("负载","load");amax=100}
    else{var rd=hw.disk_read_mb;val=rd==null?"–":fnum(rd,rd<10?1:0);
      sub2=hw.disk_write_mb==null?(st.psutil?"":tt("需 psutil","psutil needed")):(tt("写 ","write ")+fnum(hw.disk_write_mb,1)+" MB/s")}
    tiles.push(std(m,val,m.unit,sub2,amax));
  });
  var ctx=eng.max_context||0,usedNow=0;
  if(state==="reading"||state==="generating")usedNow=(lv.prompt_tokens||0)+(lv.generated||0);
  else if(last)usedNow=(last.prompt_tokens||0)+(last.output_tokens||0);
  var frac=ctx?Math.min(1,usedNow/ctx):0;
  tiles.push('<div class="tile"><div class="lab">'+tt("上下文填充","ctx fill")+'</div><div class="val">'+Math.round(frac*100)+
    '<small>%</small></div><div class="sub">'+(ctx?(kfmt(usedNow)+" / "+Math.round(ctx/1024)+"K tok"):"–")+'</div>'+
    '<div class="pbar"><i style="width:'+(frac*100).toFixed(1)+'%"></i></div></div>');
  var cacheBytes=(eng.expert_cache_mib||0)*1048576;
  var cacheFrac=(hw.gpu_mem_total&&cacheBytes)?Math.min(1,cacheBytes/hw.gpu_mem_total):0;
  tiles.push('<div class="tile alt"><div class="lab">'+tt("显存专家缓存","expert cache")+'</div><div class="val">'+
    (eng.expert_slots!=null?num(eng.expert_slots):"–")+'<small>'+tt("槽","slots")+'</small></div><div class="sub">'+
    (cacheBytes?(gbf(cacheBytes,1)+" GB · "+Math.round(cacheFrac*100)+tt("% 显存","% VRAM")):"–")+'</div>'+
    '<div class="pbar warm"><i style="width:'+(cacheFrac*100).toFixed(1)+'%"></i></div></div>');
  var rp=(hw.ram_total&&hw.ram_used!=null)?Math.min(100,100*hw.ram_used/hw.ram_total):0;
  tiles.push('<div class="tile"><div class="lab">'+tt("系统内存","system RAM")+'</div><div class="val">'+
    (hw.ram_used!=null?gbf(hw.ram_used,1):"–")+'<small>GB</small></div><div class="sub">'+
    (hw.ram_total?(tt("共 ","total ")+gbf(hw.ram_total,0)+tt(" GB · 水位 "," GB · floor ")+Math.round(rp)+"%"):"–")+'</div>'+
    '<div class="pbar ram'+(rp>92?" hot":"")+'"><i style="width:'+rp.toFixed(1)+'%"></i></div></div>');
  document.getElementById("mon").innerHTML=tiles.join("");
  
  if(t.requests){
    var pS=t.prompt_ms>0&&readTok>0?(" @ "+fnum(readTok/(t.prompt_ms/1000),0)+" tok/s"):"";
    var oS=t.decode_ms>0&&t.output_tokens>0?(" @ "+fnum(t.output_tokens/(t.decode_ms/1000),1)+" tok/s"):"";
    var since=t.since?new Date(t.since*1000):null;
    var _hm=since?("0"+since.getHours()).slice(-2)+":"+("0"+since.getMinutes()).slice(-2):"";
    var stime=!since||since.getFullYear()<=2020?tt("启动","booted"):LANG==="zh"?
      ((since.getMonth()+1)+"\u6708"+since.getDate()+"\u65e5 "+_hm):
      (since.toLocaleDateString("en-US",{month:"short",day:"numeric"})+" "+_hm);
    strip.innerHTML=tt("自 ","since ")+stime+tt(" 起：<b>"," · <b>")+num(t.requests)+tt("</b> 次请求 · 读取 prompt <b>","</b> reqs · prompt reads <b>")+num(readTok)+"</b> tok"+pS+
      tt("（复用 <b>"," (cached <b>")+num(t.reused)+tt("</b>） · 生成 <b>","</b>) · generated <b>")+num(t.output_tokens)+"</b> tok"+oS;
  }else strip.textContent=tt("本次会话尚无请求——统计从引擎启动起累计","no requests this session — counters run since engine start");
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
  hint.textContent=(d.requests_kept>TROWS)?(tt("留存 ","kept ")+d.requests_kept+tt(" 条 · 表内显示最近 "," rows · table shows the latest ")+TROWS+tt(" 条"," rows")):(requests.length?"":tt("尚无请求记录——统计从引擎启动起累计","no requests yet — counters run since engine start"));
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
    btn.textContent=cardNick(b.model);
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
    if(rj[0]>=400){say(tt("保存采样失败 HTTP ","sampling save failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    say(tt("采样默认已保存到 ","sampling defaults saved to ")+selName+tt("（即时生效）。"," (live now)."),"");
    if(rj[1].defaults){/* server may normalize; leave form as is */}
  });
};
document.getElementById("s-clear").onclick=function(){
  if(!selName)return;
  postj("router/settings?model="+encodeURIComponent(selName),{defaults:null},function(rj){
    if(rj[0]>=400){say(tt("清除失败 HTTP ","clear failed HTTP ")+rj[0],"err");return}
    say(tt("已清除：","cleared: ")+selName+tt(" 交回各客户端自带的参数。"," — clients fall back to their own params."),"");
    loadSettings();
  });
};
var cfgKeys=[];
var CFGNOTE=tt("后端 /config 白名单键。保存时 Strata 官方会自动备份配置 json；改动从该模型下次启动起生效。留空 = 删除该键（回默认）。","Whitelisted /config keys. Saving auto-backs-up the engine config json; changes apply at the model's next boot. Blank = remove the key (back to default).");
function loadConfig(){
  if(!selName)return;
  qs("router/config?model="+encodeURIComponent(selName),function(d){
    cfgKeys=d.keys||[];
    document.getElementById("cfg-note").textContent=(d.note||CFGNOTE)+(d.file?(tt("（文件: ","(file: ")+d.file+"）"):"");
    var wrap=document.getElementById("cfg-list");wrap.innerHTML="";
    cfgKeys.forEach(function(k){
      var row=document.createElement("div");row.className="crow";
      var inputHtml="";
      if(k.kind==="bool"){
        inputHtml='<span class="chk"><input type="checkbox" data-ck="'+esc(k.key)+'"'+(k.value?" checked":"")+'>'+
          '<span>'+(k.value==null?tt("默认","default"):"")+'</span></span>';
      }else if(k.kind==="enum"){
        inputHtml='<select data-ck="'+esc(k.key)+'"><option value="">'+tt("默认","default")+'</option>'+
          (k.choices||[]).map(function(c){return '<option value="'+esc(c)+'"'+(k.value===c?" selected":"")+'>'+esc(c)+'</option>'}).join("")+'</select>';
      }else{
        inputHtml='<input type="text" inputmode="'+(k.kind==="number"?"decimal":"text")+'" data-ck="'+esc(k.key)+'" value="'+(k.value==null?"":esc(String(k.value)))+'" placeholder=tt("默认","default")>';
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
    if(rj[0]>=400){say(tt("保存 Model settings 失败 HTTP ","model settings save failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");return}
    var ch=(rj[1].changed||[]);
    say(tt("Model settings 已写入 ","model settings written to ")+selName+"（"+(ch.length?tt("改动: ","changed: ")+ch.join(", "):tt("无改动","no changes"))+"）— "+tt("下次启动该模型时生效。","takes effect next time this model starts."),"busy");
    loadConfig();
  });
};

/* ---------------- about / engine info ---------------- */
function loadInfo(){
  qs("router/info",function(d){
    INFO=d.models||{};
    var b=d.build||{},a=d.app||{},rows=[];
    rows.push([tt("Strata 本体","Strata core"),"v"+String(a.version||"?").replace(/^v/,"")+(a.commit?(" @"+String(a.commit).slice(0,8)):"")]);
    rows.push([tt("引擎版本","engine version"),b.version?"v"+b.version:"—"]);
    rows.push([tt("构建","build"),(b.source||"—")+(b.commit?(" @"+String(b.commit).slice(0,8)):"")]);
    rows.push(["CUDA",(b.cuda||"?")+(b.vision?(" · vision "+b.vision):"")]);
    rows.push([tt("预编架构","built arch"),(b.archs||[]).join("/")+tt(" 本机 sm_"," · sm_ on this box")+((b.archs||[]).indexOf(86)>=0?"86":"?")]);
    var ms=d.models||{};
    Object.keys(ms).forEach(function(n){
      var m=ms[n];
      rows.push([cardNick(n),m.alive?(tt("上下文 ","ctx ")+Math.round((m.max_context||0)/1024)+"K · vision "+(m.images?tt("有","yes"):tt("无","no"))+(m.loaded?tt(" · 在位"," · live"):tt(" · 待命"," · standby"))):tt("后端离线","backend offline")]);
    });
    rows.push([tt("让卡水位","yield floor"),(d.gpu_free_target_mib==null?tt("自动","auto"):d.gpu_free_target_mib+" MiB")]);
    document.getElementById("eng-kv").innerHTML=rows.map(function(r){
      return '<span class="kvchip">'+esc(r[0])+'<b>'+esc(String(r[1]))+'</b></span>'}).join("");
    updateLiveAll();
  });
}
/* ---------------- dyn ---------------- */
/*ARCH-PURE-START*/
function dgEsc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function dgBackends(models){
  // #dg-backends local coords: cards fill y 14..164, width 150; max 4 + overflow badge
  var MAX=4,H=40,TOP=14,SPAN=150,out=[];
  var shown=models.slice(0,MAX),n=shown.length;
  for(var i=0;i<n;i++){
    var y=n===1?TOP+(SPAN-H)/2:TOP+i*(SPAN-H)/(n-1);
    out.push({card:'<path class="dg-req" d="M-20 82L-3 '+(y+H/2).toFixed(0)+'"/>'
      +'<rect class="dgbe" x="0" y="'+y.toFixed(0)+'" width="150" height="'+H+'" rx="12"/>'
      +'<text class="t" x="12" y="'+(y+17).toFixed(0)+'">'+dgEsc(shown[i].nick||shown[i].model)+'</text>'
      +'<text class="sm" x="12" y="'+(y+32).toFixed(0)+'">lazy :'+shown[i].port+'</text>'});
  }
  if(models.length>MAX)out.push({more:'<text class="xs" x="150" y="'+(TOP-4)+'" text-anchor="end">+'+(models.length-MAX)+'</text>'});
  return out;
}
/*ARCH-PURE-END*/

var I18N=(window.__I18N__&&window.__I18N__.zh)?window.__I18N__:{zh:{},en:{}};
function applyLang(){
  var _ems=document.querySelectorAll("h2.sec em");
  for(var _ei=0;_ei<_ems.length;_ei++)_ems[_ei].style.display=LANG==="en"?"none":"";
  var dict=I18N[LANG]||I18N.zh;
  document.querySelectorAll("[data-i18n]").forEach(function(el){
    var v=dict[el.getAttribute("data-i18n")];
    if(v!=null)el.textContent=v;
  });
  document.querySelectorAll("[data-i18n-html]").forEach(function(el){
    var v=dict[el.getAttribute("data-i18n-html")];
    if(v!=null)el.innerHTML=v;
  });
  document.querySelectorAll("[data-i18n-title]").forEach(function(el){
    var v=dict[el.getAttribute("data-i18n-title")];
    if(v!=null)el.setAttribute("title",v);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(function(el){
    var v=dict[el.getAttribute("data-i18n-ph")];
    if(v!=null)el.setAttribute("placeholder",v);
  });
  if(dict["pg.title"])document.title=dict["pg.title"];
}
function renderArch(backends){
  var g=document.getElementById("dg-backends");
  if(!g)return;
  var list=(backends||[]).map(function(b){
    var c=CARDS[b.model]||{};
    return {nick:c.nick||b.model,port:b.port};
  });
  g.innerHTML=dgBackends(list).map(function(o){return o.card||o.more}).join("");
}

var KIND={load:tt("载入","Load"),unload:tt("让位","yield"),gpu:tt("显存","VRAM"),switch:tt("切换","switch"),backend:tt("后端","backend"),error:tt("异常","stale")};
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
    box.innerHTML=evs.length?"":tt("<p style='color:var(--muted);font-size:.8rem'>还没有事件——加载、卸载、让卡都会出现在这里（网关重启前的记录不留存）。</p>","<p style='color:var(--muted);font-size:.8rem'>no events yet — load / unload / yield all show up here (nothing survives a gateway restart).</p>");
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
      b.textContent=evOpen?(tt("收起 · 只留最近 5 条","collapse · keep the latest 5")):(tt("展开其余 ","show ")+(evs.length-5)+tt(" 条 ▾"," more ▾"));
      b.onclick=function(){evOpen=!evOpen;loadEvents()};
      box.appendChild(b);
    }
  });
}

/* ---------------- 外部显存让卡状态条 ---------------- */
var cfree=document.getElementById("gfree"),cforce=document.getElementById("gforce");
var cfreeBusy=null,cfSeen=null;
function sayFree(res){
  var line=tt("显存释放 ","VRAM freed ")+(res.freed_vram_mib/1024).toFixed(1)+tt(" GB · 内存释放 "," GB · RAM freed ")+(res.freed_ram_mib/1024).toFixed(1)+tt(" GB · 用时 "," GB · took ")+res.waited_s+tt(" 秒","s");
  if(res.force){
    if(res.gave_card)say(tt("强制让卡完成，显卡已让出（清掉任务 ","force give-card done, GPU handed over (cleared ")+res.tasks_cleared+tt(" 个）。"," jobs).")+line,"");
    else say(tt("强制让卡：等了 ","force give-card: waited ")+res.waited_s+tt(" 秒显卡还没让出来（任务被打断后可能还在收尾）。"," s and the GPU has not handed over yet (interrupted jobs may still be wrapping up).")+line,"busy");
  }else{
    if(res.freed_vram_mib>=256)say(tt("温和清理：","gentle cleanup: ")+line,"");
    else say(tt("温和让卡：显存没降——出图任务正在跑不让卡。等它跑完再点，或用强制让卡。","gentle give-card: VRAM unchanged — a running generation refuses to hand over. Wait for it, or use force give-card."),"busy");
  }
}
function doGiveFree(force){
  if(cfreeBusy)return;
  cfreeBusy={op:force?"force":"gentle"};
  fetch("router/gpu/free",{method:"POST",headers:hdrs(true),body:JSON.stringify({force:force})})
    .then(function(r){return r.json().then(function(j){return[r.status,j]}).catch(function(){return[r.status,{}]})})
    .then(function(rj){
      cfreeBusy=null;
      if(rj[0]>=400||!rj[1].ok){say(tt("让卡失败 HTTP ","give-card failed HTTP ")+rj[0]+" "+((rj[1].error&&rj[1].error.message)||""),"err");fetchGpu();return}
      sayFree(rj[1]);
      refresh();
    })
    .catch(function(e){cfreeBusy=null;say(tt("让卡请求失败: ","give-card request failed: ")+e,"err");fetchGpu()});
}
cfree.onclick=function(){doGiveFree(false)};
cforce.onclick=function(){
  if(confirm(tt("强制让卡：会打断正在执行的出图任务并清空排队，然后释放显存。继续吗？","Force yield: interrupts running image jobs, clears the queue, then frees VRAM. Continue?")))doGiveFree(true);
};
function fetchGpu(){
  fetch("router/gpu").then(function(r){return r.json()}).then(function(c){
    var el=document.getElementById("gpuhold"),bar=el.querySelector(".bar i"),lab=el.querySelector("b");
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
    cfree.textContent=(busy&&fr.op==="gentle")?(tt("让卡中… ","yielding… ")+fr.elapsed_s+"s"):tt("让卡","Yield VRAM");
    cforce.textContent=(busy&&fr.op==="force")?(tt("强制让卡中… ","forcing yield… ")+fr.elapsed_s+"s"):tt("强制让卡","Force yield");
    cfree.classList.toggle("busy",busy&&fr.op==="gentle");
    cforce.classList.toggle("busy",busy&&fr.op==="force");
    if(!c.running){lab.textContent=tt("未运行","not running");bar.style.width="100%";return}
    var total=c.vram_total_mib||0,free=c.vram_free_mib||0;
    if(total)bar.style.width=Math.round(free/total*100)+"%";
    function g(v){return(v/1024).toFixed(1)+tt(" GiB 空"," GiB free")}
    var st=free>=(c.free_target_mib||0)?tt("空闲 · ","idle · "):(busy?tt("清理中 · ","cleaning · "):tt("出图占用 · ","image job · "));
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
    svBtn.disabled=true;svBtn.textContent=tt("声音: —","sound: —");return}
  stage.className="on "+bgmode;
  stage.setAttribute("aria-hidden",bgmode==="bg"?"true":"false");
  vid.controls=(bgmode==="solo");
  vid.muted=!(bgsound&&gestured);
  svBtn.disabled=false;svBtn.textContent=bgsound?tt("声音: 开","sound: on"):tt("声音: 关","sound: off");
  playVid()
}
function setBg(m){bgmode=m;try{localStorage.setItem("stratagw.bgmode",m)}catch(e){}paintBg()}
segbg.querySelectorAll("button").forEach(function(b){b.onclick=function(){setBg(b.dataset.bg)}});
svBtn.onclick=function(){if(bgmode==="off")return;bgsound=!bgsound;gestured=true;
  try{localStorage.setItem("stratagw.bgsound",bgsound?"1":"0")}catch(e){}
  vid.muted=!bgsound;svBtn.textContent=bgsound?tt("声音: 开","sound: on"):tt("声音: 关","sound: off")};
stage.addEventListener("click",function(e){if(bgmode==="solo"&&e.target===stage)setBg("off")});
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&bgmode==="solo")setBg("off")});
["pointerdown","keydown"].forEach(function(ev){document.addEventListener(ev,function(){
  if(!gestured){gestured=true;if(bgsound&&bgmode!=="off")vid.muted=false}})});
paintBg();

fetchCards();refresh();setInterval(refresh,2000);
setInterval(pollMetrics,2500);
setInterval(loadEvents,5000);loadEvents();
setInterval(loadInfo,10000);loadInfo();

(function wireDrawer(){
  var d=document.getElementById("dossier-edit");if(!d)return;
  var c=document.getElementById("ed-close"),s=document.getElementById("ed-save");
  if(c)c.onclick=function(){d.style.display="none"};
  if(s)s.onclick=saveEdit;
  d.addEventListener("click",function(e){if(e.target===d)d.style.display="none"});
})();
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
