/* BPV research: read-only cross-season win-loss cycles.
 * Open on betpawa.ug. Does not place bets, mutate website, export user data,
 * or retrieve any unpublished results. Test only past, completed seasons.
 * Source rules verified against backend/private_rules.py and rules_engine.py.
 * Browser output is a JSON analysis at #bpv-research-done.
 */
(async () => {
 "use strict";
 const ROOT=document.createElement("pre");ROOT.id="bpv-research-done";
 const START=Date.now();
 const ID_RANGE={
  "139430":1728371,"139431":1698065,"139432":1698099,
  "139433":1698133,"139434":1698167,"139435":1728405,
  "139436":1698201,"139437":1698235,"139438":1698269
 }; // ALL first-round IDs were verified from betPawa's published catalog.
 const LEAGUES={"7794":"English","7795":"Spanish","7796":"Italian",
  "9184":"German","9183":"French","13774":"Dutch","13773":"Portuguese"};
 const headers={Accept:"application/json","X-Pawa-Brand":"betpawa-uganda",
  "X-Pawa-Language":"en",deviceType:"web"};
 const defs=[
  ["Original English row 7","English","Over 2.5","row_ht00",7],
  ["Original Spanish HT00→loser","Spanish","Over 2.5","ht00loser"],
  ["Original Italian row 6","Italian","Over 2.5","row_ht00",6],
  ["Original German rank3→loser","German","Over 2.5","rankloser",3],
  ["Original French HT00→winner","French","Over 2.5","ht00winner"],
  ["Original Dutch FT00→same row","Dutch","Over 2.5","row_ft00"],
  ["Original Portuguese 6+→loser","Portuguese","Over 2.5","totallos",6],
  ["English rank1 winner tracker","English","Over 2.5","rankwinner",1],
  ["P2 Dutch 6+→both","Dutch","Over 2.5","totalboth",6],
  ["P2 French last3 O2.5","French","Over 2.5","last3"],
  ["P2 French 5+→home","French","Over 2.5","totalhome",5],
  ["P2 Spanish rank1→away","Spanish","Over 2.5","rankaway",1],
  ["P2 Italian HT00 O2.5→home","Italian","Over 2.5","ht00home"],
  ["P2 Dutch 6+→winner BTTS","Dutch","BTTS Yes","totalwinner",6],
  ["P2 French max-margin→winner BTTS","French","BTTS Yes","maxmarginwinner"],
  ["P2 Spanish both prev O2.5→BTTS","Spanish","BTTS Yes","bothprev"]
 ];
 const endObj={seasons:[],errors:[],patterns:[],elapsedMs:null,partial:false};
 function score(e,t,slug){
  for(const v of(e.results?.participantPeriodResults||[]))
   if(v.participant?.type===t)
    for(const p of(v.periodResults||[]))
     if(p.period?.slug===slug){const n=Number(p.result);return p.result==null?null:Number.isFinite(n)?n:null}
  return null;
 }
 function norm(e){
  const name=String(e.name||"");
  const [home,away]=name.split(" - ");
  if(!home||!away)return null;
  const fh=score(e,"HOME","FULL_TIME_EXCLUDING_OVERTIME");
  const fa=score(e,"AWAY","FULL_TIME_EXCLUDING_OVERTIME");
  const hh=score(e,"HOME","FIRST_HALF"),ha=score(e,"AWAY","FIRST_HALF");
  if([fh,fa,hh,ha].some(x=>x===null))return null;
  return {name,home,away,fh,fa,hh,ha,total:fh+fa};
 }
 const fetchJson=async url=>{
  const response=await fetch(url+(url.includes("?")?"&":"?")+"_cb="+Date.now()+"_"+Math.random(),{
   cache:"no-store",credentials:"include",headers});
  if(!response.ok)throw Error("HTTP "+response.status+" "+url);
  return response.json();
 };
 const choose=(src,target,kind,n,history,md)=>{
  const out=new Map();
  const put=t=>{if(t)out.set(t.name,t)};
  const find=team=>target.find(t=>t.home===team||t.away===team);
  const nth=pos=>target[pos-1];
  const role=(s,r)=>{
   if(r==="both")return[s.home,s.away];
   if(r==="home")return[s.home];
   if(r==="away")return[s.away];
   if(s.fh===s.fa)return[];
   return[r==="winner"?(s.fh>s.fa?s.home:s.away):(s.fh<s.fa?s.home:s.away)];
  };
  const follow=(qual,rol)=>qual.forEach(s=>role(s,rol).forEach(team=>put(find(team))));
  if(kind==="row_ht00") {const s=src[n-1];if(s?.hh===0&&s?.ha===0)put(nth(n))}
  if(kind==="row_ft00")src.forEach(s=>{if(s.fh===0&&s.fa===0)put(nth(s.position))});
  if(kind==="ht00loser"||kind==="ht00winner")follow(src.filter(s=>s.hh===0&&s.ha===0&&s.total>=3&&s.fh!==s.fa),kind.slice(4));
  if(kind==="rankloser"||kind==="rankwinner"||kind==="rankaway"){
   const unique=[...new Set(src.map(s=>s.total))].sort((a,b)=>b-a);
   if(unique.length>=n)follow(src.filter(s=>s.total===unique[n-1]),kind.slice(4));
  }
  if(kind==="totallos"||kind==="totalboth"||kind==="totalhome"||kind==="totalwinner"){
   const rr={totallos:"loser",totalboth:"both",totalhome:"home",totalwinner:"winner"}[kind];
   follow(src.filter(s=>s.total>=n),rr);
  }
  if(kind==="ht00home")follow(src.filter(s=>s.hh===0&&s.ha===0&&s.total>=3),"home");
  if(kind==="maxmarginwinner"){
   const dec=src.filter(s=>s.fh!==s.fa);
   if(dec.length){const mx=Math.max(...dec.map(s=>Math.abs(s.fh-s.fa)));
    follow(dec.filter(s=>Math.abs(s.fh-s.fa)===mx),"winner")}
  }
  if(kind==="last3"){
   for(const t of target)
    for(const team of [t.home,t.away]){
     const prev=[];
     for(let j=md-1;j>=0&&prev.length<3;j--){
      const s=history[j].find(s=>s.home===team||s.away===team);
      if(s)prev.push(s);
     }
     if(prev.length===3&&prev.every(s=>s.total>=3))put(t);
    }
  }
  if(kind==="bothprev"){
   for(const t of target){
    const prev=team=>{
     for(let j=md-1;j>=0;j--){
      const e=history[j].find(s=>s.home===team||s.away===team);
      if(e)return e;
     }
     return null;
    };
    const a=prev(t.home),b=prev(t.away);
    if(a&&b&&a.total>=3&&b.total>=3)put(t);
   }
  }
  return [...out.values()];
 };
 const events=Object.fromEntries(defs.map(d=>[d[0],[]]));
 const counters=Object.fromEntries(defs.map(d=>[d[0],{pickWins:0,pickLosses:0,triggerRounds:0,strictWins:0,strictLosses:0}]));
 const loadOne=async(sid,first)=>{
  const rounds=[],max=34;
  for(let md=0;md<max;md++){
   const r=await fetchJson("/api/sportsbook/virtual/v3/events/list/by-round/"+(first+md));
   const e=r.responses||r.events||r.items||[];
   if(!e.length)throw Error("Empty round "+sid+" md"+(md+1));
   const groups=Object.fromEntries(Object.values(LEAGUES).map(l=>[l,[]]));
   for(const item of e){
    const league=LEAGUES[String(item.competition?.id)];
    if(!league)continue;
    const n=norm(item);
    if(n)groups[league].push(n);
   }
   for(const g of Object.values(groups)){g.sort((a,b)=>a.name.localeCompare(b.name));
    g.forEach((m,i)=>m.position=i+1);}
   rounds.push(groups);
   await new Promise(ok=>setTimeout(ok,100));
  }
  return rounds;
 };
 function runForSeason(sid,rounds){
  const history={};
  for(const league of Object.values(LEAGUES))history[league]=rounds.map(r=>r[league]);
  for(const d of defs){
   const [label,league,market,kind,n]=d;
   for(let md=1;md<34;md++){
    const picks=choose(rounds[md-1][league],rounds[md][league],kind,n,history[league],md);
    if(!picks.length)continue;
    const wins=picks.filter(p=>market==="BTTS Yes"?(p.fh>0&&p.fa>0):p.total>=3).length;
    const losses=picks.length-wins;
    const event={season:sid,md:md+1,picks:picks.length,wins,losses,
     status:losses?"L":"W"};
    events[label].push(event);
    const c=counters[label];
    c.pickWins+=wins;c.pickLosses+=losses;c.triggerRounds++;
    if(losses)c.strictLosses++;else c.strictWins++;
   }
  }
 }
 try{
  const choice=new URL(location.href).searchParams.get("bpv-research");
  const keys=choice?choice.split(",").filter(s=>ID_RANGE[s]):Object.keys(ID_RANGE);
  for(const sid of keys){
   try{
    const rounds=await loadOne(sid,ID_RANGE[sid]);
    runForSeason(sid,rounds);
    endObj.seasons.push({sid,rounds:rounds.length});
   }catch(e){endObj.errors.push({sid,error:String(e)});
    if(/HTTP 429|HTTP 403/.test(String(e)))break;
   }
  }
  const prop=(num,den)=>den?Math.round(1000*num/den)/10:null;
  for(const [label,evs]of Object.entries(events)){
   const c=counters[label];
   const done=[],censored=[],afterLoss=[],after2Loss=[],patternsBySeason={};
   for(const sid of endObj.seasons.map(s=>s.sid)){
    const a=evs.filter(x=>x.season===sid);
    patternsBySeason[sid]=a.map(x=>x.md+":"+x.status).join(" ");
    for(let i=0;i<a.length;i++)if(a[i].status==="L"){
     if(i+1<a.length)afterLoss.push(a[i+1].status);
     if(i>0&&a[i-1].status==="L"&&i+1<a.length)after2Loss.push(a[i+1].status);
     let k=i+1,numW=0;
     while(k<a.length&&a[k].status==="W"){numW++;k++}
     if(k<a.length){
      done.push({season:sid,from:a[i].md,to:a[k].md,wins:numW});
     }else{censored.push({season:sid,from:a[i].md,winsSoFar:numW})}
    }
   }
   // Among completed L -> W^k -> L cycles, count how many wins precede the next loss.
   const counts={0:0,1:0,2:0,3:0,"4+":0};
   done.forEach(x=>counts[x.wins>=4?"4+":x.wins]++);
   const sorted=done.map(x=>x.wins).sort((a,b)=>a-b);
   const med=sorted.length?sorted[Math.floor((sorted.length-1)/2)]:null;
   const sortedCases=done.slice().sort((a,b)=>b.wins-a.wins);
   const splits={};
   for(const [split,ids] of [["earlier6",["139430","139431","139432","139433","139434","139435"]],
                              ["last3",["139436","139437","139438"]]]){
    const eventsIn=evs.filter(x=>ids.includes(x.season));
    const rate=(num,den)=>den?Math.round(1000*num/den)/10:null;
    let afterLoss=[],afterDoubleLoss=[],afterWin=[];
    for(const sid of ids){
     const arr=eventsIn.filter(x=>x.season===sid);
     for(let i=0;i<arr.length-1;i++){
      const a=arr[i].status, next=arr[i+1].status;
      if(a==="L")afterLoss.push(next);
      if(a==="W")afterWin.push(next);
      if(i>0&&a==="L"&&arr[i-1].status==="L")afterDoubleLoss.push(next);
     }
    }
    splits[split]={
     triggers:eventsIn.length,
     roundWins:eventsIn.filter(x=>x.status==="W").length,
     strictRate:rate(eventsIn.filter(x=>x.status==="W").length,eventsIn.length),
     afterLossN:afterLoss.length,
     afterLossWin:afterLoss.filter(x=>x==="W").length,
     afterLossRate:rate(afterLoss.filter(x=>x==="W").length,afterLoss.length),
     afterWinN:afterWin.length,
     afterWinRate:rate(afterWin.filter(x=>x==="W").length,afterWin.length),
     afterDoubleLossN:afterDoubleLoss.length,
     afterDoubleLossWin:afterDoubleLoss.filter(x=>x==="W").length,
     afterDoubleLossRate:rate(afterDoubleLoss.filter(x=>x==="W").length,afterDoubleLoss.length)
    };
   }
   endObj.patterns.push({
    name:label,market:defs.find(x=>x[0]===label)[2],splits,
    picks:c.pickWins+c.pickLosses,pickWins:c.pickWins,pickWinPct:prop(c.pickWins,c.pickWins+c.pickLosses),
    triggered:c.triggerRounds,roundWins:c.strictWins,roundWinPct:prop(c.strictWins,c.triggerRounds),
    postLossNextWinPct:prop(afterLoss.filter(x=>x==="W").length,afterLoss.length),
    postLossNextN:afterLoss.length,postDoubleLossNextWinPct:prop(after2Loss.filter(x=>x==="W").length,after2Loss.length),
    doubleLossN:after2Loss.length,
    completeCycles:done.length,winLengths:counts,medianWinsToNextLoss:med,
    avgWinsToNextLoss:done.length?Math.round(done.reduce((t,x)=>t+x.wins,0)/done.length*100)/100:null,
    longestComplete:sortedCases.slice(0,2),
    incompleteCycles:censored.length,
    traces: Object.fromEntries(Object.entries(patternsBySeason).filter(([sid])=>["139437","139438"].includes(sid)))
   });
  }
  endObj.elapsedMs=Date.now()-START;
  endObj.partial=endObj.seasons.length<Object.keys(ID_RANGE).length;
 }catch(e){endObj.errors.push({fatal:String(e)});endObj.partial=true}
 ROOT.textContent=JSON.stringify(endObj);
 document.body.appendChild(ROOT);
})();