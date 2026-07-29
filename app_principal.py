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
mx_tz = pytz.timezone('America/Caracas')

# ====================== SIDEBAR - RENOMBRAR ======================
st.sidebar.title("👤 Gestión de Usuario")

rename_status = st.sidebar.empty()

with st.sidebar.expander("🔄 Renombrar Usuario (Antiguo → Nuevo)", expanded=False):
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
                    rename_status.success(f"✅ {updated} registros cambiados a **{new_user}**")
                else:
                    rename_status.warning(f"No se encontraron registros de '{old_user}'")
        else:
            rename_status.warning("Ingresa ambos usuarios correctamente")

# ====================== PHIGROS ======================
st.title("Feliz cumpleaños wonder Acute")
st.write("Hoy los daily-alternative fueron escogidos por el cumpleañero (aunque fue ayer :⁠^⁠)) cualquier inconveniente hablarlo con el")
tab_phigros, tab_arcaea = st.tabs(["🎵 Phigros", "Arcaea"])
with tab_phigros:
    st.title(f"🎵 Canción del Día {datetime.now(mx_tz).strftime('%Y-%m-%d')} - Phigros")

    @st.cache_data
    def load_songs():
        with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
            return json.load(f)

    songs = load_songs()
    today = datetime.now(mx_tz).strftime("%Y-%m-%d")
    random.seed(today)

    daily_song = {"title": "祈 -我ら神祖と共に歩む者なり-", "IN": 16.4, "AT": 17.3}
    alternative_song= {"title": "玩具狂奏曲 -終焉-", "IN": 15.8, "AT": 17}

    CANCION_DAILY = daily_song["title"]
    CANCION_ALT = alternative_song["title"]

    st.success(f"{CANCION_DAILY} ({daily_song.get('IN')})")
    st.subheader("Cancion Alternativa")
    st.info(f"**{CANCION_ALT} ({alternative_song.get('IN', '')})**")


    @st.cache_resource
    def inicializar_ocr():
        return easyocr.Reader(['en'])

    reader = inicializar_ocr()

    st.title("🏆 Sube tu mejor puntaje")
    usuario_final = st.text_input("Coloca tu usuario", placeholder="Tu nombre de usuario")

    uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", 
                                    type=["png", "jpg", "jpeg"])

    if uploaded_file is not None and usuario_final.strip():
        imagen_completa = Image.open(uploaded_file)
        ancho, alto = imagen_completa.size
        
        with st.spinner("Analizando captura..."):
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

            if score_detectado in (10000, 100000):
                score_detectado = 1000000
            if score_detectado == 1000000:
                accuracy_detectada = 100.0

            st.subheader("📝 Datos Extraídos")
            col1, col2, col3 = st.columns(3)
            col1.metric("Usuario", usuario_final)
            col2.metric("Score", f"{score_detectado:,}")
            col3.metric("Acc", f"{accuracy_detectada}%")

            st.subheader("¿De qué canción es esta captura?")
            opcion = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True)

            cancion_seleccionada_P = daily_song if opcion == "Daily" else alternative_song

            has_AT = cancion_seleccionada_P.get("AT") is not None
            diff_key_P = "IN"  # valor por defecto

            # Solo mostrar selector si tiene ETR o beyond
            if has_AT:
                st.subheader("Dificultad del Chart")
                options = ["IN"]
                if has_AT:
                    options.append("AT")
                
                diff_option_P = st.radio("Selecciona la dificultad:", options, horizontal=True, key="ar_diff")
                diff_key_P = diff_option_P.split()[0]
            else:
                st.info("**Dificultad:** IN (automática)")
                

            if st.button("Registrar Puntaje", type="primary"):
                if opcion == "Daily":
                    cancion_objetivo = CANCION_DAILY
                    constante_activa = daily_song.get("IN") if diff_key_P == "IN" else daily_song.get("AT")
                    tipo = "Daily"
                else:
                    cancion_objetivo = CANCION_ALT
                    constante_activa = alternative_song.get("IN") if diff_key_P == "IN" else alternative_song.get("AT")
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

    # Tablas (mismo código anterior)
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
            for song, label in [(CANCION_DAILY, "🏆 Top Daily"), (CANCION_ALT, "🥈 Top Alternative")]:
                df_temp = df_hoy[df_hoy["cancion"] == song].copy()
                if not df_temp.empty:
                    df_temp = df_temp.sort_values(by=["rks", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                    st.markdown(f"### {label}")
                    st.dataframe(df_temp[["usuario", "score", "accuracy", "rks"]], use_container_width=True,hide_index=True)
                else:
                    st.info(f"Aún no hay scores para {song}")

        with tab_general:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
            best = df.sort_values(by=['usuario','fecha','rks'], ascending=[True,True,False]).drop_duplicates(subset=['usuario','fecha'])
            acum = best.groupby("usuario").agg(RKS_Total=("rks","sum"), Canciones=("rks","count")).reset_index()
            acum["RKS_Total"] = acum["RKS_Total"].round(4)
            df_filtrado = acum[acum["Canciones"] > 0]

            if len(df_filtrado) > 0:
                st.dataframe(df_filtrado.sort_values("RKS_Total", ascending=False)[["usuario", "RKS_Total", "Canciones"]], use_container_width=True,hide_index=True)
    

    
                          
                                                        # ====================== ARCAEA ======================
with tab_arcaea:
    st.title(f"🎵 Canción del Día {datetime.now(mx_tz).strftime('%Y-%m-%d')} - Arcaea")

    @st.cache_data
    def load_arcaea_songs():
        with open("arcaea_songs.json", "r", encoding="utf-8-sig") as f:
            return json.load(f)

    songs_a = load_arcaea_songs()
    today = datetime.now(mx_tz).strftime("%Y-%m-%d")
    random.seed(today)

    daily_song_a= {"title": "PRAGMATISM -RESURRECTION-", "FTR": 10.1, "ETR": null, "Beyond": 11.2}
    alternative_song_a= {"title": "Vulcanus", "FTR": 10.9, "ETR": null, "Beyond": null}
    
    if daily_song_a["ETR"] is not None:
        st.success(f"{daily_song_a['title']}/ (FTR: {daily_song_a["FTR"]}) - (ETR: {daily_song_a["ETR"]})")
    elif daily_song_a["Beyond"] is not None:
        st.success(f"{daily_song_a['title']}/ (FTR: {daily_song_a["FTR"]}) - (BYD: {daily_song_a["Beyond"]})")
    else:st.success(f"{daily_song_a['title']}/ (FTR: {daily_song_a["FTR"]})")

    st.subheader("Cancion Alternativa")
    
    if alternative_song_a["ETR"] is not None:
        st.info(f"{alternative_song_a['title']}/ (FTR: {alternative_song_a["FTR"]}) - (ETR: {alternative_song_a["ETR"]})")
    elif alternative_song_a["Beyond"] is not None:
        st.info(f"{alternative_song_a['title']}/ (FTR: {alternative_song_a["FTR"]}) - (BYD: {alternative_song_a["Beyond"]})")
    else:st.info(f"{alternative_song_a['title']}/ (FTR: {alternative_song_a["FTR"]})")

    
    
    
    st.title("🏆 Sube tu mejor puntaje")
    usuario_final_a = st.text_input("Coloca tu usuario", placeholder="Tu nombre de usuario", key="ar_user")

    uploaded_file_a = st.file_uploader("Sube la captura de pantalla de tus resultados (Arcaea):", 
                                      type=["png", "jpg", "jpeg"], key="ar_upload")

    if uploaded_file_a is not None and usuario_final_a.strip():
        imagen_completa = Image.open(uploaded_file_a)
        ancho, alto = imagen_completa.size
        
        with st.spinner("Analizando captura..."):
            score_detectado = 0
            strategies = [(0.22, 0.15, 0.80, 0.42), (0.28, 0.20, 0.75, 0.38), (0.18, 0.12, 0.85, 0.48)]
            for left, top, right, bottom in strategies:
                box = (int(ancho*left), int(alto*top), int(ancho*right), int(alto*bottom))
                img = np.array(imagen_completa.crop(box))
                ocr = reader.readtext(img, detail=0, width_ths=0.5)
                for text in ocr:
                    clean = re.sub(r'[^0-9]', '', text)
                    if len(clean) >= 7:
                        score_detectado = int(clean)
                        break
                if score_detectado > 0:
                    break

            st.subheader("📝 Datos Extraídos")
            col1, col2 = st.columns(2)
            col1.metric("Usuario", usuario_final_a)
            col2.metric("Score", f"{score_detectado:,}")

            # Elegir canción
            st.subheader("¿De qué canción es esta captura?")
            opcion_a = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True, key="ar_song_type")

            cancion_seleccionada = daily_song_a if opcion_a == "Daily" else alternative_song_a

            # Verificar dificultades disponibles (según tu JSON)
            has_eternal = cancion_seleccionada.get("ETR") is not None
            has_beyond = cancion_seleccionada.get("Beyond") is not None

            diff_key = "FTR"  # valor por defecto

            # Solo mostrar selector si tiene ETR o beyond
            if has_eternal or has_beyond:
                st.subheader("Dificultad del Chart")
                options = ["FTR (Future)"]
                if has_eternal:
                    options.append("ETR (Eternal)")
                if has_beyond:
                    options.append("BYD (Beyond)")
            
                
                diff_option = st.radio("Selecciona la dificultad:", options, horizontal=True, key="ar_diff")
                diff_key = diff_option.split()[0]
            

            # Calcular potencial
            constante_activa = cancion_seleccionada.get(diff_key, cancion_seleccionada.get("FTR", 0))

            def calcular_modificador(score):
                if score >= 10000000:
                    return 2.0
                elif score >= 9800000:
                    return 1.0 + (score - 9800000) / 200000.0
                else:
                    return (score - 9500000) / 300000.0

            mod = calcular_modificador(score_detectado)
            potencial = round(constante_activa + mod, 2)
            

            if st.button("Registrar Puntaje", type="primary", key="ar_btn"):
                if score_detectado == 0:
                    st.error("No se detectó el score.")
                else:
                    nuevo_score = {
                        "usuario": usuario_final_a,
                        "cancion": cancion_seleccionada["title"],
                        "tipo": opcion_a,
                        "score": score_detectado,
                        "potencial": potencial,
                        "fecha": today,
                        "timestamp": datetime.now(mx_tz).isoformat(),
                        "juego": "Arcaea",
                        "dificultad": diff_key
                    }
                    
                    db.collection("scores").document(f"{usuario_final_a}_{today}_{opcion_a}_arcaea").set(nuevo_score)
                    st.success(f"✅ ¡Registrado correctamente en **{opcion_a}**!")
                    st.balloons()

    # Tablas Arcaea
    st.write("---")
    st.header("📊 Tablas de Clasificación - Arcaea")
    scores_ref = db.collection("scores").stream()
    todos_los_scores = [doc.to_dict() for doc in scores_ref if doc.to_dict().get("juego") == "Arcaea"]

    if todos_los_scores:
        df = pd.DataFrame(todos_los_scores)
        tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
        
        with tab_diaria:
            st.subheader(f"Desafío del Día - {today}")
            df_hoy = df[df["fecha"] == today].copy()
            for song, label in [(daily_song_a["title"], "🏆 Top Daily"), (alternative_song_a["title"], "🥈 Top Alternative")]:
                df_temp = df_hoy[df_hoy["cancion"] == song].copy()
                if not df_temp.empty:
                    df_temp = df_temp.sort_values(by=["potencial", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                    st.markdown(f"### {label}")
                    st.dataframe(df_temp[["usuario", "score", "potencial", "dificultad"]], use_container_width=True,hide_index=True)
                else:
                    st.info(f"Aún no hay scores para {song}")

        with tab_general:
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
            best = df.sort_values(by=['usuario','fecha','potencial'], ascending=[True,True,False]).drop_duplicates(subset=['usuario','fecha'])
            acum = best.groupby("usuario").agg(Potencial_Total=("potencial","sum"), Canciones=("potencial","count")).reset_index()
            acum["Potencial_Total"] = acum["Potencial_Total"].round(4)
            st.dataframe(acum.sort_values("Potencial_Total", ascending=False)[["usuario","Potencial_Total","Canciones"]], use_container_width=True, hide_index=True)
