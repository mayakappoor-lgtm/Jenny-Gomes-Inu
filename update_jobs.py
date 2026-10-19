#!/usr/bin/env python3
"""Build jobs.json (up to 100 postings) from Job Bank's open data.

Source: Job Postings Advertised on Canada's National Job Bank Website,
Employment and Social Development Canada, Open Government Licence - Canada.

Usage:
  python update_jobs.py                 # download the newest English monthly CSV
  python update_jobs.py --file my.csv   # use a local CSV (for testing)
The script prints the CSV column names it sees. If a field is empty in
jobs.json, adjust the keywords in the pick(...) calls below.
"""
import argparse, csv, datetime, io, json, random, re, sys, urllib.parse, urllib.request

PKG = "https://open.canada.ca/data/api/action/package_show?id=ea639e28-c0fc-48bf-b5dd-b8899bd43072"
MAX = 100
CATS = {"0": "Legislative and senior management", "1": "Business, finance and administration",
        "2": "Natural and applied sciences", "3": "Health",
        "4": "Education, law, social and government services", "5": "Art, culture, recreation and sport",
        "6": "Sales and service", "7": "Trades, transport and equipment operators",
        "8": "Natural resources and agriculture", "9": "Manufacturing and utilities"}
PROVS = {"AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
         "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
         "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "PEI": "Prince Edward Island",
         "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon"}

def latest_csv():
    with urllib.request.urlopen(PKG, timeout=60) as r:
        pkg = json.load(r)["result"]
    for res in pkg["resources"]:
        u = res.get("url", "")
        if u.lower().endswith(".csv") and re.search(r"-en[-.]", u):
            return u, res.get("name", "")
    sys.exit("No English CSV found in the dataset.")

def pick(headers, *keys):
    for k in keys:
        for h in headers:
            if k in h.lower():
                return h
    return None

def clean(v):
    v = (v or "").strip()
    return "" if v.upper() in ("", "NA", "N/A", "NULL", "NONE") else v

def yes(v):
    v = clean(v).lower()
    return v in ("yes", "y", "true", "1") or v.startswith("lmia") or "approved" in v

def open_rows(src):
    csv.field_size_limit(10**7)
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "jobs-updater"})
        f = io.TextIOWrapper(urllib.request.urlopen(req, timeout=300), encoding="utf-8-sig", errors="replace", newline="")
    else:
        f = open(src, encoding="utf-8-sig", errors="replace", newline="")
    return csv.DictReader(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--out", default="jobs.json")
    a = ap.parse_args()
    src, name = (a.file, "") if a.file else latest_csv()
    rows = open_rows(src)
    H = rows.fieldnames or []
    print("Columns:", H)
    T = pick(H, "job title", "title"); E = pick(H, "employer"); CITY = pick(H, "city"); LOC = pick(H, "location")
    PROV = pick(H, "province", "territory"); SAL = pick(H, "salary"); NOC = pick(H, "noc")
    DATE = pick(H, "date posted", "posted", "date"); LM = pick(H, "lmia", "foreign", "tfw")
    URL = pick(H, "url", "link"); PID = pick(H, "posting id", "job id", "jobid")
    rnd = random.Random(datetime.date.today().isoformat())
    pools = {"lm": [], "other": []}; seen = {"lm": 0, "other": 0}
    for row in rows:
        title = clean(row.get(T)) if T else ""
        if not title:
            continue
        loc = clean(row.get(CITY)) if CITY else clean(row.get(LOC)) if LOC else ""
        prov = clean(row.get(PROV)) if PROV else ""
        if not prov:
            m = re.search(r"\b(AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|PEI|QC|SK|YT)\b", loc)
            prov = m.group(1) if m else ""
        prov = PROVS.get(prov.upper(), prov)
        m = re.search(r"\d{5}", row.get(NOC) or "") if NOC else None
        job = {"t": title, "co": clean(row.get(E)) if E else "", "loc": loc, "prov": prov,
               "f": CATS.get(m.group(0)[0], "") if m else "",
               "pay": clean(row.get(SAL)) if SAL else "", "posted": clean(row.get(DATE)) if DATE else ""}
        if LM:
            job["lmia"] = yes(row.get(LM))
        u = clean(row.get(URL)) if URL else ""
        pid = clean(row.get(PID)) if PID else ""
        job["url"] = u if u.startswith("https://") else (
            "https://www.jobbank.gc.ca/jobsearch/jobposting/" + pid if pid.isdigit() else
            "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring=" + urllib.parse.quote(title))
        job = {k: v for k, v in job.items() if v not in ("", None)}
        k = "lm" if job.get("lmia") else "other"
        seen[k] += 1
        if len(pools[k]) < MAX:
            pools[k].append(job)
        else:
            i = rnd.randrange(seen[k])
            if i < MAX:
                pools[k][i] = job
    lm_n = min(len(pools["lm"]), MAX // 2)
    jobs = pools["lm"][:lm_n] + pools["other"][:MAX - lm_n]
    if not jobs:
        sys.exit("No jobs found. Check the printed column names.")
    mo = re.match(r"([A-Za-z]+ \d{4})", name)
    out = {"updated": mo.group(1) if mo else datetime.date.today().isoformat(), "jobs": jobs}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("Wrote", len(jobs), "jobs to", a.out)

if __name__ == "__main__":
    main()
