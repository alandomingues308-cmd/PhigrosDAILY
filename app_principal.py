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
if uploaded_file is not None:
    imagen_completa = Image.open(uploaded_file)
    ancho, alto = imagen_completa.size
    
    with st.spinner("Analizando captura..."):
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
        
        # UI de confirmación
        st.subheader("📝 Datos Extraídos")
        col1, col2, col3 = st.columns(3)
        col1.metric("Usuario", usuario_final)
        col2.metric("Score", f"{score_detectado:,}")
        col3.metric("Acc", f"{accuracy_detectada}%")
    
        if st.button("Registrar Puntaje"):
        # Lógica de cálculo (reutilizando tus funciones previas)
            def calcular_rks(acc, const): return round((((acc - 55) / 45) ** 2) * const, 2)
        rks= calcular_rks(accuracy_detectada, constante_activa)
        
        rks_final=rks
    
        nuevo_score = {
            "usuario": usuario_final,
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
