/* BPV round timing: read-only display of betPawa tradingTime boundaries.
   A round window is NOT a guaranteed individual match kickoff.
   Legacy time_windows estimates are explicitly marked unverified. */
(function(root){
  "use strict";
  const EAT="Africa/Kampala";
  function toDate(value){
    if(!value || typeof value!=="string")return null;
    const instant=new Date(value);
    return Number.isFinite(instant.getTime())?instant:null;
  }
  function formatClock(date){
    return new Intl.DateTimeFormat("en-US",{
      timeZone:EAT,hour:"numeric",minute:"2-digit",hour12:true
    }).format(date);
  }
  function formatDate(date){
    return new Intl.DateTimeFormat("en-US",{
      timeZone:EAT,month:"short",day:"numeric"
    }).format(date);
  }
  function roundWindow(start,end){
    const a=toDate(start),b=toDate(end);
    if(!a && !b)return null;
    // Invalid/inverted round data must never be presented as an exact schedule.
    if(a && b && b.getTime()<a.getTime())return null;
    const from=a||b,to=b||a;
    const day=formatDate(from);
    const first=formatClock(from),last=formatClock(to);
    return {
      text: day+" · "+(a&&b&&a.getTime()!==b.getTime()?first+" – "+last:first)+" EAT",
      start_utc:a?a.toISOString():null,
      end_utc:b?b.toISOString():null,
      source:"betpawa-tradingTime",
      note:"Source feed round window; individual kickoff may differ."
    };
  }
  function savedPick(item){
    const window=roundWindow(item?.round_open_utc,item?.round_close_utc);
    if(window)return {text:window.text,label:"Round window",verified:true,note:window.note};
    const estimated=String(item?.estimated_target_time_eat||"").trim();
    if(/^\d{1,2}:\d{2}$/.test(estimated)){
      return {
        text:"≈ "+estimated+" EAT",
        label:"Model estimate",
        verified:false,
        note:"Calculated from a historical season anchor, not confirmed by the current feed."
      };
    }
    return {text:"Not available",label:"Expected play",verified:false,
      note:"No confirmed round schedule stored for this older prediction."};
  }
  root.BPVRoundTime=Object.freeze({roundWindow,savedPick});
})(window);
