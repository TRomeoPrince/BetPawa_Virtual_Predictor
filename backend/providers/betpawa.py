from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from ..private_rules import (
    EARLY_SEASON_COMPLETED_ROUNDS,
    PREVIOUS_SEASON_ROUNDS_TO_CHECK,
    MAX_PREVIOUS_SEASONS,
)

BASE = "https://www.betpawa.ug"
VIRTUAL_PAGE = BASE + "/virtual-sports?virtualTab=results&resultsTab=matches"
MATCHDAY_PAGE = BASE + "/virtual-sports/matchday/{season_id}?matchday={matchday}&leagueId="
ACTUAL = "/api/sportsbook/virtual/v2/seasons/list/actual"
PAST = "/api/sportsbook/virtual/v2/seasons/list/past"

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
    "Accept": "application/json, text/plain, */*",
    "X-Pawa-Brand": "betpawa-uganda",
    "X-Pawa-Language": "en",
    "deviceType": "web",
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
EVENT_PATH_MARKER = "/events/list/by-round/"


class FeedError(RuntimeError):
    pass


def _parse_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class BetPawaFeed:
    """Read only the public virtual-football data needed for one prediction request.

    v0.2.3 does not guess a fixed matchday API path. It opens betPawa's own
    matchday page, watches the request the live site makes, and reuses that exact
    request shape for the other recent rounds needed by the verifier.
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
        chosen: dict[str, str] = {}
        for msg in entries:
            if msg.get("method") != "Network.requestWillBeSent":
                continue
            req = (msg.get("params") or {}).get("request") or {}
            url = str(req.get("url") or "")
            if "/api/sportsbook/virtual/" not in url:
                continue
            for k, v in (req.get("headers") or {}).items():
                if str(k).lower() in SAFE_CAPTURE_NAMES:
                    chosen[str(k)] = str(v)
        return chosen

    @staticmethod
    def _browser_fetch(driver, url: str, captured_headers: dict[str, str] | None = None):
        """Fetch the exact URL. Do not append custom query parameters.

        Some betPawa endpoints reject unknown query parameters, so the predictor relies
        on fetch(cache='no-store') instead of adding a cache-busting parameter.
        """
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
        result = driver.execute_async_script(script, url, headers)
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
            time.sleep(3)
            entries = self._read_performance(driver)
            captured = self._captured_headers(entries)
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
                    try:
                        driver.quit()
                    except Exception:
                        pass
        raise FeedError(f"Browser-assisted feed failed: {last}")

    @staticmethod
    def _replace_round_id(url: str, round_id: str) -> str:
        return re.sub(r"(/by-round/)\d+", rf"\g<1>{round_id}", url, count=1)

    @staticmethod
    def _round_id_from_url(url: str) -> str | None:
        m = re.search(r"/by-round/(\d+)", url)
        return m.group(1) if m else None

    def _capture_live_round_request(
        self,
        driver,
        season_id: str,
        matchday: int,
        expected_round_id: str,
        seed_headers: dict[str, str] | None = None,
        timeout_s: float = 15.0,
    ):
        """Open betPawa's real matchday page and read its completed event request.

        The important detail is timing: Network.responseReceived only means the
        response headers have arrived. The body may still be empty at that point.
        v0.2.3 therefore waits for Network.loadingFinished for the same requestId
        before calling Network.getResponseBody.
        """
        try:
            self._read_performance(driver)  # clear stale log entries
        except Exception:
            pass

        page = MATCHDAY_PAGE.format(season_id=season_id, matchday=matchday)
        driver.get(page)

        deadline = time.time() + timeout_s
        all_entries: list[dict[str, Any]] = []
        pending: dict[str, dict[str, Any]] = {}
        observed_urls: list[str] = []
        read_errors: list[str] = []

        def parse_body(request_id: str):
            last_error = None
            for _ in range(3):
                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    )
                    text = body.get("body") or ""
                    if body.get("base64Encoded"):
                        text = base64.b64decode(text).decode(
                            "utf-8", errors="replace"
                        )
                    text = text.lstrip("\ufeff").strip()
                    if text.startswith(")]}',"):
                        text = text.split("\n", 1)[1] if "\n" in text else ""
                    if not text:
                        raise ValueError("response body was empty")
                    return json.loads(text)
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.12)
            raise last_error

        while time.time() < deadline:
            entries = self._read_performance(driver)
            if entries:
                all_entries.extend(entries)

            for msg in entries:
                method = msg.get("method")
                params = msg.get("params") or {}
                request_id = str(params.get("requestId") or "")

                if method == "Network.responseReceived":
                    response = params.get("response") or {}
                    url = str(response.get("url") or "")
                    status = int(response.get("status") or 0)

                    if EVENT_PATH_MARKER not in url or status != 200:
                        continue
                    if self._round_id_from_url(url) != expected_round_id:
                        continue

                    observed_urls.append(url)
                    pending[request_id] = {
                        "url": url,
                        "mimeType": str(response.get("mimeType") or ""),
                        "status": status,
                    }
                    continue

                if method == "Network.loadingFailed" and request_id in pending:
                    failure = str(params.get("errorText") or "request failed")
                    read_errors.append(f"live request failed after HTTP response: {failure}")
                    pending.pop(request_id, None)
                    continue

                if method != "Network.loadingFinished" or request_id not in pending:
                    continue

                meta = pending.pop(request_id)
                url = meta["url"]
                headers = dict(seed_headers or {})
                headers.update(self._captured_headers(all_entries))

                # Now the network request is complete, so Chrome should have the
                # actual response body available.
                try:
                    payload = parse_body(request_id)
                    if self._events(payload):
                        return payload, url, headers
                    read_errors.append(
                        f"completed response had no recognizable events "
                        f"(mime={meta.get('mimeType') or 'unknown'})"
                    )
                except Exception as exc:
                    read_errors.append(
                        f"completed Chrome body unreadable "
                        f"(mime={meta.get('mimeType') or 'unknown'}): {exc}"
                    )

                # Secondary fallback only after the original completed body could
                # not be parsed. Reuse the exact proven URL in the same session.
                try:
                    payload = self._browser_fetch(driver, url, headers)
                    if self._events(payload):
                        return payload, url, headers
                    read_errors.append("in-page refetch contained no recognizable events")
                except Exception as exc:
                    read_errors.append(f"in-page refetch failed: {exc}")

            time.sleep(0.20)

        seen = list(dict.fromkeys(observed_urls))[-5:]
        raise FeedError(
            f"betPawa's live event request completed but its data could not be parsed for "
            f"season {season_id} matchday {matchday} / round {expected_round_id}. "
            f"Observed event requests: {seen or 'none'}. "
            f"Read errors: {read_errors[-3:] or 'none'}"
        )

    # ---------- parsing ----------
    @staticmethod
    def _items(obj):
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("responses", "items", "data", "results"):
                value = obj.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
                if isinstance(value, dict):
                    nested = BetPawaFeed._items(value)
                    if nested:
                        return nested
        return []

    @staticmethod
    def _events(obj):
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("responses", "items", "events", "data", "results"):
                value = obj.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
                if isinstance(value, dict):
                    nested = BetPawaFeed._events(value)
                    if nested:
                        return nested
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
            if ptype == "HOME":
                home = pname
            elif ptype == "AWAY":
                away = pname
        return home, away

    @staticmethod
    def _period_result(event, participant_type: str, slug: str):
        for entry in ((event.get("results") or {}).get("participantPeriodResults") or []):
            if str((entry.get("participant") or {}).get("type") or "").upper() != participant_type.upper():
                continue
            for period in (entry.get("periodResults") or []):
                if str((period.get("period") or {}).get("slug") or "") != slug:
                    continue
                try:
                    return int(float(period.get("result")))
                except (TypeError, ValueError):
                    return None
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
                    try:
                        return int(event[hk]), int(event[ak])
                    except (TypeError, ValueError):
                        pass
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
            # fixture-name order rather than raw API order. Row rules depend on it.
            rows.sort(key=lambda x: x[0].casefold())
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
        actual = past = None
        try:
            actual = self._get(ACTUAL)
        except Exception:
            pass
        try:
            past = self._get(PAST)
        except Exception:
            pass
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
        rounds = [
            r for r in (season.get("rounds") or [])
            if isinstance(r, dict) and r.get("id") is not None
        ]
        rounds.sort(key=lambda r: _parse_ts((r.get("tradingTime") or {}).get("start")) or 0)
        return rounds

    @staticmethod
    def _season_start(season: dict[str, Any]):
        rs = BetPawaFeed._season_rounds(season)
        return _parse_ts((rs[0].get("tradingTime") or {}).get("start")) if rs else None

    @staticmethod
    def _season_end(season: dict[str, Any]):
        rs = BetPawaFeed._season_rounds(season)
        return _parse_ts((rs[-1].get("tradingTime") or {}).get("end")) if rs else None

    @staticmethod
    def _latest_settled_source_index(season: dict[str, Any], now: float) -> int | None:
        rounds = BetPawaFeed._season_rounds(season)
        latest = None
        for i in range(len(rounds) - 1):
            end = _parse_ts((rounds[i].get("tradingTime") or {}).get("end"))
            if end is not None and end + FINALITY_BUFFER_SECONDS <= now:
                latest = i
        return latest

    def _select_context_seasons(self, actual_obj: Any, past_obj: Any):
        now = time.time()
        actual = [s for s in self._items(actual_obj) if self._season_rounds(s)]
        past = [s for s in self._items(past_obj) if self._season_rounds(s)]

        # Prefer the ACTUAL feed first. This prevents an old season from winning
        # simply because its round IDs happen to be returned later in a list.
        viable_actual = [s for s in actual if self._latest_settled_source_index(s, now) is not None]
        containing_now = [
            s for s in viable_actual
            if (self._season_start(s) or float("inf")) <= now <= (self._season_end(s) or 0) + 300
        ]
        if containing_now:
            current = max(containing_now, key=lambda s: self._season_start(s) or 0)
        elif viable_actual:
            started = [s for s in viable_actual if (self._season_start(s) or 0) <= now]
            current = max(started or viable_actual, key=lambda s: self._season_start(s) or 0)
        else:
            combined = [s for s in actual + past if self._latest_settled_source_index(s, now) is not None]
            if not combined:
                raise FeedError("Could not identify a current season with a settled matchday and a next matchday.")
            current = max(combined, key=lambda s: self._season_start(s) or 0)

        source_idx = self._latest_settled_source_index(current, now)
        if source_idx is None:
            raise FeedError("The selected current season has no settled source matchday yet.")

        current_start = self._season_start(current) or 0
        previous_candidates = [
            s for s in actual + past
            if str(s.get("id")) != str(current.get("id"))
            and self._season_rounds(s)
            and (self._season_end(s) or 0) <= now
            and (self._season_start(s) or 0) < current_start
        ]
        previous_candidates.sort(key=lambda s: self._season_start(s) or 0, reverse=True)

        return current, source_idx, previous_candidates[:MAX_PREVIOUS_SEASONS]

    def _fetch_rounds(self, specs: list[dict[str, Any]], discovery_spec: dict[str, Any]):
        """Discover the live event URL once, then reuse its exact shape."""

        def work(driver, captured):
            payloads: dict[str, Any] = {}
            modes: dict[str, str] = {}

            discovery_round = str(discovery_spec["round"]["id"])
            payload, live_url, live_headers = self._capture_live_round_request(
                driver,
                str(discovery_spec["season_id"]),
                int(discovery_spec["matchday"]),
                discovery_round,
                seed_headers=captured,
            )
            captured.update(live_headers)
            payloads[discovery_round] = payload
            modes[discovery_round] = "page-capture"

            for spec in specs:
                rid = str(spec["round"]["id"])
                if rid in payloads:
                    continue

                exact_url = self._replace_round_id(live_url, rid)
                try:
                    data = self._browser_fetch(driver, exact_url, captured)
                    if not self._events(data):
                        raise FeedError("event response contained no recognizable events")
                    payloads[rid] = data
                    modes[rid] = "live-template"
                    continue
                except Exception:
                    pass

                # Fallback: ask the real page for that matchday and capture its
                # response body directly. Still no guessed API path.
                data, observed_url, more_headers = self._capture_live_round_request(
                    driver,
                    str(spec["season_id"]),
                    int(spec["matchday"]),
                    rid,
                    seed_headers=captured,
                )
                captured.update(more_headers)
                live_url = observed_url
                payloads[rid] = data
                modes[rid] = "page-capture"

            return payloads, modes, live_url

        (payloads, modes, live_url), headless = self._with_browser(work)
        parsed = urlparse(live_url)
        endpoint_shape = parsed.path + (("?" + parsed.query) if parsed.query else "")
        return (
            payloads,
            modes,
            f"browser-assisted{'-headless' if headless else '-visible'}",
            endpoint_shape,
        )

    @staticmethod
    def _pairs_by_league(normalized_rounds: list[dict[str, list[dict[str, Any]]]]):
        out = {league: [] for league in LEAGUE_IDS.values()}
        for i in range(len(normalized_rounds) - 1):
            a, b = normalized_rounds[i], normalized_rounds[i + 1]
            for league in out:
                if a.get(league) and b.get(league):
                    out[league].append((a[league], b[league]))
        return out

    @staticmethod
    def _round_specs(season: dict[str, Any], indexes: list[int]):
        rounds = BetPawaFeed._season_rounds(season)
        sid = str(season.get("id"))
        return [
            {"season_id": sid, "matchday": i + 1, "round": rounds[i]}
            for i in indexes
            if 0 <= i < len(rounds)
        ]

    def prediction_context(self):
        actual, past, catalog_mode = self._catalog()
        current, source_idx, previous = self._select_context_seasons(actual, past)
        current_rounds = self._season_rounds(current)

        completed_indexes = list(range(0, source_idx + 1))
        target_index = source_idx + 1
        current_specs = self._round_specs(current, completed_indexes + [target_index])
        discovery_spec = self._round_specs(current, [source_idx])[0]

        use_previous = len(completed_indexes) <= EARLY_SEASON_COMPLETED_ROUNDS
        previous_groups: list[tuple[dict[str, Any], list[int]]] = []
        all_specs = list(current_specs)

        if use_previous:
            for season in previous:
                rs = self._season_rounds(season)
                if len(rs) < 2:
                    continue
                start = max(0, len(rs) - PREVIOUS_SEASON_ROUNDS_TO_CHECK)
                indexes = list(range(start, len(rs)))
                previous_groups.append((season, indexes))
                all_specs.extend(self._round_specs(season, indexes))

        uniq: dict[str, dict[str, Any]] = {}
        for spec in all_specs:
            uniq[str(spec["round"]["id"])] = spec

        payloads, modes, event_feed_mode, endpoint_shape = self._fetch_rounds(
            list(uniq.values()), discovery_spec
        )

        completed = current_rounds[:source_idx + 1]
        target = current_rounds[target_index]
        current_normalized = [
            self.normalize_round(payloads[str(r["id"])], include_scores=True)
            for r in completed
        ]
        target_normalized = self.normalize_round(payloads[str(target["id"])], include_scores=False)

        previous_pairs = {league: [] for league in LEAGUE_IDS.values()}
        if use_previous:
            for season, indexes in previous_groups:
                rs = self._season_rounds(season)
                norm = [
                    self.normalize_round(payloads[str(rs[i]["id"])], include_scores=True)
                    for i in indexes
                ]
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
            "observed_event_endpoint": endpoint_shape,
        }

    def diagnose(self):
        try:
            actual, past, mode = self._catalog()
            current, source_idx, previous = self._select_context_seasons(actual, past)
            rounds = self._season_rounds(current)
            return {
                "ok": True,
                "mode": mode,
                "actual_seasons": len(self._items(actual)),
                "past_seasons": len(self._items(past)),
                "selected_season": current.get("id"),
                "latest_completed_matchday": source_idx + 1,
                "source_round_id": rounds[source_idx].get("id"),
                "next_round_id": rounds[source_idx + 1].get("id"),
                "previous_seasons_available": [s.get("id") for s in previous],
                "note": "Season selection is current-time based. Event URLs are discovered from betPawa's live matchday page during prediction requests.",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}