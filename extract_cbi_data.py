# -*- coding: utf-8 -*-
"""
استخراج السلاسل المفيدة من ملف البنك المركزي العراقي الشهري إلى ملفات CSV صغيرة.
المصدر: البيانات الشهرية.xlsx  (لا يُرفع للمستودع — كبير الحجم)
المخرجات: مجلد data/  (cbi_annual.csv, cbi_fiscal_monthly.csv)

التشغيل:  python extract_cbi_data.py
"""
import sys
import os
import re
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = "البيانات الشهرية.xlsx"
OUT = "data"
os.makedirs(OUT, exist_ok=True)


# ----------------------------------------------------------------------
# 1) المؤشرات السنوية (المؤشرات الاقتصادية)
# ----------------------------------------------------------------------
def extract_annual():
    df = pd.read_excel(SRC, sheet_name="المؤشرات الاقتصادية ", header=None)
    years = ["2023", "2024", "2025"]   # أعمدة 2،3،4

    # (التسمية في الملف -> اسم مختصر) ، نطابق عمود 0
    targets = {
        "الاحتياطيات الاجنبية لدى البنك المركزي": None,  # يتكرر (دولار/دينار) — نتعامل أدناه
        "الذهب": "الذهب (مليار دينار)",
        "التضخم": "التضخم %",
        "التضخم الاساس": "التضخم الأساس %",
        "معدل سعر الصرف": "سعر الصرف (دينار/دولار)",
        "M0": "M0 الأساس النقدي (مليار دينار)",
        "M1": "M1 (مليار دينار)",
        "M2": "M2 (مليار دينار)",
        "الصادرات السلعية": "الصادرات السلعية (مليون دولار)",
        "الواردات السلعية": "الواردات السلعية (مليون دولار)",
    }

    rows = {}
    seen_reserves = 0
    for _, r in df.iterrows():
        label = str(r[0]).strip()
        vals = [r[2], r[3], r[4]]
        if "الاحتياطيات الاجنبية" in label:
            # أول ظهور بالدولار، الثاني بالدينار
            if seen_reserves == 0:
                rows["الاحتياطيات الأجنبية (مليار دولار)"] = vals
            else:
                rows["الاحتياطيات الأجنبية (مليار دينار)"] = vals
            seen_reserves += 1
            continue
        for key, name in targets.items():
            if name is None:
                continue
            if label == key:
                rows[name] = vals

    out = pd.DataFrame(rows, index=years).T
    out.index.name = "المؤشر"
    out.columns = years
    out.to_csv(os.path.join(OUT, "cbi_annual.csv"), encoding="utf-8-sig")
    print("✅ cbi_annual.csv")
    print(out.to_string())
    return out


# ----------------------------------------------------------------------
# 2) الموازنة العامة الشهرية التراكمية (6-1)
# ----------------------------------------------------------------------
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def month_num(s):
    s = str(s).strip().lower().replace(".", "")
    return MONTHS.get(s[:4]) or MONTHS.get(s[:3])


def extract_fiscal():
    df = pd.read_excel(SRC, sheet_name="6-1", header=None)
    records = []
    year = None
    for _, r in df.iterrows():
        c0 = str(r[0]).strip()
        if re.fullmatch(r"20\d{2}", c0):
            year = int(c0)
            continue
        mn = month_num(c0)
        if year is None or mn is None:
            continue
        try:
            rev = float(r[1]) / 1000.0   # مليون -> مليار دينار
            exp = float(r[4]) / 1000.0
            bal = float(r[7]) / 1000.0
        except (TypeError, ValueError):
            continue
        records.append({
            "السنة": year, "الشهر": mn,
            "الإيرادات التراكمية (مليار دينار)": round(rev, 1),
            "النفقات التراكمية (مليار دينار)": round(exp, 1),
            "الرصيد التراكمي (مليار دينار)": round(bal, 1),
        })
    out = pd.DataFrame(records)
    out.to_csv(os.path.join(OUT, "cbi_fiscal_monthly.csv"), index=False, encoding="utf-8-sig")
    print("✅ cbi_fiscal_monthly.csv  (", len(out), "صفوف )")

    # ملخص سنوي = قيمة ديسمبر (التراكم الكامل)
    annual = out.sort_values("الشهر").groupby("السنة").last().reset_index()
    annual = annual.rename(columns={
        "الإيرادات التراكمية (مليار دينار)": "الإيرادات السنوية (مليار دينار)",
        "النفقات التراكمية (مليار دينار)": "النفقات السنوية (مليار دينار)",
        "الرصيد التراكمي (مليار دينار)": "الرصيد السنوي (مليار دينار)",
    })[["السنة", "الشهر", "الإيرادات السنوية (مليار دينار)",
        "النفقات السنوية (مليار دينار)", "الرصيد السنوي (مليار دينار)"]]
    annual.to_csv(os.path.join(OUT, "cbi_fiscal_annual.csv"), index=False, encoding="utf-8-sig")
    print("✅ cbi_fiscal_annual.csv")
    print(annual.to_string(index=False))
    return out


if __name__ == "__main__":
    extract_annual()
    print("-" * 60)
    extract_fiscal()
