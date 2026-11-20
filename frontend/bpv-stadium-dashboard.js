/* Stadium Neon client layout, built from existing account-scoped BPV APIs.
   No simulated wagers, performance percentages, confidence or bookmaker odds.
   The layout is visible ONLY when this browser chooses Stadium Neon.
   Other saved themes and all existing client pages/functions remain intact. */
(() => {
  "use strict";
  const page = location.pathname;
  const supportedMarkets = new Set(["overs","unders","btts","wins"]);
  const isMarket = /^\/client\/(overs|unders|btts|wins)$/.test(page);
  if (page !== "/client" && page !== "/client/picks" && !isMarket) return;
  const main = document.querySelector("main");
  if (!main || document.getElementById("stadium-shell")) return;
  const isPicks = page === "/client/picks";
  const isDashboard = page === "/client";
  const el = (tag, className, text) => {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text != null) result.textContent = String(text);
    return result;
  };
  const money = value => Math.round(value).toLocaleString("en-UG", {maximumFractionDigits:0});
  // Unified left navigation for every theme. Use real routes and native
  // anchors; the sidebar is not a decorative mockup or a second top toolbar.
  const shell = el("div","stadium-shell");
  shell.id = "stadium-shell";
  const sidebar = el("aside","bpv-sidebar");
  sidebar.id = "bpv-client-sidebar";
  sidebar.setAttribute("aria-label","BPV navigation sidebar");

  const brand = el("a","bpv-sidebar-brand");
  brand.href="/client";
  brand.append(el("span","bpv-sidebar-logo","BP"));
  const brandText=el("span","bpv-sidebar-brand-text","BetPawa ");
  brandText.append(el("b","","Predictor"));
  brand.append(brandText);

  const closeSidebar=el("button","bpv-sidebar-close","✕");
  closeSidebar.type="button";
  closeSidebar.setAttribute("aria-label","Close navigation");
  closeSidebar.setAttribute("aria-controls","bpv-client-sidebar");

  const sideHeading=el("div","bpv-sidebar-heading");
  sideHeading.append(brand,closeSidebar);

  const tier=el("span","bpv-sidebar-tier","Checking access…");
  tier.setAttribute("aria-live","polite");
  const nav=el("nav","bpv-side-nav");
  nav.setAttribute("aria-label","BPV primary navigation");
  const navAnchors=new Map();
  // Consistent 20px outline icons instead of mixed-weight Unicode glyphs.
  // These local SVG paths avoid external icon fonts and render on all devices.
  const iconPaths=Object.freeze({
    dashboard:["M3 3h7v7H3z","M14 3h7v7h-7z","M14 14h7v7h-7z","M3 14h7v7H3z"],
    picks:["M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"],
    overs:["m22 7-8.5 8.5-5-5L2 17","M16 7h6v6"],
    unders:["m22 17-8.5-8.5-5 5L2 7","M16 17h6v-6"],
    btts:["m8 3-4 4 4 4","M4 7h16","m16 21 4-4-4-4","M20 17H4"],
    wins:["M8 21h8","M12 17v4","M7 3h10v7a5 5 0 0 1-10 0V3Z","M7 5H4v3a4 4 0 0 0 4 4","M17 5h3v3a4 4 0 0 1-4 4"],
    proof:["M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z","M8 8h.01","m3 17 5-5 4 4 3-3 6 6"],
    vip:["m2 8 5 4 5-7 5 7 5-4-2 11H4L2 8Z","M4 19h16"],
    admin:["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z","M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06-1.94 1.94-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.52V21h-2.74v-.05a1.65 1.65 0 0 0-1-1.52 1.65 1.65 0 0 0-1.82.33l-.06.06-1.94-1.94.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.52-1H5v-2.74h.05a1.65 1.65 0 0 0 1.52-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06 1.94-1.94.06.06a1.65 1.65 0 0 0 1.82.33 1.65 1.65 0 0 0 1-1.52V5h2.74v.05a1.65 1.65 0 0 0 1 1.52 1.65 1.65 0 0 0 1.82-.33l.06-.06 1.94 1.94-.06.06a1.65 1.65 0 0 0-.33 1.82 1.65 1.65 0 0 0 1.52 1H20v2.74h-.05a1.65 1.65 0 0 0-1.52 1Z"],
    logout:["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4","M16 17l5-5-5-5","M21 12H9"]
  });
  function navIcon(name){
    const namespace="http://www.w3.org/2000/svg";
    const svg=document.createElementNS(namespace,"svg");
    svg.setAttribute("class","bpv-side-icon");
    svg.setAttribute("viewBox","0 0 24 24");
    svg.setAttribute("width","20");
    svg.setAttribute("height","20");
    svg.setAttribute("fill","none");
    svg.setAttribute("stroke","currentColor");
    svg.setAttribute("stroke-width","1.85");
    svg.setAttribute("stroke-linecap","round");
    svg.setAttribute("stroke-linejoin","round");
    svg.setAttribute("focusable","false");
    svg.setAttribute("aria-hidden","true");
    for(const d of iconPaths[name]||[]){
      const path=document.createElementNS(namespace,"path");
      path.setAttribute("d",d);
      svg.append(path);
    }
    return svg;
  }
  const menu=[
    ["dashboard","Dashboard","/client","dashboard"],
    ["picks","My Picks Hub","/client/picks","picks"],
    ["overs","Overs","/client/overs","overs"],
    ["unders","Unders","/client/unders","unders"],
    ["btts","BTTS","/client/btts","btts"],
    ["wins","Wins","/client/wins","wins"],
    ["proof","Win Proof","/client#winProofSubmit","proof"],
    ["vip","VIP Predictions","/purchase","vip"]
  ];
  for(const [key,label,url,icon] of menu){
    const anchor=el("a","bpv-side-link");
    anchor.href=url;
    anchor.dataset.section=key;
    if(key==="vip")anchor.title="VIP predictions or subscription plans";
    const glyph=navIcon(icon);
    anchor.append(glyph,document.createTextNode(label));
    nav.append(anchor);
    navAnchors.set(key,anchor);
  }
  const adminConsole=el("a","bpv-side-link");
  adminConsole.href="/admin";
  adminConsole.hidden=true;
  adminConsole.append(
    navIcon("admin"),
    document.createTextNode("Admin console")
  );
  nav.append(adminConsole);

  const logOut=el("button","bpv-side-link bpv-side-logout","Sign out");
  logOut.type="button";
  logOut.prepend(navIcon("logout"));
  nav.append(logOut);
  const navNotice=el("span","bpv-side-notice","");
  navNotice.setAttribute("role","status");
  navNotice.setAttribute("aria-live","polite");
  nav.append(navNotice);
  const sideFooter=el("p","bpv-sidebar-footer",
    "25+ only · Independent virtual-football analysis. Betting can be psychologically harmful.");
  sidebar.append(sideHeading,tier,nav,sideFooter);

  // On phones, navigation is an accessible slide-in drawer instead of an
  // overflowing top bar. Desktop users see the full-height sticky sidebar.
  const mobileBar=el("div","bpv-mobile-bar");
  const menuToggle=el("button","bpv-menu-toggle","☰  Menu");
  menuToggle.type="button";
  menuToggle.setAttribute("aria-label","Open navigation");
  menuToggle.setAttribute("aria-controls","bpv-client-sidebar");
  menuToggle.setAttribute("aria-expanded","false");
  const mobileBrand=el("a","bpv-mobile-brand","BPV · Predictor");
  mobileBrand.href="/client";
  mobileBar.append(menuToggle,mobileBrand);
  const backdrop=el("button","bpv-sidebar-backdrop","");
  backdrop.type="button";
  backdrop.hidden=true;
  backdrop.setAttribute("aria-label","Close navigation overlay");
  function closeMenu(restoreFocus=false){
    const wasOpen=sidebar.classList.contains("bpv-sidebar-open");
    sidebar.classList.remove("bpv-sidebar-open");
    menuToggle.setAttribute("aria-expanded","false");
    backdrop.hidden=true;
    if(restoreFocus&&wasOpen)menuToggle.focus();
  }
  function openMenu(){
    sidebar.classList.add("bpv-sidebar-open");
    menuToggle.setAttribute("aria-expanded","true");
    backdrop.hidden=false;
    closeSidebar.focus();
  }
  menuToggle.addEventListener("click",()=>{
    if(sidebar.classList.contains("bpv-sidebar-open"))closeMenu(true);
    else openMenu();
  });
  closeSidebar.addEventListener("click",()=>closeMenu(true));
  backdrop.addEventListener("click",()=>closeMenu(true));
  document.addEventListener("keydown",event=>{
    if(event.key==="Escape"&&sidebar.classList.contains("bpv-sidebar-open")){
      event.preventDefault();
      closeMenu(true);
    }
  });
  nav.addEventListener("click",event=>{
    if(event.target.closest("a"))closeMenu();
  });

  logOut.addEventListener("click",async()=>{
    logOut.disabled=true;
    navNotice.textContent="Signing out…";
    try{
      const response=await fetch("/api/auth/logout",{
        method:"POST",credentials:"same-origin",cache:"no-store"
      });
      if(!response.ok)throw new Error("Sign out failed. Please try again.");
      location.assign("/login");
    }catch(error){
      logOut.disabled=false;
      navNotice.textContent=error.message;
    }
  });
  function navChoice(){
    if(isPicks)return "picks";
    if(isMarket)return page.split("/").pop();
    if(location.hash==="#winProofSubmit")return "proof";
    if(location.hash==="#premiumPicksSection")return "vip";
    return "dashboard";
  }
  function syncNav(){
    const active=navChoice();
    for(const [key,anchor] of navAnchors){
      const chosen=key===active;
      anchor.classList.toggle("is-active",chosen);
      if(chosen)anchor.setAttribute("aria-current",key==="proof"||key==="vip"?"location":"page");
      else anchor.removeAttribute("aria-current");
    }
  }
  syncNav();

  const overview = el("section","stadium-overview");
  overview.setAttribute("aria-label","Client wins and saved selections");
  const heading = el("div","stadium-heading");
  const headingIcon = el("span","stadium-heading-icon","▥");
  headingIcon.setAttribute("aria-hidden","true");
  const headingCopy = el("div","");
  headingCopy.append(
    el("h1","","Client Wins & Graded Picks"),
    el("p","stadium-subtitle","Your saved selections and graded results. Use Overs, Unders, BTTS or Wins above to check the next matchday's live predictions.")
  );
  heading.append(headingIcon,headingCopy);
  overview.append(heading);
  const liveFeedStatus=el("div","stadium-live-feed","Checking the official current season…");
  liveFeedStatus.id="stadium-live-feed";
  liveFeedStatus.setAttribute("role","status");
  liveFeedStatus.setAttribute("aria-live","polite");
  overview.append(liveFeedStatus);

  const stats = el("div","stadium-stats");
  stats.setAttribute("aria-label","Your selection statistics");
  const statInfo = [
    ["stadium-win-rate","Graded hit rate","Only completed saved picks"],
    ["stadium-win-total","Graded wins","Saved selections, not bookmaker bets"],
    ["stadium-pick-total","Selected picks","Your private selection history"],
    ["stadium-journal-profit","Reported net P/L","UGX · self-reported bets only"]
  ];
  for (const [id,label,foot] of statInfo) {
    const card = el("div","stadium-stat");
    card.append(
      el("span","stadium-stat-label",label),
      Object.assign(el("b","stadium-stat-value","—"),{id}),
      el("small","stadium-stat-foot",foot)
    );
    stats.append(card);
  }
  overview.append(stats);

  const tablePanel = el("section","stadium-table-section");
  const tableHead = el("div","stadium-panel-header");
  const tableHeadTitle = el("h2","","Current & Upcoming Saved Selections");
  const tableHeadLink = el("a","","All historical picks");
  tableHeadLink.href = "/client/picks";
  tableHeadLink.style.color = "#00f2a0";
  tableHeadLink.style.fontSize = "12px";
  tableHead.append(tableHeadTitle,tableHeadLink);
  const tableScroll = el("div","stadium-table-scroll");
  const table = el("table","stadium-table");
  table.setAttribute("aria-label","Your saved BPV selections");
  const thead = el("thead","");
  const hr = el("tr","");
  for (const col of ["Virtual matchup","Prediction market","Season / MD","Expected play (EAT)","Status"]){
    hr.append(el("th","",col));
  }
  thead.append(hr);
  const tbody = el("tbody","");
  tbody.id = "stadium-picks-rows";
  const initialRow = el("tr","");
  const initialCell = el("td","","Loading saved selections…");
  initialCell.colSpan = 5;
  initialRow.append(initialCell);
  tbody.append(initialRow);
  table.append(thead,tbody);
  tableScroll.append(table);
  const tableDisclaimer = el("p","stadium-disclaimer",
    "Selections are graded against match results. They are not verified wagers or bookmaker payouts.");
  tablePanel.append(tableHead,tableScroll,tableDisclaimer);
  overview.append(tablePanel);
  if (!isMarket) main.prepend(overview);
  main.classList.add("stadium-content");

  const rail = el("aside","stadium-rail");
  rail.setAttribute("aria-label","Suggested research and calculator");
  const recPanel = el("section","stadium-side-panel");
  const recHead = el("div","stadium-panel-header");
  const recTitle = el("div","");
  recTitle.append(
    el("h2","","Current-Round H2H Picks"),
    el("small","","Shown only when the actual season and upcoming round are verified")
  );
  recHead.append(recTitle);
  const recs = el("div","stadium-recs");
  recs.id="stadium-recommendations";
  recs.append(el("p","stadium-muted","Checking available model selections…"));
  const recActions = el("div","stadium-recs-actions");
  const copy = el("button","","Copy Picks");
  copy.type = "button";
  copy.disabled = true;
  const view = el("a","","View Markets");
  view.href = "/client/overs";
  recActions.append(copy,view);
  const h2hHeading=el("h3","stadium-h2h-title","Reviewed H2H patterns to watch");
  const h2hList=el("div","stadium-h2h-list");
  h2hList.id="stadium-h2h-watchlist";
  const h2hNote=el("p","stadium-disclaimer",
    "Historical research only — these are not confirmed upcoming fixtures. BRE–SUN excluded. No guaranteed wins.");
  const recDis = el("p","stadium-disclaimer",
    "Current-round selections require an exact source schedule and venue/market match; copied picks never include archived watchlist entries.");
  recPanel.append(recHead,recs,recActions,h2hHeading,h2hList,h2hNote,recDis);
  rail.append(recPanel);

  const calcPanel = el("section","stadium-side-panel");
  const calcHead = el("div","stadium-panel-header");
  calcHead.append(el("h2","","ROI Calculator"));
  const calc = el("div","stadium-calc");
  const stakeLabel = el("label","","Your stake (UGX)");
  const stake = el("input","");
  stake.type="number";stake.id="stadium-calc-stake";stake.min="1";stake.step="1";
  stake.placeholder="Enter your stake";stake.inputMode="numeric";
  stakeLabel.append(stake);
  const oddsLabel = el("label","","Decimal odds (enter actual odds)");
  const odds = el("input","");
  odds.type="number";odds.id="stadium-calc-odds";odds.min="1.01";odds.max="1000";odds.step="0.01";
  odds.placeholder="Enter your odds";odds.inputMode="decimal";
  oddsLabel.append(odds);
  const calcResult = el("div","stadium-calc-result");
  const resultFields = [
    ["stadium-calc-return","Potential return"],
    ["stadium-calc-net","Net profit"],
    ["stadium-calc-roi","ROI"]
  ];
  for(const [id,label] of resultFields){
    const group=el("div","");
    group.append(el("small","",label),Object.assign(el("b","","—"),{id}));
    calcResult.append(group);
  }
  const calcNote = el("p","stadium-muted",
    "Illustrative return if the prediction wins. This does not predict the result.");
  calcNote.style.lineHeight="1.5";
  calcNote.style.margin="11px 0 0";
  calc.append(stakeLabel,oddsLabel,calcResult,calcNote);
  calcPanel.append(calcHead,calc);
  rail.append(calcPanel);
  main.parentElement.insertBefore(shell,main);
  if(isMarket)shell.classList.add("stadium-market-shell");
  if(isMarket)shell.append(mobileBar,backdrop,sidebar,main);
  else shell.append(mobileBar,backdrop,sidebar,main,rail);

  // On same-document hashes, scroll after layout creation; on a later page
  // navigation a delayed VIP section may become visible after API hydration.
  const scrollTargets = new Set(["winProofSubmit","premiumPicksSection"]);
  function jumpToSection(){
    syncNav();
    const targetName=location.hash.slice(1);
    if(!scrollTargets.has(targetName)) return;
    const target=document.getElementById(targetName);
    if(target && !target.hidden && getComputedStyle(target).display!=="none"){
      target.scrollIntoView({block:"start",behavior:"auto"});
    }
  }
  window.addEventListener("hashchange",()=>{closeMenu();jumpToSection();});
  if(location.hash) requestAnimationFrame(jumpToSection);

  function calculate(){
    const amount=Number(stake.value),decimal=Number(odds.value);
    const valid=stake.value.trim()!=="" && odds.value.trim()!=="" &&
      Number.isFinite(amount)&&Number.isFinite(decimal)&&amount>0&&decimal>=1.01&&decimal<=1000;
    document.getElementById("stadium-calc-return").textContent=valid?"UGX "+money(amount*decimal):"—";
    document.getElementById("stadium-calc-net").textContent=valid?"UGX "+money(amount*(decimal-1)):"—";
    document.getElementById("stadium-calc-roi").textContent=valid?((decimal-1)*100).toFixed(1)+"%":"—";
  }
  stake.addEventListener("input",calculate);
  odds.addEventListener("input",calculate);

  function showEmpty(message){
    tbody.replaceChildren();
    const tr=el("tr",""),td=el("td","",message);
    td.colSpan=5;td.className="stadium-empty";
    tr.append(td);tbody.append(tr);
  }
  function showPicks(items){
    tbody.replaceChildren();
    if(!items.length){
      showEmpty("No verified current or upcoming saved selections. Older results are kept in My Picks Hub.");
      return;
    }
    for(const item of items){
      const tr=el("tr","");
      const game=el("td","");
      const display=String(item.target_home||"")+" vs "+String(item.target_away||"");
      game.append(el("strong","",display),el("span","stadium-muted",item.league||"Virtual Football"));
      const selection=el("td","",item.expected||"—");
      const when=el("td","","Season "+String(item.season||"—")+" / "+String(item.matchday||"—"));
      const roundTime=window.BPVRoundTime?.savedPick(item)||
        {text:"Not available",label:"Expected play",note:"No schedule"};
      const whenPlays=el("td","stadium-round-time");
      whenPlays.title=roundTime.note;
      whenPlays.append(el("strong","",roundTime.text),
        el("span","stadium-muted",roundTime.label));
      const state=String(item.outcome||"PENDING").toUpperCase();
      const status=el("td","");
      status.append(el("span","stadium-status "+(state==="WON"?"won":state==="LOST"?"lost":"pending"),state));
      tr.append(game,selection,when,whenPlays,status);
      tbody.append(tr);
    }
  }
  async function getJSON(path){
    const response=await fetch(path,{credentials:"same-origin",cache:"no-store"});
    if(!response.ok) throw new Error(response.status===403?"Subscription or released access required":"Data currently unavailable");
    return response.json();
  }
  // One source snapshot drives both the dashboard history filter and the
  // current-round research rail; never treat old saved picks as live.
  const seasonSnapshot=getJSON("/api/virtual/season-status").then(data=>{
    if(data.status!=="live" || !data.current_season || !data.active_round){
      liveFeedStatus.textContent="Current virtual season could not be verified. Past selections remain in My Picks Hub.";
      return null;
    }
    const active=window.BPVRoundTime?.roundWindow(
      data.active_round.round_open_utc,data.active_round.round_close_utc);
    const upcoming=window.BPVRoundTime?.roundWindow(
      data.next_round?.round_open_utc,data.next_round?.round_close_utc);
    liveFeedStatus.textContent=
      "Official feed · Season "+data.current_season+
      " · Playing MD "+data.current_matchday+
      (active?" · "+active.text:"")+
      (upcoming?" · Next MD "+data.next_matchday+" at "+upcoming.text:" · Next round not confirmed")+
      " · Verified "+new Date(data.verified_at_utc).toLocaleTimeString("en-UG",{
        timeZone:"Africa/Kampala",hour:"numeric",minute:"2-digit"
      })+" EAT";
    return data;
  }).catch(()=>{
    liveFeedStatus.textContent=
      "Live season feed unavailable — older picks will not be presented as current.";
    return null;
  });
  function validLiveRound(data,live){
    if(!live || live.status!=="live")return false;
    const next=data?.next_round_close_utc,open=data?.next_round_open_utc;
    if(!next || !open || !Number.isFinite(Date.parse(next)))return false;
    const rightSeason=String(data.season)===String(live.current_season) ||
      (String(data.season)===String(live.upcoming_season)&&live.next_matchday===1);
    return rightSeason &&
      Number(data.next_matchday)===Number(live.next_matchday) &&
      Date.parse(next)>Date.now() && Date.parse(open)<=Date.parse(next);
  }
  async function loadAccount(){
    try{
      const data=await getJSON("/api/auth/me");
      const account=data.account||{};
      const admin=account.role==="admin";
      const vip=admin||!!account.subscription?.is_active;
      tier.textContent=admin?"ADMIN":vip?"VIP":"FREE";
      tier.title=admin?"Administrator access":vip?"Your VIP subscription is active":"Free membership";
      adminConsole.hidden=!admin;
      const vipLink=navAnchors.get("vip");
      vipLink.href=vip?"/client#premiumPicksSection":"/purchase";
      vipLink.title=vip?"View available VIP predictions":"View VIP subscription plans";
      if(isDashboard && location.hash==="#premiumPicksSection"){
        if(!vip) location.replace("/purchase");
        else {
          const section=document.getElementById("premiumPicksSection");
          if(section){
            const observer=new MutationObserver(()=>{
              if(!section.hidden){jumpToSection();observer.disconnect();}
            });
            observer.observe(section,{attributes:true,attributeFilter:["hidden"]});
            if(!section.hidden){jumpToSection();observer.disconnect();}
          }
        }
      }
    }catch(_){
      tier.textContent="Account unavailable";
    }
  }
  async function loadSaved(){
    try{
      const [data,live]=await Promise.all([
        getJSON("/api/client/picks?category=all&scope=all&outcome=all&limit=100&offset=0"),
        seasonSnapshot
      ]);
      const summary=data.summary||{};
      const rate=summary.win_rate;
      document.getElementById("stadium-win-rate").textContent=
        rate==null?"—":(Number(rate)*100).toFixed(1)+"%";
      document.getElementById("stadium-win-total").textContent=
        Number(summary.wins||0).toLocaleString("en-UG");
      document.getElementById("stadium-pick-total").textContent=
        Number(summary.total||0).toLocaleString("en-UG");
      // Never label unverified, expired, graded, or previous-season
      // selections as upcoming merely because the user saved them.
      const current=(data.items||[]).filter(item=>
        live && live.status==="live" &&
        String(item.season)===String(live.current_season) &&
        String(item.outcome||"PENDING").toUpperCase()==="PENDING" &&
        Number(item.matchday)>=Number(live.current_matchday) &&
        item.round_close_utc && Date.parse(item.round_close_utc)>Date.now());
      showPicks(current);
    }catch(error){showEmpty(error.message);}
  }
  async function loadJournal(){
    try{
      const data=await getJSON("/api/client/bet-journal?category=all&outcome=all&limit=1");
      const amount=Number(data.summary?.net_ugx||0);
      const field=document.getElementById("stadium-journal-profit");
      field.textContent=(amount<0?"−":"") +"UGX "+money(Math.abs(amount));
      field.classList.toggle("positive",amount>0);
      field.classList.toggle("negative",amount<0);
    }catch(_){/* leave placeholder, never invent data */}
  }
  let copyText="";
  async function loadRecommended(){
    try{
      const [data,live]=await Promise.all([
        getJSON("/api/recommended-picks"),seasonSnapshot
      ]);
      // Keep exactly the verified market-specific historical patterns
      // requested by the user even when not scheduled in this matchday.
      // The archive is visually separate from actual source-backed picks.
      const catalog=data.reviewed_h2h_patterns||[];
      h2hList.replaceChildren();
      for(const item of catalog){
        const card=el("div","stadium-rec stadium-h2h-item");
        card.append(
          el("strong","",item.home+" vs "+item.away),
          el("span","stadium-rec-market",item.market),
          el("small","",item.validation_wins+"/"+item.validation_tests+
            " archived · Recent "+item.recent_wins+"/"+item.recent_tests+
            " · "+(item.tier==="watch-only"?"Watch only":"Reviewed historical pattern")+
            " · Not currently scheduled")
        );
        h2hList.append(card);
      }
      if(!catalog.length){
        h2hList.append(el("p","stadium-muted","Reviewed H2H archive unavailable."));
      }

      recs.replaceChildren();
      copy.disabled=true;
      copyText="";
      const sourceVerified=validLiveRound(data,live);
      const predictions=sourceVerified?(data.featured_predictions||[]).filter(p=>
        p && p.expected && p.target_home && p.target_away):[];
      if(!sourceVerified){
        recs.append(el("p","stadium-empty",
          "No verified upcoming selection: the model response does not match the current source season and unplayed round. Historical H2H research appears below."));
        return;
      }
      if(!predictions.length){
        recs.append(el("p","stadium-empty",
          "No reviewed H2H candidate appears in the verified upcoming matchday. The archived patterns below are research, not live picks."));
        return;
      }
      const rows=predictions.slice(0,6);
      const roundWindow=window.BPVRoundTime?.roundWindow(
        data.next_round_open_utc,data.next_round_close_utc);
      for(const item of rows){
        const card=el("div","stadium-rec");
        const evidence=item.research_evidence||{};
        const sample=Number.isFinite(evidence.validation_tests)?
          " · Historical "+evidence.validation_wins+"/"+evidence.validation_tests+
          " · Recent "+evidence.recent_wins+"/"+evidence.recent_tests:"";
        card.append(
          el("strong","",item.target_home+" vs "+item.target_away),
          el("span","stadium-rec-market",item.expected),
          el("small","","Source verified · Season "+data.season+
            " · MD "+data.next_matchday+
            (roundWindow?" · "+roundWindow.text:"")+
            sample)
        );
        recs.append(card);
      }
      copyText=rows.map(p=>p.target_home+" vs "+p.target_away+
        " — "+p.expected+" (Season "+data.season+", MD "+data.next_matchday+
        "; researched, not guaranteed)").join("\n");
      copy.disabled=false;
    }catch(error){
      recs.replaceChildren(el("p","stadium-empty",
        error.message==="Subscription or released access required"?
        "Current picks and this research catalog require eligible access.":
        "Current-round picks cannot be verified right now. Try again later."));
      h2hList.replaceChildren(el("p","stadium-muted",
        "H2H research temporarily unavailable."));
      copy.disabled=true;
      copyText="";
    }
  }
  copy.addEventListener("click",async()=>{
    if(!copyText)return;
    try{
      await navigator.clipboard.writeText(copyText);
      copy.textContent="Copied";
    }catch(_){copy.textContent="Copy unavailable";}
  });

  /* The layout doesn't change authorization or grading. It only reads
     information already available to this signed-in BPV account. */
  loadAccount();
  if(!isMarket){
    loadSaved();
    loadJournal();
    loadRecommended();
  }
})();
