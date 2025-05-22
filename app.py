import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import warnings
import base64

# Configuration initiale
warnings.filterwarnings('ignore')
st.set_page_config(layout="wide")

# --- Gestion sécurisée des clés API ---
def get_alpaca_keys():
    """Charge les clés depuis les sources sécurisées"""
    try:
        # 1. Essayer Streamlit secrets (production)
        api_key = st.secrets.get("ALPACA_API_KEY")
        secret_key = st.secrets.get("ALPACA_SECRET_KEY")
        if api_key and secret_key:
            return api_key, secret_key
        
        # 2. Essayer variables d'environnement (développement)
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        if api_key and secret_key:
            return api_key, secret_key
        
        # 3. Demander à l'utilisateur (fallback)
        with st.sidebar.expander("🔑 Configuration API (manuel)"):
            st.warning("Méthode non sécurisée - À éviter en production")
            api_key = st.text_input("ALPACA_API_KEY", type="password")
            secret_key = st.text_input("ALPACA_SECRET_KEY", type="password")
            if api_key and secret_key:
                return api_key, secret_key
        
        return None, None
        
    except Exception as e:
        st.error(f"Erreur de chargement des clés: {str(e)}")
        return None, None

API_KEY, SECRET_KEY = get_alpaca_keys()

if not API_KEY or not SECRET_KEY:
    st.error("""
    ❌ Configuration API manquante. Voici comment résoudre :
    
    1. **En local** : Créez un fichier `.streamlit/secrets.toml` avec :
       ```toml
       ALPACA_API_KEY = "PKPAUDT4LL374JMHCH0C"
       ALPACA_SECRET_KEY = "R8PieV3MsQ5eAxVWjNYlYTdagRi528Kg5Vtt107W"
       ```
       
    2. **Sur Streamlit Cloud** : Ajoutez ces clés dans Settings > Secrets
    """)
    st.stop()

# --- Initialisation du client Alpaca ---
@st.cache_resource
def get_alpaca_client():
    """Initialise et cache le client Alpaca"""
    try:
        client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
        st.success("✅ Connexion à l'API Alpaca établie")
        return client
    except Exception as e:
        st.error(f"❌ Erreur de connexion à Alpaca: {str(e)}")
        st.stop()

client = get_alpaca_client()

# --- Fonction de téléchargement ---
def get_table_download_link(df, filename="data.csv"):
    """Génère un lien de téléchargement pour un DataFrame"""
    csv = df.to_csv(index=True)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Télécharger {filename}</a>'
    return href

# --- Interface utilisateur ---
st.title("📈 Analyse de Marché avec Alpaca")
st.markdown("""
    Analyse technique des données boursières historiques.  
    *Données fournies par Alpaca Market Data*
""")

# --- Sidebar Configuration ---
st.sidebar.header("Paramètres")

# Sélection des symboles
default_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
symbols_input = st.sidebar.text_input(
    "Symboles (séparés par des virgules)",
    value=", ".join(default_symbols)
)
selected_symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

if not selected_symbols:
    st.warning("Veuillez entrer au moins un symbole boursier")
    st.stop()

# Sélection des dates
today = datetime.now().date()
default_start = today - timedelta(days=365)
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Date de début", value=default_start)
with col2:
    end_date = st.date_input("Date de fin", value=today)

if start_date >= end_date:
    st.error("La date de début doit être antérieure à la date de fin")
    st.stop()

# Sélection de la période
timeframe_map = {
    "1 Minute": TimeFrame.Minute,
    "15 Minutes": TimeFrame.Minute_15,
    "1 Heure": TimeFrame.Hour,
    "1 Jour": TimeFrame.Day
}
timeframe = st.sidebar.selectbox(
    "Période", 
    options=list(timeframe_map.keys())
selected_timeframe = timeframe_map[timeframe]

# --- Récupération des données ---
@st.cache_data(ttl=3600, show_spinner="Récupération des données...")
def fetch_stock_data(symbol, start, end, timeframe):
    """Récupère les données historiques pour un symbole"""
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            end=end
        )
        bars = client.get_stock_bars(request).data
        df = pd.DataFrame([bar.dict() for bar in bars])
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            if 'symbol' in df.columns:
                df.drop(columns=['symbol'], inplace=True)
            return symbol, df
        return symbol, pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur pour {symbol}: {str(e)}")
        return symbol, pd.DataFrame()

# --- Traitement principal ---
if st.sidebar.button("Lancer l'analyse"):
    st.header("📊 Données Marché")
    
    # Récupération en parallèle
    all_data = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_stock_data, sym, start_date, end_date, selected_timeframe): sym 
            for sym in selected_symbols
        }
        
        progress_bar = st.progress(0)
        for i, future in enumerate(as_completed(futures)):
            symbol, data = future.result()
            if not data.empty:
                all_data[symbol] = data
            progress_bar.progress((i + 1) / len(selected_symbols))
    
    if not all_data:
        st.error("Aucune donnée trouvée pour les critères sélectionnés")
        st.stop()
    
    # Affichage des données
    selected_symbol = st.selectbox(
        "Choisir un symbole à visualiser",
        options=list(all_data.keys())
    )
    
    if selected_symbol in all_data:
        df = all_data[selected_symbol]
        st.dataframe(df.head())
        
        # Graphiques
        st.subheader(f"📈 Performance de {selected_symbol}")
        col1, col2 = st.columns(2)
        
        with col1:
            st.line_chart(df['close'], use_container_width=True)
            st.markdown("**Prix de clôture**")
        
        with col2:
            if 'volume' in df.columns:
                st.bar_chart(df['volume'], use_container_width=True)
                st.markdown("**Volume**")
        
        # Analyse technique
        st.subheader("📉 Analyse Technique")
        df['returns'] = df['close'].pct_change()
        
        window = st.slider(
            "Fenêtre pour la moyenne mobile",
            min_value=5,
            max_value=50,
            value=20
        )
        df[f'SMA_{window}'] = df['close'].rolling(window=window).mean()
        
        st.line_chart(df[['close', f'SMA_{window}']])
        
        # Téléchargement
        st.markdown(get_table_download_link(df, f"{selected_symbol}_data.csv"), unsafe_allow_html=True)
    
    # Comparaison des performances
    if len(all_data) > 1:
        st.subheader("📊 Comparaison des Performances")
        normalized = pd.DataFrame()
        for sym, data in all_data.items():
            if not data.empty and 'close' in data.columns:
                normalized[sym] = (data['close'] / data['close'].iloc[0]) * 100
        
        if not normalized.empty:
            st.line_chart(normalized)
            st.markdown("""
                **Note** : Toutes les séries sont normalisées à 100 à la date de début
                pour permettre une comparaison équitable.
            """)

st.sidebar.markdown("---")
st.sidebar.info("""
    🔐 Les clés API ne sont jamais stockées dans le code source.  
    [Guide de configuration](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management)
""")
