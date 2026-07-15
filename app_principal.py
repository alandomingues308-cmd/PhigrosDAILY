import os
import re
import numpy as np
import pandas as pd
import streamlit as st
import easyocr
from PIL import Image
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
import pytz
import random
import json

# ====================== CONFIGURACIÓN ======================
st.set_page_config(page_title="Daily Challenge", layout="wide")

@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()
mx_tz = pytz.timezone('America/Mexico_City')

# ====================== SIDEBAR ======================
st.sidebar.title("👤 Gestión de Usuario")
rename_status = st.sidebar.empty()

with st.sidebar.expander("🔄 Renombrar Usuario", expanded=False):
    old_user = st.text_input("Usuario Antiguo", placeholder="Nombre anterior", key="old")
    new_user = st.text_input("Usuario Nuevo", placeholder="Nombre nuevo", key="new")
    
    if st.button("🔄 Cambiar Nombre", type="primary"):
        if old_user and new_user and old_user != new_user:
            with st.spinner("Actualizando registros..."):
                updated = 0
                docs = list(db.collection("scores").where("usuario", "==", old_user).stream())
                for doc in docs:
                    data = doc.to_dict()
                    data["usuario"] = new_user
                    new_id = doc.id.replace(old_user, new_user, 1)
                    db.collection("scores").document(new_id).set(data)
                    db.collection("scores").document(doc.id).delete()
                    updated += 1
                if updated > 0:
                    rename_status.success(f"✅ {updated} registros cambiados")
                else:
                    rename_status.warning("No se encontraron registros")

# ====================== OCR ======================
@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en'])

reader = inicializar_ocr()

# ====================== FUNCIONES ======================
def detectar_phigros(ocr_list):
    texto = " ".join(ocr_list).upper()
    return "AT" if "AT" in texto else "IN"

def detectar_arcaea(ocr_list):
    texto = " ".join(ocr_list).upper()
    if "BYD" in texto or "BEYOND" in texto:
        return "BYD"
    elif "ETR" in texto or "ETERNAL" in texto:
        return "ETR"
    return "FTR"

def calcular_modificador_arcaea(score):
    if score >= 10000000:
        return 2.0
    elif score >= 9800000:
        return 1.0 + (score - 9800000) / 200000
    else:
        return max((score - 9500000) / 300000, -3.0)  # límite inferior aproximado

# ====================== PHIGROS ======================
tab_phigros, tab_arcaea = st.tabs(["🎵 Phigros", "🌊 Arcaea"])

with tab_phigros:
    st.title(f"🎵 Canción del Día {datetime.now(mx_tz).strftime('%Y-%m-%d')} - Phigros")

    @st.cache_data
    def load_phigros_songs():
        with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
            return json.load(f)

    songs = load_phigros_songs()
    today = datetime.now(mx_tz).strftime("%Y-%m-%d")
    random.seed(today)

    daily_song = random.choice(songs)
    alt_song = random.choice([s for s in songs if s["title"] != daily_song["title"]])

    st.success(f"{daily_song['title']}")
    st.info(f"**Alternativa:** {alt_song['title']}")

    usuario = st.text_input("Coloca tu usuario", placeholder="Tu nombre", key="ph_user")

    uploaded = st.file_uploader("Sube captura de Phigros", type=["png", "jpg", "jpeg"], key="ph_upload")

    if uploaded and usuario.strip():
        img = Image.open(uploaded)
        w, h = img.size
        
        with st.spinner("Analizando..."):
            # Score
            box_score = (int(w * 0.52), int(h * 0.25), int(w * 0.85), int(h * 0.45))
            ocr_score = reader.readtext(np.array(img.crop(box_score)), detail=0)
            score = 0
            for item in ocr_score:
                nums = re.findall(r'\d+', item)
                if nums:
                    score = int("".join(nums))
                    break

            # Accuracy
            box_acc = (int(w * 0.75), int(h * 0.50), int(w * 0.95), int(h * 0.62))
            ocr_acc = reader.readtext(np.array(img.crop(box_acc)), detail=0)
            acc = 0.0
            for item in ocr_acc:
                m = re.search(r'(\d+\.\d+)', item)
                if m:
                    acc = float(m.group(1))
                    break

            if score in (10000, 100000):
                score = 1000000
            if score == 1000000:
                acc = 100.0

            dificultad = detectar_phigros(ocr_score + ocr_acc)
            const = daily_song.get(dificultad, daily_song.get("IN", 0))
            potencial = round((((acc - 55) / 45) ** 2) * const, 2)

            st.subheader("📝 Datos Extraídos")
            col1, col2, col3 = st.columns(3)
            col1.metric("Usuario", usuario)
            col2.metric("Score", f"{score:,}")
            col3.metric("Acc", f"{acc}%")
            st.info(f"Dificultad detectada: **{dificultad}**")

            opcion = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True, key="ph_op")

            if st.button("Registrar Puntaje", type="primary", key="btn_ph"):
                cancion = daily_song["title"] if opcion == "Daily" else alt_song["title"]
                data = {
                    "usuario": usuario, "cancion": cancion, "tipo": opcion,
                    "score": score, "accuracy": acc, "potencial": potencial,
                    "fecha": today, "timestamp": datetime.now(mx_tz).isoformat(),
                    "juego": "Phigros", "dificultad": dificultad
                }
                db.collection("scores").document(f"{usuario}_{today}_{opcion}_ph").set(data)
                st.success(f"✅ ¡Registrado en {opcion}!")
                st.balloons()

    # ==================== TABLAS PHIGROS ====================
    st.write("---")
    st.header("📊 Clasificación - Phigros")
    all_scores = [doc.to_dict() for doc in db.collection("scores").stream() if doc.to_dict().get("juego") == "Phigros"]

    if all_scores:
        df = pd.DataFrame(all_scores)
        tab1, tab2 = st.tabs(["📅 Hoy", "🌍 General"])

        with tab1:
            df_hoy = df[df["fecha"] == today]
            for song, label in [(daily_song["title"], "🏆 Daily"), (alt_song["title"], "🥈 Alternative")]:
                temp = df_hoy[df_hoy["cancion"] == song]
                if not temp.empty:
                    temp = temp.sort_values("potencial", ascending=False).drop_duplicates("usuario")
                    st.markdown(f"### {label}")
                    st.dataframe(temp[["usuario", "score", "accuracy", "potencial", "dificultad"]], use_container_width=True)

        with tab2:
            best = df.sort_values(['usuario','fecha','potencial'], ascending=[True,True,False]).drop_duplicates(['usuario','fecha'])
            acum = best.groupby("usuario").agg(Potencial_Total=("potencial","sum"), Canciones=("potencial","count")).reset_index()
            acum["Potencial_Total"] = acum["Potencial_Total"].round(2)
            st.dataframe(acum.sort_values("Potencial_Total", ascending=False), use_container_width=True, hide_index=True)

# ====================== ARCAEA ======================
with tab_arcaea:
    st.title(f"🌊 Canción del Día {datetime.now(mx_tz).strftime('%Y-%m-%d')} - Arcaea")

    @st.cache_data
    def load_arcaea_songs():
        with open("arcaea_songs.json", "r", encoding="utf-8-sig") as f:
            return json.load(f)

    songs_a = load_arcaea_songs()
    random.seed(today)
    daily_a = random.choice(songs_a)
    alt_a = random.choice([s for s in songs_a if s["title"] != daily_a["title"]])

    st.success(f"{daily_a['title']}")
    st.info(f"**Alternativa:** {alt_a['title']}")

    usuario_a = st.text_input("Coloca tu usuario", placeholder="Tu nombre", key="ar_user")

    uploaded_a = st.file_uploader("Sube captura de Arcaea", type=["png", "jpg", "jpeg"], key="ar_upload")

    if uploaded_a and usuario_a.strip():
        img = Image.open(uploaded_a)
        w, h = img.size
        
        with st.spinner("Analizando Arcaea..."):
            box = (int(w*0.35), int(h*0.22), int(w*0.72), int(h*0.42))
            ocr = reader.readtext(np.array(img.crop(box)), detail=0)
            
            score = 0
            for item in ocr:
                nums = re.findall(r'\d+', item.replace("'", "").replace(",", ""))
                if nums:
                    score = int("".join(nums))
                    break

            diff = detectar_arcaea(ocr)
            const = daily_a.get(diff, daily_a.get("FTR", 0))
            mod = calcular_modificador_arcaea(score)
            potencial = round(const + mod, 2)

            st.subheader("📝 Datos Extraídos")
            col1, col2 = st.columns(2)
            col1.metric("Usuario", usuario_a)
            col2.metric("Score", f"{score:,}")
            st.info(f"Dificultad: **{diff}** | Modificador: **{mod:.2f}**")

            opcion_a = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True, key="ar_op")

            if st.button("Registrar Puntaje", type="primary", key="btn_ar"):
                cancion = daily_a["title"] if opcion_a == "Daily" else alt_a["title"]
                data = {
                    "usuario": usuario_a, "cancion": cancion, "tipo": opcion_a,
                    "score": score, "potencial": potencial, "fecha": today,
                    "timestamp": datetime.now(mx_tz).isoformat(), "juego": "Arcaea",
                    "dificultad": diff
                }
                db.collection("scores").document(f"{usuario_a}_{today}_{opcion_a}_ar").set(data)
                st.success(f"✅ ¡Registrado en {opcion_a}!")
                st.balloons()

    # ==================== TABLAS ARCAEA ====================
    st.write("---")
    st.header("📊 Clasificación - Arcaea")
    all_a = [doc.to_dict() for doc in db.collection("scores").stream() if doc.to_dict().get("juego") == "Arcaea"]

    if all_a:
        df_a = pd.DataFrame(all_a)
        t1, t2 = st.tabs(["📅 Hoy", "🌍 General"])

        with t1:
            hoy_a = df_a[df_a["fecha"] == today]
            for song, label in [(daily_a["title"], "🏆 Daily"), (alt_a["title"], "🥈 Alternative")]:
                temp = hoy_a[hoy_a["cancion"] == song]
                if not temp.empty:
                    temp = temp.sort_values("potencial", ascending=False).drop_duplicates("usuario")
                    st.markdown(f"### {label}")
                    st.dataframe(temp[["usuario", "score", "potencial", "dificultad"]], use_container_width=True)

        with t2:
            best_a = df_a.sort_values(['usuario','fecha','potencial'], ascending=[True,True,False]).drop_duplicates(['usuario','fecha'])
            acum_a = best_a.groupby("usuario").agg(Potencial_Total=("potencial","sum"), Canciones=("potencial","count")).reset_index()
            acum_a["Potencial_Total"] = acum_a["Potencial_Total"].round(2)
            st.dataframe(acum_a.sort_values("Potencial_Total", ascending=False), use_container_width=True, hide_index=True)
