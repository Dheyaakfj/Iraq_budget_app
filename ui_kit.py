"""نظام التصميم البصري لمرصد الموازنة العراقية.

يُستورد في أعلى app_ar.py بدل كتلة الـCSS الحالية:

    import ui_kit
    ui_kit.inject_theme()
    ui_kit.hero(...)

كل الدوال تُرجع None وتكتب مباشرة عبر st.markdown، عدا style_chart التي تُعيد الشكل.
"""

from __future__ import annotations

from contextlib import contextmanager

import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------
# رموز اللون (Design Tokens)
# ----------------------------------------------------------------------
INK_900 = "#042019"   # خلفية المشهد الافتتاحي
INK_800 = "#0A3329"
INK_700 = "#0E4A3C"
PRIMARY = "#0E6E5C"
PRIMARY_BRIGHT = "#22B58C"   # نسخة عالية التباين فوق الداكن
ACCENT = "#D9AE4E"
DANGER = "#C2392F"
DANGER_BRIGHT = "#F2705F"
INK = "#16302B"
MUTED = "#5E736D"
LINE = "#E4EBE8"
SURFACE = "#FFFFFF"
CANVAS = "#F7FAF9"

COLORWAY = [PRIMARY, ACCENT, "#2E86AB", DANGER, "#8E6C8A", "#5B8C5A"]
FONT_STACK = "'IBM Plex Sans Arabic', -apple-system, BlinkMacSystemFont, 'Segoe UI', Tahoma, sans-serif"


def inject_theme() -> None:
    """يحقن الخط ورموز اللون وكل أنماط المكوّنات. يُستدعى مرة واحدة بعد set_page_config."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# المكوّنات
# ----------------------------------------------------------------------
def hero(title: str, subtitle: str, chips: list[tuple[str, str]] | None = None,
         image_url: str | None = None, footnote: str = "") -> None:
    """المشهد الافتتاحي كامل العرض: عنوان ضخم فوق خلفية داكنة، مع رقائق مؤشرات حيّة.

    chips: قائمة (التسمية، القيمة) تظهر أسفل العنوان.
    image_url: صورة اختيارية تُوضع تحت التدرج اللوني (بغداد، البصرة، حقل نفطي...).
    footnote: سطر صغير تحت الرقائق، مثل حالة الاتصال بمصدر الأسعار.
    """
    layer = f"url('{image_url}')" if image_url else "none"
    chips_html = ""
    if chips:
        cells = "".join(
            f'<div class="hero-chip"><span class="hero-chip-label">{label}</span>'
            f'<span class="hero-chip-value">{value}</span></div>'
            for label, value in chips
        )
        chips_html = f'<div class="hero-chips">{cells}</div>'
    foot_html = f'<div class="hero-footnote">{footnote}</div>' if footnote else ""

    st.markdown(
        f"""
        <section class="hero" style="--hero-image: {layer};">
          <div class="hero-inner">
            <div class="hero-eyebrow">منصّة بيانات مالية مفتوحة</div>
            <h1 class="hero-title">{title}</h1>
            <p class="hero-subtitle">{subtitle}</p>
            {chips_html}
            {foot_html}
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section(eyebrow: str, title: str, description: str = "") -> None:
    """ترويسة قسم: تسمية صغيرة فوق عنوان كبير، مع شرح اختياري."""
    desc = f'<p class="section-desc">{description}</p>' if description else ""
    st.markdown(
        f"""
        <div class="section-head">
          <div class="section-eyebrow">{eyebrow}</div>
          <h2 class="section-title">{title}</h2>
          {desc}
        </div>
        """,
        unsafe_allow_html=True,
    )


def stat_strip(items: list[dict]) -> None:
    """شريط المؤشرات بأسلوب DataSaudi: رقم ضخم، فترة صغيرة، تسمية بأحرف متباعدة.

    كل عنصر: {"value": str, "period": str, "label": str, "tone": "pos"|"neg"|""}
    """
    cells = []
    for it in items:
        tone = it.get("tone", "")
        cells.append(
            f'<div class="stat">'
            f'<div class="stat-value {tone}">{it["value"]}</div>'
            f'<div class="stat-period">{it.get("period", "")}</div>'
            f'<div class="stat-label">{it["label"]}</div>'
            f"</div>"
        )
    st.markdown(f'<div class="stat-strip">{"".join(cells)}</div>', unsafe_allow_html=True)


def narrative(text: str) -> None:
    """فقرة سردية مولّدة آلياً تشرح ما يعرضه الرسم بلغة طبيعية."""
    st.markdown(f'<p class="narrative">{text}</p>', unsafe_allow_html=True)


def note(text: str, kind: str = "note") -> None:
    """ملاحظة منهجية أو تحذير. kind: note | warn."""
    st.markdown(f'<div class="note {kind}">{text}</div>', unsafe_allow_html=True)


@contextmanager
def card(title: str = ""):
    """بطاقة بيضاء تلتفّ حول محتواها.

    تُستخدم كسياق، لأن Streamlit يغلق أي وسم HTML مفتوح في st.markdown تلقائياً
    فلا ينفع فتح <div> وإغلاقه في استدعاءين منفصلين:

        with ui.card("الرصيد مقابل سعر النفط"):
            st.plotly_chart(...)
    """
    box = st.container(border=True)
    with box:
        if title:
            st.markdown(f'<div class="card-head"><h3 class="card-title">{title}</h3></div>',
                        unsafe_allow_html=True)
        yield box


# ----------------------------------------------------------------------
# الرسوم البيانية
# ----------------------------------------------------------------------
# أنواع لا تملك محاور ديكارتية، فلا تُطبَّق عليها إعدادات المحاور
_NON_CARTESIAN = {"pie", "sankey", "indicator", "treemap", "sunburst", "funnelarea"}
# أنواع ديكارتية لكن التلميح الموحّد يشوّهها
_NO_UNIFIED = {"heatmap", "contour", "box", "violin", "histogram2d", "histogram2dcontour"}


def style_chart(fig: go.Figure, height: int = 380, show_legend: bool = True,
                y_title: str = "", percent: bool = False) -> go.Figure:
    """يجرّد الرسم من الزخرفة الزائدة: بلا إطار، شبكة أفقية خفيفة فقط، تلميح موحّد.

    يتعرّف على نوع الرسم: الدوائر والسانكي والعدادات لا تُمسّ محاورها،
    والخرائط الحرارية والصناديق تحتفظ بتلميحها الافتراضي.
    """
    kinds = {getattr(tr, "type", "") for tr in fig.data}
    cartesian = not (kinds & _NON_CARTESIAN)
    unified = cartesian and not (kinds & _NO_UNIFIED)
    dense = bool(kinds & {"heatmap", "contour", "histogram2d"})

    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY,
        font=dict(family=FONT_STACK, size=13, color=INK),
        title=dict(text=""),   # None يجعل Plotly يرسم كلمة undefined مكان العنوان
        hovermode="x unified" if unified else "closest",
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor=LINE,
            font=dict(family=FONT_STACK, size=13, color=INK),
        ),
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.0,
            x=1.0,
            xanchor="right",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color=MUTED),
            itemclick="toggleothers",
        ),
    )
    if cartesian:
        fig.update_xaxes(
            showgrid=False,
            zeroline=False,
            showline=True,
            linecolor=LINE,
            linewidth=1,
            ticks="outside",
            ticklen=4,
            tickcolor=LINE,
            tickfont=dict(size=12, color=MUTED),
        )
        fig.update_yaxes(
            showgrid=not dense,
            gridcolor="#EFF4F2",
            gridwidth=1,
            zeroline=not dense,
            zerolinecolor="#D5E0DC",
            zerolinewidth=1,
            showline=False,
            title=dict(text=y_title, font=dict(size=12, color=MUTED)),
            tickfont=dict(size=12, color=MUTED),
            ticksuffix="%" if percent else "",
        )
    return fig


def sparkline(values, color: str = PRIMARY, height: int = 44) -> go.Figure:
    """خط مصغّر بلا محاور، يوضع داخل بطاقة مؤشر."""
    fig = go.Figure(
        go.Scatter(
            y=list(values),
            mode="lines",
            line=dict(color=color, width=2, shape="spline"),
            fill="tozeroy",
            fillcolor=_alpha(color, 0.10),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
    )
    return fig


def _alpha(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ----------------------------------------------------------------------
# الأنماط
# ----------------------------------------------------------------------
_THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap');

:root {{
  --ink: {INK};
  --muted: {MUTED};
  --line: {LINE};
  --primary: {PRIMARY};
  --accent: {ACCENT};
  --danger: {DANGER};
  --surface: {SURFACE};
  --radius: 16px;
  --shadow-sm: 0 1px 2px rgba(6, 38, 31, .04), 0 1px 3px rgba(6, 38, 31, .05);
  --shadow-md: 0 4px 12px rgba(6, 38, 31, .06), 0 12px 32px rgba(6, 38, 31, .05);
}}

html, body, .stApp, [data-testid="stAppViewContainer"],
.stMarkdown, p, span, h1, h2, h3, h4, h5, h6, label, div[data-testid="stCaptionContainer"] {{
  direction: rtl;
  text-align: right;
  font-family: {FONT_STACK};
  -webkit-font-smoothing: antialiased;
}}
[dir="ltr"], .ltr {{
  direction: ltr !important;
  unicode-bidi: isolate !important;
  display: inline-block !important;
}}

.stApp {{ background: {CANVAS}; }}
.block-container {{
  max-width: 1280px !important;
  padding-top: 0 !important;
  padding-bottom: 5rem !important;
}}
[data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}

/* ── المشهد الافتتاحي ─────────────────────────────────────── */
/* كامل العرض يعتمد على 50vw، وهو يشمل عرض الشريط الجانبي.
   لذا نبلّط الحواف فقط حين يكون الشريط مطوياً، وإلا احتوينا المشهد بزوايا دائرية
   منعاً لتمرير أفقي ولخروج المشهد أسفل الشريط. */
.hero {{
  position: relative;
  margin-inline: calc(50% - 50vw);
  padding: 92px max(28px, calc(50vw - 640px)) 76px;
  background:
    linear-gradient(105deg, {INK_900} 0%, {INK_800} 45%, {INK_700} 100%),
    var(--hero-image) center/cover no-repeat;
  background-blend-mode: normal, overlay;
  overflow: hidden;
  margin-bottom: 0;
}}
.hero::after {{
  content: "";
  position: absolute;
  inset-block: -40%;
  inset-inline-start: -10%;
  width: 55%;
  background: radial-gradient(closest-side, {_alpha(PRIMARY_BRIGHT, .22)}, transparent 70%);
  pointer-events: none;
}}
.stApp:has(section[data-testid="stSidebar"][aria-expanded="true"]) .hero {{
  margin-inline: 0;
  padding: 72px 48px 60px;
  border-radius: 22px;
}}
section.stMain {{ overflow-x: clip; }}

/* Streamlit يلوّن h1 وp داخل .stMarkdown بلون النص الداكن بخصوصية أعلى من .hero-title،
   فيصير العنوان داكناً على خلفية داكنة. نرفع الخصوصية ونستعمل !important لنصوص المشهد فقط. */
.stMarkdown .hero .hero-title,
.stMarkdown .hero h1 {{
  color: #FFFFFF !important;
  font-size: clamp(32px, 4.2vw, 58px) !important;
  line-height: 1.2 !important;
  padding: 0 !important;
  margin: 0 !important;
}}
[data-testid="stHeadingActionElements"] {{ display: none !important; }}
.stMarkdown .hero .hero-subtitle {{ color: rgba(255,255,255,.88) !important; }}
.stMarkdown .hero .hero-chip-value {{ color: #FFFFFF !important; }}
.stMarkdown .hero .hero-chip-label {{ color: rgba(255,255,255,.78) !important; }}
.stMarkdown .hero .hero-eyebrow {{ color: {PRIMARY_BRIGHT} !important; }}
.stMarkdown .hero .hero-footnote {{ color: rgba(255,255,255,.68) !important; }}

.hero-inner {{ position: relative; z-index: 1; max-width: 760px; }}
.hero-eyebrow {{
  display: inline-block;
  font-size: 14px;
  font-weight: 600;
  color: {PRIMARY_BRIGHT};
  border: 1px solid {_alpha(PRIMARY_BRIGHT, .35)};
  border-radius: 999px;
  padding: 6px 14px;
  margin-bottom: 22px;
}}
.hero-title {{
  margin: 0;
  font-size: clamp(34px, 5vw, 60px);
  font-weight: 700;
  line-height: 1.18;
  color: #FFFFFF;
}}
.hero-subtitle {{
  margin: 18px 0 0;
  font-size: clamp(15px, 1.4vw, 19px);
  line-height: 1.85;
  color: rgba(255,255,255,.88);
  max-width: 58ch;
}}
.hero-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px 44px;
  margin-top: 40px;
  padding-top: 28px;
  border-top: 1px solid rgba(255,255,255,.14);
}}
.hero-chip-label {{
  display: block;
  font-size: 14px;
  color: rgba(255,255,255,.78);
  margin-bottom: 6px;
}}
.hero-chip-value {{
  font-size: 22px;
  font-weight: 700;
  color: #FFFFFF;
  font-variant-numeric: tabular-nums;
}}
.hero-footnote {{
  margin-top: 18px;
  font-size: 13px;
  color: rgba(255,255,255,.68);
}}

/* ── ترويسة القسم ─────────────────────────────────────────── */
.section-head {{ margin: 64px 0 24px; }}
.section-eyebrow {{
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  margin-bottom: 10px;
}}
.section-title {{
  margin: 0;
  font-size: clamp(24px, 2.6vw, 34px);
  font-weight: 700;
  color: var(--ink);
  line-height: 1.3;
}}
.section-desc {{
  margin: 12px 0 0;
  font-size: 15px;
  line-height: 1.9;
  color: var(--muted);
  max-width: 68ch;
}}

/* ── شريط المؤشرات ────────────────────────────────────────── */
.stat-strip {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  margin: 28px 0 8px;
}}
.stat {{
  background: var(--surface);
  padding: 26px 22px 22px;
  transition: background .18s ease;
}}
.stat:hover {{ background: #FCFDFD; }}
.stat-value {{
  font-size: clamp(28px, 3vw, 40px);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -.02em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  direction: ltr;
  text-align: right;
}}
.stat-value.pos {{ color: var(--primary); }}
.stat-value.neg {{ color: var(--danger); }}
.stat-period {{
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}}
.stat-label {{
  margin-top: 4px;
  font-size: 14.5px;
  font-weight: 500;
  line-height: 1.6;
  color: var(--ink);
}}

/* ── البطاقات ─────────────────────────────────────────────── */
/* ui.card() يستعمل st.container(border=True)؛ نصمّم غلافه بدل <div> يدوي */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] .card-head),
div[data-testid="stVerticalBlockBorderWrapper"][style*="border"] {{
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: var(--radius) !important;
  padding: 22px 24px !important;
  box-shadow: var(--shadow-sm);
  transition: box-shadow .2s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{ box-shadow: var(--shadow-md); }}
.card-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
}}
.card-title {{
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--ink);
}}

/* ── السرد والملاحظات ─────────────────────────────────────── */
.narrative {{
  font-size: 15.5px;
  line-height: 2.05;
  color: #354943;
  max-width: 76ch;
  margin: 18px 0 0;
}}
.narrative strong {{ color: var(--ink); font-weight: 600; }}
.note {{
  border-inline-start: 3px solid var(--accent);
  background: #FCFAF4;
  padding: 12px 16px;
  border-radius: 0 10px 10px 0;
  font-size: 13px;
  line-height: 1.85;
  color: #5A4A24;
  margin: 18px 0 0;
}}
.note.warn {{
  border-inline-start-color: var(--danger);
  background: #FDF4F2;
  color: #7A2C24;
}}

/* ── التبويبات ────────────────────────────────────────────── */
.stTabs [role="tablist"] {{
  gap: 4px;
  border-bottom: 1px solid var(--line);
  padding: 0;
  margin-bottom: 8px;
  position: sticky;
  top: 3.75rem;
  z-index: 40;
  background: {CANVAS};
}}
.stTabs [role="tab"] {{
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 12px 20px !important;
  min-height: 44px;
  font-size: 14px;
  font-weight: 600;
  color: var(--muted);
  box-shadow: inset 0 -2px 0 transparent;
  transition: color .16s ease, box-shadow .16s ease;
}}
.stTabs [role="tab"]:hover {{ color: var(--ink); }}
.stTabs [aria-selected="true"] {{
  color: var(--primary) !important;
  box-shadow: inset 0 -2px 0 var(--primary);
}}
.stTabs .react-aria-SelectionIndicator {{ display: none; }}
[data-testid="stExpander"] summary {{ min-height: 44px; }}

/* ── الشريط الجانبي ───────────────────────────────────────── */
section[data-testid="stSidebar"] {{
  direction: rtl;
  background: var(--surface);
  border-inline-start: 1px solid var(--line);
}}
section[data-testid="stSidebar"] * {{ text-align: right; font-family: {FONT_STACK}; }}
[data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; direction: ltr; }}
/* أرقام الحدّين الأدنى والأعلى للمنزلقات: الافتراضي 60% شفافية يعطي تبايناً 3.98:1 */
[data-testid="stSliderTickBar"], [data-testid="stSliderTickBar"] * {{ color: var(--muted) !important; }}
/* في RTL يبقى الشريط المطوي عموداً بعرض 1px ويفيض محتواه ظاهراً فوق الصفحة (حرف تحت حرف).
   نخفي المحتوى كلياً عند الطي؛ زر الفتح (stSidebarCollapsedControl) عنصر مستقل لا يتأثر. */
section[data-testid="stSidebar"][aria-expanded="false"],
section[data-testid="stSidebar"][aria-expanded="false"] > div,
section[data-testid="stSidebar"][aria-expanded="false"] * {{
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  overflow: hidden !important;
  pointer-events: none !important;
}}
/* اسم زر الفتح يختلف بين إصدارات Streamlit: القديم stSidebarCollapsedControl والأحدث stExpandSidebarButton */
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stExpandSidebarButton"] {{
  background: #FFFFFF !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  box-shadow: var(--shadow-sm) !important;
  min-width: 44px !important;
  min-height: 44px !important;
  color: var(--primary) !important;
}}
[data-testid="stMainMenuButton"], [data-testid="stBaseButton-header"] {{ min-height: 44px; }}
[data-testid="stSidebarCollapseButton"] button {{ min-width: 44px; min-height: 44px; }}
[data-testid="stSidebarResizeHandle"] {{ display: none !important; }}

/* ── تجاوب ────────────────────────────────────────────────── */
@media (max-width: 860px) {{
  .hero {{ padding: 44px 20px 32px; }}
  .hero-eyebrow {{ margin-bottom: 16px; }}
  .stMarkdown .hero .hero-subtitle {{ font-size: 15px; line-height: 1.8; margin-top: 12px; }}
  .hero-chips {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px 20px;
    margin-top: 24px;
    padding-top: 18px;
  }}
  .hero-chip:last-child {{ grid-column: 1 / -1; }}
  .hero-chip-value {{ font-size: 18px; }}
  .section-head {{ margin: 44px 0 18px; }}
  .stat-strip {{ grid-template-columns: repeat(2, 1fr); }}
  .card {{ padding: 18px 16px; }}
  /* شريط أدوات Plotly (كاميرا/تكبير) يغطي أرقام الرسم على الشاشات الصغيرة ولا فائدة منه باللمس */
  .js-plotly-plot .modebar-container {{ display: none !important; }}
  .stTabs [role="tablist"] {{ overflow-x: auto; flex-wrap: nowrap; }}
  .stTabs [role="tab"] {{ padding: 12px 14px !important; white-space: nowrap; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }}
}}

/* ── بطاقات المؤشرات داخل التبويبات ────────────────────────
   يستعملها kpi_card() في app_ar.py. الترويسة والذيل والرقائق متاحة
   للبطاقات الأغنى ولا يستدعيها kpi_card() الحالي. */
.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 20px;
  min-width: 0;
  box-shadow: var(--shadow-sm);
}}
.kpi-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}}
.kpi-label {{ font-size: 13px; font-weight: 500; color: var(--muted); }}
.kpi-value {{
  font-size: 28px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}}
.kpi-unit {{ font-size: 13px; font-weight: 500; color: var(--muted); }}
.kpi-footer {{ font-size: 13px; color: var(--muted); line-height: 1.7; margin-top: 8px; }}
.kpi-card .sub {{ font-size: 13px; color: var(--muted); line-height: 1.7; margin-top: 8px; }}
.kpi-card .sub.pos {{ color: var(--primary); font-weight: 600; }}
.kpi-card .sub.neg {{ color: var(--danger); font-weight: 600; }}
.kpi-chip {{
  font-size: 12px;
  padding: 2px 9px;
  border-radius: 999px;
  background: #EEF3F1;
  color: #3E504C;
  font-weight: 600;
}}
.kpi-badge {{ font-size: 13px; padding: 3px 11px; border-radius: 999px; font-weight: 600; }}
.kpi-badge.surplus {{ background: #E6F4F1; color: var(--primary); }}
.kpi-badge.deficit {{ background: #FDEEE9; color: var(--danger); }}

.input-origin {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-top: -10px;
  margin-bottom: 2px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}}
.input-origin .origin-badge {{
  border-radius: 6px;
  padding: 1px 7px;
  font-weight: 600;
  background: #EEF2F1;
  color: #435952;
}}
.input-origin.official .origin-badge {{ background: #E6F4EF; color: #0A604B; }}
.input-origin.manual .origin-badge {{ background: #FFF1D6; color: #805200; }}
.input-origin a {{ color: #0A604B; text-decoration: underline; text-underline-offset: 3px; }}

.ticker-change.pos {{ color: {PRIMARY_BRIGHT}; font-weight: 600; }}
.ticker-change.neg {{ color: {DANGER_BRIGHT}; font-weight: 600; }}

@media print {{
  section[data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"] {{ display: none !important; }}
  .block-container {{ max-width: 100% !important; padding: 0 !important; }}
  .card, .stat-strip {{ box-shadow: none !important; page-break-inside: avoid; }}
  .hero {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style>
"""
