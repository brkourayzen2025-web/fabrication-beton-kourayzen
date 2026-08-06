"""Application Streamlit — Production Béton, Chantier Kourayzen.

Point d'entrée. Les autres pages sont dans pages/ et Streamlit les affiche
automatiquement dans la barre latérale.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

# Assurer que les imports relatifs marchent quand Streamlit est lancé
# depuis le dossier racine ou ailleurs.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from models.constants import (  # noqa: E402
    CHANTIER_MARCHE,
    CHANTIER_NOM,
    DB_PATH,
)
from services import auth  # noqa: E402
from services.calcul import fr  # noqa: E402
from services.repositories import (  # noqa: E402
    lister_formules,
    lister_materiaux,
    lister_productions_par_date,
)


# ==================================================================
# Cache
# ==================================================================
@st.cache_data(ttl=60)
def _materiaux_cache():
    return lister_materiaux()


# ==================================================================
# Config globale de la page
# ==================================================================
st.set_page_config(
    page_title="Fabrication Béton — Kourayzen",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================================================================
# LOGIN GATE — bloque la page si pas connecté
# ==================================================================
user = auth.exiger_connexion()
auth.afficher_barre_utilisateur()

# ==================================================================
# Initialisation BD (une seule fois)
# ==================================================================
@st.cache_resource
def _init():
    init_db()
    return True

_init()

# ==================================================================
# En-tête
# ==================================================================
st.title("🏗️ Fabrication Béton")
st.markdown(f"**{CHANTIER_NOM}** · {CHANTIER_MARCHE}")

st.markdown("---")

# ==================================================================
# Statistiques du jour
# ==================================================================
today = date.today().isoformat()
prods_jour = lister_productions_par_date(today)
volume_jour = sum(
    (p.get("volume_reel_m3") or p.get("volume_prevu_m3") or 0.0) for p in prods_jour
)
terminees = sum(1 for p in prods_jour if p["statut"] == "terminee")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Aujourd'hui", f"{len(prods_jour)}", help="Nombre de préparations")
col2.metric("Volume", f"{fr(volume_jour)} m³")
col3.metric("Terminées", f"{terminees}")
col4.metric("En cours", f"{len(prods_jour) - terminees}")

st.markdown("---")

# ==================================================================
# Actions rapides
# ==================================================================
st.subheader("Que voulez-vous faire ?")

col_a, col_b = st.columns(2)

with col_a:
    if st.button(
        "🏗️  Préparer un nouveau mélange",
        type="primary",
        use_container_width=True,
    ):
        st.switch_page("pages/1_🏗️_Préparer_un_mélange.py")

with col_b:
    if st.button(
        "📋  Voir les productions",
        use_container_width=True,
    ):
        st.switch_page("pages/2_📋_Productions.py")

col_c, col_d = st.columns(2)
with col_c:
    if st.button("📦  Stock des matériaux", use_container_width=True):
        st.switch_page("pages/3_📦_Stock.py")
with col_d:
    if st.button("🚚  Engins et godets", use_container_width=True):
        st.switch_page("pages/4_🚚_Engins_et_godets.py")

col_e, col_f = st.columns(2)
with col_e:
    if st.button("🧪  Formules", use_container_width=True):
        st.switch_page("pages/5_🧪_Formules.py")
with col_f:
    if st.button("📊  Tableau de bord", use_container_width=True):
        st.switch_page("pages/6_📊_Tableau_de_bord.py")

col_g, col_h = st.columns(2)
with col_g:
    if st.button("📝  Journal des modifications", use_container_width=True):
        st.switch_page("pages/7_📝_Journal.py")
with col_h:
    if auth.est_admin():
        if st.button("📥  Import Excel (backup)", use_container_width=True):
            st.switch_page("pages/8_📥_Import_Excel.py")

st.markdown("---")

# ==================================================================
# Formules disponibles (aperçu)
# ==================================================================
st.subheader("📚 Formules disponibles")

formules = lister_formules()
if formules:
    for f in formules:
        badge = "🟢 VALIDÉE" if f["statut"] == "validee" else "🟠 À VALIDER"
        with st.expander(f"{badge}  ·  **{f['nom']}**  ({len(f['composition'])} composants)"):
            if f.get("observations"):
                st.caption(f["observations"])
            # Petit tableau des composants
            import pandas as pd
            df_data = []
            mats = {m["id"]: m for m in _materiaux_cache()}
            for c in f["composition"]:
                mat = mats.get(c["materiau_id"])
                df_data.append({
                    "Matériau": mat["nom"] if mat else c["materiau_id"],
                    "Quantité / m³": f"{fr(c['quantite'])} {c['unite']}",
                    "Ordre": c.get("ordre_ajout") or "-",
                })
            st.dataframe(pd.DataFrame(df_data), hide_index=True, use_container_width=True)
else:
    st.info("Aucune formule chargée.")

# ==================================================================
# Info technique en bas
# ==================================================================
with st.sidebar:
    st.markdown("**Info technique**")
    st.caption("Base : PostgreSQL (Supabase)")
