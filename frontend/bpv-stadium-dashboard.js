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
  const symbols = {
    dashboard:"▦",wins:"♜",live:"ϟ",vip:"♛",
    market:"▥",proof:"▣",logout:"↪"
  };
  const shell = el("div","stadium-shell");
  shell.id = "stadium-shell";
  const sidebar = el("aside","stadium-sidebar");
  sidebar.setAttribute("aria-label","Stadium dashboard navigation");
  const sidebarInner = el("div","stadium-sidebar-inner");
  const brand = el("a","stadium-brand");
  brand.href = "/client";
  brand.append(el("span","stadium-brand-mark","BP"));
  const brandName = el("span","","BetPawa ");
  brandName.append(el("b","","Predictor"));
  brand.append(brandName);
  const tier = el("div","stadium-tier","Account tier: Checking…");
  tier.id = "stadium-tier";
  tier.setAttribute("aria-live","polite");
  const nav = el("nav","stadium-nav");
  const links = [
    ["dashboard","Dashboard","/client",!isPicks],
    ["wins","Client Wins","/client/picks",isPicks],
    ["live","Live Selections","/client#stadium-recommendations",false],
    ["vip","VIP Predictions","/client#premiumPicksSection",false],
    ["market","Market Research","/client#marketResearch",isMarket],
    ["proof","Win Proof","/client#winProofSubmit",false]
  ];
  const navAnchors = new Map();
  for (const [id,label,url,current] of links) {
    const anchor = el("a",current?"is-current":"");
    anchor.href = url;
    if (current) anchor.setAttribute("aria-current","page");
    const symbol = el("span","stadium-nav-icon",symbols[id]);
    symbol.setAttribute("aria-hidden","true");
    anchor.append(symbol,document.createTextNode(label));
    nav.append(anchor);
    navAnchors.set(id,anchor);
  }
  // Highlight the destination or active section, not merely the first page
  // the visitor entered. Plain links remain keyboard-accessible and work
  // even with script-disabled browser navigation.
  function activeNavId(){
    if(isMarket) return "market";
    if(isPicks) return "wins";
    switch(location.hash){
      case "#stadium-recommendations": return "live";
      case "#premiumPicksSection": return "vip";
      case "#marketResearch": return "market";
      case "#winProofSubmit": return "proof";
      default: return "dashboard";
    }
  }
  function syncNav(){
    const active=activeNavId();
    for(const [id,a] of navAnchors){
      const selected=id===active;
      a.classList.toggle("is-current",selected);
      if(selected)a.setAttribute("aria-current",id==="wins"||isMarket?"page":"location");
      else a.removeAttribute("aria-current");
    }
  }
  const adminConsole = el("a","","Admin console");
  adminConsole.href="/admin";
  adminConsole.style.display="none"; // revealed for administrators only
  adminConsole.append(el("span","stadium-nav-icon","⚙"));
  nav.append(adminConsole);
  const logOut = el("button","","Sign out");
  logOut.type = "button";
  logOut.append(el("span","stadium-nav-icon",symbols.logout));
  logOut.addEventListener("click",async () => {
    logOut.disabled = true;
    try {await fetch("/api/auth/logout",{method:"POST",credentials:"same-origin"});}
    finally {location.assign("/login");}
  });
  nav.append(logOut);
  const sidebarNote = el("p","stadium-sidebar-note","Independent virtual-football research. Graded picks are not verified wagers. 25+ only.");
  sidebarInner.append(brand,tier,nav,sidebarNote);
  sidebar.append(sidebarInner);

  const overview = el("section","stadium-overview");
  overview.setAttribute("aria-label","Client wins and saved selections");
  const heading = el("div","stadium-heading");
  const headingIcon = el("span","stadium-heading-icon","▥");
  headingIcon.setAttribute("aria-hidden","true");
  const headingCopy = el("div","");
  headingCopy.append(
    el("h1","","Client Wins & Graded Picks"),
    el("p","stadium-subtitle","Your own saved selections, genuine outcomes, and private journal.")
  );
  heading.append(headingIcon,headingCopy);
  overview.append(heading);

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
  const tableHeadTitle = el("h2","","Saved Selections & Results");
  const tableHeadLink = el("a","","View picks");
  tableHeadLink.href = "/client/picks";
  tableHeadLink.style.color = "#00f2a0";
  tableHeadLink.style.fontSize = "12px";
  tableHead.append(tableHeadTitle,tableHeadLink);
  const tableScroll = el("div","stadium-table-scroll");
  const table = el("table","stadium-table");
  table.setAttribute("aria-label","Your saved BPV selections");
  const thead = el("thead","");
  const hr = el("tr","");
  for (const col of ["Virtual matchup","Prediction market","Season / MD","Status"]){
    hr.append(el("th","",col));
  }
  thead.append(hr);
  const tbody = el("tbody","");
  tbody.id = "stadium-picks-rows";
  const initialRow = el("tr","");
  const initialCell = el("td","","Loading saved selections…");
  initialCell.colSpan = 4;
  initialRow.append(initialCell);
  tbody.append(initialRow);
  table.append(thead,tbody);
  tableScroll.append(table);
  const tableDisclaimer = el("p","stadium-disclaimer",
    "Selections are graded against match results; this does not verify a placed bet or a payout.");
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
    el("h2","","Today's Research Picks"),
    el("small","","Markets from BPV's current feed; no invented odds")
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
  const recDis = el("p","stadium-disclaimer","These are historical-pattern research selections, not guaranteed outcomes or bookmaker offers.");
  recPanel.append(recHead,recs,recActions,recDis);
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
  if(isMarket) shell.classList.add("stadium-market-shell");
  if(isMarket) shell.append(sidebar,main);
  else shell.append(sidebar,main,rail);

  // Fragment targets can be inserted after the browser's initial hash scroll,
  // so resolve them again after building the dashboard, and on hash changes.
  const allowedSections = new Set([
    "stadium-recommendations","premiumPicksSection","marketResearch","winProofSubmit"
  ]);
  function jumpToSection(){
    syncNav();
    const id=decodeURIComponent(location.hash.slice(1));
    if(!allowedSections.has(id)) return;
    const target=document.getElementById(id);
    if(target && !target.hidden && getComputedStyle(target).display!=="none"){
      target.scrollIntoView({block:"start",behavior:"auto"});
    }
  }
  window.addEventListener("hashchange",jumpToSection);
  syncNav();
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
    td.colSpan=4;td.className="stadium-empty";
    tr.append(td);tbody.append(tr);
  }
  function showPicks(items){
    tbody.replaceChildren();
    if(!items.length){
      showEmpty("No saved selections yet. Open a market to save your first pick.");
      return;
    }
    for(const item of items){
      const tr=el("tr","");
      const game=el("td","");
      const display=String(item.target_home||"")+" vs "+String(item.target_away||"");
      game.append(el("strong","",display),el("span","stadium-muted",item.league||"Virtual Football"));
      const selection=el("td","",item.expected||"—");
      const when=el("td","","Season "+String(item.season||"—")+" / "+String(item.matchday||"—"));
      const state=String(item.outcome||"PENDING").toUpperCase();
      const status=el("td","");
      status.append(el("span","stadium-status "+(state==="WON"?"won":state==="LOST"?"lost":"pending"),state));
      tr.append(game,selection,when,status);
      tbody.append(tr);
    }
  }
  async function getJSON(path){
    const response=await fetch(path,{credentials:"same-origin",cache:"no-store"});
    if(!response.ok) throw new Error(response.status===403?"Subscription or released access required":"Data currently unavailable");
    return response.json();
  }
  async function loadAccount(){
    try{
      const response=await getJSON("/api/auth/me");
      const account=response.account||{};
      const label=account.role==="admin"?"Account Tier — Admin":
                  account.subscription?.is_active?"Account Tier — VIP Active":
                  "Account Tier — Free Member";
      tier.textContent=label;
      adminConsole.style.display=account.role==="admin"?"flex":"none";
      // Free members must not be sent to a hidden VIP-only table.
      // They get the actual upgrade page instead, without leaking VIP data.
      const vipAllowed=account.role==="admin"||!!account.subscription?.is_active;
      const vipLink=navAnchors.get("vip");
      if(vipLink){
        vipLink.href=vipAllowed?"/client#premiumPicksSection":"/purchase";
        vipLink.title=vipAllowed?"Open VIP picks":"Explore VIP access plans";
      }
      if(isDashboard && location.hash==="#premiumPicksSection" && !vipAllowed){
        location.replace("/purchase");
      }
    }catch(_){tier.textContent="Account tier unavailable";}
  }
  async function loadSaved(){
    try{
      const data=await getJSON("/api/client/picks?category=all&scope=all&outcome=all&limit=12&offset=0");
      const s=data.summary||{};
      const rate=s.win_rate;
      document.getElementById("stadium-win-rate").textContent=
        rate==null?"—":(Number(rate)*100).toFixed(1)+"%";
      document.getElementById("stadium-win-total").textContent=Number(s.wins||0).toLocaleString("en-UG");
      document.getElementById("stadium-pick-total").textContent=Number(s.total||0).toLocaleString("en-UG");
      showPicks(data.items||[]);
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
      const data=await getJSON("/api/recommended-picks");
      const predictions=(data.predictions||[]).filter(p=>
        p && p.expected && p.target_home && p.target_away);
      recs.replaceChildren();
      if(!predictions.length){
        recs.append(el("p","stadium-empty","No qualifying research picks in the current published matchday."));
        return;
      }
      const rows=predictions.slice(0,6);
      for(const item of rows){
        const card=el("div","stadium-rec");
        const fixture=String(item.target_home)+" vs "+String(item.target_away);
        card.append(el("strong","",fixture),
                    el("span","stadium-rec-market",item.expected),
                    el("small","","Season "+String(data.season||"—")+
                      " · MD "+String(data.next_matchday||"—")+" · "+String(item.league||"Virtual Football")));
        recs.append(card);
      }
      copyText=rows.map(p=>p.target_home+" vs "+p.target_away+
        " — "+p.expected+" ("+p.league+")").join("\n");
      copy.disabled=false;
    }catch(error){
      recs.replaceChildren(el("p","stadium-empty",
        error.message==="Subscription or released access required"?
        "Recommendations are available with VIP or during an active Free release.":
        "Recommendations are temporarily unavailable. Try again later."));
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
