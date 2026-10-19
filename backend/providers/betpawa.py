from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import requests

from ..private_rules import (
    EARLY_SEASON_COMPLETED_ROUNDS,
    PREVIOUS_SEASON_ROUNDS_TO_CHECK,
    MAX_PREVIOUS_SEASONS,
)

BASE = "https://www.betpawa.ug"
VIRTUAL_PAGE = BASE + "/virtual-sports?virtualTab=results&resultsTab=matches"
ACTUAL = "/api/sportsbook/virtual/v2/seasons/list/actual"
PAST = "/api/sportsbook/virtual/v2/seasons/list/past"
EVENTS_V3 = "/api/sportsbook/virtual/v3/events/list/by-round/{round_id}"
EVENTS_V2 = "/api/sportsbook/virtual/v2/events/list/by-round/{round_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-UG,en;q=0.9",
    "Referer": VIRTUAL_PAGE,
    "Origin": BASE,
    "deviceType": "web",
    "X-Pawa-Brand": "betpawa-uganda",
    "X-Pawa-Language": "en",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

BROWSER_FETCH_HEADERS = {
    "X-Pawa-Brand": "betpawa-uganda",
    "deviceType": "web",
    "Accept": "application/json",
    "X-Pawa-Language": "en",
}

LEAGUE_IDS = {
    "7794": "English",
    "7795": "Spanish",
    "7796": "Italian",
    "9184": "German",
    "9183": "French",
    "13774": "Dutch",
    "13773": "Portuguese",
}
FULL_TIME_SLUG = "FULL_TIME_EXCLUDING_OVERTIME"
FIRST_HALF_SLUG = "FIRST_HALF"
FINALITY_BUFFER_SECONDS = 60

SAFE_CAPTURE_NAMES = {
    "x-pawa-brand", "x-pawa-language", "x-device-fingerprint",
    "devicetype", "traceid", "vuejs", "accept", "accept-language",
}


class FeedError(RuntimeError):
    pass


def _cache_bust(url: str) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q["_cb"] = f"{int(time.time() * 1000)}-{random.randint(100000, 999999)}"
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))


def _parse_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class BetPawaFeed:
    """Read only the recent public virtual-football data needed for one request.

    No full-season archive is written to disk. The app reads current/recent rounds
    into memory, verifies the frozen rules, produces predictions, then discards the
    raw feed payloads.
    """

    def __init__(self, timeout: int = 20):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.timeout = timeout

    # ---------- basic HTTP ----------
    def _request(self, path: str, params: dict[str, Any] | None = None):
        return self.s.get(BASE + path, params=params, timeout=self.timeout, allow_redirects=True)

    def _get(self, path: str, params: dict[str, Any] | None = None):
        r = self._request(path, params)
        if r.status_code != 200:
            raise FeedError(f"GET {r.url} returned HTTP {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except Exception as e:
            raise FeedError(f"GET {r.url} did not return JSON: {r.text[:300]}") from e

    # ---------- browser-assisted public feed ----------
    @staticmethod
    def _new_driver(headless: bool = True):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except Exception as e:
            raise FeedError("Selenium is not installed. Run run.bat again.") from e

        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1400,1000")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        driver.set_script_timeout(60)
        driver.execute_cdp_cmd("Network.enable", {})
        return driver

    @staticmethod
    def _read_performance(driver):
        out = []
        try:
            raw = driver.get_log("performance")
        except Exception:
            return out
        for item in raw:
            try:
                out.append(json.loads(item["message"])["message"])
            except Exception:
                pass
        return out

    @staticmethod
    def _captured_headers(entries):
        by_id: dict[str, dict[str, str]] = {}
        urls: dict[str, str] = {}
        for msg in entries:
            params = msg.get("params") or {}
            rid = params.get("requestId")
            if not rid:
                continue
            if msg.get("method") == "Network.requestWillBeSent":
                req = params.get("request") or {}
                url = req.get("url") or ""
                if "/api/sportsbook/virtual/" not in url:
                    continue
                urls[rid] = url
                by_id.setdefault(rid, {}).update({str(k): str(v) for k, v in (req.get("headers") or {}).items()})
            elif msg.get("method") == "Network.requestWillBeSentExtraInfo":
                by_id.setdefault(rid, {}).update({str(k): str(v) for k, v in (params.get("headers") or {}).items()})

        chosen: dict[str, str] = {}
        for rid, headers in by_id.items():
            if rid not in urls and not any(k.lower() == "x-pawa-brand" for k in headers):
                continue
            for k, v in headers.items():
                if k.lower() in SAFE_CAPTURE_NAMES:
                    chosen[k] = v
        return chosen

    @staticmethod
    def _browser_fetch(driver, url: str, captured_headers: dict[str, str] | None = None):
        headers = dict(BROWSER_FETCH_HEADERS)
        for k, v in (captured_headers or {}).items():
            if k.lower() in SAFE_CAPTURE_NAMES:
                headers[k] = v

        script = r"""
        const url = arguments[0], headers = arguments[1], done = arguments[arguments.length - 1];
        fetch(url, {method:'GET', headers, credentials:'include', cache:'no-store'})
          .then(async r => done({ok:r.ok,status:r.status,url:r.url,text:await r.text()}))
          .catch(e => done({ok:false,status:0,url,error:String(e),text:''}));
        """
        result = driver.execute_async_script(script, _cache_bust(url), headers)
        if not isinstance(result, dict):
            raise FeedError("Browser fetch returned an unexpected response.")
        if not result.get("ok"):
            raise FeedError(
                f"Browser GET {result.get('url') or url} returned HTTP {result.get('status')}: "
                f"{(result.get('error') or result.get('text') or '')[:280]}"
            )
        try:
            return json.loads(result.get("text") or "")
        except Exception as e:
            raise FeedError(f"Browser GET {url} did not return JSON.") from e

    def _open_browser(self, headless: bool = True):
        driver = self._new_driver(headless=headless)
        try:
            driver.get(VIRTUAL_PAGE)
            time.sleep(5)
            captured = self._captured_headers(self._read_performance(driver))
            return driver, captured
        except Exception:
            driver.quit()
            raise

    def _with_browser(self, fn):
        last = None
        for headless in (True, False):
            driver = None
            try:
                driver, captured = self._open_browser(headless=headless)
                return fn(driver, captured), headless
            except Exception as e:
                last = e
            finally:
                if driver is not None:
                    try: driver.quit()
                    except Exception: pass
        raise FeedError(f"Browser-assisted feed failed: {last}")

    # ---------- parsing ----------
    @staticmethod
    def _items(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("items", "data", "results"):
                if isinstance(obj.get(key), list):
                    return obj[key]
        return []

    @staticmethod
    def _events(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("responses", "items", "events", "data", "results"):
                if isinstance(obj.get(key), list):
                    return obj[key]
        return []

    @staticmethod
    def _competition_id(event):
        value = (event.get("competition") or {}).get("id")
        return str(value) if value is not None else None

    @staticmethod
    def _participants_from_name(event):
        name = str(event.get("name") or "").strip()
        if " - " in name:
            h, a = name.split(" - ", 1)
            return h.strip(), a.strip()
        idx = name.lower().find(" vs ")
        if idx >= 0:
            return name[:idx].strip(), name[idx + 4:].strip()
        home = away = None
        for part in (event.get("participants") or []):
            ptype = str(part.get("type") or part.get("participantType") or "").upper()
            pname = part.get("name") or (part.get("participant") or {}).get("name")
            if ptype == "HOME": home = pname
            elif ptype == "AWAY": away = pname
        return home, away

    @staticmethod
    def _period_result(event, participant_type: str, slug: str):
        for entry in ((event.get("results") or {}).get("participantPeriodResults") or []):
            if str((entry.get("participant") or {}).get("type") or "").upper() != participant_type.upper():
                continue
            for period in (entry.get("periodResults") or []):
                if str((period.get("period") or {}).get("slug") or "") != slug:
                    continue
                try: return int(float(period.get("result")))
                except (TypeError, ValueError): return None
        return None

    @classmethod
    def _score_pair(cls, event, slug: str):
        h = cls._period_result(event, "HOME", slug)
        a = cls._period_result(event, "AWAY", slug)
        if h is not None and a is not None:
            return h, a
        if slug == FULL_TIME_SLUG:
            for hk, ak in (("HomeScore", "AwayScore"), ("homeScore", "awayScore")):
                if event.get(hk) is not None and event.get(ak) is not None:
                    try: return int(event[hk]), int(event[ak])
                    except (TypeError, ValueError): pass
        return None, None

    @classmethod
    def normalize_round(cls, raw: Any, include_scores: bool) -> dict[str, list[dict[str, Any]]]:
        grouped = {league: [] for league in LEAGUE_IDS.values()}
        for event in cls._events(raw):
            league = LEAGUE_IDS.get(cls._competition_id(event))
            if not league:
                continue
            home, away = cls._participants_from_name(event)
            if not home or not away:
                continue
            grouped[league].append((str(event.get("name") or f"{home} - {away}"), event, home, away))

        out: dict[str, list[dict[str, Any]]] = {}
        for league, rows in grouped.items():
            # Current virtual UI has been observed to display league fixtures in
            # fixture-name order rather than raw API order. Row-based frozen rules
            # rely on that displayed order.
            rows.sort(key=lambda x: x[0])
            norm = []
            for position, (_, event, home, away) in enumerate(rows, start=1):
                row: dict[str, Any] = {"position": position, "home": home, "away": away}
                if include_scores:
                    ht_h, ht_a = cls._score_pair(event, FIRST_HALF_SLUG)
                    ft_h, ft_a = cls._score_pair(event, FULL_TIME_SLUG)
                    row.update({"ht_home": ht_h, "ht_away": ht_a, "ft_home": ft_h, "ft_away": ft_a})
                norm.append(row)
            out[league] = norm
        return out

    # ---------- live fetch ----------
    def _catalog(self):
        # Direct HTTP is cheap; use it if the current gateway accepts it.
        actual = past = None
        try: actual = self._get(ACTUAL)
        except Exception: pass
        try: past = self._get(PAST)
        except Exception: pass
        if actual is not None and past is not None:
            return actual, past, "direct-http"

        def work(driver, captured):
            return (
                self._browser_fetch(driver, BASE + ACTUAL, captured),
                self._browser_fetch(driver, BASE + PAST, captured),
            )
        (actual, past), headless = self._with_browser(work)
        return actual, past, f"browser-assisted{'-headless' if headless else '-visible'}"

    @staticmethod
    def _season_rounds(season: dict[str, Any]):
        rounds = [r for r in (season.get("rounds") or []) if isinstance(r, dict) and r.get("id") is not None]
        rounds.sort(key=lambda r: _parse_ts((r.get("tradingTime") or {}).get("start")) or 0)
        return rounds

    @staticmethod
    def _season_start(season: dict[str, Any]):
        rs = BetPawaFeed._season_rounds(season)
        return _parse_ts(((rs[0].get("tradingTime") or {}).get("start"))) if rs else None

    @staticmethod
    def _season_end(season: dict[str, Any]):
        rs = BetPawaFeed._season_rounds(season)
        return _parse_ts(((rs[-1].get("tradingTime") or {}).get("end"))) if rs else None

    def _select_context_seasons(self, actual_obj: Any, past_obj: Any):
        seasons_by_id: dict[str, dict[str, Any]] = {}
        for obj in (actual_obj, past_obj):
            for s in self._items(obj):
                sid = str(s.get("id"))
                if sid and self._season_rounds(s):
                    # Prefer the richer duplicate if both endpoints return it.
                    old = seasons_by_id.get(sid)
                    if old is None or len(self._season_rounds(s)) > len(self._season_rounds(old)):
                        seasons_by_id[sid] = s

        seasons = list(seasons_by_id.values())
        seasons.sort(key=lambda s: self._season_start(s) or 0)
        now = time.time()
        buffer_s = FINALITY_BUFFER_SECONDS

        selected = None
        selected_idx = None
        source_idx = None
        for si, season in enumerate(seasons):
            rounds = self._season_rounds(season)
            for i in range(len(rounds) - 1):
                end = _parse_ts((rounds[i].get("tradingTime") or {}).get("end"))
                if end is not None and end + buffer_s <= now:
                    # Keep advancing; final value becomes the latest settled round
                    # that has a next round in the same season.
                    selected, selected_idx, source_idx = season, si, i

        if selected is None or source_idx is None:
            raise FeedError("Could not identify a settled matchday followed by a next matchday.")

        previous = []
        for s in reversed(seasons[:selected_idx]):
            if self._season_end(s) and self._season_end(s) <= now:
                previous.append(s)
            if len(previous) >= MAX_PREVIOUS_SEASONS:
                break
        return selected, source_idx, previous

    @staticmethod
    def _round_url_candidates(round_id: Any):
        v3 = BASE + EVENTS_V3.format(round_id=round_id)
        v2 = BASE + EVENTS_V2.format(round_id=round_id)
        return [v3, v3 + "?page=matchups", v2 + "?page=matchups", v2]

    def _fetch_rounds(self, rounds: list[dict[str, Any]]):
        # One browser session per prediction request; raw payloads stay in memory.
        def work(driver, captured):
            out = {}
            modes = {}
            for rnd in rounds:
                rid = str(rnd["id"])
                last = None
                for n, url in enumerate(self._round_url_candidates(rid), start=1):
                    try:
                        out[rid] = self._browser_fetch(driver, url, captured)
                        modes[rid] = n
                        break
                    except Exception as e:
                        last = e
                if rid not in out:
                    raise FeedError(f"Could not read matchday round {rid}: {last}")
            return out, modes

        (payloads, modes), headless = self._with_browser(work)
        return payloads, modes, f"browser-assisted{'-headless' if headless else '-visible'}"

    @staticmethod
    def _pairs_by_league(normalized_rounds: list[dict[str, list[dict[str, Any]]]]):
        out = {league: [] for league in LEAGUE_IDS.values()}
        for i in range(len(normalized_rounds) - 1):
            a, b = normalized_rounds[i], normalized_rounds[i + 1]
            for league in out:
                if a.get(league) and b.get(league):
                    out[league].append((a[league], b[league]))
        return out

    def prediction_context(self):
        actual, past, catalog_mode = self._catalog()
        current, source_idx, previous = self._select_context_seasons(actual, past)
        current_rounds = self._season_rounds(current)

        # If target is MD10, this reads MD1..MD9 for current verification and MD10
        # only for fixture lookup. Nothing is archived to disk.
        completed = current_rounds[:source_idx + 1]
        target = current_rounds[source_idx + 1]

        selected_rounds = list(completed) + [target]
        use_previous = len(completed) <= EARLY_SEASON_COMPLETED_ROUNDS
        previous_round_groups: list[list[dict[str, Any]]] = []
        if use_previous:
            for season in previous:
                rs = self._season_rounds(season)
                if len(rs) >= 2:
                    previous_round_groups.append(rs[-PREVIOUS_SEASON_ROUNDS_TO_CHECK:])
                    selected_rounds.extend(previous_round_groups[-1])

        # De-duplicate IDs before one browser-assisted batch.
        uniq = {}
        for r in selected_rounds:
            uniq[str(r["id"])] = r
        payloads, modes, event_feed_mode = self._fetch_rounds(list(uniq.values()))

        current_normalized = [
            self.normalize_round(payloads[str(r["id"])], include_scores=True)
            for r in completed
        ]
        target_normalized = self.normalize_round(payloads[str(target["id"])], include_scores=False)

        previous_pairs = {league: [] for league in LEAGUE_IDS.values()}
        if use_previous:
            for group in previous_round_groups:
                norm = [self.normalize_round(payloads[str(r["id"])], include_scores=True) for r in group]
                group_pairs = self._pairs_by_league(norm)
                for league, pairs in group_pairs.items():
                    previous_pairs[league].extend(pairs)

        current_pairs = self._pairs_by_league(current_normalized)
        latest_source = current_normalized[-1]

        return {
            "season": current.get("id"),
            "latest_completed_matchday": source_idx + 1,
            "next_matchday": source_idx + 2,
            "current_pairs_by_league": current_pairs,
            "previous_pairs_by_league": previous_pairs,
            "latest_source": latest_source,
            "next_target": target_normalized,
            "use_previous_for_alignment": use_previous,
            "alignment_scope": (
                f"Current season MD1-{source_idx + 1} plus recent prior-season rounds"
                if use_previous else f"Current season MD1-{source_idx + 1}"
            ),
            "feed_mode": event_feed_mode,
            "catalog_mode": catalog_mode,
            "round_endpoint_modes": modes,
        }

    def diagnose(self):
        try:
            actual, past, mode = self._catalog()
            return {
                "ok": True,
                "mode": mode,
                "actual_seasons": len(self._items(actual)),
                "past_seasons": len(self._items(past)),
                "note": "Public season feeds reached. Prediction requests read only recent matchdays into memory.",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
