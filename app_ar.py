# -*- coding: utf-8 -*-
"""
تطبيق تحليل سيناريوهات الموازنة العراقية وأسعار النفط وسعر الصرف
================================================================
واجهة تفاعلية (Streamlit + Plotly) بتصميم RTL عربي.
"""

import io
from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from cbi_data import load_data, latest_preset, data_signature, LATEST_SCENARIO
from input_provenance import describe_input, format_value, audit_row, INPUT_UNITS, official_inputs, same_value
from reported_inputs import REPORTED_INPUTS, age_days, is_stale, supersedes
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import ui_kit as ui

from scenario_engine_ar import (
    مدخلات,
    جدول_حسب_سعر_النفط,
    جدول_حسب_سعر_الصرف,
    مصفوفة_الحساسية,
    تحليل_الفجوة,
    تقدير_التضخم,
    ملخص_السيناريو,
    حساب_الموازنة,
    صافي_براميل_التصدير,
    حفظ_النتائج,
    السيناريوهات_المسبقة,
    انشاء_مدخلات_من_سيناريو,
    حساب_مؤشر_الاستقرار,
    توليد_بيانات_سانكي,
    مقارنة_سيناريوهين,
    محاكاة_مونت_كارلو,
    جلب_اسعار_النفط_الحية,
    توليد_توصيات_السياسات,
)

# ----------------------------------------------------------------------
# إعداد الصفحة والهوية البصرية
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="مرصد الموازنة العراقية",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="auto",
)

# لوحة ألوان موحّدة مصدرها ui_kit، كي لا تتفرّع الألوان بين الواجهة والرسوم
PRIMARY = ui.PRIMARY
ACCENT = ui.ACCENT
DANGER = ui.DANGER
INK = ui.INK
MUTED = ui.MUTED
COLORWAY = ui.COLORWAY

ui.inject_theme()


def kpi_card(label, value, sub="", tone="ink"):
    cls = {"pos": "pos", "neg": "neg"}.get(tone, "")
    sub_html = f'<div class="sub {cls}">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """


def fmt_trln(x):
    """تنسيق مليار دينار إلى ترليون."""
    return f"{x/1000.0:,.1f} ترليون"


def fmt_trln_html(x):
    """تنسيق مليار دينار إلى ترليون مع الحفاظ على اتجاه الإشارة السالبة في HTML."""
    val = x / 1000.0
    if val < 0:
        return f'<span dir="ltr">-{abs(val):,.1f}</span> ترليون'
    return f"{val:,.1f} ترليون"


def style_fig(fig, height=360, show_legend=True, y_title=""):
    """يفوّض إلى نظام التصميم؛ يبقى الاسم كما هو حتى لا تتغيّر مواضع الاستدعاء."""
    return ui.style_chart(fig, height=height, show_legend=show_legend, y_title=y_title)


# ----------------------------------------------------------------------
# تحميل بيانات البنك المركزي الفعلية (إن وُجدت)
# ----------------------------------------------------------------------
import os
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@st.cache_data
def تحميل_بيانات_المركزي(signature):
    """Invalidate cached tables whenever the published snapshot or status changes."""
    return load_data(_DATA_DIR)


def قيمة_سنوية(بيانات, مؤشر, سنة, افتراضي=None):
    """يجلب قيمة مؤشر سنوي من جدول cbi_annual."""
    df = بيانات.get("سنوي")
    if df is None or مؤشر not in df.index or str(سنة) not in df.columns:
        return افتراضي
    try:
        v = float(df.loc[مؤشر, str(سنة)])
        return v if v == v else افتراضي  # تفادي NaN
    except Exception:
        return افتراضي


cbi_signature = data_signature(_DATA_DIR)
بيانات_المركزي = تحميل_بيانات_المركزي(cbi_signature)
السيناريوهات_المتاحة = dict(السيناريوهات_المسبقة)
if بيانات_المركزي.get("snapshot"):
    baseline = next(iter(السيناريوهات_المسبقة.values()))
    السيناريوهات_المتاحة = {
        LATEST_SCENARIO: latest_preset(بيانات_المركزي["snapshot"], baseline),
        **السيناريوهات_المسبقة,
    }


input_audit = []


def عرض_مصدر_المدخل(field, label, value):
    reported = REPORTED_INPUTS.get(field)
    if reported is not None and field in d and not same_value(d[field], reported["value"]):
        reported = None  # السيناريو يعلن قيمة أخرى (تاريخية)؛ لا يُنسب إليها التصريح
    baseline = d.get(field, reported["value"] if reported else next(iter(السيناريوهات_المسبقة.values()))[field])
    detail = describe_input(value, baseline, input_sources.get(field),
                            historical=سيناريو_مختار in السيناريوهات_المسبقة, reported=reported)
    input_audit.append(audit_row(label, detail, INPUT_UNITS[field]))
    parts = [f'<span class="origin-badge">{detail["label"]}</span>']
    if detail["origin"] in ("official", "reported"):
        parts.append(f'<bdi dir="ltr">{escape(detail["period"])}</bdi>')
        جهة = "البنك المركزي" if detail["origin"] == "official" else (reported or {}).get("link_label", "المصدر")
        link_text = "المرجع الرسمي" if detail["kind"] == "manual" else جهة
        parts.append(f'<a href="{escape(detail["source_url"], quote=True)}" target="_blank" rel="noopener noreferrer">{link_text}</a>')
    elif detail["origin"] == "reference":
        parts.append('<span>قيمة ثابتة للسيناريو</span>')
    else:
        parts.append('<span>قابل للتعديل · غير مستخرج من النشرة</span>')
    if detail["kind"] == "manual":
        parts.append(f'<span>المرجع: <bdi dir="ltr">{escape(format_value(detail["reference"]))}</bdi></span>')
    st.markdown(f'<div class="input-origin {detail["kind"]}" data-field="{escape(field)}">{"".join(parts)}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------
# الشريط الجانبي — المدخلات والسيناريوهات الجاهزة
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ المدخلات والسيناريوهات")

    قائمة_السيناريوهات = list(السيناريوهات_المتاحة.keys()) + ["⚙️ مخصّص (تعديل حر)"]
    سيناريو_مختار = st.selectbox(
        "🎯 السيناريو الجاهز (Presets)",
        قائمة_السيناريوهات,
        index=0,
        help="اختر سيناريو قياسي جاهز لضبط جميع الافتراضات تلقائياً بنقرة واحدة.",
    )

    if سيناريو_مختار in السيناريوهات_المتاحة:
        d = السيناريوهات_المتاحة[سيناريو_مختار]
        st.info(f"💡 **نبذة:** {d['وصف']}")
    else:
        d = السيناريوهات_المسبقة["الوضع الراهن 2025 (الإنفاق الفعلي - البنك المركزي)"]

    # Each preset gets its own defaults, including on Streamlit versions where
    # changing a widget default does not reset the previous session value.
    revision = بيانات_المركزي.get("snapshot", {}).get("source", {}).get("sha256", "") if سيناريو_مختار == LATEST_SCENARIO else ""
    widget_scope = f"inputs:{سيناريو_مختار}:{revision}"
    input_sources = official_inputs(بيانات_المركزي["snapshot"]) if سيناريو_مختار == LATEST_SCENARIO else {}
    _صرف_نشرة = input_sources.get("سعر_الصرف_الرسمي")
    if _صرف_نشرة and supersedes(REPORTED_INPUTS["سعر_الصرف_الرسمي"], _صرف_نشرة["period"]):
        input_sources.pop("سعر_الصرف_الرسمي")  # قرار مجلس الوزراء أحدث من فترة النشرة
    st.caption("رسمي: قيمة من النشرة مع فترتها ومصدرها. افتراض: اختيار للنموذج. تعديل القيمة الرسمية يجعلها معدّلة يدويًا.")

    with st.expander("🛢️ النفط والإنتاج والتكاليف", expanded=True):
        اسعار = st.multiselect(
            "أسعار النفط (دولار/برميل)",
            sorted(set([35, 40, 45, 50, 55, 60, 62, 65, 67, 70, 72, 75, 80, 85, 90, 95, 100, 110, 120, 125] + d.get("اسعار_النفط", []))),
            default=d.get("اسعار_النفط", [50, 60, 70, 80, 90, 110]),
            key=f"{widget_scope}:اسعار",
        )
        if not اسعار:
            اسعار = [60]
            st.caption("لم تُحدد قيم؛ تُستخدم القيمة الاحتياطية الموضحة في سجل المدخلات.")
        عرض_مصدر_المدخل("اسعار_النفط", "أسعار النفط (دولار/برميل)", اسعار)
        _صادرات_مرجعية = REPORTED_INPUTS["صادرات_مقاسة_مليون_برميل_يوم"]
        _مقاسة_السيناريو = d.get("صادرات_مقاسة_مليون_برميل_يوم")
        استخدم_مقاسة = st.toggle(
            "استخدام الصادرات المقاسة بدل (الإنتاج − الاستهلاك)",
            value=_مقاسة_السيناريو is not None,
            help="الإيرادات النفطية تُحسب على الصادرات الفعلية المعلنة. الإنتاج والاستهلاك يُهملان حين يُفعَّل.",
            key=f"{widget_scope}:استخدم_مقاسة",
        )
        صادرات_مقاسة = None
        if استخدم_مقاسة:
            صادرات_مقاسة = st.number_input(
                "الصادرات المقاسة (مليون برميل/يوم)",
                min_value=0.0,
                value=float(_مقاسة_السيناريو if _مقاسة_السيناريو is not None else _صادرات_مرجعية["value"]),
                step=0.05,
                help="صافي ما يُصدَّر فعلياً، وهو صافٍ أصلاً من استهلاك المصافي المحلية.",
                key=f"{widget_scope}:صادرات_مقاسة",
            )
            عرض_مصدر_المدخل("صادرات_مقاسة_مليون_برميل_يوم", "الصادرات المقاسة (مليون برميل/يوم)", صادرات_مقاسة)
            if is_stale(_صادرات_مرجعية):
                st.warning(f"المرجع الرسمي للتصدير عمره {age_days(_صادرات_مرجعية)} يوماً. حدّثه قبل الاعتماد على الإيرادات.")
            st.caption(f"ملاحظة المرجع: {_صادرات_مرجعية['note']}")
        _لاحقة = " (غير مستخدم)" if استخدم_مقاسة else ""
        انتاج = st.number_input(
            "حجم الإنتاج الكلي (مليون برميل/يوم)",
            value=float(d.get("حجم_الصادرات_مليون_برميل_يوم", 4.2)),
            step=0.1,
            help="إجمالي إنتاج النفط الخام في العراق (عادة بين 4.0 و 4.3 م ب/ي)",
            disabled=استخدم_مقاسة,
            key=f"{widget_scope}:انتاج",
        )
        عرض_مصدر_المدخل("حجم_الصادرات_مليون_برميل_يوم", "حجم الإنتاج الكلي (مليون برميل/يوم)" + _لاحقة, انتاج)
        محلي = st.number_input(
            "الاستهلاك المحلي للمصافي (مليون برميل/يوم)",
            value=float(d.get("الاستهلاك_المحلي_مليون_برميل_يوم", 0.8)),
            step=0.1,
            help="النفط الخام الموجه للمصافي المحلية ومحطات الكهرباء",
            disabled=استخدم_مقاسة,
            key=f"{widget_scope}:محلي",
        )
        عرض_مصدر_المدخل("الاستهلاك_المحلي_مليون_برميل_يوم", "الاستهلاك المحلي للمصافي (مليون برميل/يوم)" + _لاحقة, محلي)
        حصة = st.slider("حصة الحكومة من الصادرات", 0.0, 1.0, float(d.get("حصة_الحكومة_من_الصادرات", 1.0)), 0.05, key=f"{widget_scope}:حصة")
        عرض_مصدر_المدخل("حصة_الحكومة_من_الصادرات", "حصة الحكومة من الصادرات", حصة)

        صافي_تصدير_يومي = (صادرات_مقاسة if صادرات_مقاسة is not None else max(انتاج - محلي, 0.0)) * حصة
        st.caption(f"🔹 صافي التصدير الحكومي: **{صافي_تصدير_يومي:.2f}** مليون برميل/يوم ({صافي_تصدير_يومي * 365:.1f} مليون برميل سنوياً)")

        خصم_بصرة = st.number_input(
            "خصم خام البصرة عن برنت (دولار/برميل)",
            value=float(d.get("خصم_خام_البصرة_دولار", 3.0)),
            step=0.5,
            help="فارق خصم سلة نفط العراق التصديرية عن خام برنت العالمي القياسي (عادة 2-4$)",
            key=f"{widget_scope}:خصم_بصرة",
        )
        عرض_مصدر_المدخل("خصم_خام_البصرة_دولار", "خصم خام البصرة عن برنت (دولار/برميل)", خصم_بصرة)
        كلفة_برميل = st.number_input(
            "كلف جولات التراخيص والاستخراج (دولار/برميل)",
            value=float(d.get("كلفة_انتاج_البرميل_دولار", 0.0)),
            step=0.5,
            help="مستحقات شركات النفط العالمية ككلفة استخراج لكل برميل مصدّر (إن وُجدت)",
            key=f"{widget_scope}:كلفة_برميل",
        )
        عرض_مصدر_المدخل("كلفة_انتاج_البرميل_دولار", "كلف جولات التراخيص والاستخراج (دولار/برميل)", كلفة_برميل)

    with st.expander("💱 سعر الصرف", expanded=True):
        رسمي = st.number_input("السعر الرسمي الحالي (دينار/دولار)", value=float(d.get("سعر_الصرف_الرسمي", 1300.0)), step=10.0, key=f"{widget_scope}:رسمي")
        عرض_مصدر_المدخل("سعر_الصرف_الرسمي", "السعر الرسمي الحالي (دينار/دولار)", رسمي)
        موازي = st.number_input("السعر الموازي في السوق (دينار/دولار)", value=float(d.get("سعر_الصرف_الموازي", 1500.0)), step=10.0, key=f"{widget_scope}:موازي")
        عرض_مصدر_المدخل("سعر_الصرف_الموازي", "السعر الموازي في السوق (دينار/دولار)", موازي)
        اسعار_صرف = st.multiselect(
            "سيناريوهات سعر الصرف (للتخفيض)",
            sorted(set([1190, 1250, 1300, 1310, 1350, 1400, 1450, 1500, 1550, 1600] + d.get("اسعار_الصرف_سيناريو", []))),
            default=d.get("اسعار_الصرف_سيناريو", [1300, 1400, 1450, 1500]),
            key=f"{widget_scope}:اسعار_صرف",
        )
        if not اسعار_صرف:
            اسعار_صرف = [رسمي]
            st.caption("لم تُحدد قيم؛ تُستخدم القيمة الاحتياطية الموضحة في سجل المدخلات.")
        عرض_مصدر_المدخل("اسعار_الصرف_سيناريو", "سيناريوهات سعر الصرف (للتخفيض)", اسعار_صرف)

    with st.expander("💰 المالية العامة (مليار دينار)", expanded=False):
        غير_نفطي = st.number_input("الإيرادات غير النفطية", value=float(d.get("ايرادات_غير_نفطية_مليار", 12000.0)), step=500.0, key=f"{widget_scope}:غير_نفطي")
        عرض_مصدر_المدخل("ايرادات_غير_نفطية_مليار", "الإيرادات غير النفطية", غير_نفطي)
        اجمالي = st.number_input("إجمالي النفقات", value=float(d.get("اجمالي_النفقات_مليار", 141228.0)), step=1000.0, key=f"{widget_scope}:اجمالي")
        عرض_مصدر_المدخل("اجمالي_النفقات_مليار", "إجمالي النفقات", اجمالي)
        جاري = st.number_input("النفقات الجارية", value=float(d.get("النفقات_الجارية_مليار", 119164.0)), step=1000.0, key=f"{widget_scope}:جاري")
        عرض_مصدر_المدخل("النفقات_الجارية_مليار", "النفقات الجارية", جاري)
        رواتب = st.number_input(
            "فاتورة الرواتب والتقاعد والرعاية",
            value=float(d.get("فاتورة_الرواتب_مليار", 68000.0)),
            step=1000.0,
            help="الكتلة المالية غير المرنة المخصصة لتعويضات الموظفين والتقاعد وشبكة الحماية الاجتماعية",
            key=f"{widget_scope}:رواتب",
        )
        عرض_مصدر_المدخل("فاتورة_الرواتب_مليار", "فاتورة الرواتب والتقاعد والرعاية", رواتب)
        استخدم_الاجمالي = st.toggle("استخدام الإجمالي بدل الجاري", value=d.get("استخدام_الاجمالي", True), key=f"{widget_scope}:استخدم_الاجمالي")
        عرض_مصدر_المدخل("استخدام_الاجمالي", "استخدام الإجمالي بدل الجاري", استخدم_الاجمالي)

    with st.expander("🏦 النقد والاحتياطي (مليار دينار)", expanded=False):
        احتياطي = st.number_input("الاحتياطيات الأجنبية", value=float(d.get("الاحتياطيات_الاجنبية_مليار", 126661.0)), step=1000.0, key=f"{widget_scope}:احتياطي")
        عرض_مصدر_المدخل("الاحتياطيات_الاجنبية_مليار", "الاحتياطيات الأجنبية", احتياطي)
        نقد = st.number_input("النقد القاعدي M0", value=float(d.get("النقد_القاعدي_مليار", 132081.0)), step=1000.0, key=f"{widget_scope}:نقد")
        عرض_مصدر_المدخل("النقد_القاعدي_مليار", "النقد القاعدي M0", نقد)
        نسبة_المركزي = st.slider("نسبة تمويل المركزي للعجز", 0.0, 1.0, float(d.get("نسبة_تمويل_المركزي", 0.3)), 0.05, key=f"{widget_scope}:نسبة_المركزي")
        عرض_مصدر_المدخل("نسبة_تمويل_المركزي", "نسبة تمويل المركزي للعجز", نسبة_المركزي)
        نسبة_فائض = st.slider("نسبة الفائض تذهب للاحتياطي", 0.0, 1.0, float(d.get("نسبة_الفائض_للاحتياطي", 0.5)), 0.05, key=f"{widget_scope}:نسبة_فائض")
        عرض_مصدر_المدخل("نسبة_الفائض_للاحتياطي", "نسبة الفائض تذهب للاحتياطي", نسبة_فائض)

    with st.expander("📈 التضخم والاستيراد", expanded=False):
        واردات = st.number_input("الواردات السنوية (مليار دولار)", value=float(d.get("واردات_سنوية_مليار_دولار", 74.0)), step=1.0, key=f"{widget_scope}:واردات")
        عرض_مصدر_المدخل("واردات_سنوية_مليار_دولار", "الواردات السنوية (مليار دولار)", واردات)
        حصة_مستورد = st.slider("حصة السلع المستوردة في سلة المستهلك", 0.0, 1.0, float(d.get("حصة_المستورد_من_السلة", 0.40)), 0.05, key=f"{widget_scope}:حصة_مستورد")
        عرض_مصدر_المدخل("حصة_المستورد_من_السلة", "حصة السلع المستوردة في سلة المستهلك", حصة_مستورد)
        تمرير = st.slider("معامل تمرير الصرف إلى الأسعار", 0.0, 1.0, float(d.get("معامل_تمرير_التضخم", 0.50)), 0.05, key=f"{widget_scope}:تمرير")
        عرض_مصدر_المدخل("معامل_تمرير_التضخم", "معامل تمرير الصرف إلى الأسعار", تمرير)

p = مدخلات(
    اسعار_النفط=اسعار,
    حجم_الصادرات_مليون_برميل_يوم=انتاج,
    الاستهلاك_المحلي_مليون_برميل_يوم=محلي,
    صادرات_مقاسة_مليون_برميل_يوم=صادرات_مقاسة,
    حصة_الحكومة_من_الصادرات=حصة,
    ايام_السنة=365,
    سعر_الصرف_الرسمي=float(رسمي),
    سعر_الصرف_الموازي=float(موازي),
    اسعار_الصرف_سيناريو=[float(x) for x in اسعار_صرف],
    ايرادات_غير_نفطية_مليار=غير_نفطي,
    اجمالي_النفقات_مليار=اجمالي,
    النفقات_الجارية_مليار=جاري,
    فاتورة_الرواتب_مليار=رواتب,
    استخدام_الاجمالي=استخدم_الاجمالي,
    الاحتياطيات_الاجنبية_مليار=احتياطي,
    النقد_القاعدي_مليار=نقد,
    نسبة_تمويل_المركزي=نسبة_المركزي,
    نسبة_الفائض_للاحتياطي=نسبة_فائض,
    واردات_سنوية_مليار_دولار=واردات,
    حصة_المستورد_من_السلة=حصة_مستورد,
    معامل_تمرير_التضخم=تمرير,
    خصم_خام_البصرة_دولار=float(خصم_بصرة),
    كلفة_انتاج_البرميل_دولار=float(كلفة_برميل),
    اسم_السيناريو=سيناريو_مختار,
)

# ----------------------------------------------------------------------
# رأس التطبيق وشبكة المؤشرات الرئيسية التنفيذية
# ----------------------------------------------------------------------
as3ar_sooq = جلب_اسعار_النفط_الحية()
brent_val = as3ar_sooq["سعر_برنت"]
basrah_val = as3ar_sooq["سعر_البصرة_المتوسط_التقديري"]
chg = as3ar_sooq["التغير"]
pct_chg = as3ar_sooq["نسبة_التغير"]
chg_tone = "pos" if chg >= 0 else "neg"
chg_sign = "+" if chg >= 0 else ""
market_status = "أسعار السوق" if as3ar_sooq["متاح"] else "أسعار مرجعية · دون اتصال"
market_change_html = (
    f'<span class="ticker-change {chg_tone}" dir="ltr">({chg_sign}{pct_chg:.2f}%)</span>'
    if as3ar_sooq["متاح"] else ""
)

ui.hero(
    title="مرصد الموازنة العراقية",
    subtitle=(
        "منصّة تفاعلية تقيس أثر أسعار النفط وسعر صرف الدينار على الإيرادات والعجز "
        "والاحتياطيات الأجنبية، اعتماداً على النشرة الرسمية للبنك المركزي العراقي."
    ),
    chips=[
        ("خام برنت", f'<span dir="ltr">${brent_val:.2f}</span> {market_change_html}'),
        ("خام البصرة التصديري", f'<span dir="ltr">${basrah_val:.2f}</span>'),
        ("سعر الصرف الرسمي", f'<span dir="ltr">{p.سعر_الصرف_الرسمي:,.0f}</span> د/$'),
        ("السيناريو الحالي", p.اسم_السيناريو),
    ],
    footnote=market_status,
)


@st.fragment(run_every="60s")
def عرض_حداثة_البيانات():
    # A deployed data update invalidates tables and scenario defaults, even in an open tab.
    if data_signature(_DATA_DIR) != cbi_signature:
        st.rerun()
    snapshot = بيانات_المركزي.get("snapshot")
    status = بيانات_المركزي.get("metadata", {})
    if not snapshot:
        st.caption("بيانات مرجعية محلية؛ لم يُعتمد تحديث آلي بعد.")
        return
    periods = snapshot["periods"]
    st.caption(f"البنك المركزي · المؤشرات النقدية: {periods['monetary']} · الموازنة التراكمية حتى: {periods['fiscal']} · آخر سنة إنفاق مكتملة: {periods['annual_budget']}")
    if status.get("status") == "failed":
        st.warning("تعذّر آخر تحديث من البنك المركزي. المعروض هو آخر بيانات اجتازت التحقق.")
    elif status.get("last_success_at"):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(status["last_success_at"])
        if age.total_seconds() > 18 * 3600:
            st.warning("مضى أكثر من 18 ساعة على آخر تحقق ناجح من المصدر؛ قد يكون التحديث المجدول متأخرًا.")
    with st.expander("المصدر وتواريخ التحديث"):
        def توقيت(value):
            return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Baghdad")).strftime("%Y-%m-%d %H:%M") if value else "غير متاح"
        st.write(f"آخر فحص: {توقيت(status.get('last_checked_at'))} — توقيت بغداد")
        st.write(f"آخر فحص ناجح: {توقيت(status.get('last_success_at'))}")
        st.write(f"آخر نسخة بيانات معتمدة: {توقيت(snapshot['source']['updated_at'])}")
        st.markdown(f"[صفحة النشرة الرسمية]({snapshot['source']['page_url']}) · [تنزيل ملف البنك المركزي]({snapshot['source']['file_url']})")
        st.caption("نفحص المصدر كل 6 ساعات. تاريخ الفحص يختلف عن الفترة التي تمثلها الأرقام. يتم استبعاد أعمدة التواريخ المستقبلية دون تخمين تاريخ بديل.")
        for warning in snapshot.get("warnings", []):
            st.warning(f"استُبعد العمود {warning['column']} في جدول {warning['sheet']} لأن تاريخ المصدر مستقبلي: {warning['source_header']}.")


عرض_حداثة_البيانات()

input_audit_df = pd.DataFrame(input_audit)
official_count = sum(row["التصنيف"] == "رسمي" for row in input_audit)
manual_count = sum(row["التصنيف"] == "معدّل يدويًا" for row in input_audit)
with st.expander(f"مصادر مدخلات السيناريو · {official_count} رسمية · {manual_count} معدّلة يدويًا"):
    st.caption("التصنيف يخص القيمة المستخدمة الآن. الفترة والرابط يصفان المرجع الأصلي، حتى بعد تعديله. الوحدات موضحة في الجدول؛ الحصص والمعاملات كسور من 0 إلى 1.")
    st.dataframe(input_audit_df, hide_index=True, width="stretch",
                 column_config={"رابط المصدر المرجعي": st.column_config.LinkColumn("المصدر", display_text="فتح النشرة")})
    st.caption("العجز ومؤشر الاستقرار والتضخم المتوقع نتائج محسوبة من هذه المدخلات، وليست بيانات رسمية منشورة.")

سعر_متوسط = sorted(اسعار)[len(اسعار) // 2]
ملخص = ملخص_السيناريو(p, p.سعر_الصرف_الرسمي)
صف_مرجعي = حساب_الموازنة(سعر_متوسط, p.سعر_الصرف_الرسمي, p)
الفجوة_صرف = p.سعر_الصرف_الموازي - p.سعر_الصرف_الرسمي
نسبة_فجوة_صرف = (الفجوة_صرف / p.سعر_الصرف_الرسمي * 100.0) if p.سعر_الصرف_الرسمي else 0.0

رصيد = صف_مرجعي["الرصيد (مليار دينار)"]
is_surplus = رصيد >= 0
status_text = "فائض مالي" if is_surplus else "عجز مالي"
badge_class = "surplus" if is_surplus else "deficit"
hero_class = "" if is_surplus else "deficit"
balance_explanation = (
    "الإيرادات تغطي الإنفاق مع فائض وفق هذه الافتراضات."
    if رصيد > 0 else
    "الإنفاق يتجاوز الإيرادات بهذا المقدار وفق هذه الافتراضات."
    if رصيد < 0 else
    "الإيرادات تساوي الإنفاق وفق هذه الافتراضات."
)
if رصيد == 0:
    status_text = "توازن مالي"

تع = ملخص["سعر نفط التعادل (دولار)"]

تع_رواتب = ملخص["سعر تعادل الرواتب (دولار)"]
wage_tone = "pos" if (تع_رواتب and تع_رواتب < 55) else "neg"

m0_cover = (p.الاحتياطيات_الاجنبية_مليار / p.النقد_القاعدي_مليار * 100.0) if p.النقد_القاعدي_مليار else 0.0

ui.section(
    eyebrow="نظرة عامة",
    title="الوضع المالي عند السيناريو الحالي",
    description=(
        f"الأرقام محسوبة عند سعر نفط {سعر_متوسط:g} دولاراً للبرميل وسعر صرف رسمي "
        f"{p.سعر_الصرف_الرسمي:,.0f} ديناراً للدولار. "
        "غيّر الافتراضات من الشريط الجانبي لإعادة الحساب فوراً."
    ),
)

ui.stat_strip([
    {
        "value": f"{رصيد / 1000:,.1f}",
        "period": status_text,
        "label": "الرصيد المالي المقدّر (ترليون دينار)",
        "tone": "pos" if is_surplus else "neg",
    },
    {
        "value": f"{تع:,.1f}" if تع else "—",
        "period": "توازن كامل الإنفاق",
        "label": "سعر تعادل الموازنة (دولار/برميل)",
    },
    {
        "value": f"{تع_رواتب:,.1f}" if تع_رواتب else "—",
        "period": "تأمين الرواتب فقط",
        "label": "سعر تعادل الرواتب (دولار/برميل)",
        "tone": wage_tone,
    },
    {
        "value": f"{p.الاحتياطيات_الاجنبية_مليار / 1000:,.1f}",
        "period": f"غطاء M0: {m0_cover:,.0f}%",
        "label": "الاحتياطيات الأجنبية (ترليون دينار)",
    },
    {
        "value": f"{الفجوة_صرف:,.0f}",
        "period": f"فارق {نسبة_فجوة_صرف:,.1f}% فوق الرسمي",
        "label": "فجوة سعر الصرف (دينار)",
    },
])

نفقات_مرجعية = صف_مرجعي["النفقات (مليار دينار)"]
نسبة_الرصيد = (abs(رصيد) / نفقات_مرجعية * 100.0) if نفقات_مرجعية else 0.0
ui.narrative(
    f"عند سعر نفط <strong><span dir=\"ltr\">{سعر_متوسط:g}</span> دولاراً للبرميل</strong>، "
    f"تبلغ الإيرادات المقدّرة <strong>{fmt_trln_html(صف_مرجعي['إجمالي الإيرادات (مليار دينار)'])} دينار</strong> "
    f"مقابل إنفاق <strong>{fmt_trln_html(نفقات_مرجعية)} دينار</strong>. {balance_explanation} "
    f"يمثّل ذلك <strong><span dir=\"ltr\">{نسبة_الرصيد:,.1f}%</span></strong> من الإنفاق الكلي. "
    + (
        f"يحتاج التوازن الكامل إلى سعر نفط عند <strong><span dir=\"ltr\">{تع:,.1f}</span> دولاراً</strong>، "
        if تع else ""
    )
    + (
        f"بينما يكفي <strong><span dir=\"ltr\">{تع_رواتب:,.1f}</span> دولاراً</strong> "
        "لتغطية فاتورة الرواتب والتقاعد وشبكة الحماية وحدها."
        if تع_رواتب else ""
    )
)

# ----------------------------------------------------------------------
# محاور التحليل الرئيسية (5 Core Executive Pillars)
# ----------------------------------------------------------------------
tab_overview, tab_scenarios, tab_monetary, tab_policy, tab_deep = st.tabs(
    [
        "نظرة عامة",
        "السيناريوهات",
        "سعر الصرف",
        "التقرير",
        "البيانات",
    ]
)

# --- نظرة عامة ---------------------------------------------------------
with tab_overview:
    # 1. عداد الاستقرار المالي ومخطط سانكي للتدفقات
    st.subheader("🧭 بوصلة الاستدامة المالية وتدفق الأموال")
    stab = حساب_مؤشر_الاستقرار(سعر_متوسط, p)
    col_gauge, col_sankey = st.columns([1, 1.4])

    with col_gauge:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=stab["الدرجة"],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"مؤشر الاستقرار المالي (عند سعر {سعر_متوسط} دولار)", 'font': {'size': 17, 'family': 'IBM Plex Sans Arabic'}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': INK},
                'bar': {'color': stab["اللون"], 'thickness': 0.3},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#eef1f0",
                'steps': [
                    {'range': [0, 45], 'color': 'rgba(194,57,47,0.18)'},
                    {'range': [45, 70], 'color': 'rgba(200,160,66,0.18)'},
                    {'range': [70, 100], 'color': 'rgba(14,110,92,0.18)'},
                ],
                'threshold': {
                    'line': {'color': DANGER, 'width': 4},
                    'thickness': 0.75,
                    'value': 45.0,
                },
            },
        ))
        fig_gauge.update_layout(height=280, margin=dict(l=15, r=15, t=50, b=15),
                                font=dict(family="IBM Plex Sans Arabic, sans-serif"))
        st.plotly_chart(fig_gauge, width='stretch')

        st.markdown(
            f"""
            <div style="background:{'#e8f5e9' if stab['الدرجة']>=70 else ('#fff8e1' if stab['الدرجة']>=45 else '#ffebee')};
                        border-right: 4px solid {stab['اللون']}; padding: 12px 14px; border-radius: 8px; font-size: 13px; color: {INK};">
                <strong>{stab['الحالة']}</strong> ({stab['الدرجة']}/100)<br>
                <span>{stab['الشرح']}</span>
                <hr style="margin: 8px 0; border: none; border-top: 1px solid rgba(0,0,0,0.08);">
                <div style="display:flex; justify-content:space-between; font-size:12px;">
                    <span>🛡️ تغطية النقد M0: <strong>{stab['نسبة تغطية M0 %']}%</strong></span>
                    <span>📦 كفاية الاستيراد: <strong>{stab['أشهر تغطية الاستيراد']} شهر</strong></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_sankey:
        sankey_data = توليد_بيانات_سانكي(سعر_متوسط, p)
        fig_sankey = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=18,
                line=dict(color="black", width=0.5),
                label=sankey_data["labels"],
                color=[PRIMARY, "#2E86AB", PRIMARY, DANGER, INK, ACCENT, MUTED, "#2E86AB", PRIMARY, DANGER],
            ),
            link=dict(
                source=sankey_data["source"],
                target=sankey_data["target"],
                value=sankey_data["value"],
                color=sankey_data["color"],
            ),
        )])
        fig_sankey.update_layout(
            title_text=f"مخطط تدفق أموال النفط والموازنة (ترليون دينار عند سعر {سعر_متوسط} دولار)",
            height=370,
            margin=dict(l=10, r=10, t=40, b=10),
            font=dict(family="IBM Plex Sans Arabic, sans-serif", size=11),
        )
        st.plotly_chart(fig_sankey, width='stretch')

    st.write("")
    st.subheader("📈 تحليلات الموازنة حسب مسار أسعار النفط")

    df_oil = جدول_حسب_سعر_النفط(p, p.سعر_الصرف_الرسمي)
    cc1, cc2 = st.columns(2)

    with cc1:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_oil["سعر النفط (دولار)"],
            y=df_oil["الرصيد (مليار دينار)"] / 1000.0,
            marker_color=[PRIMARY if v >= 0 else DANGER for v in df_oil["الرصيد (مليار دينار)"]],
            name="الرصيد",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color=MUTED)
        fig.update_layout(title=f"الرصيد حسب سعر النفط (عند صرف {p.سعر_الصرف_الرسمي})",
                          xaxis_title="سعر النفط (دولار/برميل)", yaxis_title="ترليون دينار")
        st.plotly_chart(style_fig(fig), width='stretch')

    with cc2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_oil["سعر النفط (دولار)"], y=df_oil["إجمالي الإيرادات (مليار دينار)"] / 1000.0,
            mode="lines+markers", name="إجمالي الإيرادات", line=dict(color=PRIMARY, width=3)))
        fig.add_trace(go.Scatter(
            x=df_oil["سعر النفط (دولار)"], y=df_oil["النفقات (مليار دينار)"] / 1000.0,
            mode="lines+markers", name="النفقات الإجمالية", line=dict(color=DANGER, width=3, dash="dot")))
        fig.add_trace(go.Scatter(
            x=df_oil["سعر النفط (دولار)"], y=[p.فاتورة_الرواتب_مليار / 1000.0] * len(df_oil),
            mode="lines", name="فاتورة الرواتب والتقاعد", line=dict(color=ACCENT, width=2.5, dash="dash")))
        fig.update_layout(title="الإيرادات مقابل النفقات وفاتورة الرواتب",
                          xaxis_title="سعر النفط (دولار/برميل)", yaxis_title="ترليون دينار")
        st.plotly_chart(style_fig(fig), width='stretch')

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_oil["سعر النفط (دولار)"],
                             y=df_oil["الاحتياطي بعد (مليار دينار)"] / 1000.0,
                             mode="lines+markers", name="الاحتياطي بعد", line=dict(color=PRIMARY, width=3)))
    fig.add_trace(go.Scatter(x=df_oil["سعر النفط (دولار)"],
                             y=df_oil["النقد القاعدي (مليار دينار)"] / 1000.0,
                             mode="lines", name="النقد القاعدي", line=dict(color=ACCENT, width=2, dash="dash")))
    fig.add_trace(go.Bar(x=df_oil["سعر النفط (دولار)"],
                         y=df_oil["الفجوة النقدية (مليار دينار)"] / 1000.0,
                         name="الفجوة النقدية", marker_color="rgba(46,134,171,0.45)"))
    fig.update_layout(title="الاحتياطي والقاعدة النقدية والفجوة النقدية",
                      xaxis_title="سعر النفط (دولار/برميل)", yaxis_title="ترليون دينار")
    st.plotly_chart(style_fig(fig, height=420), width='stretch')

# --- السيناريوهات والمخاطر ---------------------------------------------
with tab_scenarios:
    st.markdown(
        '<div class="note">استكشف مسارات المخاطر الاحتمالية لأسعار النفط عبر محاكاة مونت كارلو، '
        'أو قارن السيناريو الحالي جنباً إلى جنب مع سيناريو بديل لقياس فوارق العجز والوفرة والاحتياطيات ومؤشر الاستقرار.</div>',
        unsafe_allow_html=True,
    )
    sub_monte, sub_compare = st.tabs(
        [
            "🎲 محاكاة مونت كارلو لمخاطر النفط (GBM Simulation)",
            "⚖️ مقارنة السيناريوهات (أ vs ب - Delta Analysis)",
        ]
    )

    with sub_monte:
        st.subheader("🎲 محاكاة مونت كارلو لمخاطر أسعار النفط والعجز المالي")
        st.caption(
            "تعتمد هذه المحاكاة على نمذجة تقلبات أسعار النفط العالمية عبر مسارات احتمالية عشوائية "
            "(Geometric Brownian Motion) لتوليد آلاف التقديرات الممكنة للموازنة والاحتياطيات خلال العام، "
            "مما يتيح قياس احتمالية حدوث عجز، ومخاطر كسر تغطية النقد القاعدي M0، وحساب القيمة المعرضة للخطر (Fiscal VaR 95%)."
        )

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            سعر_محاكاة = st.slider("سعر النفط الأساس للمحاكاة (دولار)", 40.0, 110.0, float(سعر_متوسط), 1.0)
        with col_m2:
            تقلب_محاكاة = st.slider("نسبة تقلب أسعار النفط السنوية (Volatility %)", 10, 50, 25, 5,
                                    help="الانحراف المعياري السنوي المتوقع لتحركات خام برنت (المعتاد تاريخياً بين 20% و 35%)")
        with col_m3:
            عدد_مسارات = st.select_slider("عدد المسارات المحاكاة", options=[500, 1000, 2000, 3000, 5000], value=2000)

        mc_res = محاكاة_مونت_كارلو(
            p,
            سعر_اساس=سعر_محاكاة,
            عدد_المحاكاة=عدد_مسارات,
            تقلب_النفط=تقلب_محاكاة / 100.0,
            seed=42,
        )

        # بطاقات مؤشرات المخاطر
        mc_c1, mc_c2, mc_c3, mc_c4 = st.columns(4)
        with mc_c1:
            احتمال_عجز = mc_res["احتمالية حدوث عجز %"]
            st.markdown(
                kpi_card(
                    "احتمالية تسجيل عجز",
                    f"{احتمال_عجز:.1f}%",
                    "من إجمالي المسارات",
                    "neg" if احتمال_عجز > 50 else "pos",
                ),
                unsafe_allow_html=True,
            )
        with mc_c2:
            احتمال_m0 = mc_res["احتمالية هبوط الاحتياطي دون M0 %"]
            st.markdown(
                kpi_card(
                    "مخاطر كسر غطاء النقد M0",
                    f"{احتمال_m0:.1f}%",
                    "هبوط الاحتياطي دون النقد القاعدي",
                    "neg" if احتمال_m0 > 15 else "pos",
                ),
                unsafe_allow_html=True,
            )
        with mc_c3:
            var_val = mc_res["أقصى عجز بمستوى ثقة 95% (VaR)"]
            st.markdown(
                kpi_card(
                    "أقصى عجز محتمل (VaR 95%)",
                    f"{var_val:,.1f} ترليون",
                    "أسوأ 5% من السيناريوهات",
                    "neg",
                ),
                unsafe_allow_html=True,
            )
        with mc_c4:
            median_val = mc_res["وسيط الرصيد المتوقع (ترليون)"]
            st.markdown(
                kpi_card(
                    "وسيط الرصيد المتوقع (P50)",
                    f"{median_val:+,.1f} ترليون",
                    f"نطاق P10–P90: [{mc_res['السيناريو المتشائم P10 (ترليون)']:,.1f} إلى {mc_res['السيناريو المتفائل P90 (ترليون)']:,.1f}]",
                    "pos" if median_val >= 0 else "neg",
                ),
                unsafe_allow_html=True,
            )

        st.write("")

        # رسوم بيانية: 1. توزيع الرصيد المالي  2. توزيع أسعار النفط
        col_chart_bal, col_chart_oil = st.columns([1.3, 1])

        with col_chart_bal:
            df_mc_bal = pd.DataFrame({"الرصيد": mc_res["عينة_الارصدة"]})
            fig_hist = px.histogram(
                df_mc_bal,
                x="الرصيد",
                nbins=40,
                title="توزيع الرصيد المالي المحتمل للموازنة (ترليون دينار)",
                labels={"الرصيد": "الرصيد المالي (ترليون دينار)", "count": "تكرار السيناريو"},
                color_discrete_sequence=[PRIMARY],
            )
            p10_val = mc_res["السيناريو المتشائم P10 (ترليون)"]
            p90_val = mc_res["السيناريو المتفائل P90 (ترليون)"]
            fig_hist.add_vline(x=0, line_dash="solid", line_color=INK, line_width=2, annotation_text="نقطة التعادل (0)", annotation_position="top left")
            fig_hist.add_vline(x=median_val, line_dash="dash", line_color=ACCENT, line_width=2, annotation_text=f"الوسيط: {median_val:,.1f}", annotation_position="top right")
            fig_hist.add_vline(x=p10_val, line_dash="dot", line_color=DANGER, line_width=1.5, annotation_text=f"P10: {p10_val:,.1f}", annotation_position="bottom left")
            fig_hist.add_vline(x=p90_val, line_dash="dot", line_color="#2E86AB", line_width=1.5, annotation_text=f"P90: {p90_val:,.1f}", annotation_position="bottom right")
            st.plotly_chart(style_fig(fig_hist, height=350), width='stretch')

        with col_chart_oil:
            df_mc_oil = pd.DataFrame({"سعر_النفط": mc_res["عينة_الاسعار"]})
            fig_oil_box = px.box(
                df_mc_oil,
                y="سعر_النفط",
                title="نطاق تحركات أسعار النفط المحاكاة (دولار/برميل)",
                labels={"سعر_النفط": "سعر خام برنت المحاكى ($)"},
                color_discrete_sequence=[ACCENT],
            )
            st.plotly_chart(style_fig(fig_oil_box, height=350), width='stretch')

        with st.expander("📊 جدول المؤشرات الإحصائية الكامل لمحاكاة مونت كارلو"):
            st.dataframe(
                pd.DataFrame([
                    {"المؤشر الاحتمالي": "عدد المسارات المحاكاة", "القيمة": f"{mc_res['عدد المحاكاة']:,}", "الوحدة": "مسار"},
                    {"المؤشر الاحتمالي": "سعر النفط الأساس المعتمد", "القيمة": f"{mc_res['سعر النفط الأساس']:.1f}", "الوحدة": "دولار/برميل"},
                    {"المؤشر الاحتمالي": "تقلب الأسعار السنوي (Volatility)", "القيمة": f"{mc_res['تقلب النفط %']:.1f}%", "الوحدة": "نسبة مئوية"},
                    {"المؤشر الاحتمالي": "احتمالية تسجيل عجز سنوي", "القيمة": f"{mc_res['احتمالية حدوث عجز %']:.1f}%", "الوحدة": "احتمال"},
                    {"المؤشر الاحتمالي": "احتمالية هبوط الاحتياطي دون النقد M0", "القيمة": f"{mc_res['احتمالية هبوط الاحتياطي دون M0 %']:.1f}%", "الوحدة": "احتمال"},
                    {"المؤشر الاحتمالي": "أقصى عجز بمستوى ثقة 95% (VaR)", "القيمة": f"{mc_res['أقصى عجز بمستوى ثقة 95% (VaR)']:,.1f}", "الوحدة": "ترليون دينار"},
                    {"المؤشر الاحتمالي": "السيناريو المتشائم (العُشير الأدنى P10)", "القيمة": f"{mc_res['السيناريو المتشائم P10 (ترليون)']:,.1f}", "الوحدة": "ترليون دينار"},
                    {"المؤشر الاحتمالي": "الوسيط المتوقع (P50)", "القيمة": f"{mc_res['وسيط الرصيد المتوقع (ترليون)']:,.1f}", "الوحدة": "ترليون دينار"},
                    {"المؤشر الاحتمالي": "السيناريو المتفائل (العُشير الأعلى P90)", "القيمة": f"{mc_res['السيناريو المتفائل P90 (ترليون)']:,.1f}", "الوحدة": "ترليون دينار"},
                    {"المؤشر الاحتمالي": "أدنى سعر نفط مسجل في المحاكاة", "القيمة": f"{mc_res['أدنى سعر في المحاكاة']:.1f}", "الوحدة": "دولار/برميل"},
                    {"المؤشر الاحتمالي": "أعلى سعر نفط مسجل في المحاكاة", "القيمة": f"{mc_res['أعلى سعر في المحاكاة']:.1f}", "الوحدة": "دولار/برميل"},
                ]),
                width='stretch',
            )

    with sub_compare:
        st.subheader("⚖️ مقارنة سيناريوهين جنباً إلى جنب (Delta Analysis)")
        st.caption("قارن السيناريو الحالي المعتمد (أ) مع سيناريو بديل (ب) للتعرف على فوارق الإيرادات والعجز والاحتياطيات ومؤشر الاستدامة المالية.")

        cmp_c1, cmp_c2 = st.columns([1, 1])
        with cmp_c1:
            خيارات_ب = [k for k in السيناريوهات_المسبقة.keys() if k != p.اسم_السيناريو]
            if not خيارات_ب:
                خيارات_ب = list(السيناريوهات_المسبقة.keys())
            سيناريو_ب_اسم = st.selectbox("اختر السيناريو البديل (ب) للمقارنة", خيارات_ب, index=0)
            p_b = انشاء_مدخلات_من_سيناريو(سيناريو_ب_اسم)
        with cmp_c2:
            سعر_مقارنة = st.select_slider(
                "سعر النفط المرجعي للمقارنة (دولار)",
                options=sorted(set(p.اسعار_النفط + p_b.اسعار_النفط)),
                value=سعر_متوسط if سعر_متوسط in set(p.اسعار_النفط + p_b.اسعار_النفط) else 70,
            )

        df_comp = مقارنة_سيناريوهين(p, p_b, سعر_مقارنة)

        # بطاقات الفروقات الرئيسية (Delta Cards)
        r_a = حساب_الموازنة(سعر_مقارنة, p.سعر_الصرف_الرسمي, p)
        r_b = حساب_الموازنة(سعر_مقارنة, p_b.سعر_الصرف_الرسمي, p_b)
        فارق_الرصيد = (r_b["الرصيد (مليار دينار)"] - r_a["الرصيد (مليار دينار)"]) / 1000.0
        فارق_الاحتياطي = (r_b["الاحتياطي بعد (مليار دينار)"] - r_a["الاحتياطي بعد (مليار دينار)"]) / 1000.0

        m_a = ملخص_السيناريو(p, p.سعر_الصرف_الرسمي)
        m_b = ملخص_السيناريو(p_b, p_b.سعر_الصرف_الرسمي)
        فارق_التعادل = (m_b["سعر نفط التعادل (دولار)"] - m_a["سعر نفط التعادل (دولار)"]) if (m_a["سعر نفط التعادل (دولار)"] and m_b["سعر نفط التعادل (دولار)"]) else 0.0

        k_c1, k_c2, k_c3 = st.columns(3)
        with k_c1:
            st.markdown(
                kpi_card(
                    "فارق الرصيد المالي (ب − أ)",
                    f"{فارق_الرصيد:+,.1f} ترليون",
                    "تحسن إيجابي" if فارق_الرصيد >= 0 else "تفاقم في العجز",
                    "pos" if فارق_الرصيد >= 0 else "neg",
                ),
                unsafe_allow_html=True,
            )
        with k_c2:
            st.markdown(
                kpi_card(
                    "فارق الاحتياطيات بعد السيناريو",
                    f"{فارق_الاحتياطي:+,.1f} ترليون",
                    "تراكم إضافي" if فارق_الاحتياطي >= 0 else "انخفاض إضافي",
                    "pos" if فارق_الاحتياطي >= 0 else "neg",
                ),
                unsafe_allow_html=True,
            )
        with k_c3:
            st.markdown(
                kpi_card(
                    "فارق سعر تعادل الموازنة",
                    f"{فارق_التعادل:+,.1f}$",
                    "أسهل في التعادل" if فارق_التعادل <= 0 else "يتطلب سعراً أعلى للتعادل",
                    "pos" if فارق_التعادل <= 0 else "neg",
                ),
                unsafe_allow_html=True,
            )

        # رسم بياني ثنائي للمقارنة
        f_comp = go.Figure()
        فئات = ["الإيرادات النفطية", "إجمالي الإيرادات", "النفقات", "الرصيد المالي", "الاحتياطي بعد"]
        قيم_أ = [
            r_a["الإيرادات النفطية (مليار دينار)"] / 1000.0,
            r_a["إجمالي الإيرادات (مليار دينار)"] / 1000.0,
            r_a["النفقات (مليار دينار)"] / 1000.0,
            r_a["الرصيد (مليار دينار)"] / 1000.0,
            r_a["الاحتياطي بعد (مليار دينار)"] / 1000.0,
        ]
        قيم_ب = [
            r_b["الإيرادات النفطية (مليار دينار)"] / 1000.0,
            r_b["إجمالي الإيرادات (مليار دينار)"] / 1000.0,
            r_b["النفقات (مليار دينار)"] / 1000.0,
            r_b["الرصيد (مليار دينار)"] / 1000.0,
            r_b["الاحتياطي بعد (مليار دينار)"] / 1000.0,
        ]

        f_comp.add_trace(go.Bar(name=f"أ: {p.اسم_السيناريو}", x=فئات, y=قيم_أ, marker_color=PRIMARY))
        f_comp.add_trace(go.Bar(name=f"ب: {p_b.اسم_السيناريو}", x=فئات, y=قيم_ب, marker_color=ACCENT))
        f_comp.update_layout(
            title=f"مقارنة المؤشرات المالية الرئيسية (ترليون دينار عند سعر {سعر_مقارنة} دولار)",
            barmode="group",
            yaxis_title="ترليون دينار",
        )
        st.plotly_chart(style_fig(f_comp, height=380), width='stretch')

        # جدول المقارنة التفصيلي
        st.subheader("📋 جدول المقارنة التفصيلي")
        st.dataframe(df_comp, width='stretch')

# --- السياسة النقدية وسعر الصرف ---------------------------------------
with tab_monetary:
    st.markdown(
        '<div class="note">تحليل متكامل للسياسة النقدية: أثر فجوة السوق الموازية، خيارات تعديل سعر الصرف الرسمي، '
        'ومقايضة تحسين الرصيد المالي مقابل التضخم المستورد وارتفاع فاتورة الواردات.</div>',
        unsafe_allow_html=True,
    )
    sub_gap, sub_fx, sub_infl = st.tabs(
        [
            "↔️ فجوة السعر الموازي وسدّ الفجوة (Parallel Gap)",
            "💱 أثر تعديل سعر الصرف الرسمي (Devaluation Impact)",
            "📈 التضخم المستورد وكلفة الواردات (Imported Inflation)",
        ]
    )

    with sub_gap:
        st.subheader("↔️ تحليل فجوة السعر الموازي وسيناريوهات سدّ الفجوة")
        st.caption("الفجوة بين السعر الموازي والرسمي تعكس ضغطاً على الدينار؛ سدّ الفجوة يعني رفع السعر الرسمي نحو الموازي — يحرّك المالية العامة والتضخم معاً.")

        cc1, cc2 = st.columns([1, 1])
        with cc1:
            نسبة_السد = st.slider("نسبة سدّ الفجوة", 0.0, 1.0, 0.5, 0.05,
                                  help="0 = إبقاء السعر الرسمي، 1 = مساواته بالسعر الموازي")
        with cc2:
            سعر_نفط_فجوة = st.select_slider("سعر النفط المرجعي", options=sorted(اسعار),
                                            value=سعر_متوسط, key="gap_oil")

        g = تحليل_الفجوة(p, نسبة_السد, سعر_نفط_فجوة)

        k1, k2, k3 = st.columns(3)
        with k1:
            st.markdown(kpi_card("الفجوة الحالية", f"{g['الفجوة (دينار)']:,.0f} دينار",
                                 f"{g['نسبة الفجوة %']:,.1f}% فوق الرسمي", "neg"), unsafe_allow_html=True)
        with k2:
            st.markdown(kpi_card("السعر الرسمي الجديد", f"{g['السعر الرسمي الجديد']:,.0f}",
                                 f"بعد سدّ {g['نسبة السد %']:,.0f}% من الفجوة"), unsafe_allow_html=True)
        with k3:
            تح = g["تحسن الرصيد (مليار دينار)"]
            st.markdown(kpi_card("تحسّن الرصيد", fmt_trln(تح),
                                 "نتيجة التخفيض", "pos" if تح >= 0 else "neg"), unsafe_allow_html=True)

        # رسم: السعر الرسمي يتحرك نحو الموازي عبر نسب السد
        نسب = [i / 10 for i in range(0, 11)]
        صفوف = [تحليل_الفجوة(p, n, سعر_نفط_فجوة) for n in نسب]
        df_gap = pd.DataFrame(صفوف)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_gap["نسبة السد %"], y=df_gap["تحسن الرصيد (مليار دينار)"] / 1000.0,
                                 mode="lines+markers", name="تحسّن الرصيد", line=dict(color=PRIMARY, width=3)))
        fig.add_trace(go.Scatter(x=df_gap["نسبة السد %"], y=df_gap["التضخم المستورد التقديري %"],
                                 mode="lines+markers", name="التضخم المستورد %",
                                 line=dict(color=DANGER, width=3, dash="dot"), yaxis="y2"))
        fig.update_layout(
            title="مقايضة: تحسّن الرصيد مقابل التضخم المستورد عبر نسبة سدّ الفجوة",
            xaxis_title="نسبة سدّ الفجوة %",
            yaxis=dict(title="تحسّن الرصيد (ترليون دينار)"),
            yaxis2=dict(title="التضخم المستورد %", overlaying="y", side="left", anchor="free",
                        position=0.0, showgrid=False),
        )
        st.plotly_chart(style_fig(fig, height=380), width='stretch')

    with sub_fx:
        st.subheader("💱 أثر رفع سعر الصرف الرسمي (تخفيض قيمة الدينار)")
        st.caption("يقيس هذا القسم أثر رفع سعر الصرف على الإيرادات النفطية المحوّلة للدينار والرصيد.")

        سعر_نفط_مرجعي = st.select_slider("اختر سعر النفط المرجعي", options=sorted(اسعار),
                                         value=سعر_متوسط)
        df_fx = جدول_حسب_سعر_الصرف(p, سعر_نفط_مرجعي)

        cc1, cc2 = st.columns(2)
        with cc1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_fx["سعر الصرف (دينار/دولار)"].astype(str),
                y=df_fx["الرصيد (مليار دينار)"] / 1000.0,
                marker_color=[PRIMARY if v >= 0 else DANGER for v in df_fx["الرصيد (مليار دينار)"]],
            ))
            fig.add_hline(y=0, line_dash="dash", line_color=MUTED)
            fig.update_layout(title=f"الرصيد حسب سعر الصرف (سعر النفط {سعر_نفط_مرجعي} دولار)",
                              xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
            st.plotly_chart(style_fig(fig, height=340), width='stretch')

        with cc2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_fx["سعر الصرف (دينار/دولار)"],
                y=df_fx["الإيرادات النفطية (مليار دينار)"] / 1000.0,
                mode="lines+markers", line=dict(color=ACCENT, width=3), name="الإيرادات النفطية"))
            fig.update_layout(title="الإيرادات النفطية بالدينار حسب سعر الصرف",
                              xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
            st.plotly_chart(style_fig(fig, height=340), width='stretch')

        st.dataframe(
            df_fx[["سعر الصرف (دينار/دولار)", "الإيرادات النفطية (مليار دينار)",
                   "الرصيد (مليار دينار)", "تحسن الرصيد عن الأساس (مليار دينار)",
                   "الاحتياطي بعد (مليار دينار)"]].style.format("{:,.0f}"),
            width='stretch',
        )

    with sub_infl:
        st.subheader("📈 التضخم المستورد وفاتورة الاستيراد")
        st.caption("تقدير تقريبي: التضخم المستورد ≈ حصة السلع المستوردة × معامل التمرير × نسبة تغيّر سعر الصرف.")

        df_infl = pd.DataFrame([
            {**{"سعر الصرف": fx}, **تقدير_التضخم(p, p.سعر_الصرف_الرسمي, fx)}
            for fx in sorted(p.اسعار_الصرف_سيناريو)
        ])

        cc1, cc2 = st.columns(2)
        with cc1:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_infl["سعر الصرف"].astype(str),
                                 y=df_infl["التضخم المستورد التقديري %"],
                                 marker_color=ACCENT))
            fig.update_layout(title="التضخم المستورد التقديري حسب سعر الصرف",
                              xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="%")
            st.plotly_chart(style_fig(fig, height=340), width='stretch')
        with cc2:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_infl["سعر الصرف"].astype(str),
                                 y=df_infl["زيادة فاتورة الاستيراد (مليار دينار)"] / 1000.0,
                                 marker_color=DANGER))
            fig.update_layout(title="الزيادة في فاتورة الاستيراد",
                              xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
            st.plotly_chart(style_fig(fig, height=340), width='stretch')

        st.dataframe(
            df_infl[["سعر الصرف", "نسبة تغير الصرف %", "التضخم المستورد التقديري %",
                     "زيادة فاتورة الاستيراد (مليار دينار)"]].style.format("{:,.1f}"),
            width='stretch',
        )

# --- التقرير التنفيذي والسياسات ----------------------------------------
with tab_policy:
    st.subheader("📋 التقرير التنفيذي وتوصيات السياسات الاقتصادية")
    st.markdown(
        '<div class="note">تشخيص شامل وموجّه لصنّاع القرار والباحثين، يستعرض الوضع الهيكلي للموازنة '
        'ويقدّم حزمة سياسات اقتصادية وتوصيات إصلاحية ذكية مبنية على معطيات السيناريو المختار.</div>',
        unsafe_allow_html=True,
    )

    # 1. بطاقة الملخص التنفيذي
    انفاق_كلي = p.اجمالي_النفقات_مليار if p.استخدام_الاجمالي else p.النفقات_الجارية_مليار
    نسبة_رواتب = (p.فاتورة_الرواتب_مليار / انفاق_كلي * 100.0) if انفاق_كلي else 0.0
    تغطية_m0 = (p.الاحتياطيات_الاجنبية_مليار / p.النقد_القاعدي_مليار * 100.0) if p.النقد_القاعدي_مليار else 0.0

    st.markdown(
        f"""
        <div style="background: #ffffff; border: 1px solid #dbe2df; border-radius: 12px; padding: 20px 24px; margin-bottom: 22px; box-shadow: 0 1px 4px rgba(0,0,0,0.03);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eef1f0; padding-bottom: 12px; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                <h3 style="margin: 0; color: #0E6E5C; font-size: 19px;">📄 تقرير الاستدامة والسياسات: {p.اسم_السيناريو}</h3>
                <span style="font-size: 13.5px; color: #435952; background: #eef2f1; padding: 4px 12px; border-radius: 6px;">
                    سعر النفط المرجعي: <strong>{سعر_متوسط}$</strong> | السعر الرسمي: <strong>{p.سعر_الصرف_الرسمي:,.0f}</strong>
                </span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; font-size: 14px;">
                <div>🔹 <strong>الرصيد المالي المقدر:</strong> <span style="color: {'#0E6E5C' if رصيد >= 0 else '#C2392F'}; font-weight: 700;">{fmt_trln(رصيد)}</span></div>
                <div>🔹 <strong>سعر تعادل الموازنة:</strong> <strong>{ملخص['سعر نفط التعادل (دولار)']:,.1f}$</strong> للبرميل</div>
                <div>🔹 <strong>سعر تعادل الرواتب:</strong> <strong>{ملخص['سعر تعادل الرواتب (دولار)']:,.1f}$</strong> للبرميل</div>
                <div>🔹 <strong>فجوة السعر الموازي:</strong> <span style="color: #C2392F; font-weight: 700;">{نسبة_فجوة_صرف:,.1f}% ({الفجوة_صرف:,.0f} دينار)</span></div>
                <div>🔹 <strong>تغطية النقد M0:</strong> <strong>{تغطية_m0:,.1f}%</strong> من القاعدة النقدية</div>
                <div>🔹 <strong>حصّة الرواتب من الإنفاق:</strong> <strong>{نسبة_رواتب:,.1f}%</strong> ({fmt_trln(p.فاتورة_الرواتب_مليار)})</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. حزمة توصيات السياسات الذكية
    st.subheader("💡 توصيات السياسة المالية والنقدية المقترحة")
    توصيات_ذكية = توليد_توصيات_السياسات(p, سعر_متوسط)

    # (لون الحد، خلفية البطاقة، لون العنوان، خلفية الشارة). الشارة أغمق من الحد
    # لأن نصها أبيض ويلزمه تباين 4.5:1 على الأقل.
    لون_أولوية = {
        "حرجة": ("#C2392F", "#fdf2f2", "#9E2A22", "#B3302A"),
        "عالية": ("#C8A042", "#fffbf0", "#7A5600", "#8A6212"),
        "متوسطة": ("#2E86AB", "#f0f8fd", "#0B5F80", "#1F6F8F"),
        "استراتيجية": ("#0E6E5C", "#f0f8f6", "#0B5A4B", "#0E6E5C"),
        "منخفضة": ("#6b7c78", "#f9faf9", "#3A3A3A", "#566863"),
    }

    for rec in توصيات_ذكية:
        border_col, bg_col, text_col, badge_col = لون_أولوية.get(rec["الأولوية"], ("#0E6E5C", "#f0f8f6", "#0B5A4B", "#0E6E5C"))
        st.markdown(
            f"""
            <div style="background: {bg_col}; border-right: 5px solid {border_col}; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: {text_col}; font-size: 15px;">🏛️ {rec['المجال']} — {rec['النوع']}</strong>
                    <span style="background: {badge_col}; color: #ffffff; padding: 3px 12px; border-radius: 12px; font-size: 12.5px; font-weight: 600;">أولوية {rec['الأولوية']}</span>
                </div>
                <div style="color: #16302B; font-size: 13.5px; line-height: 1.6;">
                    {rec['النص']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # 3. خيارات الطباعة والتصدير
    col_pr1, col_pr2 = st.columns([1, 1])
    with col_pr1:
        st.markdown(
            """
            <button onclick="window.print()" style="background: #0E6E5C; color: white; border: none; padding: 10px 22px; border-radius: 8px; font-weight: 600; cursor: pointer; font-family: 'IBM Plex Sans Arabic'; font-size: 14px; width: 100%;">
                🖨️ طباعة التقرير التنفيذي (أو الحفظ بصيغة PDF)
            </button>
            """,
            unsafe_allow_html=True,
        )
    with col_pr2:
        نص_التقرير = f"""تقرير الاستدامة المالية والسياسات العامة — العراق
السيناريو المعتمد: {p.اسم_السيناريو}
سعر النفط المرجعي: {سعر_متوسط}$ للبرميل
سعر الصرف الرسمي: {p.سعر_الصرف_الرسمي:,.0f} دينار/دولار
سعر الصرف الموازي: {p.سعر_الصرف_الموازي:,.0f} دينار/دولار

الرصيد المالي المقدر: {fmt_trln(رصيد)}
سعر نفط التعادل الإجمالي: {ملخص['سعر نفط التعادل (دولار)']:,.1f}$
سعر تعادل فاتورة الرواتب: {ملخص['سعر تعادل الرواتب (دولار)']:,.1f}$
فجوة سعر الصرف: {نسبة_فجوة_صرف:,.1f}% ({الفجوة_صرف:,.0f} دينار)
نسبة تغطية النقد القاعدي M0: {تغطية_m0:,.1f}%

التوصيات المقترحة:
"""
        for r in توصيات_ذكية:
            نص_التقرير += f"\n- [{r['المجال']} | أولوية {r['الأولوية']}] {r['النص']}\n"

        st.download_button(
            "📄 تنزيل ملخص التقرير (نصي)",
            data=نص_التقرير.encode("utf-8-sig"),
            file_name=f"تقرير_السياسات_{p.اسم_السيناريو}.txt",
            mime="text/plain",
            width='stretch',
        )

# --- التحليل والبيانات المرجعية ----------------------------------------
with tab_deep:
    st.markdown(
        '<div class="note">مساحة التحليل والتحقق: خريطة الحساسية المزدوجة، السلاسل الرسمية للبنك المركزي العراقي '
        'للتحقق من دقة النموذج، وتصدير الجداول الكاملة بصيغتي Excel و CSV.</div>',
        unsafe_allow_html=True,
    )
    sub_sens, sub_cbi, sub_export = st.tabs(
        [
            "🔥 مصفوفة الحساسية المزدوجة (نفط × صرف)",
            "📅 بيانات البنك المركزي والتحقق من النموذج (CBI)",
            "🗂️ الجداول الكاملة وتصدير البيانات (Excel / CSV)",
        ]
    )

    with sub_sens:
        st.subheader("🔥 مصفوفة الحساسية المزدوجة (سعر النفط × سعر الصرف)")
        st.caption("خريطة حرارية تُظهر الرصيد المالي (ترليون دينار) عند كل تركيبة من سعر النفط وسعر الصرف. الأخضر = فائض، والأحمر = عجز.")
        mat = مصفوفة_الحساسية(p) / 1000.0  # ترليون
        fig_sens = px.imshow(
            mat,
            labels=dict(x="سعر النفط (دولار)", y="سعر الصرف (دينار/دولار)", color="ترليون دينار"),
            x=[str(c) for c in mat.columns],
            y=[str(i) for i in mat.index],
            color_continuous_scale=[[0, DANGER], [0.5, "#f7f7f0"], [1, PRIMARY]],
            color_continuous_midpoint=0,
            text_auto=".1f",
            aspect="auto",
        )
        fig_sens.update_layout(title="مصفوفة حساسية الرصيد (نفط × صرف)")
        st.plotly_chart(style_fig(fig_sens, height=440), width='stretch')

    with sub_cbi:
        df_year = بيانات_المركزي.get("سنوي")
        df_fis = بيانات_المركزي.get("مالية_سنوي")

        if df_year is None and df_fis is None:
            st.warning("ملفات البيانات الفعلية غير موجودة (مجلد data/). "
                       "شغّل extract_cbi_data.py لتوليدها من ملف البنك المركزي.")
        else:
            st.caption("بيانات رسمية من البنك المركزي العراقي. المقارنة السنوية تستخدم السنوات المكتملة فقط؛ الأرقام الشهرية للموازنة تراكمية منذ بداية السنة.")

            if بيانات_المركزي.get("snapshot"):
                with st.expander("المؤشرات حسب الفترة — أحدث البيانات الشهرية"):
                    st.caption("الاحتياطي وM0 أرصدة بنهاية الفترة، والتضخم نسبة. بيانات التجارة في الأعمدة الشهرية لا تُستخدم كإجماليات سنوية.")
                    st.dataframe(بيانات_المركزي["مؤشرات"], width="stretch")
                with st.expander("الموازنة الشهرية — تراكم منذ بداية السنة"):
                    st.dataframe(بيانات_المركزي["مالية_شهري"], width="stretch", hide_index=True)

            # ---- المؤشرات السنوية ----
            if df_year is not None:
                سنوات = list(df_year.columns)

                def صف(مؤشر):
                    try:
                        return [float(x) for x in df_year.loc[مؤشر].values]
                    except Exception:
                        return [None] * len(سنوات)

                r1, r2 = st.columns(2)
                with r1:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=سنوات, y=صف("الاحتياطيات الأجنبية (مليار دينار)"),
                                         marker_color=PRIMARY, name="الاحتياطي"))
                    fig.add_trace(go.Scatter(x=سنوات, y=صف("M0 الأساس النقدي (مليار دينار)"),
                                             mode="lines+markers", name="M0", line=dict(color=ACCENT, width=3)))
                    fig.update_layout(title="الاحتياطي الأجنبي و M0 (مليار دينار)")
                    st.plotly_chart(style_fig(fig, height=340), width='stretch')
                with r2:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=سنوات, y=صف("التضخم %"), marker_color="#2E86AB", name="التضخم"))
                    fig.add_trace(go.Scatter(x=سنوات, y=صف("سعر الصرف (دينار/دولار)"),
                                             mode="lines+markers", name="سعر الصرف", line=dict(color=DANGER, width=3),
                                             yaxis="y2"))
                    fig.update_layout(
                        title="التضخم وسعر الصرف الرسمي",
                        yaxis=dict(title="التضخم %"),
                        yaxis2=dict(title="سعر الصرف", overlaying="y", side="left",
                                    anchor="free", position=0.0, showgrid=False),
                    )
                    st.plotly_chart(style_fig(fig, height=340), width='stretch')

            # ---- المالية: الإيرادات/النفقات/العجز السنوي ----
            if df_fis is not None:
                fis = df_fis[df_fis["الشهر"] == 12].copy()  # السنوات المكتملة فقط
                if not fis.empty:
                    سنوات_م = [str(int(y)) for y in fis["السنة"]]
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=سنوات_م, y=fis["الإيرادات السنوية (مليار دينار)"] / 1000.0,
                                         name="الإيرادات", marker_color=PRIMARY))
                    fig.add_trace(go.Bar(x=سنوات_م, y=fis["النفقات السنوية (مليار دينار)"] / 1000.0,
                                         name="النفقات", marker_color=DANGER))
                    fig.add_trace(go.Scatter(x=سنوات_م, y=fis["الرصيد السنوي (مليار دينار)"] / 1000.0,
                                             name="الرصيد", mode="lines+markers+text",
                                             text=[f"{v/1000:,.1f}" for v in fis["الرصيد السنوي (مليار دينار)"]],
                                             textposition="top center", line=dict(color=INK, width=3)))
                    fig.update_layout(title="الموازنة الفعلية: الإيرادات والنفقات والرصيد (ترليون دينار)",
                                      barmode="group")
                    st.plotly_chart(style_fig(fig, height=380), width='stretch')

            # ---- التحقق: مقارنة النموذج بالواقع ----
            st.subheader("🔎 التحقق: النموذج مقابل الواقع")
            if df_fis is not None and not df_fis[df_fis["الشهر"] == 12].empty:
                سنوات_متاحة = [str(int(y)) for y in df_fis[df_fis["الشهر"] == 12]["السنة"]]
                ساق = st.columns([1, 1])
                with ساق[0]:
                    سنة_تحقق = st.selectbox("سنة التحقق", سنوات_متاحة, index=len(سنوات_متاحة) - 1)
                صف_سنة = df_fis[(df_fis["السنة"] == int(سنة_تحقق)) & (df_fis["الشهر"] == 12)].iloc[0]
                ايراد_فعلي = float(صف_سنة["الإيرادات السنوية (مليار دينار)"])
                نفقات_فعلية = float(صف_سنة["النفقات السنوية (مليار دينار)"])
                رصيد_فعلي = float(صف_سنة["الرصيد السنوي (مليار دينار)"])

                صرف_سنة = قيمة_سنوية(بيانات_المركزي, "سعر الصرف (دينار/دولار)", سنة_تحقق, p.سعر_الصرف_الرسمي)
                براميل_سنوياً = صافي_براميل_التصدير(p) * 1_000_000 * 365
                نفط_ضمني = ايراد_فعلي - غير_نفطي
                سعر_ضمني = (نفط_ضمني * 1e9) / (براميل_سنوياً * صرف_سنة) if براميل_سنوياً and صرف_سنة else None

                with ساق[1]:
                    st.caption(f"بافتراض إيراد غير نفطي = {غير_نفطي:,.0f} مليار دينار "
                               f"وسعر صرف {صرف_سنة:,.0f} وصادرات {صافي_براميل_التصدير(p):.2f} مليون ب/ي.")

                v1, v2, v3 = st.columns(3)
                with v1:
                    st.markdown(kpi_card("العجز الفعلي", fmt_trln(رصيد_فعلي),
                                         f"إيراد {ايراد_فعلي/1000:,.1f} − نفقات {نفقات_فعلية/1000:,.1f}",
                                         "neg" if رصيد_فعلي < 0 else "pos"), unsafe_allow_html=True)
                with v2:
                    st.markdown(kpi_card("سعر النفط الضمني", f"{سعر_ضمني:,.1f}$" if سعر_ضمني else "—",
                                         "السعر الذي يفسّر الإيراد الفعلي"), unsafe_allow_html=True)
                with v3:
                    سعر_فعلي = st.number_input("سعر النفط الفعلي المعروف (للمقارنة)", value=0.0, step=1.0,
                                               help="أدخل متوسط سعر تصدير النفط الفعلي لتلك السنة للمقارنة.")
                    فرق = (سعر_ضمني - سعر_فعلي) if (سعر_ضمني and سعر_فعلي) else None
                    st.markdown(kpi_card("الفرق عن الفعلي",
                                         (f"{فرق:+,.1f}$" if فرق is not None else "—"),
                                         "كلما اقترب من الصفر، كان النموذج أدق",
                                         "pos" if (فرق is not None and abs(فرق) < 5) else ""),
                                unsafe_allow_html=True)
                st.caption("فكرة التحقق: نشتقّ من الإيراد الفعلي «سعر النفط الضمني» وفق معادلة النموذج، "
                           "ثم نقارنه بمتوسط السعر الفعلي. التقارب يؤكد سلامة منطق الإيراد النفطي.")

            # جدول المؤشرات الخام
            if df_year is not None:
                with st.expander("📋 جدول المؤشرات السنوية الكامل"):
                    st.dataframe(df_year, width='stretch')

    with sub_export:
        df_oil = جدول_حسب_سعر_النفط(p, p.سعر_الصرف_الرسمي)
        df_fx_all = جدول_حسب_سعر_الصرف(p, سعر_متوسط)
        mat = مصفوفة_الحساسية(p)

        st.subheader("🗂️ الجداول الكاملة وتصدير البيانات")
        st.dataframe(df_oil.style.format("{:,.0f}", subset=[c for c in df_oil.columns if "سعر" not in c]),
                     width='stretch')

        st.subheader("الملخص الفني للسيناريو")
        st.json(ملخص)

        # تصدير Excel في الذاكرة
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_oil.to_excel(writer, sheet_name="حسب سعر النفط", index=False)
                df_fx_all.to_excel(writer, sheet_name="حسب سعر الصرف", index=False)
                mat.to_excel(writer, sheet_name="مصفوفة الحساسية")
                pd.DataFrame([ملخص]).to_excel(writer, sheet_name="الملخص", index=False)
                input_audit_df.to_excel(writer, sheet_name="مصادر المدخلات", index=False)
            st.download_button(
                "⬇️ تنزيل كافة النتائج (Excel)",
                data=buffer.getvalue(),
                file_name=f"نتائج_الموازنة_{p.اسم_السيناريو}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.warning(f"تعذّر إنشاء ملف Excel: {e}")

        csv = df_oil.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ تنزيل جدول الموازنة (CSV)", data=csv, file_name="نتائج_الموازنة.csv", mime="text/csv")

st.caption("⚠️ هذه نتائج تقديرية لأغراض تحليل السيناريوهات، وليست توقعات رسمية. "
           "افتراضات التضخم والاستيراد مبسّطة وقابلة للتعديل من الشريط الجانبي.")
