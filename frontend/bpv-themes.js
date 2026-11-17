/* BPV shared themes · privacy-first, no account or server storage. */
(function () {
  "use strict";
  var STORAGE_KEY = "bpv-theme-choice-v1";
  var OPTIONS = [
    {id:"system", name:"Follow Device", detail:"Light or dark automatically", sample:"system"},
    {id:"light", name:"Botanical Light", detail:"Clean, natural and bright", sample:"light"},
    {id:"dark", name:"Midnight", detail:"Deep, calm and focused", sample:"dark"},
    {id:"stadium", name:"Stadium Neon", detail:"Floodlights, emerald glow and VIP gold", sample:"stadium"},
    {id:"forest", name:"Forest", detail:"Fresh leaves and pine", sample:"forest"},
    {id:"ocean", name:"Ocean", detail:"Clear blue and sea glass", sample:"ocean"},
    {id:"sunset", name:"Sunset", detail:"Warm peach and terracotta", sample:"sunset"},
    {id:"violet", name:"Royal Violet", detail:"Lavender and amethyst", sample:"violet"}
  ];
  var COLORS = {
    light:"#f6f9f1",dark:"#111d20",stadium:"#061016",forest:"#edf5e9",
    ocean:"#eaf5fa",sunset:"#fff3e9",violet:"#f4f0fc"
  };
  function valid(id) {return OPTIONS.some(function(item){return item.id === id;});}
  function read() {
    try { var value = localStorage.getItem(STORAGE_KEY); return valid(value)?value:"system"; }
    catch (_) { return "system"; }
  }
  function save(value) {
    try {localStorage.setItem(STORAGE_KEY,value);} catch (_) { /* storage disabled */ }
  }
  var mq;
  try {mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;}
  catch (_) {mq = null;}
  var selected = read();
  var current = "light";
  var page = window.location.pathname;
  var pageName = page === "/" ? "index" : page.indexOf("/client/") === 0 ?
    (page === "/client/picks" ? "picks" : "market") :
    (page === "/access" ? "access-link" : page.substring(1).split("/")[0] || "index");
  document.documentElement.setAttribute("data-bpv-page",pageName);
  function resolved(name) { return name === "system" ? (mq && mq.matches ? "dark" : "light") : name; }
  function syncMenu() {
    var root = document.getElementById("bpv-theme-root");
    if(!root) return;
    var label = root.querySelector(".bpv-theme-current");
    if(label) label.textContent = OPTIONS.filter(function(x){return x.id===selected;})[0].name;
    root.querySelectorAll("[data-bpv-pick]").forEach(function(button) {
      var chosen = button.getAttribute("data-bpv-pick") === selected;
      button.setAttribute("aria-pressed", String(chosen));
      button.classList.toggle("bpv-is-selected",chosen);
    });
  }
  function setTheme(name,persist) {
    if(!valid(name)) return false;
    selected = name;
    current = resolved(name);
    document.documentElement.setAttribute("data-bpv-theme",current);
    document.documentElement.setAttribute("data-bpv-choice",selected);
    document.documentElement.style.colorScheme = (current === "dark" || current === "stadium") ? "dark" : "light";
    var themeMeta = document.querySelector('meta[name="theme-color"]');
    if(themeMeta) themeMeta.setAttribute("content", COLORS[current]);
    if(persist) save(selected);
    syncMenu();
    return true;
  }
  setTheme(selected,false); // Apply before page CSS and body are parsed.
  if(mq) {
    var onSystemChange = function() {if(selected === "system") setTheme("system",false);};
    if(mq.addEventListener) mq.addEventListener("change",onSystemChange);
    else if(mq.addListener) mq.addListener(onSystemChange);
  }
  function makePicker() {
    if(document.getElementById("bpv-theme-root") || !document.body) return;
    var root = document.createElement("div");
    root.id = "bpv-theme-root";
    var toggle = document.createElement("button");
    toggle.id = "bpv-theme-toggle";
    toggle.type = "button";
    toggle.setAttribute("aria-haspopup","true");
    toggle.setAttribute("aria-expanded","false");
    toggle.setAttribute("aria-controls","bpv-theme-menu");
    toggle.setAttribute("aria-label","Choose color theme");
    var icon = document.createElement("span");
    icon.className = "bpv-theme-icon";
    icon.setAttribute("aria-hidden","true");
    icon.textContent = "◐";
    var short = document.createElement("span");
    short.textContent = "Themes";
    toggle.append(icon,short);
    var panel = document.createElement("section");
    panel.id = "bpv-theme-menu";
    panel.setAttribute("aria-label","Appearance settings");
    panel.hidden = true;
    var heading = document.createElement("div");
    heading.className = "bpv-theme-heading";
    var title = document.createElement("strong");
    title.textContent = "Make BPV yours";
    var subtitle = document.createElement("span");
    subtitle.className = "bpv-theme-current";
    heading.append(title,subtitle);
    panel.append(heading);
    var list = document.createElement("div");
    list.className = "bpv-theme-options";
    for(var i=0;i<OPTIONS.length;i++){
      (function(opt){
        var button = document.createElement("button");
        button.type = "button";
        button.className = "bpv-theme-option";
        button.setAttribute("data-bpv-pick",opt.id);
        button.setAttribute("aria-pressed","false");
        var swatch = document.createElement("span");
        swatch.className = "bpv-theme-swatch";
        swatch.setAttribute("data-bpv-swatch",opt.sample);
        swatch.setAttribute("aria-hidden","true");
        var copy = document.createElement("span");
        copy.className = "bpv-theme-option-text";
        var name = document.createElement("strong");
        name.textContent = opt.name;
        var description = document.createElement("small");
        description.textContent = opt.detail;
        copy.append(name,description);
        var check = document.createElement("span");
        check.className = "bpv-theme-selected-mark";
        check.textContent = "✓";
        check.setAttribute("aria-hidden","true");
        button.append(swatch,copy,check);
        button.addEventListener("click",function(){
          setTheme(opt.id,true);
          close();
          toggle.focus();
        });
        list.append(button);
      })(OPTIONS[i]);
    }
    panel.append(list);
    root.append(panel,toggle);
    document.body.append(root);
    function close(){
      panel.hidden = true;
      toggle.setAttribute("aria-expanded","false");
    }
    function open(){
      panel.hidden = false;
      toggle.setAttribute("aria-expanded","true");
      var active = panel.querySelector('[aria-pressed="true"]');
      if(active) active.focus();
    }
    toggle.addEventListener("click",function(){
      if(panel.hidden) open(); else close();
    });
    document.addEventListener("pointerdown",function(event){
      if(!panel.hidden && !root.contains(event.target)) close();
    });
    document.addEventListener("keydown",function(event){
      if(event.key === "Escape" && !panel.hidden){
        close();
        toggle.focus();
      }
    });
    syncMenu();
  }
  window.BPVThemes = Object.freeze({
    getChoice:function(){return selected;},
    getActive:function(){return current;},
    setTheme:function(name){return setTheme(name,true);},
    available:OPTIONS.map(function(x){return x.id;})
  });
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded",makePicker,{once:true});
  else makePicker();
})();
