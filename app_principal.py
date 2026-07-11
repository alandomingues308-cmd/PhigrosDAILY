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
import gc  # Necesario para liberar memoria

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
daily_song = random.choice(songs)
CANCION_DAILY = daily_song["title"]

# Optimización: Solo guardar backup si es necesario, se puede limitar la frecuencia
with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
    json.dump(daily_song, f, ensure_ascii=False, indent=2)

st.subheader(f"La canción elegida para hoy, {today}, es:")
diff_parts = []
if daily_song.get("IN") is not None: diff_parts.append(f"IN: {daily_song['IN']}")
if daily_song.get("AT") is not None: diff_parts.append(f"AT: {daily_song['AT']}")
diff_string = " - ".join(diff_parts)
st.info(f"👉 **{daily_song['title']} / ({diff_string})**")

@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en'])

reader = inicializar_ocr()

cancion_objetivo = daily_song["title"]
constante_activa = daily_song.get("IN")

st.title("🏆 Sube tu mejor puntaje")
uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", type=["png", "jpg", "jpeg"])

# Botón para disparar el procesamiento y ahorrar RAM
if uploaded_file is not None and st.button("Analizar y Registrar Puntaje"):
    with st.spinner("Analizando captura..."):
        imagen_completa = Image.open(uploaded_file)
        ancho, alto = imagen_completa.size
        
        # 📌 1. Área del Usuario
        box_usuario = (int(ancho * 0.56), int(alto * 0.02), int(ancho * 0.82), int(alto * 0.12))
        img_usuario = np.array(imagen_completa.crop(box_usuario))
        ocr_user = reader.readtext(img_usuario, detail=0)
        usuario_final = " ".join(ocr_user).strip() if ocr_user else "Usuario_Desconocido"
        del img_usuario
        
        # 📌 2. Área de la Canción
        box_cancion = (int(ancho * 0.05), int(alto * 0.65), int(ancho * 0.40), int(alto * 0.80))
        img_cancion = np.array(imagen_completa.crop(box_cancion))
        reader.readtext(img_cancion, detail=0) # OCR de canción
        del img_cancion
        
        # 📌 3. Área del Score
        box_score = (int(ancho * 0.52), int(alto * 0.25), int(ancho * 0.85), int(alto * 0.45))
        img_score = np.array(imagen_completa.crop(box_score))
        ocr_score = reader.readtext(img_score, detail=0)
        score_detectado = 0
        for item in ocr_score:
            nums = re.findall(r'\d+', item)
            if nums:
                score_detectado = int("".join(nums))
                break
        del img_score
                
        # 📌 4. Área de la Accuracy
        box_acc = (int(ancho * 0.75), int(alto * 0.50), int(ancho * 0.95), int(alto * 0.62))
        img_acc = np.array(imagen_completa.crop(box_acc))
        ocr_acc = reader.readtext(img_acc, detail=0)
        accuracy_detectada = 0.0
        for item in ocr_acc:
            match = re.search(r'(\d+\.\d+)', item)
            if match:
                accuracy_detectada = float(match.group(1))
                break
        del img_acc, imagen_completa
        gc.collect() # Forzar limpieza de RAM
        
        # Correcciones
        correcciones = {"crafi": "craftyy!", "Evz": "Evanii", "Shadom": "Shadow", "3 MathyPop": "MathyPop", ">OMathyPop": "MathyPop", "5 MathyPop": "MathyPop", "Sir": "SirNix", "MalenaF": "MalenaPop"}
        usuario_final = correcciones.get(usuario_final, usuario_final)
    
        st.subheader("📝 Datos Extraídos")
        st.metric("Usuario", usuario_final)
        st.metric("Score", f"{score_detectado:,}")
        st.metric("Acc", f"{accuracy_detectada}%")
    
        # Lógica de registro
        def calcular_rks(acc, const): return round((((acc - 55) / 45) ** 2) * const, 2)
        rks_final = calcular_rks(accuracy_detectada, constante_activa)
    
        db.collection("scores").document(f"{usuario_final}_{today}").set({
            "usuario": usuario_final, "cancion": cancion_objetivo, "score": score_detectado,
            "accuracy": accuracy_detectada, "rks": rks_final, "fecha": today,
        })
        st.success("¡Registrado con éxito!")

# Renderear tablas
st.write("---")
st.header("📊 Tablas de Clasificación")
scores_ref = db.collection("scores").stream()
todos_los_scores = [doc.to_dict() for doc in scores_ref]

if todos_los_scores:
    df = pd.DataFrame(todos_los_scores)
    tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
    with tab_diaria:
        df_hoy = df[(df["fecha"] == today) & (df["cancion"] == cancion_objetivo)].sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario"], keep="first")
        if not df_hoy.empty: st.dataframe(df_hoy[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
        else: st.info("Aún no hay scores subidos para el desafío de hoy.")
    with tab_general:
        df_acumulado = df.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario", "cancion"], keep="first").groupby("usuario").agg(RKS_Total=("rks", "sum"), Canciones_Jugadas=("cancion", "count")).reset_index().sort_values(by="RKS_Total", ascending=False)
        st.dataframe(df_acumulado, use_container_width=True)
    
