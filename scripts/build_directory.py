"""Build the bilingual university and academic-unit directory from saved official sources (no network, reproducible).

Inputs (data/sources/, each line exactly as the source published it):
  moe114_institutions_en.txt   MOE University and College Directory (大專校院一覽表), academic year 114, school list with
                               English names: https://udb.moe.edu.tw/ulist/Resource/download/ulistaddress?extension=csv
                               (export dated 115.01.08). code|name_zh|name_en|website
  moe114_units.txt             same directory, departments by college:
                               https://udb.moe.edu.tw/ulist/Resource/download/ulistdepartmentlist_college?extension=csv
                               code|college_zh|unit_code|unit_zh (deduplicated by school + unit code)
  moe108_institutions_en.txt   MOE English school names, academic year 108 (data.gov.tw dataset 33207), cross-check only
  seed_*.csv                   the seed workbook the team supplied (MOE 2026 English-taught programme list, NTU's
                               official English academic list)
  ../institutions_moe.csv      the 139 institutions Crossroads already has (MOE year 115, stable moe_code)
  ../../app/departments.json   NTHU's reviewed department catalog (unchanged; used only to pair NTHU units)

Rules: English names are copied from a source, never translated or re-cased. Only data-encoding artifacts are cleaned
(runs of spaces, a doubled '' from CSV escaping); anything else odd (lower-case words, ALL CAPS, "And", "Liberal Art")
is kept as published and marked needs_review. A Chinese unit gets an English name only when a source pairs the two
for the same school (identical Chinese name); otherwise name_en stays empty.

Run: python scripts/build_directory.py  -> data/institutions_directory.csv, data/academic_units.csv, data/research/*
"""
import csv, json, os, re, collections

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "data", "sources")
OUT = os.path.join(ROOT, "data")
REP = os.path.join(ROOT, "data", "research")
U114 = "https://udb.moe.edu.tw/ulist/Resource/download/ulistaddress?extension=csv"
U114_UNITS = "https://udb.moe.edu.tw/ulist/Resource/download/ulistdepartmentlist_college?extension=csv"
U114_PAGE = "https://udb.moe.edu.tw/ulist/Resource"
M108 = "https://data.gov.tw/dataset/33207"
NTHU_UNITS = "https://www.nthu.edu.tw/units/education"
NTU_EN_LIST = "https://www.ntu.edu.tw/english/academics/academics_list.html"
HOST_SKIP = {"www", "www1", "w3", "w5", "web", "a001", "eng", "en"}


def lines(fn):
    with open(os.path.join(SRC, fn), encoding="utf-8") as f:
        return [l.rstrip("\n").split("|") for l in f if l.strip()]


def rows(fn):
    with open(os.path.join(SRC, fn), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean_en(s):
    """Encoding artifacts only: collapse runs of spaces, undo a doubled apostrophe from CSV escaping."""
    t = re.sub(r"\s+", " ", (s or "")).strip().replace("''", "'")
    return t


def oddities(s):
    """Reasons to have a person look at a published English name (it is still kept exactly as published)."""
    why = []
    words = s.replace(",", " ").split()
    if s.isupper() and len(s) > 6: why.append("all capitals as published")
    small = {"of", "and", "the", "for", "in", "at", "&"}
    for w in words[1:]:
        if w.lower() in small and w != w.lower(): why.append(f"capitalised '{w}' as published"); break
    for w in words:
        if w[:1].islower() and w.lower() not in small: why.append(f"lower-case '{w}' as published"); break
    if re.search(r"\bLiberal Art\b", s): why.append("'Liberal Art' (singular) as published")
    if re.search(r"\b(TZU HUI)\b", s): why.append("partly capitalised as published")
    return why


def unit_kind(name):
    base = re.sub(r"[（(].*?[)）]\s*$", "", name).strip() or name
    if re.search(r"(學位學程|學程)$", base): return "program"
    if re.search(r"(在職專班|專班|學士班|碩士班|博士班|學位班|MBA|EMBA|EMPP|MPP|IMBA)$", base, re.I): return "program"
    if re.search(r"研究所$", base): return "institute"
    if re.search(r"(學系|系|科)$", base): return "department"
    return "other"


def host_alias(url):
    h = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    parts = h.split(".")
    if "edu" not in parts: return ""
    left = parts[:parts.index("edu")]
    left = [p for p in left if p not in HOST_SKIP]
    return left[-1].upper() if left else ""


def main():
    os.makedirs(REP, exist_ok=True)
    with open(os.path.join(OUT, "institutions_moe.csv"), encoding="utf-8") as f:
        ours = list(csv.DictReader(f, delimiter="|"))
    m114 = {r[0]: r for r in lines("moe114_institutions_en.txt")}
    m108 = {r[0]: r for r in lines("moe108_institutions_en.txt")}
    seed_inst = {r["institution_zh"]: r for r in rows("seed_verified_universities.csv")}
    by_zh = {r["name_zh"]: r["moe_code"] for r in ours}

    inst_out, unverified = [], []
    for r in ours:
        c, zh = r["moe_code"], r["name_zh"]
        s = m114.get(c)
        en_raw = s[2] if s else ""
        en = clean_en(en_raw)
        why = oddities(en) if en else ["not in the MOE 114 English directory"]
        if en and en != en_raw: why = ["spacing/escaping cleaned from: " + en_raw] + why
        old = clean_en(m108[c][2]) if c in m108 else ""
        cross = "same" if old == en else ("renamed or corrected since 108" if old else "no 108 entry")
        seed = seed_inst.get(zh)
        if seed and seed["institution_en"] == en: cross += "; matches MOE 2026 English-taught list"
        status = "verified" if en and not [w for w in why if not w.startswith("spacing")] else ("needs_review" if en else "missing")
        web = (s[3] if s else "") or ("https://" + r["website_host"])
        alias = host_alias(web)
        own_dir = NTHU_UNITS if c == "0002" else (NTU_EN_LIST if c == "0003" else "")
        inst_out.append(dict(moe_code=c, name_zh=zh, name_en=en, en_status=status, en_source=U114 if en else "",
                             en_source_name="MOE University and College Directory, academic year 114 (export 115.01.08)" if en else "",
                             en_note="; ".join(why), en_crosscheck=cross, moe108_en=old, aliases=alias,
                             alias_source=("official website domain " + re.sub(r"^https?://", "", web).split("/")[0]) if alias else "",
                             website=web, directory_url=own_dir, directory_source="school" if own_dir else "",
                             moe_directory_url=U114_PAGE, intl_admissions_url=""))
        if status != "verified": unverified.append(inst_out[-1])

    # ---------- academic units ----------
    units = lines("moe114_units.txt")
    ours_codes = {r["moe_code"] for r in ours}
    dj = json.load(open(os.path.join(ROOT, "app", "departments.json"), encoding="utf-8"))
    nthu_src = dj.get("sources", {})
    nthu_zh = {u["zh"]: u for u in dj["units"]}
    seed_prog = collections.defaultdict(list)
    for p in rows("seed_moe_english_programs.csv"):
        seed_prog[by_zh.get(p["institution_zh"], "")].append(p)

    out_units, pairs, seed_used = [], collections.Counter(), set()
    for c, col, code, zh in units:
        if c not in ours_codes: continue
        en, src, st = "", "", ""
        if c == "0002" and zh in nthu_zh and nthu_zh[zh].get("en") and nthu_zh[zh].get("en_status") == "official":
            u = nthu_zh[zh]; en = u["en"]; src = nthu_src.get(u.get("en_source", ""), "app/departments.json"); st = "verified"
        for p in seed_prog.get(c, []):
            pz = p["department_or_program_zh"].strip()
            if (pz == zh or pz == zh + "(所)") and not en:   # "系(所)" in the MOE list = the department and its institute
                en = p["department_or_program_en"].strip(); src = p["source_url"]; st = "verified"; seed_used.add((c, zh))
                if re.search(r"\b(for|of|in|and|the) (Global|International)?$", en) or en.endswith((" for", " in", " of", " and")):
                    st = "needs_review"
        if en: pairs[st] += 1
        out_units.append(dict(moe_code=c, unit_code=code, college_zh=col, college_en="", name_zh=zh, name_en=en, en_status=st,
                              en_source=src, kind=unit_kind(zh), source=U114_UNITS, source_year="114"))

    seed_unmatched = [p for c, ps in seed_prog.items() for p in ps if (c, p["department_or_program_zh"].strip()) not in seed_used
                     and (c, p["department_or_program_zh"].strip().removesuffix("(所)")) not in seed_used]
    ntu_en = rows("seed_ntu_units_en.csv")

    def wcsv(path, recs, fields=None):
        fields = fields or list(recs[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", extrasaction="ignore"); w.writeheader(); w.writerows(recs)

    wcsv(os.path.join(OUT, "institutions_directory.csv"), inst_out)
    wcsv(os.path.join(OUT, "academic_units.csv"), out_units)
    wcsv(os.path.join(REP, "unverified_english_names.csv"), unverified)
    per = collections.Counter(u["moe_code"] for u in out_units)
    missing = [dict(moe_code=i["moe_code"], name_zh=i["name_zh"], name_en=i["name_en"], moe_units=per.get(i["moe_code"], 0),
                    school_directory_url=i["directory_url"], status="school directory captured" if i["directory_url"] else
                    ("MOE list only: school's own directory not captured" if per.get(i["moe_code"]) else "no units in any source")) for i in inst_out]
    wcsv(os.path.join(REP, "academic_directories.csv"), missing)
    wcsv(os.path.join(REP, "seed_programs_not_matched.csv"), seed_unmatched or [dict(note="none")])

    # NTHU: what the MOE list has that the reviewed catalog does not (for a person to review; nothing is changed)
    nthu_moe = [u for u in out_units if u["moe_code"] == "0002"]
    cat_only = [u for u in dj["units"] if u.get("active", True) and u["zh"] not in {x["name_zh"] for x in nthu_moe}]
    moe_only = [u for u in nthu_moe if u["name_zh"] not in nthu_zh]
    wcsv(os.path.join(REP, "nthu_catalog_vs_moe.csv"),
         [dict(side="catalog only", id=u["id"], zh=u["zh"], en=u.get("en", "")) for u in cat_only] +
         [dict(side="MOE 114 only", id=u["unit_code"], zh=u["name_zh"], en="") for u in moe_only], ["side", "id", "zh", "en"])

    kinds = collections.Counter(u["kind"] for u in out_units)
    st = collections.Counter(i["en_status"] for i in inst_out)
    rep = f"""# Directory coverage report

Generated by `scripts/build_directory.py` from saved official sources (`data/sources/`). Nothing here is machine-translated.

## Institutions (Crossroads' 139)

| | count |
|---|---|
| Total institutions | {len(inst_out)} |
| English name from MOE 114 directory | {sum(1 for i in inst_out if i['name_en'])} |
| English name verified (as published, no anomaly) | {st['verified']} |
| English name published but flagged for review (casing / wording kept as published) | {st['needs_review']} |
| No English name in any source | {st['missing']} |
| Same English name as MOE 108 | {sum(1 for i in inst_out if i['en_crosscheck'].startswith('same'))} |
| Renamed or corrected since MOE 108 | {sum(1 for i in inst_out if i['en_crosscheck'].startswith('renamed'))} |
| Search abbreviation from the school's own web domain | {sum(1 for i in inst_out if i['aliases'])} |
| School's own academic directory URL captured | {sum(1 for i in inst_out if i['directory_url'])} |
| Institutions with official units in the MOE 114 department list | {sum(1 for i in inst_out if per.get(i['moe_code']))} |
| International admissions URL verified | {sum(1 for i in inst_out if i['intl_admissions_url'])} |

## Academic units

| | count |
|---|---|
| Official units collected (MOE 114, Chinese, with college and MOE unit code) | {len(out_units)} |
| departments / graduate institutes / degree programmes / other | {kinds['department']} / {kinds['institute']} / {kinds['program']} / {kinds['other']} |
| Verified Chinese-English pairs | {pairs['verified']} |
| Pairs needing a check (English looks truncated in the seed) | {pairs['needs_review']} |
| Units with Chinese only (English left blank) | {len(out_units) - sum(pairs.values())} |
| NTU English-only entries from the seed (not paired: no source links them to a Chinese name) | {len(ntu_en)} |
| Seed English-taught programmes not found by exact Chinese name | {len(seed_unmatched)} |
| NTHU: catalog units not in MOE 114 / MOE 114 units not in catalog | {len(cat_only)} / {len(moe_only)} |

Still requiring manual verification: {st['needs_review'] + st['missing']} institution English names, {len(out_units) - pairs['verified']} unit English names
(all units without an English name, plus flagged pairs), {len(ntu_en)} NTU English names awaiting a Chinese pairing source.
"""
    open(os.path.join(REP, "coverage_report.md"), "w", encoding="utf-8").write(rep)
    print(rep)


if __name__ == "__main__":
    main()
