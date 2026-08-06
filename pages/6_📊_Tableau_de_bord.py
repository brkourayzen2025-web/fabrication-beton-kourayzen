"""Tableau de bord : production, consommation théorique par matériau, export Excel.

Note : la gestion du stock physique (livraisons, stock restant) est faite
       dans l'application `materiaux_kourayzen` séparément.
       Cette page ne suit QUE les consommations (théoriques et réelles)
       basées sur les productions réalisées.
"""
from __future__ import annotations

import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services.calcul import fr  # noqa: E402
from services.repositories import (  # noqa: E402
    formule_par_id,
    lignes_production,
    lister_productions,
    materiaux_par_id,
)

from services import auth  # noqa: E402

st.set_page_config(page_title="Tableau de bord", page_icon="📊", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_connexion()
auth.afficher_barre_utilisateur()

st.title("📊 Tableau de bord")
st.caption(
    "Suivi des productions et consommations. "
    "Pour la gestion du stock physique (livraisons, bons de commande), "
    "utilise ton application `materiaux_kourayzen`."
)


# ==================================================================
# Filtre période
# ==================================================================
col_p1, col_p2, col_p3 = st.columns([2, 2, 3])
with col_p1:
    depuis = st.date_input("Depuis", value=date.today() - timedelta(days=30))
with col_p2:
    jusqua = st.date_input("Jusqu'à", value=date.today())
with col_p3:
    preset = st.selectbox(
        "Période rapide",
        options=[
            "Personnalisée",
            "Aujourd'hui",
            "7 derniers jours",
            "30 derniers jours",
            "Depuis début du mois",
        ],
    )
    if preset == "Aujourd'hui":
        depuis = jusqua = date.today()
    elif preset == "7 derniers jours":
        depuis = date.today() - timedelta(days=7)
        jusqua = date.today()
    elif preset == "30 derniers jours":
        depuis = date.today() - timedelta(days=30)
        jusqua = date.today()
    elif preset == "Depuis début du mois":
        depuis = date.today().replace(day=1)
        jusqua = date.today()

st.markdown(f"**Période analysée : {depuis} → {jusqua}**")
st.markdown("---")


# ==================================================================
# Chargement données
# ==================================================================
@st.cache_data(ttl=15)
def _load(depuis_iso: str, jusqua_iso: str):
    prods_all = lister_productions(limite=2000)
    prods = [
        p for p in prods_all
        if depuis_iso <= p["date"] <= jusqua_iso
    ]
    all_lignes = []
    for p in prods:
        for l in lignes_production(p["id"]):
            l["_date"] = p["date"]
            l["_statut"] = p["statut"]
            l["_zone"] = p.get("zone_mise_en_oeuvre")
            l["_volume"] = p.get("volume_reel_m3") or p.get("volume_prevu_m3")
            l["_formule_id"] = p["formule_id"]
            all_lignes.append(l)
    return prods, all_lignes

prods, lignes = _load(depuis.isoformat(), jusqua.isoformat())

formules_noms = {}
for p in prods:
    if p["formule_id"] not in formules_noms:
        f = formule_par_id(p["formule_id"])
        formules_noms[p["formule_id"]] = f["nom"] if f else p["formule_id"]

mats = materiaux_par_id()


# ==================================================================
# BLOC 1 : KPIs de production
# ==================================================================
st.subheader("🏗️ Production")

nb_prods = len(prods)
volume_total = sum(p.get("volume_reel_m3") or p["volume_prevu_m3"] for p in prods)
nb_terminees = sum(1 for p in prods if p["statut"] == "terminee")
nb_annulees = sum(1 for p in prods if p["statut"] == "annulee")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Préparations", nb_prods)
col2.metric("Volume total", f"{fr(volume_total)} m³")
col3.metric("Terminées", nb_terminees)
col4.metric("Annulées", nb_annulees)


# ==================================================================
# BLOC 2 : Graphes de production
# ==================================================================
if prods:
    df_prods = pd.DataFrame([
        {
            "Date": p["date"],
            "Volume (m³)": p.get("volume_reel_m3") or p["volume_prevu_m3"],
            "Type": formules_noms.get(p["formule_id"], p["formule_id"]),
            "Statut": p["statut"],
            "Zone": p.get("zone_mise_en_oeuvre") or "—",
        }
        for p in prods
    ])

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Volume par jour**")
        par_jour = df_prods.groupby("Date")["Volume (m³)"].sum().reset_index()
        st.bar_chart(par_jour, x="Date", y="Volume (m³)")

    with col_b:
        st.markdown("**Volume par type de béton**")
        par_type = df_prods.groupby("Type")["Volume (m³)"].sum().reset_index()
        st.bar_chart(par_type, x="Type", y="Volume (m³)")

    col_c, col_d = st.columns(2)
    with col_c:
        st.markdown("**Volume par zone de mise en œuvre**")
        par_zone = df_prods.groupby("Zone")["Volume (m³)"].sum().reset_index()
        st.bar_chart(par_zone, x="Zone", y="Volume (m³)")
    with col_d:
        st.markdown("**Nombre de préparations par jour**")
        cnt_jour = df_prods.groupby("Date").size().reset_index(name="Nombre")
        st.bar_chart(cnt_jour, x="Date", y="Nombre")


# ==================================================================
# BLOC 3 : Consommation par matériau (théorique vs réel)
# ==================================================================
st.markdown("---")
st.subheader("📉 Consommation par matériau")
st.caption(
    "Ces valeurs viennent des productions enregistrées dans cette app. "
    "Elles peuvent servir à mettre à jour manuellement ton stock dans `materiaux_kourayzen`."
)

if lignes:
    conso_map: dict[str, dict] = {}
    for l in lignes:
        mid = l["materiau_id"]
        if mid not in conso_map:
            conso_map[mid] = {
                "theo": 0.0, "reel": 0.0,
                "unite_theo": l.get("unite_theorique"),
            }
        conso_map[mid]["theo"] += float(l.get("quantite_theorique") or 0)
        if l.get("quantite_reelle") is not None:
            conso_map[mid]["reel"] += float(l["quantite_reelle"])

    rows = []
    for mid, v in conso_map.items():
        m = mats.get(mid, {})
        rows.append({
            "Matériau": m.get("nom", mid),
            "Théorique": v["theo"],
            "Réel": v["reel"],
            "Unité": v["unite_theo"] or m.get("unite_stock") or "?",
            "Écart": v["reel"] - v["theo"] if v["reel"] else None,
            "Écart %": (
                (v["reel"] - v["theo"]) / v["theo"] * 100
                if v["theo"] and v["reel"] else None
            ),
        })
    df_conso = pd.DataFrame(rows)

    def _fmt(v):
        return fr(v) if v is not None else "-"

    df_conso_disp = df_conso.copy()
    df_conso_disp["Théorique"] = df_conso_disp["Théorique"].apply(_fmt)
    df_conso_disp["Réel"] = df_conso_disp["Réel"].apply(lambda v: _fmt(v) if v > 0 else "-")
    df_conso_disp["Écart"] = df_conso_disp["Écart"].apply(_fmt)
    df_conso_disp["Écart %"] = df_conso_disp["Écart %"].apply(
        lambda v: f"{v:+.1f} %" if v is not None else "-"
    )
    st.dataframe(df_conso_disp, hide_index=True, use_container_width=True)

    df_chart = df_conso[df_conso["Théorique"] > 0].copy()
    if not df_chart.empty:
        st.bar_chart(
            df_chart.set_index("Matériau")[["Théorique", "Réel"]],
            height=300,
        )
else:
    st.info("Aucune production dans la période.")


# ==================================================================
# BLOC 4 : Export Excel
# ==================================================================
st.markdown("---")
st.subheader("📤 Export Excel")

st.caption("Génère un fichier Excel avec les productions et le détail des matériaux consommés sur la période.")

if st.button("📥 Générer le fichier Excel", type="primary"):
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Onglet Productions
        if prods:
            df_p = pd.DataFrame([
                {
                    "Date": p["date"],
                    "Heure": p["heure"],
                    "Type de béton": formules_noms.get(p["formule_id"], p["formule_id"]),
                    "Volume prévu (m³)": p["volume_prevu_m3"],
                    "Volume réel (m³)": p.get("volume_reel_m3"),
                    "Statut": p["statut"],
                    "Zone mise en œuvre": p.get("zone_mise_en_oeuvre"),
                    "Zone mélange": p.get("zone_melange"),
                    "Opérateur": p.get("operateur"),
                    "Observation": p.get("observation"),
                    "ID": p["id"],
                }
                for p in prods
            ])
            df_p.to_excel(writer, sheet_name="Productions", index=False)

        # Onglet Détails matériaux
        if lignes:
            df_l = pd.DataFrame([
                {
                    "Production ID": l["production_id"],
                    "Date": l["_date"],
                    "Matériau": mats.get(l["materiau_id"], {}).get("nom", l["materiau_id"]),
                    "Qté théorique": l.get("quantite_theorique"),
                    "Qté réelle": l.get("quantite_reelle"),
                    "Unité": l.get("unite_theorique"),
                    "Nb godets théo": l.get("nb_godets_theorique"),
                    "Nb godets réel": l.get("nb_godets_reel"),
                    "Nb sacs théo": l.get("nb_sacs_theorique"),
                    "Nb sacs réel": l.get("nb_sacs_reel"),
                    "Écart absolu": l.get("ecart_absolu"),
                    "Écart %": l.get("ecart_pct"),
                }
                for l in lignes
            ])
            df_l.to_excel(writer, sheet_name="Détails matériaux", index=False)

        # Onglet Consommation totale par matériau (pour report dans materiaux_kourayzen)
        if lignes:
            conso_map: dict[str, dict] = {}
            for l in lignes:
                mid = l["materiau_id"]
                if mid not in conso_map:
                    conso_map[mid] = {"theo": 0.0, "reel": 0.0}
                conso_map[mid]["theo"] += float(l.get("quantite_theorique") or 0)
                if l.get("quantite_reelle") is not None:
                    conso_map[mid]["reel"] += float(l["quantite_reelle"])

            df_c = pd.DataFrame([
                {
                    "Matériau": mats.get(mid, {}).get("nom", mid),
                    "Unité": mats.get(mid, {}).get("unite_stock", "?"),
                    "Consommation théorique": v["theo"],
                    "Consommation réelle": v["reel"] if v["reel"] > 0 else None,
                    "Consommation à déduire du stock":
                        v["reel"] if v["reel"] > 0 else v["theo"],
                }
                for mid, v in conso_map.items()
            ])
            df_c.to_excel(writer, sheet_name="Conso à déduire du stock", index=False)

    buffer.seek(0)
    filename = f"production_beton_kourayzen_{depuis.isoformat()}_{jusqua.isoformat()}.xlsx"

    st.download_button(
        label=f"💾 Télécharger {filename}",
        data=buffer,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.success(
        "Fichier Excel prêt — clique pour télécharger ↑\n\n"
        "L'onglet **« Conso à déduire du stock »** est prêt à être utilisé "
        "pour mettre à jour ton stock dans `materiaux_kourayzen`."
    )
