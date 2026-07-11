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

# Selección de dos canciones
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

reader = inicializar_


# =============================================================================
# 4. RENDERS DE LAS TABLAS DE POSICIONES
# =============================================================================
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
            # === TOP DAILY ===
            df_daily = df_hoy[df_hoy["cancion"] == CANCION_DAILY]
            df_daily = df_daily.sort_values(by="rks", ascending=False)\
                              .drop_duplicates(subset=["usuario"], keep="first")
            
            st.markdown("### 🏆 Top Daily")
            if not df_daily.empty:
                st.dataframe(df_daily[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
            else:
                st.info("Aún no hay scores para el Daily.")
            
            st.markdown("---")
            
            # === TOP ALTERNATIVE ===
            df_alt = df_hoy[df_hoy["cancion"] == CANCION_ALT]
            df_alt = df_alt.sort_values(by="rks", ascending=False)\
                          .drop_duplicates(subset=["usuario"], keep="first")
            
            st.markdown("### 🥈 Top Alternative")
            if not df_alt.empty:
                st.dataframe(df_alt[["usuario", "score", "accuracy", "rks"]], use_container_width=True)
            else:
                st.info("Aún no hay scores para el Alternative.")
        else:
            st.info("Aún no hay scores subidos para el desafío de hoy.")

    with tab_general:
        st.subheader("Tabla Global Histórica (Mejor canción por día)")
        
        # === LÓGICA OPción 2: Solo la mejor canción por día por usuario ===
        df_hoy_max = df[df["fecha"] == today].copy()
        
        if not df_hoy_max.empty:
            # Agrupar por usuario y quedarse solo con la mejor RKS del día (entre Daily y Alternative)
            df_best_per_day = df_hoy_max.loc[df_hoy_max.groupby("usuario")["rks"].idxmax()]
        else:
            df_best_per_day = pd.DataFrame()

        # Combinar con datos históricos (días anteriores)
        df_historico = df[df["fecha"] != today]
        
        df_all = pd.concat([df_historico, df_best_per_day]) if not df_best_per_day.empty else df_historico
        
        # Mejor score por usuario + canción (para evitar duplicados de misma canción)
        df_mejores = df_all.sort_values(by="rks", ascending=False)\
                           .drop_duplicates(subset=["usuario", "cancion"], keep="first")
        
        df_acumulado = df_mejores.groupby("usuario").agg(
            RKS_Total=("rks", "sum"),
            Canciones_Jugadas=("cancion", "count")
        ).reset_index()
        
        df_acumulado["RKS_Total"] = df_acumulado["RKS_Total"].round(4)
        df_acumulado = df_acumulado.sort_values(by="RKS_Total", ascending=False)
        
        if not df_acumulado.empty:
            st.dataframe(df_acumulado[["usuario", "RKS_Total", "Canciones_Jugadas"]], 
                        use_container_width=True)
            st.caption("Nota: Solo se cuenta la mejor canción (Daily o Alternative) por día.")
        else:
            st.info("No hay datos suficientes para calcular la tabla global.")
else:
    st.info("No se ha creado ningún registro histórico en el servidor.")
