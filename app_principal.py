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
import rosu_pp_py as rosu
import requests 

# ====================== CONFIGURACIÓN ======================
st.set_page_config(page_title="Daily Challenge", layout="wide")

@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()
mx_tz = pytz.timezone('America/Caracas')

# --- CONTRASEÑA ADMIN ---
PASSWORD_ADMIN = "ritmo123"

# --- PANEL DE ADMINISTRACIÓN (SIDEBAR) ---
st.sidebar.write("---")
st.sidebar.header("🔐 Panel de Admin (osu!)")
password_input = st.sidebar.text_input("Contraseña", type="password", key="pwd_admin_osu")

if password_input == PASSWORD_ADMIN:
    st.sidebar.success("Acceso concedido")
    modo_config = st.sidebar.radio("¿Qué modo configurar?", ["Daily", "Alternative"], key="modo_cfg_osu")
    url_beatmap = st.sidebar.text_input(f"Enlace del beatmapset ({modo_config})", key=f"url_{modo_config}")
    
    CLIENT_ID = '65710'
    CLIENT_SECRET = 'l6nKIojPmG72RM7LsuHYVyH9PpCrSJAkqPen7Ax0'

    def get_osu_token():
        url = "https://osu.ppy.sh/oauth/token"
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials',
            'scope': 'public'
        }
        r = requests.post(url, data=data)
        return r.json().get('access_token')

    if st.sidebar.button(f"Guardar {modo_config}", key=f"btn_save_{modo_config}"):
        match_set = re.search(r"beatmapsets/(\d+)", url_beatmap)
        set_id = match_set.group(1) if match_set else None
        
        if set_id:
            try:
                token = get_osu_token()
                headers = {"Authorization": f"Bearer {token}"}
                res = requests.get(f"https://osu.ppy.sh/api/v2/beatmapsets/{set_id}", headers=headers)
                data = res.json()
                
                if 'artist' in data:
                    nombre_cancion_final = f"{data['artist']} - {data['title']}"
                    beatmaps_list = []
                    
                    for bm in data.get('beatmaps', []):
                        if bm['mode'] == 'mania':
                            beatmaps_list.append({
                                "id": bm['id'],
                                "version": bm['version']
                            })
                    
                    db.collection("config").document("canciones_activas_osu").set({
                        modo_config.lower(): nombre_cancion_final,
                        f"{modo_config.lower()}_beatmaps": beatmaps_list
                    }, merge=True)
                    st.sidebar.success(f"¡Configurado con {len(beatmaps_list)} dificultades de Mania!")
                else:
                    st.sidebar.error("No se pudo obtener información del beatmapset. Verifica el ID.")
            except Exception as e:
                st.sidebar.error(f"Error al conectar con API: {e}")
        else:
            st.sidebar.error("Enlace de osu! inválido (debe ser un beatmapset).")




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

# ====================== PHIGROS =====================
tab_phigros, tab_arcaea, tab_osu = st.tabs(["🎵 Phigros", "Arcaea","Osu"])
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

    if daily_song["AT"] is not None:
        st.success(f"{CANCION_DAILY} /// IN: ({daily_song.get('IN')}) - AT: ({daily_song.get('AT')})")
    else: 
        st.success(f"{CANCION_DAILY} /// IN: ({daily_song.get('IN')})")
    
    st.subheader("Cancion Alternativa")

    if alternative_song["AT"] is not None:
        st.info(f"{CANCION_ALT} /// IN: ({alternative_song.get('IN')}) - AT: ({alternative_song.get('AT')})")
    else: 
        st.info(f"{CANCION_ALT} /// IN: ({alternative_song.get('IN')})")

    @st.cache_resource
    def inicializar_ocr():
        return easyocr.Reader(['en'])

    reader = inicializar_ocr()

    st.title("🏆 Sube tu mejor puntaje")
    usuario_final = st.text_input("Coloca tu usuario", placeholder="Tu nombre de usuario", key="usuario_input_phigros")

    uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", 
                                    type=["png", "jpg", "jpeg"], key="uploader_file_phigros")

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
            opcion = st.radio("Selecciona:", ["Daily", "Alternative"], horizontal=True, key="opcion_cancion_phigros")

            cancion_seleccionada_P = daily_song if opcion == "Daily" else alternative_song

            has_AT = cancion_seleccionada_P.get("AT") is not None
            diff_key_P = "IN"  

            if has_AT:
                st.subheader("Dificultad del Chart")
                options = ["IN"]
                if has_AT:
                    options.append("AT")
                
                diff_option_P = st.radio("Selecciona la dificultad:", options, horizontal=True, key="ar_diff_phigros")
                diff_key_P = diff_option_P.split()[0]
            else:
                st.info("**Dificultad:** IN (automática)")
                

            if st.button("Registrar Puntaje", type="primary", key="btn_registrar_phigros"):
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

    # Tablas de Clasificación
    st.write("---")
    st.header("📊 Tablas de Clasificación")
    scores_ref = db.collection("scores").stream()
    todos_los_scores = [doc.to_dict() for doc in scores_ref]

    if todos_los_scores:
        df = pd.DataFrame(todos_los_scores)
        
        # Si la columna "juego" no existe, o si tiene valores vacíos/nulos, les asignamos "Phigros" por defecto
        if "juego" not in df.columns:
            df["juego"] = "Phigros"
        else:
            df["juego"] = df["juego"].fillna("Phigros")
            # También cubrimos por si hay campos vacíos como string ""
            df["juego"] = df["juego"].replace("", "Phigros")
        
        # Filtramos para quedarnos exclusivamente con Phigros
        df = df[df["juego"] == "Phigros"]
        
        tab_diaria, tab_general, tab_historial = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales", "🔍 Historial por Fecha"])
        
        with tab_diaria:
            st.subheader(f"Desafío del Día - {today}")
            df_hoy = df[df["fecha"] == today].copy()
            for song, label in [(CANCION_DAILY, "🏆 Top Daily"), (CANCION_ALT, "🥈 Top Alternative")]:
                df_temp = df_hoy[df_hoy["cancion"] == song].copy()
                if not df_temp.empty:
                    df_temp = df_temp.sort_values(by=["rks", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                    st.markdown(f"### {label}")
                    st.dataframe(df_temp[["usuario", "score", "accuracy", "rks"]], use_container_width=True, hide_index=True)
                else:
                    st.info(f"Aún no hay scores para {song}")

        with tab_general:
            st.write("solo se suma tu mejor puntaje del dia (Daily o Alternative)")
            df['fecha'] = pd.to_datetime(df['fecha']).dt.date
            best = df.sort_values(by=['usuario','fecha','rks'], ascending=[True,True,False]).drop_duplicates(subset=['usuario','fecha'])
            acum = best.groupby("usuario").agg(RKS_Total=("rks","sum"), Canciones=("rks","count")).reset_index()
            acum["RKS_Total"] = acum["RKS_Total"].round(4)
            df_filtrado = acum[acum["Canciones"] > 0]

            if len(df_filtrado) > 0:
                st.dataframe(df_filtrado.sort_values("RKS_Total", ascending=False)[["usuario", "RKS_Total", "Canciones"]], use_container_width=True, hide_index=True)

        with tab_historial:
            st.header("📅 Historial de Desafíos")

            FECHA_CREACION = datetime(2026, 7, 10).date()

            fecha_seleccionada = st.date_input(
                "Selecciona una fecha para ver el ranking:",
                value=datetime.now(mx_tz).date(),
                max_value=datetime.now(mx_tz).date(),
                key="historial_fecha_phigros"
            )

            fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')
            
            fechas_existentes = df["fecha"].astype(str).unique() if not df.empty else []

            if fecha_seleccionada < FECHA_CREACION:
                st.warning("⏳ Aún no existíamos esto :⁠^⁠)")
            elif fecha_str not in fechas_existentes:
                st.info("❌ Nadie jugó este daily")
            else:
                df_historial = df[df["fecha"].astype(str) == fecha_str].copy()
                
                if df_historial.empty:
                    st.info("❌ Nadie jugó este daily")
                else:
                    if "tipo" not in df_historial.columns:
                        df_historial["tipo"] = "Daily"
                    else:
                        df_historial["tipo"] = df_historial["tipo"].fillna("Daily")

                    for tipo_objetivo, label in [("Daily", "🏆 Top Daily"), ("Alternative", "🥈 Top Alternative")]:
                        df_tipo = df_historial[df_historial["tipo"] == tipo_objetivo].copy()
                        
                        if not df_tipo.empty:
                            song_name = df_tipo["cancion"].iloc[0]
                            
                            st.markdown(f"### {label} ({song_name})")
                            
                            df_temp = df_tipo.sort_values(by=["rks", "timestamp"], ascending=[False, True]).drop_duplicates(subset=["usuario"], keep="first")
                            st.dataframe(df_temp[["usuario", "score", "accuracy", "rks"]], use_container_width=True, hide_index=True)
                        else:
                            st.info(f"Aún no hay scores para la categoría **{tipo_objetivo}** en esta fecha.")



    
                          
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

    daily_song_a = {"title": "Riven Pilgrimage", "FTR": 10.4, "ETR": None, "BYD": None,"INS":11.5}
    alternative_song_a = random.choice([s for s in songs_a if s["title"] != daily_song_a["title"]])

    if daily_song_a["ETR"] is not None:
        st.success(f"{daily_song_a['title']} /// (FTR: {daily_song_a["FTR"]}) - (ETR: {daily_song_a["ETR"]})")
    elif daily_song_a["BYD"] is not None:
        st.success(f"{daily_song_a['title']} /// (FTR: {daily_song_a["FTR"]}) - (BYD: {daily_song_a["BYD"]})")
    elif daily_song_a.get("INS") is not None:
        st.info(f"{daily_song_a['title']} /// (FTR: {daily_song_a["FTR"]}) - (INS: {daily_song_a["INS"]})")
    else:st.success(f"{daily_song_a['title']} /// (FTR: {daily_song_a["FTR"]})")

    st.subheader("Cancion Alternativa")
    
    if alternative_song_a["ETR"] is not None:
        st.info(f"{alternative_song_a['title']} /// (FTR: {alternative_song_a["FTR"]}) - (ETR: {alternative_song_a["ETR"]})")
    elif alternative_song_a["BYD"] is not None:
        st.info(f"{alternative_song_a['title']} /// (FTR: {alternative_song_a["FTR"]}) - (BYD: {alternative_song_a["BYD"]})")
    elif alternative_song_a.get("INS") is not None:
        st.info(f"{alternative_song_a['title']} /// (FTR: {alternative_song_a["FTR"]}) - (INS: {alternative_song_a["INS"]})")
    else:st.info(f"{alternative_song_a['title']} /// (FTR: {alternative_song_a["FTR"]})")

    
    
    
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

            # Verificar dificultades disponibles 
            has_eternal = cancion_seleccionada.get("ETR") is not None
            has_beyond = cancion_seleccionada.get("BYD") is not None
            has_INS= cancion_seleccionada.get("INS") is not None

            diff_key = "FTR"  # valor por defecto

            # Solo mostrar selector si tiene ETR o beyond
            if has_eternal or has_beyond or has_INS: 
                st.subheader("Dificultad del Chart")
                options = ["FTR (Future)"]
                if has_eternal:
                    options.append("ETR (Eternal)")
                if has_beyond:
                    options.append("BYD (Beyond)")
                if has_INS:
                    options.append("INS (inscribed)")
            
                
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

       #================== OSU =====================

with tab_osu:
    import rosu_pp_py as rosu
    import pandas as pd
    from datetime import datetime
    import requests

    # --- OBTENER CONFIGURACIÓN ACTUAL ---
    config_ref = db.collection("config").document("canciones_activas_osu").get()
    config_data = config_ref.to_dict() if config_ref.exists else {}

    cancion_daily = config_data.get("daily", "Sin configurar")
    cancion_alternative = config_data.get("alternative", "Sin configurar")
    daily_bm_list = config_data.get("daily_beatmaps", [])
    alt_bm_list = config_data.get("alternative_beatmaps", [])

    # --- INTERFAZ ---
    st.title("🎵 Canción del Día - Osu")
    st.success(f"{cancion_daily}")
    if daily_bm_list:
        st.markdown(f"[🔗 Descargar / Ver Daily](https://osu.ppy.sh/b/{daily_bm_list[0]['id']})")
    
    st.subheader("Canción Alternativa")
    st.info(f"{cancion_alternative}")
    if alt_bm_list:
        st.markdown(f"[🔗 Descargar / Ver Alternative](https://osu.ppy.sh/b/{alt_bm_list[0]['id']})")
    st.write("---")

    # --- REGISTRO Y CÁLCULO ---
    st.title("🏆 Registra tu puntaje")
    usuario_final_o = st.text_input("Usuario:", key="user_osu_input")
    tipo_envio = st.selectbox("Modo:", ["Daily", "Alternative"], key="envio_osu")
    
    current_bm_list = daily_bm_list if tipo_envio == "Daily" else alt_bm_list
    
    if current_bm_list:
        opciones_diff = {bm["version"]: bm["id"] for bm in current_bm_list}
        diff_elegida = st.selectbox("Dificultad:", list(opciones_diff.keys()), key="diff_sel")
        beatmap_id = opciones_diff[diff_elegida]

        col1, col2 = st.columns(2)
        with col1:
            accuracy = st.number_input("Accuracy (%)", 0.0, 100.0, 95.0, 0.01)
        with col2:
            count_320 = st.number_input("320 counts (MAX)", 0, 50000, 1500, 1)

        if st.button("Subir puntuación"):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(f"https://osu.ppy.sh/osu/{beatmap_id}", headers=headers)
                mapa = rosu.Beatmap(bytes=resp.content)
                mapa.convert(rosu.GameMode.Mania)
                
                # Usar n_geki en lugar de n320 para los juicios MAX en Mania
                perf = rosu.Performance(
                    accuracy=accuracy,
                    n_geki=count_320
                )
                result = perf.calculate(mapa)
                pp_final = result.pp

                # Guardar en Firestore
                nuevo_score = {
                    "usuario": usuario_final_o,
                    "pp": round(pp_final, 2),
                    "tipo": tipo_envio,
                    "cancion": cancion_daily if tipo_envio == "Daily" else cancion_alternative,
                    "dificultad": diff_elegida,
                    "timestamp": datetime.now().isoformat(),
                    "fecha": today
                }
                db.collection("scores_osu").document(f"{usuario_final_o}_{tipo_envio}_{today}").set(nuevo_score)
                st.success(f"✅ ¡Registrado con **{round(pp_final, 2)} PP**!")
                st.balloons()
            except Exception as e:
                st.error(f"Error técnico: {e}")
 
    # --- TABLAS DE CLASIFICACIÓN ---
    st.write("---")
    st.header("📊 Tablas de Clasificación")

    scores_ref = db.collection("scores_osu").stream()
    todos_los_scores = [doc.to_dict() for doc in scores_ref]

    if todos_los_scores:
        df_osu = pd.DataFrame(todos_los_scores)
        df_osu['fecha_date'] = pd.to_datetime(df_osu['fecha']).dt.date

        tab_diaria_o, tab_general_o = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
    
        with tab_diaria_o:
            st.subheader(f"Desafío del Día - {today}")
            
            st.markdown("### 🏆 Top Daily")
            df_daily = df_osu[(df_osu["tipo"] == "Daily") & (df_osu["cancion"] == cancion_daily)]
            if not df_daily.empty:
                st.dataframe(df_daily.sort_values(by="pp", ascending=False)[["usuario", "pp", "dificultad"]], use_container_width=True)
            else:
                st.info("Aún no hay registros para el Daily actual.")
            
            st.markdown("### 🥈 Top Alternative")
            df_alt = df_osu[(df_osu["tipo"] == "Alternative") & (df_osu["cancion"] == cancion_alternative)]
            if not df_alt.empty:
                st.dataframe(df_alt.sort_values(by="pp", ascending=False)[["usuario", "pp", "dificultad"]], use_container_width=True)
            else:
                st.info("Aún no hay registros para el Alternative actual.")

        with tab_general_o:
            best = df_osu.sort_values(by=['usuario', 'fecha_date', 'pp'], ascending=[True, True, False]).drop_duplicates(subset=['usuario', 'fecha_date'])
            acum = best.groupby("usuario").agg(PP_Total=("pp", "sum"), Canciones=("pp", "count")).reset_index()
            acum["PP_Total"] = acum["PP_Total"].round(2)
            st.dataframe(acum.sort_values("PP_Total", ascending=False), use_container_width=True)
    else:
        st.info("No hay registros en la base de datos de osu! todavía.")
