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
daily_song = random.choice(songs)
CANCION_DAILY = daily_song["title"]

with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
    json.dump(daily_song, f, ensure_ascii=False, indent=2)

st.subheader(f"La canción elegida para hoy, {today}, es:")
diff_parts = []
if daily_song.get("IN") is not None: diff_parts.append(f"IN: {daily_song['IN']}")
if daily_song.get("AT") is not None: diff_parts.append(f"AT: {daily_song['AT']}")
diff_string = " - ".join(diff_parts)

@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en']) # 'en' suele ser suficiente para nombres de usuario

reader = inicializar_ocr()

# Variables de estado
cancion_objetivo = daily_song["title"]

st.title("🏆 Sube tu mejor puntaje")

uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    with st.spinner("Analizando captura..."):
        # 📌 2.5. Área de la Dificultad
        # Ajustado según la posición en la imagen (esquina inferior derecha de la tarjeta)
        box_diff = (int(ancho * 0.35), int(alto * 0.75), int(ancho * 0.45), int(alto * 0.82))
        img_diff = np.array(imagen_completa.crop(box_diff))
        ocr_diff = reader.readtext(img_diff, detail=0)
        diff_detectada = " ".join(ocr_diff).upper()
        
        # Determinar qué constante usar basándonos en lo que detectó el OCR
        if "AT" in diff_detectada and daily_song.get("AT") is not None:
               constante_activa = daily_song["AT"]
               dificultad_usada = "AT"
        else:
            # Por defecto, o si detecta IN, usa la constante de IN
                constante_activa = daily_song.get("IN", 0)
                dificultad_usada = "IN"
            
        st.info(f"Dificultad detectada: {dificultad_usada}")
                
        # 📌 1. Área del Usuario (Esquina superior derecha)
        box_usuario = (int(ancho * 0.56), int(alto * 0.02), int(ancho * 0.82), int(alto * 0.12))
        img_usuario = np.array(imagen_completa.crop(box_usuario))
        ocr_user = reader.readtext(img_usuario, detail=0)
        usuario_final = " ".join(ocr_user).strip() if ocr_user else "Usuario_Desconocido"
        
        # 📌 2. Área de la Canción (Esquina inferior izquierda)
        box_cancion = (int(ancho * 0.05), int(alto * 0.65), int(ancho * 0.40), int(alto * 0.80))
        img_cancion = np.array(imagen_completa.crop(box_cancion))
        ocr_cancion = reader.readtext(img_cancion, detail=0)
        
        # 📌 3. Área del Score (Centro derecho superior)
        box_score = (int(ancho * 0.52), int(alto * 0.25), int(ancho * 0.85), int(alto * 0.45))
        img_score = np.array(imagen_completa.crop(box_score))
        ocr_score = reader.readtext(img_score, detail=0)
        score_detectado = 0
        for item in ocr_score:
            nums = re.findall(r'\d+', item)
            if nums:
                score_detectado = int("".join(nums))
                break
                
        # 📌 4. Área de la Accuracy (Centro derecho medio)
        box_acc = (int(ancho * 0.75), int(alto * 0.50), int(ancho * 0.95), int(alto * 0.62))
        img_acc = np.array(imagen_completa.crop(box_acc))
        ocr_acc = reader.readtext(img_acc, detail=0)
        accuracy_detectada = 0.0
        for item in ocr_acc:
            match = re.search(r'(\d+\.\d+)', item)
            if match:
                accuracy_detectada = float(match.group(1))
                break
                
        #Los que se leyeron mal
        if usuario_final== "crafi": usuario_final= "craftyy!"
        if usuario_final== "Evz": usuario_final= "Evanii"
        if usuario_final== "Shadom": usuario_final= "Shadow"
        if usuario_final== "3 MathyPop": usuario_final= "MathyPop"
        if usuario_final== ">OMathyPop": usuario_final= "MathyPop"
        if usuario_final== "MalenaF": usuario_final= "MalenaPop"
        if usuario_final== "5 MathyPop": usuario_final= "MathyPop"
        st.session_state.usuario= usuario_final
        
        def actualizar_nombre():
            st.session_state.usuario = st.session_state.input_key
            st.rerun()
    
        # UI de confirmación
        st.subheader("📝 Datos Extraídos")
        col1, col2, col3 = st.columns(3)
        col1.metric("Usuario", st.session_state.usuario)
        col2.metric("Score", f"{score_detectado:,}")
        col3.metric("Acc", f"{accuracy_detectada}%")
        
        st.text_input(
            "¿Usuario incorrecto?, cámbialo aquí:", 
            key="input_key", 
            on_change=actualizar_nombre
            )
    
        if st.button("Registrar Puntaje"):
        # Lógica de cálculo (reutilizando tus funciones previas)
            def calcular_rks(acc, const): return round((((acc - 55) / 45) ** 2) * const, 2)
        rks= calcular_rks(accuracy_detectada, constante_activa)
        
        rks_final=rks
    
        nuevo_score = {
            "usuario": st.session_state.usuario,
             "cancion": cancion_objetivo,
             "score": score_detectado,
             "accuracy": accuracy_detectada,
             "rks": rks_final,
             "fecha": today,
        }
        db.collection("scores").document(f"{usuario_final}_{today}").set(nuevo_score)
        st.success("¡Registrado con éxito!")
    

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
