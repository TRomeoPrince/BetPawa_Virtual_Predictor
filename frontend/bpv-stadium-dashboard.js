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
  const menu=[
    ["dashboard","Dashboard","/client","▦"],
    ["picks","My Picks Hub","/client/picks","▤"],
    ["overs","Overs","/client/overs","↗"],
    ["unders","Unders","/client/unders","↘"],
    ["btts","BTTS","/client/btts","⇄"],
    ["wins","Wins","/client/wins","✓"],
    ["proof","Win Proof","/client#winProofSubmit","▣"],
    ["vip","VIP Predictions","/purchase","♛"]
  ];
  for(const [key,label,url,icon] of menu){
    const anchor=el("a","bpv-side-link");
    anchor.href=url;
    anchor.dataset.section=key;
    if(key==="vip")anchor.title="VIP predictions or subscription plans";
    const glyph=el("span","bpv-side-icon",icon);
    glyph.setAttribute("aria-hidden","true");
    anchor.append(glyph,document.createTextNode(label));
    nav.append(anchor);
    navAnchors.set(key,anchor);
  }
  const adminConsole=el("a","bpv-side-link");
  adminConsole.href="/admin";
  adminConsole.hidden=true;
  adminConsole.append(
    el("span","bpv-side-icon","⚙"),
    document.createTextNode("Admin console")
  );
  nav.append(adminConsole);

  const logOut=el("button","bpv-side-link bpv-side-logout","Sign out");
  logOut.type="button";
  logOut.prepend(el("span","bpv-side-icon","↪"));
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
