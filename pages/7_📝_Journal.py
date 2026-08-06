"""Page "Journal des modifications" : consultation de l'audit log."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services import journal  # noqa: E402

from services import auth  # noqa: E402

st.set_page_config(page_title="Journal", page_icon="📝", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_admin()
auth.afficher_barre_utilisateur()

st.title("📝 Journal des modifications")
st.caption(
    "Historique des créations, éditions, changements de statut et autres actions "
    "importantes effectuées dans l'application."
)


def _pretty(v: str) -> str:
    """Tente de formater comme JSON, sinon renvoie tel quel."""
    try:
        return json.dumps(json.loads(v), indent=2, ensure_ascii=False)
    except Exception:
        return str(v)

# ==================================================================
# Filtres
# ==================================================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    depuis = st.date_input("Depuis", value=date.today() - timedelta(days=30))
with col2:
    jusqua = st.date_input("Jusqu'à", value=date.today())
with col3:
    table_choix = st.selectbox(
        "Table",
        options=["Toutes", "formules", "productions", "engins", "godets"],
    )
with col4:
    utilisateurs = ["Tous"] + journal.lister_utilisateurs()
    user_choix = st.selectbox("Utilisateur", options=utilisateurs)

action_filtre = st.text_input(
    "Filtrer par action (ex: creation, edition_en_place, nouvelle_version, statut_validee)"
)

# ==================================================================
# Chargement
# ==================================================================
entries = journal.lister(
    table_nom=table_choix if table_choix != "Toutes" else None,
    action=action_filtre.strip() or None,
    depuis=depuis.isoformat(),
    jusqua=jusqua.isoformat(),
    utilisateur=user_choix if user_choix != "Tous" else None,
    limite=2000,
)

st.markdown(f"**{len(entries)} entrée(s)**")
st.markdown("---")

if not entries:
    st.info("Aucune entrée pour ces filtres.")
    st.stop()

# ==================================================================
# Affichage : deux modes (tableau + timeline)
# ==================================================================
onglet_timeline, onglet_tableau = st.tabs(["🕒 Timeline", "📊 Tableau"])

with onglet_timeline:
    ICONES = {
        "creation": "➕",
        "edition_en_place": "✏️",
        "nouvelle_version": "🔄",
        "statut_validee": "🟢",
        "statut_a_valider": "🟠",
        "statut_brouillon": "📝",
        "statut_desactivee": "❌",
        "suppression": "🗑️",
    }
    for e in entries[:100]:  # limiter l'affichage timeline
        icone = ICONES.get(e["action"], "•")
        with st.container(border=True):
            col_head, col_body = st.columns([1, 5])
            with col_head:
                st.markdown(f"### {icone}")
                st.caption(e["timestamp"][:19])
            with col_body:
                st.markdown(
                    f"**{e['action']}** dans `{e['table_nom']}` · id `{e['enregistrement_id']}`"
                )
                st.caption(f"par **{e['utilisateur']}**"
                           + (f" · motif : *{e['motif']}*" if e.get("motif") else ""))

                if e.get("ancienne_valeur") or e.get("nouvelle_valeur"):
                    with st.expander("Voir détails", expanded=False):
                        if e.get("ancienne_valeur"):
                            st.markdown("**Ancienne valeur :**")
                            st.code(_pretty(e["ancienne_valeur"]), language="json")
                        if e.get("nouvelle_valeur"):
                            st.markdown("**Nouvelle valeur :**")
                            st.code(_pretty(e["nouvelle_valeur"]), language="json")
    if len(entries) > 100:
        st.info(f"Affichage limité aux 100 premières entrées ({len(entries)} au total). "
                "Utiliser l'onglet Tableau pour voir tout.")

with onglet_tableau:
    df = pd.DataFrame([
        {
            "ID": e["id"],
            "Timestamp": e["timestamp"][:19],
            "Action": e["action"],
            "Table": e["table_nom"],
            "Enreg. ID": e["enregistrement_id"],
            "Utilisateur": e["utilisateur"],
            "Motif": e.get("motif") or "",
        }
        for e in entries
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)
