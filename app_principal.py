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
import difflib

@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

# Configuración de zona horaria México
mx_tz = pytz.timezone('America/Mexico_City')

@st.cache_data
def load_songs():
    with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)

songs = load_songs()

st.title("🎵 Canción del Día - Phigros")

today = datetime.now(mx_tz).strftime("%Y-%m-%d")
random.seed(today)

# === NUEVO: Seleccionar 2 canciones distintas ===
daily_song = random.choice(songs)
alternative_song = random.choice([s for s in songs if s["title"] != daily_song["title"]])

CANCION_DAILY = daily_song["title"]
CANCION_ALT = alternative_song["title"]

# Guardar backup
with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
    json.dump({"daily": daily_song, "alternative": alternative_song}, f, ensure_ascii=False, indent=2)

st.subheader(f"🎵 Canciones del día {today}")
col1, col2 = st.columns(2)

with col1:
    st.info(f"**Daily**\n**{daily_song['title']}**")
    diff_parts = []
    if daily_song.get("IN"): diff_parts.append(f"IN: {daily_song['IN']}")
    if daily_song.get("AT"): diff_parts.append(f"AT: {daily_song['AT']}")
    st.caption(" - ".join(diff_parts))

with col2:
    st.info(f"**Alternative**\n**{alternative_song['title']}**")
    diff_parts = []
    if alternative_song.get("IN"): diff_parts.append(f"IN: {alternative_song['IN']}")
    if alternative_song.get("AT"): diff_parts.append(f"AT: {alternative_song['AT']}")
    st.caption(" - ".join(diff_parts))

# OCR
@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en'])

reader = inicializar_ocr()

st.title("🏆 Sube tu mejor puntaje")

uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    with st.spinner("Analizando captura..."):
        # === OCR Usuario ===
        box_usuario = (int(ancho * 0.56), int(alto * 0.02), int(ancho * 0.82), int(alto * 0.12))
        img_usuario = np.array(imagen_completa.crop(box_usuario))
        ocr_user = reader.readtext(img_usuario, detail=0)
        usuario_final = " ".join(ocr_user).strip() or "Usuario_Desconocido"

        # === OCR Canción ===
        box_cancion = (int(ancho * 0.05), int(alto * 0.65), int(ancho * 0.40), int(alto * 0.80))
        img_cancion = np.array(imagen_completa.crop(box_cancion))
        ocr_cancion = reader.readtext(img_cancion, detail=0)
        cancion_detectada = " ".join(ocr_cancion).strip()

        # === OCR Score y Accuracy ===
        box_score = (int(ancho * 0.52), int(alto * 0.25), int(ancho * 0.85), int(alto * 0.45))
        img_score = np.array(imagen_completa.crop(box_score))
        ocr_score = reader.readtext(img_score, detail=0)
        score_detectado = 0
        for item in ocr_score:
            nums = re.findall(r'\d+', item)
            if nums:
                score_detectado = int("".join(nums))
                break

        box_acc = (int(ancho * 0.75), int(alto * 0.50), int(ancho * 0.95), int(alto * 0.62))
        img_acc = np.array(imagen_completa.crop(box_acc))
        ocr_acc = reader.readtext(img_acc, detail=0)
        accuracy_detectada = 0.0
        for item in ocr_acc:
            match = re.search(r'(\d+\.\d+)', item)
            if match:
                accuracy_detectada = float(match.group(1))
                break

        # Correcciones de nombres
        corrections = {
            "crafi": "craftyy!", "Evz": "Evanii", "Shadom": "Shadow",
            "3 MathyPop": "MathyPop", ">OMathyPop": "MathyPop"
        }
        usuario_final = corrections.get(usuario_final, usuario_final)

        # === VALIDACIÓN DE CANCIÓN ===
        canciones_validas = {CANCION_DAILY.lower(), CANCION_ALT.lower()}
        cancion_lower = cancion_detectada.lower()
        
        es_daily = any(difflib.SequenceMatcher(None, cancion_lower, title.lower()).ratio() > 0.75 
                      for title in [CANCION_DAILY])
        es_alt = any(difflib.SequenceMatcher(None, cancion_lower, title.lower()).ratio() > 0.75 
                    for title in [CANCION_ALT])

        if not (es_daily or es_alt):
            st.error(f"❌ La canción detectada (**{cancion_detectada}**) no corresponde al Daily ni al Alternative de hoy.")
            st.stop()

        # Determinar cuál es
        if es_daily:
            cancion_objetivo = CANCION_DAILY
            constante_activa = daily_song.get("IN")
            tipo = "Daily"
        else:
            cancion_objetivo = CANCION_ALT
            constante_activa = alternative_song.get("IN")
            tipo = "Alternative"

        st.success(f"✅ Canción detectada: **{cancion_objetivo}** ({tipo})")

        # Mostrar datos
        st.subheader("📝 Datos Extraídos")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usuario", usuario_final)
        col2.metric("Canción", cancion_objetivo)
        col3.metric("Score", f"{score_detectado:,}")
        col4.metric("Acc", f"{accuracy_detectada}%")

        if st.button("Registrar Puntaje"):
            def calcular_rks(acc, const): 
                return round((((acc - 55) / 45) ** 2) * const, 2)
            
            rks = calcular_rks(accuracy_detectada, constante_activa)

            nuevo_score = {
                "usuario": usuario_final,
                "cancion": cancion_objetivo,
                "tipo": tipo,                    # Nuevo campo
                "score": score_detectado,
                "accuracy": accuracy_detectada,
                "rks": rks,
                "fecha": today,
            }
            db.collection("scores").document(f"{usuario_final}_{today}_{tipo}").set(nuevo_score)
            st.success(f"¡Registrado con éxito en **{tipo}**!")
   
#=============================================================================
# 4. RENDERS DE LAS TABLAS DE POSICIONES (Desde Base de Datos)
# =============================================================================
st.write("---")
st.header("📊 Tablas de Clasificación")

# 🔥 LEER DIRECTO DESDE LA BASE DE DATOS DE STREAMLIT
scores_ref = db.collection("scores").stream()
todos_los_scores = [doc.to_dict() for doc in scores_ref]

if todos_los_scores:
    df = pd.DataFrame(todos_los_scores)
    tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
    
    with tab_diaria:
        # Filtrar por fecha y canción, ordenar de mayor a menor y conservar solo el mejor por usuario
        df_hoy = df[(df["fecha"] == today) & (df["cancion"] == cancion_objetivo)]
        df_hoy = df_hoy.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario"], keep="first")
        if not df_hoy.empty:
            st.subheader(f"Top del Día - {CANCION_DAILY}")
            st.dataframe(df_hoy[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
        else:
            st.info("Aún no hay scores subidos para el desafío de hoy.")
            
    with tab_general:
        st.subheader("Tabla Global Histórica (RKS Acumulado)")
        
        # Lógica de acumulación por canciones distintas
        df_mejores_por_cancion = df.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario", "cancion"], keep="first")
        
        df_acumulado = df_mejores_por_cancion.groupby("usuario").agg(
            RKS_Total=("rks", "sum"),
            Canciones_Jugadas=("cancion", "count")
        ).reset_index()
        
        df_acumulado["RKS_Total"] = df_acumulado["RKS_Total"].round(4)
        df_acumulado = df_acumulado.sort_values(by="RKS_Total", ascending=False)
        
        if not df_acumulado.empty:
            st.dataframe(df_acumulado[["usuario", "RKS_Total", "Canciones_Jugadas"]], use_container_width=True)
        else:
            st.info("No hay datos suficientes para calcular la tabla global.")
else:
    st.info("No se ha creado ningún registro histórico en el servidor.")
