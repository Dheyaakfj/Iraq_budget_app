import streamlit as st
import matplotlib.pyplot as plt

# دعم العربية داخل الرسوم فقط
import arabic_reshaper
from bidi.algorithm import get_display

from scenario_engine_ar import مدخلات, تشغيل_السيناريو, حفظ_النتائج

# دالة لإعادة تشكيل العربية (للرسوم فقط)
def ar(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return get_display(arabic_reshaper.reshape(text))

# اختر خطاً يدعم العربية للرسوم
for fontname in ["Segoe UI", "Arial", "Tahoma", "Noto Naskh Arabic", "Amiri", "DejaVu Sans"]:
    try:
        plt.rcParams["font.family"] = fontname
        break
    except Exception:
        continue

st.set_page_config(page_title="تحليل سيناريو الموازنة العراقية", layout="wide")

# اجعل واجهة ستريملت RTL بدون إعادة تشكيل الحروف
st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; font-family: "Segoe UI","Tahoma","Arial",sans-serif; }
</style>
""", unsafe_allow_html=True)

# عناوين الواجهة (بدون ar())
st.title("تحليل سيناريو الموازنة العراقية حسب أسعار النفط")
st.caption("منهجية الصفحات 12–22، مع قاعدة: الفائض يذهب للاحتياطيات")

with st.sidebar:
    st.header("المدخلات")
    اسعار = st.multiselect("أسعار النفط (دولار/برميل)",
                            [50, 55, 58.5, 60, 62, 65, 67, 70, 72, 75, 80, 90, 100, 110, 120],
                            default=[60, 70, 90, 110])
    صادرات = st.number_input("حجم الصادرات (مليون برميل/يوم)", value=4.1, step=0.1)
    محلي = st.number_input("الاستهلاك المحلي (مليون برميل/يوم)", value=0.8, step=0.1)
    حصة = st.slider("حصة الحكومة من الصادرات", 0.0, 1.0, 1.0, 0.05)
    سعر_الصرف = st.number_input("سعر الصرف (دينار/دولار)", value=1300)
    غير_نفطي = st.number_input("الإيرادات غير النفطية (مليار دينار)", value=12000, step=500)
    اجمالي = st.number_input("إجمالي النفقات (مليار دينار)", value=147000, step=1000)
    جاري = st.number_input("النفقات الجارية (مليار دينار)", value=120000, step=1000)
    استخدم_الاجمالي = st.toggle("استخدام الإجمالي بدل الجاري", value=True)
    احتياطي = st.number_input("الاحتياطيات الأجنبية (مليار دينار)", value=132000, step=1000)
    نقد = st.number_input("النقد القاعدي (مليار دينار)", value=104000, step=1000)
    نسبة_المركزي = st.slider("نسبة تمويل المركزي للعجز", 0.0, 1.0, 0.3, 0.05)
    نسبة_فائض = st.slider("نسبة الفائض تذهب للاحتياطي", 0.0, 1.0, 0.5, 0.05)

p = مدخلات(
    اسعار_النفط=اسعار,
    حجم_الصادرات_مليون_برميل_يوم=صادرات,
    الاستهلاك_المحلي_مليون_برميل_يوم=محلي,
    حصة_الحكومة_من_الصادرات=حصة,
    ايام_السنة=365,
    سعر_الصرف=سعر_الصرف,
    ايرادات_غير_نفطية_مليار=غير_نفطي,
    اجمالي_النفقات_مليار=اجمالي,
    النفقات_الجارية_مليار=جاري,
    استخدام_الاجمالي=استخدم_الاجمالي,
    الاحتياطيات_الاجنبية_مليار=احتياطي,
    النقد_القاعدي_مليار=نقد,
    نسبة_تمويل_المركزي=نسبة_المركزي,
    نسبة_الفائض_للاحتياطي=نسبة_فائض,
)

df, ملخص = تشغيل_السيناريو(p)

st.subheader("النتائج")
st.dataframe(df, use_container_width=True)

# ثلاث رسومات جنبًا إلى جنب وبأحجام منطقية
col1, col2, col3 = st.columns(3)

with col1:
    fig1 = plt.figure(figsize=(5.5, 4))
    plt.plot(df["سعر النفط (دولار)"], df["الرصيد (مليار دينار)"]/1000.0, marker="o")
    plt.title(ar("الرصيد مقابل سعر النفط (ترليون دينار)"))
    plt.xlabel(ar("سعر النفط (دولار/برميل)"))
    plt.ylabel(ar("ترليون دينار"))
    plt.grid(True)
    plt.tight_layout()
    st.pyplot(fig1)

with col2:
    fig2 = plt.figure(figsize=(5.5, 4))
    plt.plot(df["سعر النفط (دولار)"], df["صافي تغير الاحتياطي (مليار دينار)"]/1000.0, marker="o")
    plt.title(ar("صافي تغير الاحتياطي (ترليون دينار)"))
    plt.xlabel(ar("سعر النفط (دولار/برميل)"))
    plt.ylabel(ar("ترليون دينار"))
    plt.grid(True)
    plt.tight_layout()
    st.pyplot(fig2)

with col3:
    fig3 = plt.figure(figsize=(5.5, 4))
    plt.plot(df["سعر النفط (دولار)"], df["الاحتياطي بعد (مليار دينار)"]/1000.0, marker="o", label=ar("الاحتياطي بعد"))
    plt.plot(df["سعر النفط (دولار)"], df["النقد القاعدي (مليار دينار)"]/1000.0, marker="o", label=ar("النقد القاعدي"))
    plt.plot(df["سعر النفط (دولار)"], df["الفجوة (مليار دينار)"]/1000.0, marker="o", label=ar("الفجوة"))
    plt.title(ar("الاحتياطي، القاعدة النقدية، والفجوة (ترليون دينار)"))
    plt.xlabel(ar("سعر النفط (دولار/برميل)"))
    plt.ylabel(ar("ترليون دينار"))
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    st.pyplot(fig3)

st.subheader("الملخص")
st.json(ملخص)

if st.button("تصدير إلى Excel"):
    حفظ_النتائج(df, ملخص, "output/النتائج.xlsx")
    st.success("تم الحفظ في output/النتائج.xlsx")
