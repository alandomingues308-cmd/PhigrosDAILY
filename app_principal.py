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

@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

mx_tz = pytz.timezone('America/Mexico_City')

@st.cache_data
def load_songs():
    with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)

songs = load_songs()

today = datetime.now(mx_tz).strftime("%Y-%m-%d")
random.seed(today)
st.title(f"🎵 Canción del Día {today} - Phigros")

# Selección de dos canciones
daily_song = random.choice(songs)
alternative_song = random.choice([s for s in songs if s["title"] != daily_song["title"]])

CANCION_DAILY = daily_song["title"]
CANCION_ALT = alternative_song["title"]

with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
    json.dump({"daily": daily_song, "alternative": alternative_song}, f, ensure_ascii=False, indent=2)


st.info(f"**Daily: **\n**{CANCION_DAILY} ({daily_song["IN"]})**")
st.subheader(f"🎵 Cancion Alternativa {today}")
st.info(f"**Alternative: **\n**{CANCION_ALT} ({alternative_song["IN"]})**")

@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en'])

reader = inicializar_ocr()

st.title("🏆 Sube tu mejor puntaje")

# ==================== SUBIDA DE IMAGEN ====================
uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", 
                                type=["png", "jpg", "jpeg"], 
                                help="Captura de resultados de Phigros")

if uploaded_file is not None:
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    with st.spinner("Analizando captura..."):
        # OCR Usuario
        box_usuario = (int(ancho * 0.56), int(alto * 0.02), int(ancho * 0.82), int(alto * 0.12))
        img_usuario = np.array(imagen_completa.crop(box_usuario))
        ocr_user = reader.readtext(img_usuario, detail=0)
        usuario_final = " ".join(ocr_user).strip() or "Usuario_Desconocido"

        # OCR Score
        box_score = (int(ancho * 0.52), int(alto * 0.25), int(ancho * 0.85), int(alto * 0.45))
        img_score = np.array(imagen_completa.crop(box_score))
        ocr_score = reader.readtext(img_score, detail=0)
        score_detectado = 0
        for item in ocr_score:
            nums = re.findall(r'\d+', item)
            if nums:
                score_detectado = int("".join(nums))
                break

        # OCR Accuracy
        box_acc = (int(ancho * 0.75), int(alto * 0.50), int(ancho * 0.95), int(alto * 0.62))
        img_acc = np.array(imagen_completa.crop(box_acc))
        ocr_acc = reader.readtext(img_acc, detail=0)
        accuracy_detectada = 0.0
        for item in ocr_acc:
            match = re.search(r'(\d+\.\d+)', item)
            if match:
                accuracy_detectada = float(match.group(1))
                break

        # Correcciones comunes
        corrections = {"crafi": "craftyy!", "Evz": "Evanii", "Shadom": "Shadow",
                       "3 MathyPop": "MathyPop", ">OMathyPop": "MathyPop"}
        usuario_final = corrections.get(usuario_final, usuario_final)

        st.subheader("📝 Datos Extraídos")
        col1, col2, col3 = st.columns(3)
        col1.metric("Usuario", usuario_final)
        col2.metric("Score", f"{score_detectado:,}")
        col3.metric("Acc", f"{accuracy_detectada}%")

        # Selección manual
        st.subheader("¿De qué canción es esta captura?")
        opcion = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True, key="tipo_cancion")

        if st.button("Registrar Puntaje", type="primary"):
            if opcion == "Daily":
                cancion_objetivo = CANCION_DAILY
                constante_activa = daily_song.get("IN")
                tipo = "Daily"
            else:
                cancion_objetivo = CANCION_ALT
                constante_activa = alternative_song.get("IN")
                tipo = "Alternative"

            def calcular_rks(acc, const): 
                return round((((acc - 55) / 45) ** 2) * const, 2)
            
            rks = calcular_rks(accuracy_detectada, constante_activa)

            nuevo_score = {
                "usuario": usuario_final,
                "cancion": cancion_objetivo,
                "tipo": tipo,
                "score": score_detectado,
                "accuracy": accuracy_detectada,
                "rks": rks,
                "fecha": today,
            }
            
            db.collection("scores").document(f"{usuario_final}_{today}_{tipo}").set(nuevo_score)
            st.success(f"✅ ¡Registrado correctamente en **{tipo}**!")
            st.balloons()

# ==================== TABLAS DE CLASIFICACIÓN ====================
st.write("---")
st.header("📊 Tablas de Clasificación")

scores_ref = db.collection("scores").stream()
todos_los_scores = [doc.to_dict() for doc in scores_ref]

if todos_los_scores:
    df = pd.DataFrame(todos_los_scores)
    tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
    
    with tab_diaria:
        st.subheader(f"Desafío del Día - {today}")
        df_hoy = df[df["fecha"] == today].copy()
        
        if not df_hoy.empty:
            # Top Daily
            df_daily = df_hoy[df_hoy["cancion"] == CANCION_DAILY]
            df_daily = df_daily.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario"], keep="first")
            st.markdown("### 🏆 Top Daily")
            if not df_daily.empty:
                st.dataframe(df_daily[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
            else:
                st.info("Aún no hay scores para el Daily.")

            st.markdown("---")

            # Top Alternative
            df_alt = df_hoy[df_hoy["cancion"] == CANCION_ALT]
            df_alt = df_alt.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario"], keep="first")
            st.markdown("### 🥈 Top Alternative")
            if not df_alt.empty:
                st.dataframe(df_alt[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
            else:
                st.info("Aún no hay scores para el Alternative.")
        else:
            st.info("Aún no hay scores subidos hoy.")

    with tab_general:
        st.subheader("Tabla Global Histórica (Mejor por día)")
        df_hoy_max = df[df["fecha"] == today]
        if not df_hoy_max.empty:
            df_best_per_day = df_hoy_max.loc[df_hoy_max.groupby("usuario")["rks"].idxmax()]
        else:
            df_best_per_day = pd.DataFrame()

        df_historico = df[df["fecha"] != today]
        df_all = pd.concat([df_historico, df_best_per_day]) if not df_best_per_day.empty else df_historico

        df_mejores = df_all.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario", "cancion"], keep="first")
        
        df_acumulado = df_mejores.groupby("usuario").agg(
            RKS_Total=("rks", "sum"),
            Canciones_Jugadas=("cancion", "count")
        ).reset_index()
        
        df_acumulado["RKS_Total"] = df_acumulado["RKS_Total"].round(4)
        df_acumulado = df_acumulado.sort_values(by="RKS_Total", ascending=False)
        
        if not df_acumulado.empty:
            st.dataframe(df_acumulado[["usuario", "RKS_Total", "Canciones_Jugadas"]], use_container_width=True)
            st.caption("Solo se cuenta la mejor canción (Daily o Alternative) por día.")
        else:
            st.info("No hay datos aún.")
else:
    st.info("No hay registros todavía.")
