"""Administrator-curated premium fixtures for 13 November 2026.

These records are manually supplied research selections, not bookmaker offers,
prediction-engine signals, verified odds, or automatically placed bets.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from . import access
import re
import sqlite3
import threading
import time

EAT = ZoneInfo("Africa/Kampala")
PICK_DATE = "2026-11-13"

# The user's 13 November schedule, with home/away order preserved.
# 'watch' deliberately has no definitive betting selection.
PICKS = (
    ("139445", 7,  "BRE – SUN", "BRE WIN",           "20:37", "20:40", "20:45", "pick"),
    ("139445", 11, "CHE – TOT", "BTTS / Over 2.5",   "20:57", "21:00", "21:05", "pick"),
    ("139445", 13, "AST – CRY", "AST WIN",           "21:07", "21:10", "21:15", "pick"),
    ("139445", 20, "CRY – TOT", "Win/loss pattern",  "21:42", "21:45", "21:50", "watch"),
    ("139445", 26, "SUN – BRE", "BRE WIN",           "22:12", "22:15", "22:20", "pick"),
    ("139445", 30, "TOT – CHE", "BTTS / Over 2.5",   "22:32", "22:35", "22:40", "pick"),
    ("139445", 32, "CRY – AST", "AST WIN",           "22:42", "22:45", "22:50", "pick"),
    ("139446", 1,  "BRE – SUN", "BRE WIN",           "22:57", "23:00", "23:05", "pick"),
    ("139446", 5,  "CHE – TOT", "BTTS / Over 2.5",   "23:17", "23:20", "23:25", "pick"),
)



# The initial schedule is migrated to SQLite exactly once. Subsequent changes
# survive Railway deployments and are never overwritten by later code releases.
_ALLOWED_SELECTIONS = {
    "BTTS / Over 2.5", "BTTS YES", "BTTS NO",
    "Over 1.5", "Over 2.5", "Over 3.5",
    "Under 2.5", "Under 3.5", "Win/loss pattern",
}
_FIXTURE = re.compile(r"^([A-Z0-9]{2,6})\s*[–-]\s*([A-Z0-9]{2,6})$")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SEASON = re.compile(r"^\d{3,12}$")


def _datetime(local_time: str, date_eat: str = PICK_DATE) -> datetime:
    return datetime.fromisoformat(f"{date_eat}T{local_time}:00").replace(tzinfo=EAT)


def _connect():
    con = access.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS premium_pick_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_eat TEXT NOT NULL,
            season TEXT NOT NULL,
            matchday INTEGER NOT NULL CHECK(matchday BETWEEN 1 AND 34),
            fixture TEXT NOT NULL,
            selection TEXT NOT NULL,
            alarm_eat TEXT NOT NULL,
            window_open_eat TEXT NOT NULL,
            window_close_eat TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'pick',
            enabled INTEGER NOT NULL DEFAULT 1,
            edited_after_open INTEGER NOT NULL DEFAULT 0,
            revised_from TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by INTEGER,
            UNIQUE(date_eat,season,matchday,fixture)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS premium_pick_metadata(
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )
    """)
    # BEGIN IMMEDIATE also serializes first-time seed across parallel requests.
    con.execute("BEGIN IMMEDIATE")
    if not con.execute("SELECT 1 FROM premium_pick_metadata WHERE key='seed_v1'").fetchone():
        stamp=datetime.now(timezone.utc).isoformat()
        for season, md, fixture, selection, alarm, opened, closed, kind in PICKS:
            con.execute("""
                INSERT OR IGNORE INTO premium_pick_entries
                (date_eat,season,matchday,fixture,selection,alarm_eat,
                 window_open_eat,window_close_eat,kind,enabled,
                 edited_after_open,revised_from,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?)
            """, (PICK_DATE,season,md,fixture,selection,alarm,opened,closed,kind,
                  0,"",stamp,stamp))
        con.execute("INSERT INTO premium_pick_metadata(key,value) VALUES('seed_v1',?)",(stamp,))
    con.commit()
    return con


def _dict(row):
    return {
        "id":int(row["id"]),"date_eat":row["date_eat"],"season":row["season"],
        "matchday":int(row["matchday"]),"fixture":row["fixture"],
        "selection":row["selection"],"kind":row["kind"],
        "alarm_eat":row["alarm_eat"],"window_open_eat":row["window_open_eat"],
        "window_close_eat":row["window_close_eat"],"enabled":bool(row["enabled"]),
        "edited_after_open":bool(row["edited_after_open"]),
        "revised_from":row["revised_from"],"updated_at":row["updated_at"],
    }


def list_entries(include_disabled: bool = False) -> list[dict]:
    con=_connect()
    try:
        condition="" if include_disabled else "WHERE enabled=1"
        rows=con.execute(f"""
            SELECT * FROM premium_pick_entries {condition}
            ORDER BY date_eat,window_open_eat,matchday,id
        """).fetchall()
        return [_dict(r) for r in rows]
    finally:
        con.close()


def _validated(data):
    d={}
    try:
        day=str(data["date_eat"]).strip()
        if date.fromisoformat(day).isoformat()!=day:
            raise ValueError("Invalid EAT date.")
        d["date_eat"]=day
        d["season"]=str(data["season"]).strip()
        if not _SEASON.fullmatch(d["season"]):
            raise ValueError("Season must be a numeric ID.")
        d["matchday"]=int(data["matchday"])
        if d["matchday"] not in range(1,35):
            raise ValueError("Matchday must be between 1 and 34.")
        match=_FIXTURE.fullmatch(str(data["fixture"]).strip().upper())
        if not match or match.group(1)==match.group(2):
            raise ValueError("Fixture must be HOME – AWAY, e.g. BRE – SUN.")
        d["fixture"]=match.group(1)+" – "+match.group(2)
        d["selection"]=str(data["selection"]).strip()
        choices=_ALLOWED_SELECTIONS | {match.group(1)+" WIN",match.group(2)+" WIN"}
        if d["selection"] not in choices:
            raise ValueError("Choose a supported prediction market or team winner.")
        for key in ("alarm_eat","window_open_eat","window_close_eat"):
            value=str(data[key]).strip()
            if not _CLOCK.fullmatch(value):
                raise ValueError(f"{key} must be HH:MM (EAT).")
            d[key]=value
        alarm=_datetime(d["alarm_eat"],day)
        opened=_datetime(d["window_open_eat"],day)
        closed=_datetime(d["window_close_eat"],day)
        if not alarm<=opened<closed:
            raise ValueError("Alarm must precede opening; the betting window must end after opening.")
        if (closed-opened).total_seconds()>1800:
            raise ValueError("A betting window cannot be longer than 30 minutes.")
        d["kind"]="watch" if d["selection"]=="Win/loss pattern" else "pick"
        d["enabled"]=bool(data.get("enabled",True))
        return d
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError("Complete the match details, date and EAT times.") from exc


def save_entry(data, admin_id: int, entry_id: int | None = None) -> dict:
    d=_validated(data)
    stamp=datetime.now(timezone.utc).isoformat()
    now=datetime.now(EAT)
    mid_window=now>=_datetime(d["window_open_eat"],d["date_eat"])
    con=_connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        old=None
        if entry_id is not None:
            old=con.execute("SELECT * FROM premium_pick_entries WHERE id=?",(int(entry_id),)).fetchone()
            if old is None:
                raise ValueError("Premium pick not found.")
        if old:
            revised=str(old["revised_from"] or "")
            if old["selection"]!=d["selection"] and not revised:
                revised=str(old["selection"])
            late=bool(old["edited_after_open"]) or mid_window
            con.execute("""
                UPDATE premium_pick_entries
                SET date_eat=?,season=?,matchday=?,fixture=?,selection=?,alarm_eat=?,
                    window_open_eat=?,window_close_eat=?,kind=?,enabled=?,
                    edited_after_open=?,revised_from=?,updated_at=?,updated_by=?
                WHERE id=?
            """, (d["date_eat"],d["season"],d["matchday"],d["fixture"],d["selection"],
                  d["alarm_eat"],d["window_open_eat"],d["window_close_eat"],d["kind"],
                  int(d["enabled"]),int(late),revised,stamp,int(admin_id),int(entry_id)))
            ident=int(entry_id)
        else:
            cur=con.execute("""
                INSERT INTO premium_pick_entries
                (date_eat,season,matchday,fixture,selection,alarm_eat,
                 window_open_eat,window_close_eat,kind,enabled,
                 edited_after_open,created_at,updated_at,updated_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (d["date_eat"],d["season"],d["matchday"],d["fixture"],d["selection"],
                  d["alarm_eat"],d["window_open_eat"],d["window_close_eat"],d["kind"],
                  int(d["enabled"]),int(mid_window),stamp,stamp,int(admin_id)))
            ident=int(cur.lastrowid)
        con.commit()
        return _dict(con.execute("SELECT * FROM premium_pick_entries WHERE id=?",(ident,)).fetchone())
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise ValueError("That fixture already exists in this season and matchday. Edit it instead.") from exc
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def toggle_entry(entry_id: int, admin_id: int, enabled: bool) -> dict:
    con=_connect()
    try:
        stamp=datetime.now(timezone.utc).isoformat()
        changed=con.execute("""
            UPDATE premium_pick_entries SET enabled=?,updated_at=?,updated_by=?
            WHERE id=?
        """,(int(bool(enabled)),stamp,int(admin_id),int(entry_id))).rowcount
        if not changed:
            raise ValueError("Premium pick not found.")
        con.commit()
        return _dict(con.execute("SELECT * FROM premium_pick_entries WHERE id=?",(int(entry_id),)).fetchone())
    finally:
        con.close()


def snapshot(now: datetime | None = None) -> dict:
    """Return current premium records; keep ended entries for one day."""
    current=(now or datetime.now(EAT)).astimezone(EAT)
    output=[]
    for item in list_entries():
        close_at=_datetime(item["window_close_eat"],item["date_eat"])
        if current>=close_at+timedelta(days=1):
            continue
        alarm_at=_datetime(item["alarm_eat"],item["date_eat"])
        open_at=_datetime(item["window_open_eat"],item["date_eat"])
        if current>=close_at:
            item["status"]="closed"
        elif current>=open_at:
            item["status"]="window"
        elif current>=alarm_at:
            item["status"]="soon"
        else:
            item["status"]="upcoming"
        output.append(item)
    return {
        "timezone":"Africa/Kampala",
        "source":"admin-curated; scheduled EAT, results read from betPawa after settlement",
        "items":output,
    }


# Official scores are read from the existing betPawa provider and held in memory
# after settlement; unresolved rounds retry at most once a minute per process.
_RESULTS: dict[tuple[str, str, int, str, str], dict] = {}
_ATTEMPTS: dict[tuple[str, int], float] = {}
_LOCK = threading.RLock()
RETRY_SECONDS = 60

_ALIASES = {
    "ARS": {"ars","arsenal"},
    "BOU": {"bou","bournemouth"},
    "BHA": {"bha","brighton","brightonandhovealbion"},
    "BUR": {"bur","burnley"},
    "EVE": {"eve","everton"},
    "FUL": {"ful","fulham"},
    "LEE": {"lee","leeds","leedsunited"},
    "LIV": {"liv","liverpool"},
    "MCI": {"mci","mancity","manchestercity"},
    "MUN": {"mun","manutd","manchesterunited"},
    "NEW": {"new","newcastle","newcastleunited"},
    "NFO": {"nfo","nottinghamforest","nottingham"},
    "WHU": {"whu","westham","westhamunited"},
    "WOL": {"wol","wolves","wolverhampton","wolverhamptonwanderers"},
    "AVL": {"avl","astonvilla"},
    "LEI": {"lei","leicester","leicestercity"},
    "SOU": {"sou","southampton"},
    "IPS": {"ips","ipswich","ipswichtown"},
    "SHU": {"shu","sheffieldunited"},
    "BRE": {"bre","brentford"},
    "SUN": {"sun", "sunderland"},
    "CHE": {"che", "chelsea"},
    "TOT": {"tot", "tottenham", "tottenhamhotspur", "spurs"},
    "CRY": {"cry", "crystalpalace"},
    "AST": {"ast", "astonvilla", "astonvillafc"},
}


def _team_matches(abbreviation: str, feed_name: str) -> bool:
    clean = "".join(c for c in str(feed_name).lower() if c.isalnum())
    return clean in _ALIASES.get(abbreviation, {abbreviation.lower()})


def _grade(item: dict, league_fixtures: list[dict]) -> dict | None:
    codes = item["fixture"].replace("–", "-").split("-")
    if len(codes) != 2:
        return None
    home_code, away_code = (v.strip().upper() for v in codes)
    matches = [
        x for x in league_fixtures
        if _team_matches(home_code, x.get("home", ""))
        and _team_matches(away_code, x.get("away", ""))
    ]
    if len(matches) != 1:
        return None
    match = matches[0]
    h, a = match.get("ft_home"), match.get("ft_away")
    if not isinstance(h, int) or not isinstance(a, int) or min(h, a) < 0:
        return None
    score = f"{h}–{a}"
    if item["kind"] == "watch":
        return {"ft_score": score, "result_summary": "FT recorded · pattern watch",
                "status": "watch-result"}
    if item["selection"] == "BTTS / Over 2.5":
        btts = "WON" if h > 0 and a > 0 else "LOST"
        over = "WON" if h + a >= 3 else "LOST"
        label = (f"BTTS {btts} · Over 2.5 {over}")
        kind = ("mixed" if btts != over else "won" if btts == "WON" else "lost")
        return {"ft_score": score, "result_summary": label, "status": kind,
                "market_results": {"btts": btts, "over_2_5": over}}
    if item["selection"] in {"BTTS YES","BTTS NO","Over 1.5","Over 2.5","Over 3.5","Under 2.5","Under 3.5"}:
        selection=item["selection"]
        total=h+a
        if selection=="BTTS YES":
            won=h>0 and a>0
        elif selection=="BTTS NO":
            won=h==0 or a==0
        elif selection.startswith("Over "):
            won=total>float(selection[5:])
        else:
            won=total<float(selection[6:])
        return {"ft_score":score,"result_summary":"WON" if won else "LOST",
                "status":"won" if won else "lost"}
    selected = item["selection"].split(" ", 1)[0].upper()
    if selected not in (home_code, away_code) or not item["selection"].endswith(" WIN"):
        return None
    won = (h > a) if selected == home_code else (a > h)
    return {"ft_score": score, "result_summary": "WON" if won else "LOST",
            "status": "won" if won else "lost"}


def attach_results(snapshot_payload: dict, feed, now: datetime | None = None) -> dict:
    """Best-effort score check starting one minute after the scheduled close.

    A missing result remains pending; no historical winning rate is inserted
    as an actual outcome. Server and existing access checks remain separate.
    """
    current = (now or datetime.now(EAT)).astimezone(EAT)
    rows = snapshot_payload.get("items") or []
    eligible = [
        row for row in rows
        if row.get("status") == "closed"
        and current >= _datetime(row["window_close_eat"],row["date_eat"]) + timedelta(minutes=1)
    ]
    with _LOCK:
        # Throttle costly live browser-assisted reads across simultaneous users.
        due = sorted({
            (row["season"], int(row["matchday"])) for row in eligible
            if (row["date_eat"], row["season"], int(row["matchday"]), row["fixture"], row["selection"]) not in _RESULTS
            and current.timestamp() - _ATTEMPTS.get((row["season"], int(row["matchday"])), 0)
            >= RETRY_SECONDS
        })
        if due:
            for key in due:
                _ATTEMPTS[key] = current.timestamp()
            try:
                completed = feed.completed_premium_rounds(due)
            except Exception:
                completed = {}
            for row in eligible:
                key = (row["season"], int(row["matchday"]))
                cache_key = (row["date_eat"],) + key + (row["fixture"], row["selection"])
                if cache_key not in _RESULTS and key in completed:
                    grade = _grade(row, completed[key])
                    if grade:
                        _RESULTS[cache_key] = grade
        for row in eligible:
            grade = _RESULTS.get((row["date_eat"],row["season"], int(row["matchday"]), row["fixture"],row["selection"]))
            if grade:
                row.update(grade)
            else:
                row["status"] = "awaiting"
                row["result_summary"] = "Awaiting official FT score"
    return snapshot_payload
