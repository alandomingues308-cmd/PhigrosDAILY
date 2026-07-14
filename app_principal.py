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

# Inicializar Firestore
@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()
mx_tz = pytz.timezone('America/Mexico_City')

# ====================== RENOMBRAR USUARIO ======================
st.sidebar.title("👤 Gestión de Usuario")

with st.sidebar.expander("🔄 Renombrar Usuario (Antiguo → Nuevo)", expanded=True):
    old_user = st.text_input("Usuario Antiguo", placeholder="Nombre anterior")
    new_user = st.text_input("Usuario Nuevo", placeholder="Nombre nuevo")
    
    if st.button("🔄 Cambiar Nombre de Usuario", type="primary"):
        if old_user and new_user and old_user != new_user:
            with st.spinner(f"Actualizando todos los registros de '{old_user}' a '{new_user}'..."):
                scores_ref = db.collection("scores").where("usuario", "==", old_user).stream()
                updated_count = 0
                
                for doc in scores_ref:
                    data = doc.to_dict()
                    data["usuario"] = new_user
                    # Actualizamos también el document ID si es necesario
                    new_doc_id = doc.id.replace(old_user, new_user)
                    db.collection("scores").document(new_doc_id).set(data)
                    # Borramos el documento viejo
                    db.collection("scores").document(doc.id).delete()
                    updated_count += 1
                
                if updated_count > 0:
                    st.success(f"✅ ¡{updated_count} registros actualizados de **{old_user}** a **{new_user}**!")
                else:
                    st.warning(f"No se encontraron registros para el usuario '{old_user}'.")
        else:
            st.warning("Ingresa ambos nombres y asegúrate de que sean diferentes.")

# Usuario actual (se usa el nuevo después de renombrar)
if "usuario_actual" not in st.session_state:
    st.session_state.usuario_actual = ""

usuario_final = st.sidebar.text_input("Usuario actual para subir scores:", 
                                      value=st.session_state.usuario_actual)

if st.sidebar.button("Guardar Usuario"):
    if usuario_final.strip():
        st.session_state.usuario_actual = usuario_final.strip()
        st.sidebar.success("Usuario guardado")

# ====================== SELECCIÓN DE JUEGO ======================
tab_phigros, tab_arcaea = st.tabs(["🎵 Phigros", "Arcaea"])

# ====================== PHIGROS ======================
with tab_phigros:
    st.title(f"🎵 Canción del Día {datetime.now(mx_tz).strftime('%Y-%m-%d')} - Phigros")
    
    @st.cache_data
    def load_songs():
        with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
            return json.load(f)

    songs = load_songs()
    today = datetime.now(mx_tz).strftime("%Y-%m-%d")
    random.seed(today)

    daily_song = random.choice(songs)
    alternative_song = random.choice([s for s in songs if s["title"] != daily_song["title"]])

    CANCION_DAILY = daily_song["title"]
    CANCION_ALT = alternative_song["title"]

    with open("daily_backup.json", "w", encoding="utf-8-sig") as f:
        json.dump({"daily": daily_song, "alternative": alternative_song}, f, ensure_ascii=False, indent=2)

    st.success(f"{CANCION_DAILY} ({daily_song.get('IN', '')})")
    st.subheader("Cancion Alternativa")
    st.info(f"**{CANCION_ALT} ({alternative_song.get('IN', '')})**")

    @st.cache_resource
    def inicializar_ocr():
        return easyocr.Reader(['en'])

    reader = inicializar_ocr()

    st.title("🏆 Sube tu mejor puntaje")

    uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", 
                                    type=["png", "jpg", "jpeg"])

    if uploaded_file is not None and usuario_final:
        imagen_completa = Image.open(uploaded_file)
        ancho, alto = imagen_completa.size
        
        with st.spinner("Analizando captura..."):
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

            if score_detectado == 10000: score_detectado = 1000000
            if score_detectado == 100000: score_detectado = 1000000
            if score_detectado == 1000000: accuracy_detectada = 100
            if accuracy_detectada == 100: score_detectado = 1000000
                
            st.subheader("📝 Datos Extraídos")
            col1, col2, col3 = st.columns(3)
            col1.metric("Usuario", usuario_final)
            col2.metric("Score", f"{score_detectado:,}")
            col3.metric("Acc", f"{accuracy_detectada}%")

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
                    "timestamp": datetime.now(mx_tz).isoformat()
                }
                
                db.collection("scores").document(f"{usuario_final}_{today}_{tipo}").set(nuevo_score)
                st.success(f"✅ ¡Registrado correctamente en **{tipo}**!")
                st.balloons()

    # ==================== TABLAS ====================
    st.write("---")
    st.header("📊 Tablas de Clasificación")

    scores_ref = db.collection("scores").stream()
    todos_los_scores = [doc.to_dict() for doc in scores_ref]

    if todos_los_scores:
        df = pd.DataFrame(todos_los_scores)
        tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
        
        with tab_diaria:
            st.subheader(f"Desafío del Día - {today}")
            df_hoy = df[df.get("fecha") == today].copy()
            # ... (resto del código de tablas se mantiene igual, solo muestro lo esencial) ...
            if not df_hoy.empty:
                df_daily = df_hoy[df_hoy["cancion"] == CANCION_DAILY].copy()
                if not df_daily.empty:
                    df_daily = df_daily.sort_values(by=["rks", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                    st.markdown("### 🏆 Top Daily")
                    st.dataframe(df_daily[["usuario", "score", "accuracy", "rks"]], use_container_width=True)

                df_alt = df_hoy[df_hoy["cancion"] == CANCION_ALT].copy()
                if not df_alt.empty:
                    df_alt = df_alt.sort_values(by=["rks", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                    st.markdown("### 🥈 Top Alternative")
                    st.dataframe(df_alt[["usuario", "score", "accuracy", "rks"]], use_container_width=True)

        with tab_general:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
            df_best = df.sort_values(by=['usuario', 'fecha', 'rks'], ascending=[True, True, False]).drop_duplicates(subset=['usuario', 'fecha'], keep='first')
            df_acum = df_best.groupby("usuario").agg(RKS_Total=("rks", "sum"), Canciones=("rks", "count")).reset_index()
            df_acum["RKS_Total"] = df_acum["RKS_Total"].round(4)
            st.dataframe(df_acum.sort_values("RKS_Total", ascending=False)[["usuario", "RKS_Total", "Canciones"]], use_container_width=True, hide_index=True)

# ====================== ARCAEA ======================
with tab_arcaea:
    st.title("Arcaea - Daily Challenge")
    st.info("🚧 **En proceso...** Esta sección estará disponible próximamente.")
