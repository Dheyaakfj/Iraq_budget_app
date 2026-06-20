# -*- coding: utf-8 -*-
"""
تطبيق تحليل سيناريوهات الموازنة العراقية وأسعار النفط وسعر الصرف
================================================================
واجهة تفاعلية (Streamlit + Plotly) بتصميم RTL عربي.
"""

import io
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from scenario_engine_ar import (
    مدخلات,
    جدول_حسب_سعر_النفط,
    جدول_حسب_سعر_الصرف,
    مصفوفة_الحساسية,
    تحليل_الفجوة,
    تقدير_التضخم,
    ملخص_السيناريو,
    حساب_الموازنة,
    حفظ_النتائج,
)

# ----------------------------------------------------------------------
# إعداد الصفحة والهوية البصرية
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="سيناريوهات الموازنة العراقية",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# لوحة ألوان
PRIMARY = "#0E6E5C"      # أخضر نفطي
ACCENT = "#C8A042"       # ذهبي
DANGER = "#C2392F"       # أحمر (عجز)
INK = "#16302B"          # داكن
MUTED = "#6b7c78"

PLOTLY_TEMPLATE = "plotly_white"
COLORWAY = [PRIMARY, ACCENT, DANGER, "#2E86AB", "#8E6C8A", "#5B8C5A"]

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stMarkdown, .stMetric {{
    direction: rtl;
    text-align: right;
    font-family: 'IBM Plex Sans Arabic', 'Segoe UI', Tahoma, sans-serif;
}}

/* رأس الصفحة المخصص */
.app-hero {{
    background: linear-gradient(120deg, {PRIMARY} 0%, #0a4f42 60%, {INK} 100%);
    color: #fff;
    padding: 26px 30px;
    border-radius: 18px;
    margin-bottom: 18px;
    box-shadow: 0 10px 30px rgba(14,110,92,0.25);
}}
.app-hero h1 {{ margin: 0; font-size: 30px; font-weight: 700; }}
.app-hero p  {{ margin: 8px 0 0; opacity: .92; font-size: 15px; }}

/* بطاقات المؤشرات */
.kpi {{
    background: #ffffff;
    border: 1px solid #eef1f0;
    border-radius: 16px;
    padding: 16px 18px;
    box-shadow: 0 4px 14px rgba(16,48,43,0.06);
    height: 100%;
}}
.kpi .label {{ color: {MUTED}; font-size: 13px; margin-bottom: 6px; }}
.kpi .value {{ font-size: 26px; font-weight: 700; color: {INK}; }}
.kpi .sub   {{ font-size: 12px; margin-top: 4px; }}
.pos {{ color: {PRIMARY}; }}
.neg {{ color: {DANGER}; }}

/* التبويبات */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{
    background: #f3f6f5; border-radius: 12px 12px 0 0;
    padding: 8px 16px; font-weight: 600;
}}
.stTabs [aria-selected="true"] {{ background: {PRIMARY}; color: #fff; }}

section[data-testid="stSidebar"] {{ direction: rtl; }}
section[data-testid="stSidebar"] * {{ text-align: right; }}

/* صندوق ملاحظة */
.note {{
    background: #fbf6e9; border-right: 4px solid {ACCENT};
    padding: 10px 14px; border-radius: 8px; font-size: 13px; color: #5b4f2e;
}}

/* ===== التجاوب مع الموبايل ===== */
@media (max-width: 640px) {{
    /* تكديس الأعمدة عمودياً (البطاقات والرسوم جنباً إلى جنب) */
    [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: 10px !important; }}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important;
    }}
    /* تصغير الرأس والخطوط */
    .app-hero {{ padding: 18px 16px; border-radius: 14px; }}
    .app-hero h1 {{ font-size: 21px; }}
    .app-hero p  {{ font-size: 13px; }}
    .kpi {{ padding: 12px 14px; }}
    .kpi .value {{ font-size: 21px; }}
    /* تمرير أفقي لشريط التبويبات بدل الازدحام */
    .stTabs [data-baseweb="tab-list"] {{ overflow-x: auto; flex-wrap: nowrap; }}
    .stTabs [data-baseweb="tab"] {{ padding: 6px 10px; font-size: 13px; white-space: nowrap; }}
    /* تقليص الحشو الجانبي لاستغلال عرض الشاشة */
    .block-container {{ padding-left: 0.6rem !important; padding-right: 0.6rem !important; }}

    /* إصلاح: عند طي المدخلات لا يبقى شريط في المنتصف */
    section[data-testid="stSidebar"][aria-expanded="false"] {{
        display: none !important;
        width: 0 !important; min-width: 0 !important;
        transform: translateX(-110%) !important;
    }}
    [data-testid="stSidebarResizeHandle"],
    [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
    /* المحتوى يأخذ كامل العرض عند الطي */
    [data-testid="stAppViewContainer"] > .main {{ width: 100% !important; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


def kpi_card(label, value, sub="", tone="ink"):
    cls = {"pos": "pos", "neg": "neg"}.get(tone, "")
    sub_html = f'<div class="sub {cls}">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {sub_html}
    </div>
    """


def fmt_trln(x):
    """تنسيق مليار دينار إلى ترليون."""
    return f"{x/1000.0:,.1f} ترليون"


def style_fig(fig, height=380):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        colorway=COLORWAY,
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        font=dict(family="IBM Plex Sans Arabic, Segoe UI, sans-serif", size=13),
        title_x=0.5,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right"),
    )
    return fig


# ----------------------------------------------------------------------
# الرأس
# ----------------------------------------------------------------------
st.markdown(
    """
<div class="app-hero">
    <h1>🛢️ تحليل سيناريوهات الموازنة العراقية</h1>
    <p>أثر أسعار النفط وتخفيض سعر صرف الدينار على الإيرادات والعجز والاحتياطيات —
    مع تحليل الفجوة بين السعر الموازي والرسمي والتضخم المستورد.</p>
</div>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# الشريط الجانبي — المدخلات
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ المدخلات")

    with st.expander("🛢️ النفط والصادرات", expanded=True):
        اسعار = st.multiselect(
            "أسعار النفط (دولار/برميل)",
            [40, 45, 50, 55, 58.5, 60, 62, 65, 67, 70, 72, 75, 80, 85, 90, 100, 110, 120],
            default=[50, 60, 70, 80, 90, 110],
        )
        صادرات = st.number_input("حجم الصادرات (مليون برميل/يوم)", value=4.1, step=0.1)
        محلي = st.number_input("الاستهلاك المحلي (مليون برميل/يوم)", value=0.8, step=0.1)
        حصة = st.slider("حصة الحكومة من الصادرات", 0.0, 1.0, 1.0, 0.05)

    with st.expander("💱 سعر الصرف", expanded=True):
        رسمي = st.number_input("السعر الرسمي الحالي (دينار/دولار)", value=1310, step=10)
        موازي = st.number_input("السعر الموازي في السوق (دينار/دولار)", value=1500, step=10)
        اسعار_صرف = st.multiselect(
            "سيناريوهات سعر الصرف (للتخفيض)",
            [1190, 1250, 1300, 1310, 1350, 1400, 1450, 1500, 1550, 1600],
            default=[1310, 1400, 1450, 1500],
        )

    with st.expander("💰 المالية العامة (مليار دينار)", expanded=False):
        غير_نفطي = st.number_input("الإيرادات غير النفطية", value=20000, step=500)
        اجمالي = st.number_input("إجمالي النفقات", value=199000, step=1000)
        جاري = st.number_input("النفقات الجارية", value=150000, step=1000)
        استخدم_الاجمالي = st.toggle("استخدام الإجمالي بدل الجاري", value=True)

    with st.expander("🏦 النقد والاحتياطي (مليار دينار)", expanded=False):
        احتياطي = st.number_input("الاحتياطيات الأجنبية", value=132000, step=1000)
        نقد = st.number_input("النقد القاعدي", value=104000, step=1000)
        نسبة_المركزي = st.slider("نسبة تمويل المركزي للعجز", 0.0, 1.0, 0.3, 0.05)
        نسبة_فائض = st.slider("نسبة الفائض تذهب للاحتياطي", 0.0, 1.0, 0.5, 0.05)

    with st.expander("📈 التضخم والاستيراد", expanded=False):
        واردات = st.number_input("الواردات السنوية (مليار دولار)", value=60.0, step=1.0)
        حصة_مستورد = st.slider("حصة السلع المستوردة في سلة المستهلك", 0.0, 1.0, 0.40, 0.05)
        تمرير = st.slider("معامل تمرير الصرف إلى الأسعار", 0.0, 1.0, 0.50, 0.05)

# حماية من القوائم الفارغة
if not اسعار:
    اسعار = [60]
if not اسعار_صرف:
    اسعار_صرف = [رسمي]

p = مدخلات(
    اسعار_النفط=اسعار,
    حجم_الصادرات_مليون_برميل_يوم=صادرات,
    الاستهلاك_المحلي_مليون_برميل_يوم=محلي,
    حصة_الحكومة_من_الصادرات=حصة,
    ايام_السنة=365,
    سعر_الصرف_الرسمي=float(رسمي),
    سعر_الصرف_الموازي=float(موازي),
    اسعار_الصرف_سيناريو=[float(x) for x in اسعار_صرف],
    ايرادات_غير_نفطية_مليار=غير_نفطي,
    اجمالي_النفقات_مليار=اجمالي,
    النفقات_الجارية_مليار=جاري,
    استخدام_الاجمالي=استخدم_الاجمالي,
    الاحتياطيات_الاجنبية_مليار=احتياطي,
    النقد_القاعدي_مليار=نقد,
    نسبة_تمويل_المركزي=نسبة_المركزي,
    نسبة_الفائض_للاحتياطي=نسبة_فائض,
    واردات_سنوية_مليار_دولار=واردات,
    حصة_المستورد_من_السلة=حصة_مستورد,
    معامل_تمرير_التضخم=تمرير,
)

# ----------------------------------------------------------------------
# بطاقات المؤشرات (نظرة عامة)
# ----------------------------------------------------------------------
سعر_متوسط = sorted(اسعار)[len(اسعار) // 2]  # سعر نفط مرجعي (الوسيط)
ملخص = ملخص_السيناريو(p, p.سعر_الصرف_الرسمي)
صف_مرجعي = حساب_الموازنة(سعر_متوسط, p.سعر_الصرف_الرسمي, p)
الفجوة_صرف = p.سعر_الصرف_الموازي - p.سعر_الصرف_الرسمي
نسبة_فجوة_صرف = (الفجوة_صرف / p.سعر_الصرف_الرسمي * 100.0) if p.سعر_الصرف_الرسمي else 0.0

c1, c2, c3, c4 = st.columns(4)
with c1:
    رصيد = صف_مرجعي["الرصيد (مليار دينار)"]
    st.markdown(
        kpi_card(
            f"الرصيد عند {سعر_متوسط}$ للبرميل",
            fmt_trln(رصيد),
            ("فائض" if رصيد >= 0 else "عجز"),
            "pos" if رصيد >= 0 else "neg",
        ),
        unsafe_allow_html=True,
    )
with c2:
    تع = ملخص["سعر نفط التعادل (دولار)"]
    st.markdown(
        kpi_card("سعر نفط التعادل", f"{تع:,.1f}$" if تع else "—",
                 "السعر الذي يوازن الموازنة"),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        kpi_card("فجوة سعر الصرف", f"{الفجوة_صرف:,.0f} دينار",
                 f"{نسبة_فجوة_صرف:,.1f}% فوق الرسمي", "neg"),
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        kpi_card("الاحتياطيات الأجنبية", fmt_trln(p.الاحتياطيات_الاجنبية_مليار),
                 f"النقد القاعدي: {fmt_trln(p.النقد_القاعدي_مليار)}"),
        unsafe_allow_html=True,
    )

st.write("")

# ----------------------------------------------------------------------
# التبويبات
# ----------------------------------------------------------------------
tab_overview, tab_fx, tab_gap, tab_sens, tab_infl, tab_data = st.tabs(
    ["📊 نظرة عامة", "💱 تخفيض سعر الصرف", "↔️ الفجوة الموازية/الرسمية",
     "🔥 الحساسية المزدوجة", "📈 التضخم والاستيراد", "🗂️ البيانات والتصدير"]
)

# --- نظرة عامة ---------------------------------------------------------
with tab_overview:
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
            mode="lines+markers", name="النفقات", line=dict(color=DANGER, width=3, dash="dot")))
        fig.update_layout(title="الإيرادات مقابل النفقات",
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

# --- تخفيض سعر الصرف ---------------------------------------------------
with tab_fx:
    st.markdown(
        '<div class="note">يقيس هذا القسم أثر رفع سعر الصرف (تخفيض قيمة الدينار) '
        'على الإيرادات النفطية المحوّلة للدينار والرصيد. التخفيض يرفع الإيراد بالدينار '
        'لكنه يرفع كلفة الاستيراد والتضخم (انظر تبويب التضخم).</div>',
        unsafe_allow_html=True,
    )
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
        fig.update_layout(title=f"الرصيد حسب سعر الصرف (نفط {سعر_نفط_مرجعي}$)",
                          xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
        st.plotly_chart(style_fig(fig), width='stretch')

    with cc2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_fx["سعر الصرف (دينار/دولار)"],
            y=df_fx["الإيرادات النفطية (مليار دينار)"] / 1000.0,
            mode="lines+markers", line=dict(color=ACCENT, width=3), name="الإيرادات النفطية"))
        fig.update_layout(title="الإيرادات النفطية بالدينار حسب سعر الصرف",
                          xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
        st.plotly_chart(style_fig(fig), width='stretch')

    st.dataframe(
        df_fx[["سعر الصرف (دينار/دولار)", "الإيرادات النفطية (مليار دينار)",
               "الرصيد (مليار دينار)", "تحسن الرصيد عن الأساس (مليار دينار)",
               "الاحتياطي بعد (مليار دينار)"]].style.format("{:,.0f}"),
        width='stretch',
    )

# --- الفجوة الموازية/الرسمية -------------------------------------------
with tab_gap:
    st.markdown(
        '<div class="note">الفجوة بين السعر الموازي والرسمي تعكس ضغطاً على الدينار. '
        'سدّ الفجوة يعني رفع السعر الرسمي نحو الموازي — يحرّك المالية العامة والتضخم معاً.</div>',
        unsafe_allow_html=True,
    )
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
    st.plotly_chart(style_fig(fig, height=420), width='stretch')

# --- الحساسية المزدوجة -------------------------------------------------
with tab_sens:
    st.markdown(
        '<div class="note">خريطة حرارية تُظهر الرصيد (ترليون دينار) عند كل تركيبة من '
        'سعر النفط وسعر الصرف. الأخضر = فائض، الأحمر = عجز.</div>',
        unsafe_allow_html=True,
    )
    mat = مصفوفة_الحساسية(p) / 1000.0  # ترليون
    fig = px.imshow(
        mat,
        labels=dict(x="سعر النفط (دولار)", y="سعر الصرف (دينار/دولار)", color="ترليون دينار"),
        x=[str(c) for c in mat.columns],
        y=[str(i) for i in mat.index],
        color_continuous_scale=[[0, DANGER], [0.5, "#f7f7f0"], [1, PRIMARY]],
        color_continuous_midpoint=0,
        text_auto=".1f",
        aspect="auto",
    )
    fig.update_layout(title="مصفوفة حساسية الرصيد (نفط × صرف)")
    st.plotly_chart(style_fig(fig, height=460), width='stretch')

# --- التضخم والاستيراد -------------------------------------------------
with tab_infl:
    st.markdown(
        '<div class="note">تقدير تقريبي: التضخم المستورد ≈ حصة السلع المستوردة × معامل التمرير × '
        'نسبة تغيّر سعر الصرف. وفاتورة الاستيراد بالدينار = الواردات (دولار) × سعر الصرف.</div>',
        unsafe_allow_html=True,
    )
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
        st.plotly_chart(style_fig(fig), width='stretch')
    with cc2:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_infl["سعر الصرف"].astype(str),
                             y=df_infl["زيادة فاتورة الاستيراد (مليار دينار)"] / 1000.0,
                             marker_color=DANGER))
        fig.update_layout(title="الزيادة في فاتورة الاستيراد",
                          xaxis_title="سعر الصرف (دينار/دولار)", yaxis_title="ترليون دينار")
        st.plotly_chart(style_fig(fig), width='stretch')

    st.dataframe(
        df_infl[["سعر الصرف", "نسبة تغير الصرف %", "التضخم المستورد التقديري %",
                 "زيادة فاتورة الاستيراد (مليار دينار)"]].style.format("{:,.1f}"),
        width='stretch',
    )

# --- البيانات والتصدير -------------------------------------------------
with tab_data:
    df_oil = جدول_حسب_سعر_النفط(p, p.سعر_الصرف_الرسمي)
    df_fx_all = جدول_حسب_سعر_الصرف(p, سعر_متوسط)
    mat = مصفوفة_الحساسية(p)

    st.subheader("جدول الموازنة حسب سعر النفط")
    st.dataframe(df_oil.style.format("{:,.0f}", subset=[c for c in df_oil.columns if "سعر" not in c]),
                 width='stretch')

    st.subheader("الملخص")
    st.json(ملخص)

    # تصدير Excel في الذاكرة
    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_oil.to_excel(writer, sheet_name="حسب سعر النفط", index=False)
            df_fx_all.to_excel(writer, sheet_name="حسب سعر الصرف", index=False)
            mat.to_excel(writer, sheet_name="مصفوفة الحساسية")
            pd.DataFrame([ملخص]).to_excel(writer, sheet_name="الملخص", index=False)
        st.download_button(
            "⬇️ تنزيل النتائج (Excel)",
            data=buffer.getvalue(),
            file_name="نتائج_الموازنة.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.warning(f"تعذّر إنشاء ملف Excel: {e}")

    csv = df_oil.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ تنزيل (CSV)", data=csv, file_name="نتائج_الموازنة.csv", mime="text/csv")

st.caption("⚠️ هذه نتائج تقديرية لأغراض تحليل السيناريوهات، وليست توقعات رسمية. "
           "افتراضات التضخم والاستيراد مبسّطة وقابلة للتعديل من الشريط الجانبي.")
