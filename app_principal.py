import streamlit as st
import random
import json
import datetime
import pytz

# Configuración de zona horaria México
mx_tz = pytz.timezone('America/Mexico_City')

@st.cache_data
def load_songs():
    with open("phigros_songs.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)
songs = load_songs()

st.title("🎵 Canción del Día - Phigros")

# Obtenemos la fecha actual en México
today = datetime.datetime.now(mx_tz).strftime("%Y-%m-%d")

# Usamos la fecha como 'seed' para que todos vean la misma canción el mismo día
# y para que cambie automáticamente al llegar a las 00:00
random.seed(today)
daily_song = random.choice(songs)

with open("daily_backup.json","w",encoding="utf-8-sig") as f:
    json.dump(daily_song,f,ensure_ascii=False,indent=2)

st.subheader(f"La canción elegida para hoy, {today}, es:")

diff_parts = []
if daily_song.get("IN") is not None: diff_parts.append(f"IN: {daily_song['IN']}")
if daily_song.get("AT") is not None: diff_parts.append(f"AT: {daily_song['AT']}")
diff_string = " - ".join(diff_parts)

st.info(f"👉 **{daily_song['title']} / ({diff_string})**")
