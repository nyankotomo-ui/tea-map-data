#!/usr/bin/env python3
"""Tea Map five-prefecture, checkpointed OSM evidence prescreen.
Does NOT certify six-genre web/Instagram verification or shop eligibility.
Writes exactly one checkpoint commit per 200 stations. Never edits release files.
"""
import csv
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SRC = "https://raw.githubusercontent.com/eng213035/gachi-open-datasets/main/station-master/stations.csv"
TARGET = {"Tokyo": "東京", "Kanagawa": "神奈川", "Osaka": "大阪", "Aichi": "愛知", "Hyogo": "兵庫"}
OUT = Path("research/station-discovery/2026-10-27")
BATCH_SIZE = 200
JST = timezone(timedelta(hours=9))
HOSTS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
USER_AGENT = "TeaMapResearch/0.1 (public OpenStreetMap checkpoint discovery; non-commercial)"
NAMEPAT = "(茶|Tea|TEA|ティー|チャイ|紅茶|抹茶|茶房)"

def request(url, data=None, timeout=90):
    req = Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as f:
        return f.read()

def station_data():
    # Same 2026-07-31 source used in prior 2346-station provisional ledger.
    body = request(SRC, timeout=40).decode("utf-8-sig")
    stations = []
    for row in csv.DictReader(io.StringIO(body)):
        p = TARGET.get(row["pref"])
        if not p:
            continue
        try:
            lat, lon = float(row["lat"]), float(row["lng"])
        except (ValueError, TypeError):
            continue
        stations.append({"source_station_id": row["station_id"], "prefecture": p,
                         "station_name": row["name_ja"], "lat": lat, "lon": lon,
                         "operators": row["operators"], "source_name": row["name_source"]})
    if len(stations) != 2346:
        raise RuntimeError("Refusing unverified master: 2346 expected, got %d" % len(stations))
    return stations

def overpass_query(stations):
    latitudes = [r["lat"] for r in stations]
    longitudes = [r["lon"] for r in stations]
    b = (min(latitudes) - .013, min(longitudes) - .013,
         max(latitudes) + .013, max(longitudes) + .013)
    bbox = ",".join(f"{z:.5f}" for z in b)
    return (f'[out:json][timeout:120];('
            f'nwr["shop"="tea"]({bbox});'
            f'nwr["amenity"="cafe"]["name"~"{NAMEPAT}",i]({bbox});'
            f'nwr["shop"="beverages"]["name"~"{NAMEPAT}",i]({bbox});'
            f');out center tags;')

def discover(pref, stations):
    body = urlencode({"data":overpass_query(stations)}).encode("utf-8")
    errors=[]
    for endpoint in HOSTS:
        for attempt in range(2):
            try:
                data = json.loads(request(endpoint, body, timeout=180))
                if not isinstance(data.get("elements"), list):
                    raise RuntimeError("Missing Overpass elements")
                return data["elements"], endpoint, errors
            except (HTTPError, URLError, OSError, ValueError, RuntimeError) as e:
                errors.append(f"{endpoint} attempt {attempt+1}: {str(e)[:160]}")
                time.sleep(3 * (attempt + 1))
    return None, "", errors

def distance_m(a,b,c,d):
    rad = math.pi / 180
    delta_lat,delta_lon=(c-a)*rad,(d-b)*rad
    x=math.sin(delta_lat/2)**2+math.cos(a*rad)*math.cos(c*rad)*math.sin(delta_lon/2)**2
    return 12742000*math.atan2(math.sqrt(x),math.sqrt(max(0.0,1-x)))

def candidate_tags(x):
    return x.get("tags") or {}

def match_candidates(station, objects):
    result=[]
    for obj in objects:
        c=obj.get("center") or obj
        if "lat" not in c or "lon" not in c:
            continue
        d=distance_m(station["lat"],station["lon"],c["lat"],c["lon"])
        if d>1200:
            continue
        tags=candidate_tags(obj)
        result.append({"osm_type":obj["type"],"osm_id":obj["id"],
                       "name":tags.get("name",""),"distance_m":round(d),
                       "shop":tags.get("shop",""),"amenity":tags.get("amenity",""),
                       "website":tags.get("website") or tags.get("contact:website",""),
                       "instagram":tags.get("contact:instagram") or tags.get("instagram",""),
                       "osm_source_url":f'https://www.openstreetmap.org/{obj["type"]}/{obj["id"]}'})
    return sorted(result,key=lambda x:x["distance_m"])

def csvwrite(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def git(*args):
    subprocess.run(["git",*args],check=True)

def main():
    stations=station_data()
    now=datetime.now(JST).isoformat(timespec="seconds")
    groups=defaultdict(list)
    for station in stations:groups[station["prefecture"]].append(station)
    results={}
    statuses={}
    errs={}
    for prefecture in TARGET.values():
        elements,endpoint,errors=discover(prefecture,groups[prefecture])
        results[prefecture]=elements
        statuses[prefecture]=endpoint
        errs[prefecture]=errors
        print(prefecture,"elements",len(elements) if elements is not None else "ERROR","source",endpoint, flush=True)
    if all(elements is None for elements in results.values()):
        raise RuntimeError("No Overpass source returned evidence; aborting without commits")

    station_rows=[]
    candidate_rows=[]
    for station in stations:
        pref=station["prefecture"]
        objects=results[pref]
        checked=objects is not None
        nearby=match_candidates(station,objects) if checked else []
        s={"source_station_id":station["source_station_id"],
           "prefecture":pref,"station_name":station["station_name"],
           "latitude":station["lat"],"longitude":station["lon"],
           "checkpoint_time_jst":now,
           "osm_scan_status":"osm_prescreened" if checked else "blocked",
           "osm_candidates_1200m":len(nearby),
           "six_tea_genres_web_verified":"NO",
           "instagram_verified":"NO",
           "actual_station_keyword_web_search":"NO",
           "not_found_meaning":"OSM absence does not imply shop absence",
           "osm_api_endpoint":statuses[pref],
           "source_station_master":SRC}
        station_rows.append(s)
        for item in nearby:
            c=dict(s)
            c.update(item)
            c["verification_status"]="unverified_osm_lead"
            candidate_rows.append(c)
    fields_station=list(station_rows[0].keys())
    fields_candidates=list(candidate_rows[0].keys()) if candidate_rows else fields_station+["verification_status"]
    csvwrite(OUT/"station_master_2346.csv",station_rows,fields_station)
    manifest={"source":SRC,"source_version":"2.1.2 (2026-07-31; N02-2024/ODPT)",
              "source_license":"CC BY 4.0","scope":list(TARGET.values()),
              "station_count":len(stations),"batch_size":BATCH_SIZE,
              "completed_six_genre_web_station_count":0,"data_timestamp_jst":now,
              "overpass_endpoints":statuses,"errors":errs,
              "meaning":"OSM candidate prescreen only, NOT complete tea shop web+Instagram exploration"}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    git("add",str(OUT/"station_master_2346.csv"),str(OUT/"manifest.json"))
    git("commit","-m","research: preserve 2346-station source and OSM prescreen provenance")
    git("push","origin","HEAD")

    for start in range(0,len(station_rows),BATCH_SIZE):
        stop=min(start+BATCH_SIZE,len(station_rows))
        bno=start//BATCH_SIZE+1
        slice_rows=station_rows[start:stop]
        idset={s["source_station_id"] for s in slice_rows}
        cands=[c for c in candidate_rows if c["source_station_id"] in idset]
        base=OUT/"batches"/f"batch_{bno:03d}"
        csvwrite(base.with_suffix(".stations.csv"),slice_rows,fields_station)
        csvwrite(base.with_suffix(".osm_candidates.csv"),cands,fields_candidates)
        audit={"batch_number":bno,"station_start":start+1,"station_end":stop,
               "station_count":len(slice_rows),"osm_prescreened":sum(s["osm_scan_status"]=="osm_prescreened" for s in slice_rows),
               "blocked":sum(s["osm_scan_status"]=="blocked" for s in slice_rows),
               "osm_leads":len(cands),"fully_web_verified_stations":0,
               "warning":"Not evidence of exhaustive tea-genre/Instagram search"}
        base.with_suffix(".qa.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
        git("add",str(base.with_suffix(".stations.csv")),str(base.with_suffix(".osm_candidates.csv")),str(base.with_suffix(".qa.json")))
        git("commit","-m",f"research: checkpoint {bno:02d} stations {start+1}-{stop} (OSM prescreen only)")
        git("push","origin","HEAD")
        print(json.dumps(audit,ensure_ascii=False),flush=True)
    print("All checkpoints written; NOT completed full web and Instagram tea genre research.",flush=True)

if __name__=="__main__":
    main()
