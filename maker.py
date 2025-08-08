#!/usr/bin/env python3
"""
maker.py — Always fetch NFL + CFB teams, flatten, merge, and save to:
  - teams.xml
  - teams.csv

Strategy
- NFL: ESPN public JSON teams endpoint
- CFB: try SportsDataverse (pandas); if empty/error -> ESPN college-football teams endpoint
- Flatten nested dicts/lists -> scalar columns
- Merge with existing teams.xml; de-dupe by league+uid/id/name
- Output teams.csv + teams.xml

Requirements:
  pip install pandas lxml requests sportsdataverse
"""

import json
import math
import os
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import requests

# Try to import SDV; we'll gracefully fall back if it fails or returns empty
try:
    import sportsdataverse as sdv  # type: ignore
except Exception:
    sdv = None

# --------------------------
# Config
# --------------------------
ESPN_NFL_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
ESPN_CFB_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams"
# Doc-ish refs: ESPN “hidden” API (teams endpoints for leagues incl. CFB/NFL). See: ak easwaran gist & related notes.
# We’ll parse the same structure as NFL: sports -> leagues[0] -> teams[] -> team
ROOT_NAME = "teams"
ROW_NAME = "team"
MAX_LIST_ITEMS = 5
XML_FILE = "teams.xml"
CSV_FILE = "teams.csv"

# --------------------------
# Flattening helpers
# --------------------------
def is_scalar(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool, datetime))

def sanitize_key(key: str) -> str:
    return (
        str(key).strip()
        .replace(" ", "_").replace("-", "_").replace(".", "_")
        .replace("[", "_").replace("]", "").replace("__", "_")
    )

def flatten_obj(obj: Any, prefix: str = "", out: Dict[str, Any] | None = None, max_items: int = MAX_LIST_ITEMS) -> Dict[str, Any]:
    if out is None:
        out = {}
    if prefix:
        prefix = sanitize_key(prefix)

    if isinstance(obj, dict):
        emitted = False
        for k, v in obj.items():
            flatten_obj(v, f"{prefix}_{sanitize_key(k)}" if prefix else sanitize_key(k), out, max_items)
            emitted = True
        if not emitted:
            out[prefix or "value"] = "{}"
    elif isinstance(obj, list):
        dict_like = [x for x in obj if isinstance(x, dict)]
        scalar_like = [x for x in obj if is_scalar(x)]
        base = prefix or "list"
        if dict_like:
            for i, item in enumerate(obj[:max_items]):
                flatten_obj(item, f"{base}_{i}", out, max_items)
            out[f"{base}_count"] = len(obj)
        elif scalar_like and not dict_like:
            for i, item in enumerate(obj[:max_items]):
                out[f"{base}_{i}"] = item
            out[f"{base}_joined"] = " | ".join("" if v is None else str(v) for v in obj)
            out[f"{base}_count"] = len(obj)
        else:
            out[prefix or "value"] = json.dumps(obj, default=str)
    else:
        out[prefix or "value"] = obj

    return out

def dataframe_flatten(df: pd.DataFrame, max_items: int = MAX_LIST_ITEMS) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        flat_row: Dict[str, Any] = {}
        for col in df.columns:
            val = row[col]
            key = sanitize_key(col)
            if isinstance(val, (dict, list)):
                flatten_obj(val, key, flat_row, max_items)
            else:
                flat_row[key] = val
        rows.append(flat_row)
    flat_df = pd.DataFrame(rows)

    # Keep original col order when those cols still exist; then append new ones
    orig = [sanitize_key(c) for c in df.columns]
    keep_orig = [c for c in orig if c in flat_df.columns]
    rest = [c for c in flat_df.columns if c not in keep_orig]
    try:
        return flat_df[keep_orig + rest]
    except Exception:
        return flat_df

def cast_all_to_str(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    def caster(x: Any) -> str:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return ""
        if isinstance(x, datetime):
            return x.isoformat()
        return str(x)
    return df.applymap(caster)

# --------------------------
# ESPN fetchers (NFL + CFB)
# --------------------------
def _espn_teams(url: str, league_marker: str) -> pd.DataFrame:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    leagues = (data.get("sports") or [{}])[0].get("leagues") or []
    if not leagues:
        raise RuntimeError(f"ESPN payload missing leagues[] for {league_marker}")
    teams_wrapped = leagues[0].get("teams") or []
    teams = []
    for entry in teams_wrapped:
        t = entry.get("team") or entry
        teams.append(t)
    df = pd.DataFrame(teams)
    df["league_marker"] = league_marker
    return df

def fetch_nfl_teams() -> pd.DataFrame:
    df = _espn_teams(ESPN_NFL_TEAMS_URL, "NFL")
    print(f"    NFL fetch ok: rows={len(df)}, cols={len(df.columns)}")
    return df

def fetch_cfb_teams_via_sdv() -> pd.DataFrame:
    """Try SportsDataverse first; force pandas; mark league."""
    if sdv is None:
        return pd.DataFrame()
    try:
        df_like = sdv.cfb.espn_cfb_teams(groups=80, return_as_pandas=True)  # FBS (80); change if you want FCS/all
        df = df_like if isinstance(df_like, pd.DataFrame) else getattr(df_like, "to_pandas", lambda: pd.DataFrame())()
        if df is None or df.empty:
            return pd.DataFrame()
        df["league_marker"] = "CFB"
        return df
    except Exception:
        return pd.DataFrame()

def fetch_cfb_teams() -> pd.DataFrame:
    """
    College Football teams:
    1) Try SportsDataverse (FBS) — some environments return empty.
    2) If empty, fall back to ESPN college-football teams endpoint.
    """
    df = fetch_cfb_teams_via_sdv()
    if df is not None and not df.empty:
        print(f"    CFB via SDV ok: rows={len(df)}, cols={len(df.columns)}")
        return df

    print("    SDV returned empty; falling back to ESPN college-football teams endpoint…")
    df2 = _espn_teams(ESPN_CFB_TEAMS_URL, "CFB")
    print(f"    CFB via ESPN ok: rows={len(df2)}, cols={len(df2.columns)}")
    return df2

# --------------------------
# Merge + de-dupe helpers
# --------------------------
def read_existing_xml(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_xml(path)
    except Exception as e:
        print(f"Warning: failed to read existing XML ({path}): {e}")
        return None

def dedupe_merge(existing: pd.DataFrame | None, new_df: pd.DataFrame) -> pd.DataFrame:
    if new_df is None or new_df.empty:
        return existing if existing is not None else pd.DataFrame()
    if existing is None or existing.empty:
        return new_df

    merged = pd.concat([existing, new_df], ignore_index=True, sort=False)

    def key_row(r: pd.Series) -> str:
        league = str(r.get("league_marker", "")).strip()
        uid = str(r.get("uid", "")).strip()
        tid = str(r.get("id", "")).strip()
        name = str(r.get("displayName", "")).strip()
        base = uid or (f"id:{tid}" if tid else "") or (f"name:{name}" if name else "")
        return f"{league}:{base}" if base else f"{league}:row{r.name}"

    merged["_dedupe_key"] = merged.apply(key_row, axis=1)
    merged = merged.drop_duplicates(subset=["_dedupe_key"]).drop(columns=["_dedupe_key"])
    return merged

# --------------------------
# Main
# --------------------------
def main():
    print("[1/6] Fetching NFL teams…")
    nfl_df_raw = fetch_nfl_teams()

    print("[2/6] Fetching CFB teams…")
    cfb_df_raw = fetch_cfb_teams()

    print("[3/6] Flattening…")
    nfl_df_flat = dataframe_flatten(nfl_df_raw)
    cfb_df_flat = dataframe_flatten(cfb_df_raw)
    print(f"    NFL flat cols={len(nfl_df_flat.columns)} | CFB flat cols={len(cfb_df_flat.columns)}")

    print("[4/6] Merging NFL + CFB…")
    new_df = pd.concat([nfl_df_flat, cfb_df_flat], ignore_index=True, sort=False)

    print(f"[5/6] Reading existing XML (if present): {XML_FILE}")
    existing_df = read_existing_xml(XML_FILE)
    if existing_df is not None:
        print(f"    Existing rows={len(existing_df)}, cols={len(existing_df.columns)}")
    merged = dedupe_merge(existing_df, new_df)

    print("[6/6] Casting to strings and writing XML + CSV…")
    safe = cast_all_to_str(merged)

    # sanity: how many per league made it out?
    try:
        print("    Output league counts:", safe["league_marker"].value_counts().to_dict())
    except Exception:
        pass

    safe.to_csv(CSV_FILE, index=False, encoding="utf-8")
    print(f"    Wrote CSV: {os.path.abspath(CSV_FILE)}")
    safe.to_xml(XML_FILE, index=False, root_name=ROOT_NAME, row_name=ROW_NAME)
    print(f"    Wrote XML: {os.path.abspath(XML_FILE)}")

if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    main()
