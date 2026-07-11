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

st.title("🎵 Canción del Día - Phigros")

today = datetime.now(mx_tz).strftime("%Y-%m-%d")
random.seed(today)

daily_song = random.choice(songs)
alternative_song = random.choice([s for s in songs if s["title"] != daily_song["title"]])

CANCION_DAILY = daily_song["title"]
CANCION_ALT = alternative_song["title"]

with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
    json.dump({"daily": daily_song, "alternative": alternative_song}, f, ensure_ascii=False, indent=2)

st.subheader(f"🎵 Canciones del día {today}")
col1, col2 = st.columns(2)
with col1:
    st.success(f"**Daily**\n**{CANCION_DAILY}**")
with col2:
    st.info(f"**Alternative**\n**{CANCION_ALT}**")

@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['en'])

reader = inicializar_ocr()

st.title("🏆 Sube tu mejor puntaje")

uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", 
                                type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    with st.spinner("Analizando captura..."):
        # OCR Usuario
        box_usuario = (int(ancho * 0.56), int(alto * 0.02), int(ancho * 0.82), int(alto * 0.12))
        img_usuario = np.array(imagen_completa.crop(box_usuario))
        ocr_user = reader.readtext(img_usuario, detail=0)
        usuario_detectado = " ".join(ocr_user).strip() or "Usuario_Desconocido"

        # Correcciones automáticas
        corrections = {"crafi": "craftyy!", "Evz": "Evanii", "Shadom": "Shadow",
                       "3 MathyPop": "MathyPop", ">OMathyPop": "MathyPop"}
        usuario_detectado = corrections.get(usuario_detectado, usuario_detectado)

        # OCR Score y Accuracy
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

        st.subheader("📝 Datos Extraídos")
        col1, col2, col3 = st.columns(3)
        col1.metric("Usuario (detectado)", usuario_detectado)
        col2.metric("Score", f"{score_detectado:,}")
        col3.metric("Acc", f"{accuracy_detectada}%")

        # === Editar Usuario ===
        st.subheader("✏️ Corregir Nombre de Usuario")
        usuario_final = st.text_input("Nombre de usuario:", value=usuario_detectado, key="user_edit")

        # Selección de canción
        st.subheader("¿De qué canción es esta captura?")
        opcion = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True)

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
                "usuario": usuario_final.strip(),
                "cancion": cancion_objetivo,
                "tipo": tipo,
                "score": score_detectado,
                "accuracy": accuracy_detectada,
                "rks": rks,
                "fecha": today,
            }
            
            db.collection("scores").document(f"{usuario_final.strip()}_{today}_{tipo}").set(nuevo_score)
            st.success(f"✅ ¡Registrado correctamente en **{tipo}** con usuario **{usuario_final}**!")
            st.balloons()
