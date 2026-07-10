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

@st.cache_resource
def init_firestore():
    key_dict = dict(st.secrets["firestore"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

# Uso de la conexión
db = init_firestore()


# =============================================================================
# 1. FUNCIONES CORE (Cálculos y Lógica de Phigros)
# =============================================================================

def calcular_rks_puro(accuracy, constante):
    """Calcula el RKS base oficial de Phigros según la Accuracy."""
    if accuracy < 70.0:
        return 0.0
    rks = (((accuracy - 55) / 45) ** 2) * constante
    return round(rks, 4)

def obtener_rango_y_bono(score, bads, misses):
    """Determina el rango de la partida y calcula los bonos acumulados."""
    if score >= 1000000:
        rango = "Phi"
    elif score >= 960000:
        rango = "V"
    elif score >= 920000:
        rango = "S"
    elif score >= 820000:
        rango = "A"
    elif score >= 700000:
        rango = "B"
    else:
        rango = "C"
        
    bono = 0.0
    if score == 1000000:
        bono += 2.0
    if (bads + misses) == 0:
        bono += 1.5
        
    return rango, bono


# =============================================================================
# 2. INICIALIZACIÓN DE COMPONENTES Y ESTADOS
# =============================================================================

@st.cache_resource
def inicializar_ocr():
    return easyocr.Reader(['ja', 'en'])

reader = inicializar_ocr()

if "palabras_excluidas" not in st.session_state:
    st.session_state.palabras_excluidas = ["SCORE", "ACCURACY", "TOTAL", "PERFECT", "GOOD", "BAD", "MISS", "MAX COMBO"]

# Lee automáticamente la canción sorteada por el archivo app_principal.py
cancion_objetivo = st.session_state.get("daily_cancion", "狂喜蘭舞")
constante_activa = st.session_state.get("daily_constante", 16.0)
today = st.session_state.get("daily_fecha", datetime.now().strftime("%Y-%m-%d"))


# =============================================================================
# 3. INTERFAZ DE USUARIO (Streamlit)
# =============================================================================

st.title("🏆 Phigros Score Tracker & Leaderboard")

usuario_activo = st.text_input("Ingresa tu nombre de usuario del juego:", "").strip()

uploaded_file = st.file_uploader("Sube la captura de pantalla de tus resultados:", type=["png", "jpg", "jpeg"])

if uploaded_file is not None and usuario_activo != "":
    
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    if usuario_activo.upper() not in st.session_state.palabras_excluidas:
        st.session_state.palabras_excluidas.append(usuario_activo.upper())
        
    with st.spinner("Analizando regiones de la captura..."):
        
        # 📌 Recorte 1: Área de la Canción (Esquina inferior izquierda)
        box_cancion = (int(ancho * 0.05), int(alto * 0.65), int(ancho * 0.35), int(alto * 0.78))
        img_cancion = np.array(imagen_completa.crop(box_cancion))
        ocr_cancion_res = reader.readtext(img_cancion, detail=0)
        cancion_detectada = " ".join(ocr_cancion_res).strip() if ocr_cancion_res else "Desconocida"
        
        # 📌 Recorte 2: Área del Score (Centro derecho superior)
        box_score = (int(ancho * 0.52), int(alto * 0.25), int(ancho * 0.80), int(alto * 0.50))
        img_score = np.array(imagen_completa.crop(box_score))
        ocr_score_res = reader.readtext(img_score, detail=0)
        score_detectado = 0
        for item in ocr_score_res:
            numeros = re.findall(r'\d+', item)
            if numeros:
                score_detectado = int("".join(numeros))
                break
                
        # 📌 Recorte 3: Área de la Accuracy (Centro derecho medio)
        box_acc = (int(ancho * 0.70), int(alto * 0.50), int(ancho * 0.92), int(alto * 0.65))
        img_acc = np.array(imagen_completa.crop(box_acc))
        ocr_acc_res = reader.readtext(img_acc, detail=0)
        accuracy_detectada = 0.0
        for item in ocr_acc_res:
            match = re.search(r'(\d+\.\d+)', item)
            if match:
                accuracy_detectada = float(match.group(1))
                break

        # 📌 Recorte 4: Área exclusiva para BAD
        box_bad = (int(ancho * 0.61), int(alto * 0.66), int(ancho * 0.69), int(alto * 0.77))
        img_bad = np.array(imagen_completa.crop(box_bad))
        ocr_bad_res = reader.readtext(img_bad, detail=0)
        
        bad_detectados = 0
        numeros_bad = re.findall(r'\d+', " ".join(ocr_bad_res))
        if numeros_bad:
            bad_detectados = int(numeros_bad[0])

        # 📌 Recorte 5: Área exclusiva para MISS
        box_miss = (int(ancho * 0.69), int(alto * 0.66), int(ancho * 0.77), int(alto * 0.77))
        img_miss = np.array(imagen_completa.crop(box_miss))
        ocr_miss_res = reader.readtext(img_miss, detail=0)
        
        miss_detectados = 0
        numeros_miss = re.findall(r'\d+', " ".join(ocr_miss_res))
        if numeros_miss:
            miss_detectados = int(numeros_miss[0])

    # --- MOSTRAR DATOS EXTRAÍDOS ---
    st.subheader("📝 Datos Extraídos de la Imagen")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Canción", cancion_detectada)
    col2.metric("Score", f"{score_detectado:,}")
    col3.metric("Accuracy", f"{accuracy_detectada}%")
    col4.metric("Bad / Miss", f"{bad_detectados} / {miss_detectados}")

    # --- BOTÓN DE PROCESAMIENTO Y VALIDACIÓN ---
    if st.button("Validar y Registrar Puntaje"):
        
        if cancion_detectada.strip().lower() != cancion_objetivo.strip().lower():
            st.error(f"❌ La captura corresponde a '{cancion_detectada}', pero el Daily de hoy es '{cancion_objetivo}'.")
        else:
            rks_base = calcular_rks_puro(accuracy_detectada, constante_activa)
            rango, bono = obtener_rango_y_bono(score_detectado, bad_detectados, miss_detectados)
            rks_final = round(rks_base + bono, 4)
            
            nuevo_score = {
                "usuario": usuario_activo,
                "cancion": cancion_objetivo,
                "score": score_detectado,
                "accuracy": accuracy_detectada,
                "rks": rks_final,
                "rango": rango,
                "fecha": today
            }
            
            # 🔥 GUARDAR DIRECTO EN LA BASE DE DATOS DE STREAMLIT
            # Crea un identificador único en la nube (Usuario_Cancion_Fecha) para no duplicar datos
            doc_id = f"{usuario_activo}_{cancion_objetivo}_{today}"
            doc_ref = conn.collection("scores").document(doc_id)
            doc_ref.set(nuevo_score)
                
            st.success(f"🏆 ¡Score registrado en la nube! RKS final logrado: {rks_final} ({rango})")
            st.balloons()


# =============================================================================
# 4. RENDERS DE LAS TABLAS DE POSICIONES (Desde Base de Datos)
# =============================================================================
st.write("---")
st.header("📊 Tablas de Clasificación")

# 🔥 LEER DIRECTO DESDE LA BASE DE DATOS DE STREAMLIT
scores_ref = conn.collection("scores").stream()
todos_los_scores = [doc.to_dict() for doc in scores_ref]

if todos_los_scores:
    df = pd.DataFrame(todos_los_scores)
    tab_diaria, tab_general = st.tabs(["📅 Desafío de Hoy", "🌍 Récords Generales"])
    
    with tab_diaria:
        # Filtrar por fecha y canción, ordenar de mayor a menor y conservar solo el mejor por usuario
        df_hoy = df[(df["fecha"] == today) & (df["cancion"] == cancion_objetivo)]
        df_hoy = df_hoy.sort_values(by="rks", ascending=False).drop_duplicates(subset=["usuario"], keep="first")
        
        if not df_hoy.empty:
            st.subheader(f"Top del Día - {cancion_objetivo}")
            st.dataframe(df_hoy[["usuario", "score", "accuracy", "rks", "rango"]], use_container_width=True)
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
