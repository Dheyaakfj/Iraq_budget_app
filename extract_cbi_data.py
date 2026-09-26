# -*- coding: utf-8 -*-
"""Parse the official CBI workbook without fixed years or positional units.

Local export: python extract_cbi_data.py [workbook.xlsx] --output data
Scheduled ingestion and validation: python sync_cbi_data.py
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from io import BytesIO
import math
from pathlib import Path
import re

from openpyxl import load_workbook
import pandas as pd

PARSER_VERSION = 1
RESERVES = "الاحتياطيات الأجنبية (مليار دينار)"
M0 = "M0 الأساس النقدي (مليار دينار)"
FX = "سعر الصرف (دينار/دولار)"
IMPORTS = "الواردات السلعية (مليون دولار)"
REVENUE = "الإيرادات التراكمية (مليار دينار)"
EXPENSE = "النفقات التراكمية (مليار دينار)"
CURRENT = "النفقات الجارية التراكمية (مليار دينار)"
BALANCE = "الرصيد التراكمي (مليار دينار)"
ANNUAL_NAMES = {
    REVENUE: "الإيرادات السنوية (مليار دينار)",
    EXPENSE: "النفقات السنوية (مليار دينار)",
    CURRENT: "النفقات الجارية السنوية (مليار دينار)",
    BALANCE: "الرصيد السنوي (مليار دينار)",
}
MONTHS = {name: i for i, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class DataValidationError(ValueError):
    """Source cannot be safely interpreted; keep the last published dataset."""


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "").replace("ـ", "")).strip()


def number(value):
    if value is None or normalize(value) in {"", "-", "…", "...", "—"}:
        return None
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise DataValidationError(f"Invalid numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise DataValidationError("Non-finite number in source")
    return result


def period(value):
    if isinstance(value, (datetime, date)):
        return date(value.year, value.month, 1)
    text = normalize(value)
    match = re.fullmatch(r"Dec\.?\s*(20\d{2})", text, re.I)
    if match:
        return date(int(match[1]), 12, 1)
    match = re.fullmatch(r"\d{1,2}/(\d{1,2})/(20\d{2})", text)
    if match:
        return date(int(match[2]), int(match[1]), 1)
    return None


# Match the Arabic part of bilingual row labels, and validate units explicitly.
INDICATORS = [
    ("الذهب", "الذهب (مليار دينار)", "مليار دينار"),
    ("التضخم الاساس", "التضخم الأساس %", "%"),
    ("التضخم", "التضخم %", "%"),
    ("معدل سعر الصرف", FX, "دينار"),
    ("M0", M0, "مليار دينار"),
    ("M1", "M1 (مليار دينار)", "مليار دينار"),
    ("M2", "M2 (مليار دينار)", "مليار دينار"),
    ("الصادرات السلعية", "الصادرات السلعية (مليون دولار)", "مليون دولار"),
    ("الواردات السلعية", IMPORTS, "مليون دولار"),
]


def parse_indicators(rows, today):
    header_index = next((i for i, r in enumerate(rows) if normalize(r[0]) == "التفاصيل"), None)
    if header_index is None:
        raise DataValidationError("Missing economic indicators header")
    columns, warnings, seen_dates = [], [], set()
    for col, raw in enumerate(rows[header_index][2:], 2):
        if raw is None:
            continue
        parsed = period(raw)
        if parsed is None:
            raise DataValidationError(f"Unknown period header: {raw!r}")
        if parsed > date(today.year, today.month, 1):
            warnings.append({"sheet": "المؤشرات الاقتصادية", "column": col + 1,
                             "source_header": str(raw), "reason": "future_period_excluded"})
            continue
        key = parsed.strftime("%Y-%m")
        if columns and key < columns[-1][1]:
            raise DataValidationError("Indicator date columns are not chronological")
        if key in seen_dates:
            raise DataValidationError(f"Duplicate indicator period: {key}")
        seen_dates.add(key)
        columns.append((col, key))
    if not columns:
        raise DataValidationError("No valid indicator periods")
    records = {}
    for row in rows[header_index + 1:]:
        label, unit = normalize(row[0]), normalize(row[1])
        matched = None
        if label.startswith("الاحتياطيات الاجنبية"):
            if unit == "مليار دينار":
                matched = RESERVES
            elif unit == "مليار دولار":
                matched = "الاحتياطيات الأجنبية (مليار دولار)"
            else:
                raise DataValidationError(f"Unknown reserves unit: {unit}")
        else:
            for prefix, metric, required_unit in INDICATORS:
                if label == prefix or label.startswith(prefix + " "):
                    if unit != required_unit:
                        raise DataValidationError(f"Unexpected unit for {metric}: {unit}")
                    matched = metric
                    break
        if matched:
            if matched in records:
                raise DataValidationError(f"Duplicate indicator: {matched}")
            records[matched] = {key: number(row[col]) for col, key in columns}
    required = {RESERVES, M0, FX, IMPORTS}
    if not required <= records.keys():
        raise DataValidationError(f"Missing indicators: {required - records.keys()}")
    periods = sorted(seen_dates)
    complete = [p for p in periods if all(records[m][p] is not None for m in [RESERVES, M0, FX])]
    if not complete or complete[-1] != periods[-1]:
        raise DataValidationError("Latest monetary period lacks reserves, M0 or exchange rate")
    for metric in [RESERVES, M0, FX]:
        if any(v is not None and v <= 0 for v in records[metric].values()):
            raise DataValidationError(f"Non-positive value for {metric}")
    annual_periods = [p for p in periods if p.endswith('-12') and int(p[:4]) < today.year]
    if not annual_periods:
        raise DataValidationError("No completed annual indicator periods")
    return records, annual_periods, complete[-1], warnings


def parse_fiscal(rows, today):
    if not any("million id" in normalize(cell).lower() for row in rows[:10] for cell in row):
        raise DataValidationError("Fiscal table unit must be Million ID")
    header = next((i for i, r in enumerate(rows) if normalize(r[0]).lower() == "period"), None)
    if header is None:
        raise DataValidationError("Missing fiscal header")
    # English header names are independent of column positions.
    english = [normalize(v).lower() for v in rows[header + 1]]
    names = {REVENUE: "actual revenues", EXPENSE: "actual expenditures",
             CURRENT: "current expenditures", BALANCE: "surplus /deficit*"}
    positions = {}
    for key, label in names.items():
        matches = [i for i, text in enumerate(english) if text.replace(' ', '') == label.replace(' ', '')]
        if len(matches) != 1:
            raise DataValidationError(f"Missing/ambiguous fiscal column: {label}")
        positions[key] = matches[0]
    monthly, annual, year = [], {}, None
    for row in rows[header + 2:]:
        first = normalize(row[0])
        if re.fullmatch(r"20\d{2}(?:\.0)?", first):
            year = int(float(first))
            # Older completed years are single annual rows, not January observations.
            if all(row[positions[k]] is not None for k in [REVENUE, EXPENSE, BALANCE]):
                month, annual_only = 12, True
            else:
                continue
        else:
            month = MONTHS.get(first.lower().replace('.', '')[:3])
            annual_only = False
            if month is None:
                if first and any(row[c] is not None for c in positions.values()):
                    raise DataValidationError(f"Unknown fiscal period: {first}")
                continue
        if year is None or date(year, month, 1) > date(today.year, today.month, 1):
            raise DataValidationError("Missing or future fiscal year")
        values = {k: number(row[c]) for k, c in positions.items()}
        if all(v is None for v in values.values()):
            continue  # unpublished, blank month
        if any(values[k] is None for k in [REVENUE, EXPENSE, BALANCE]):
            raise DataValidationError(f"Incomplete fiscal record: {year}-{month:02d}")
        if abs(values[REVENUE] - values[EXPENSE] - values[BALANCE]) > 2:
            raise DataValidationError(f"Revenue/expenditure identity failed: {year}-{month:02d}")
        if min(values[REVENUE], values[EXPENSE]) < 0:
            raise DataValidationError("Negative revenue/expenditure")
        if values[CURRENT] is not None and not 0 <= values[CURRENT] <= values[EXPENSE] + 2:
            raise DataValidationError("Invalid current expenditures")
        record = {"السنة": year, "الشهر": month,
                  **{k: round(v / 1000, 3) if v is not None else None for k, v in values.items()}}
        if not annual_only:
            monthly.append(record)
        if month == 12 and year < today.year:
            if year in annual:
                raise DataValidationError(f"Duplicate fiscal year: {year}")
            annual[year] = {ANNUAL_NAMES.get(k, k): v for k, v in record.items()}
    monthly.sort(key=lambda r: (r["السنة"], r["الشهر"]))
    keys = [(r['السنة'], r['الشهر']) for r in monthly]
    if not monthly or not annual or len(keys) != len(set(keys)):
        raise DataValidationError("Missing or duplicate fiscal periods")
    for year in {y for y, m in keys}:
        months = [m for y, m in keys if y == year]
        if months != list(range(1, max(months) + 1)):
            raise DataValidationError(f"Missing cumulative fiscal month in {year}")
    return monthly, [annual[y] for y in sorted(annual)]


def parse_workbook(content: bytes, today=None):
    today = today or date.today()
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        sheets = {name.strip(): name for name in workbook.sheetnames}
        if not {"المؤشرات الاقتصادية", "6-1"} <= sheets.keys():
            raise DataValidationError("Required CBI sheets missing")
        indicators, annual_periods, latest, warnings = parse_indicators(
            list(workbook[sheets["المؤشرات الاقتصادية"]].values), today)
        monthly, annual = parse_fiscal(list(workbook[sheets["6-1"]].values), today)
    finally:
        workbook.close()
    annual_indicators = {metric: {p[:4]: values[p] for p in annual_periods}
                         for metric, values in indicators.items()}
    if annual[-1][ANNUAL_NAMES[CURRENT]] is None:
        raise DataValidationError("Latest completed year has no current expenditure value")
    if not any(value is not None and value > 0 for value in annual_indicators[IMPORTS].values()):
        raise DataValidationError("No valid annual import data")
    return {"parser_version": PARSER_VERSION, "indicators": indicators,
            "annual_indicators": annual_indicators, "fiscal_monthly": monthly,
            "fiscal_annual": annual, "periods": {
                "monetary": latest,
                "fiscal": f"{monthly[-1]['السنة']}-{monthly[-1]['الشهر']:02d}",
                "annual_budget": str(annual[-1]['السنة'])}, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', nargs='?', default='البيانات الشهرية.xlsx')
    parser.add_argument('--output', default='data')
    args = parser.parse_args()
    result = parse_workbook(Path(args.workbook).read_bytes())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    # Parse and validate everything before exporting any file.
    for key, filename in [('annual_indicators', 'cbi_annual.csv'), ('indicators', 'cbi_indicators.csv')]:
        frame = pd.DataFrame.from_dict(result[key], orient='index')
        frame.index.name = 'المؤشر'
        frame.to_csv(out / filename, encoding='utf-8-sig')
    for key in ['fiscal_monthly', 'fiscal_annual']:
        pd.DataFrame(result[key]).to_csv(out / f'cbi_{key}.csv', index=False, encoding='utf-8-sig')
    print(result['periods'])
    for warning in result['warnings']:
        print('WARNING:', warning)


if __name__ == '__main__':
    main()
