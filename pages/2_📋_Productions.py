"""Page "Productions" : liste par date + écran de saisie des réels.

Deux modes :
 1. Liste des productions du jour (par défaut)
 2. Saisie des quantités réelles pour une production sélectionnée
    (activé via session_state.prod_active ou clic sur une production)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services.calcul import (  # noqa: E402
    ecart_godets,
    ecart_quantite,
    ecart_sacs,
    fr,
    fr_signe,
)
from services.repositories import (  # noqa: E402
    formule_par_id,
    lignes_production,
    lister_engins,
    lister_productions_par_date,
    lister_godets,
    maj_ligne_reels,
    materiaux_par_id,
    production_par_id,
    terminer_production,
    annuler_production,
)
from models.constants import SEUIL_ECART_ALERTE_PCT  # noqa: E402

from services import auth  # noqa: E402

st.set_page_config(page_title="Productions", page_icon="📋", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_connexion()
auth.afficher_barre_utilisateur()

st.title("📋 Productions")


# ==================================================================
# Mode : liste ou détail ?
# ==================================================================
prod_active = st.session_state.get("prod_active")

if prod_active:
    # ==============================================================
    # MODE DÉTAIL — SAISIE DES RÉELS
    # ==============================================================
    prod = production_par_id(prod_active)
    if not prod:
        st.error("Production introuvable.")
        st.session_state.prod_active = None
        st.stop()

    # Bouton retour à la liste
    if st.button("← Retour à la liste"):
        st.session_state.prod_active = None
        st.rerun()

    lignes = lignes_production(prod_active)
    mats = materiaux_par_id()
    godets = {g["id"]: g for g in lister_godets()}
    formule = formule_par_id(prod["formule_id"])

    # En-tête
    st.subheader(formule["nom"] if formule else prod["formule_id"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Date", prod["date"])
    col2.metric("Heure", prod["heure"])
    col3.metric("Volume prévu", f"{fr(prod['volume_prevu_m3'])} m³")
    col4.metric(
        "Statut",
        "✅ Terminée" if prod["statut"] == "terminee" else "🟠 En cours",
    )

    if prod["statut"] == "terminee":
        st.info("Cette production est déjà terminée. Les valeurs affichées sont figées.")

    st.markdown("---")
    st.subheader("Volume réel préparé")
    vol_reel = st.number_input(
        "Volume réellement préparé (m³)",
        min_value=0.0,
        max_value=200.0,
        value=float(prod.get("volume_reel_m3") or prod["volume_prevu_m3"]),
        step=0.5,
        disabled=(prod["statut"] == "terminee"),
    )

    st.markdown("---")
    st.subheader("Quantités réellement utilisées")

    # Pour chaque ligne, saisie + affichage de l'écart en direct
    inputs_reels: dict[int, dict] = {}
    for l in lignes:
        mat = mats.get(l["materiau_id"], {"nom": l["materiau_id"], "categorie": "autre"})
        godet = godets.get(l["godet_id"]) if l.get("godet_id") else None

        with st.container(border=True):
            st.markdown(f"### {mat['nom'].upper()}")

            # Déterminer le type de saisie
            if l.get("nb_godets_theorique") is not None:
                # Godets
                theo = float(l["nb_godets_theorique"])
                unite = "godets"
                sub = (
                    f"Théorique : **{fr(theo)} godets** "
                    f"({l['godets_complets_theorique']} complets + "
                    f"{l['pct_dernier_godet_theorique']:.0f} %)"
                )
                st.caption(sub)
                default = float(l.get("nb_godets_reel") or theo)
                saisi = st.number_input(
                    f"Réellement utilisé ({unite})",
                    min_value=0.0,
                    max_value=100.0,
                    value=default,
                    step=0.01,
                    format="%.2f",
                    key=f"reel_{l['id']}",
                    disabled=(prod["statut"] == "terminee"),
                )
                # Calcul écart
                if godet:
                    capa_utile = godet["capacite_mesuree_l"] * godet["coef_remplissage"]
                    ec = ecart_godets(theo, saisi, capa_utile)
                    hors = abs(ec["ecart_pct"]) > SEUIL_ECART_ALERTE_PCT
                    msg = (
                        f"Écart : **{fr_signe(ec['ecart_godets'])} godet(s)** · "
                        f"{fr_signe(ec['ecart_litres'])} L · "
                        f"**{fr_signe(ec['ecart_pct'])} %**"
                    )
                    (st.error if hors else st.success)(("⚠️  " if hors else "✅ ") + msg)
                    inputs_reels[l["id"]] = {
                        "quantite_reelle": saisi * capa_utile,
                        "nb_godets_reel": saisi,
                        "nb_sacs_reel": None,
                        "ecart_absolu": ec["ecart_litres"],
                        "ecart_pct": ec["ecart_pct"],
                    }
                else:
                    st.warning("Godet manquant — impossible de calculer l'écart en litres.")
                    inputs_reels[l["id"]] = {
                        "quantite_reelle": None,
                        "nb_godets_reel": saisi,
                        "nb_sacs_reel": None,
                        "ecart_absolu": None,
                        "ecart_pct": None,
                    }
            elif l.get("nb_sacs_theorique") is not None:
                # Sacs
                theo = float(l["nb_sacs_theorique"])
                unite = "sacs"
                st.caption(
                    f"Théorique : **{fr(theo)} sacs** ({fr(l['quantite_theorique'])} kg)"
                )
                default = float(l.get("nb_sacs_reel") or theo)
                saisi = st.number_input(
                    f"Réellement utilisé ({unite})",
                    min_value=0.0,
                    max_value=1000.0,
                    value=default,
                    step=1.0,
                    key=f"reel_{l['id']}",
                    disabled=(prod["statut"] == "terminee"),
                )
                ec = ecart_sacs(theo, saisi, prod["poids_sac_ciment_kg"])
                hors = abs(ec["ecart_pct"]) > SEUIL_ECART_ALERTE_PCT
                msg = (
                    f"Écart : **{fr_signe(ec['ecart_sacs'])} sac(s)** · "
                    f"{fr_signe(ec['ecart_kg'])} kg · "
                    f"**{fr_signe(ec['ecart_pct'])} %**"
                )
                (st.error if hors else st.success)(("⚠️  " if hors else "✅ ") + msg)
                inputs_reels[l["id"]] = {
                    "quantite_reelle": saisi * prod["poids_sac_ciment_kg"],
                    "nb_godets_reel": None,
                    "nb_sacs_reel": saisi,
                    "ecart_absolu": ec["ecart_kg"],
                    "ecart_pct": ec["ecart_pct"],
                }
            else:
                # Eau / adjuvant / autre — saisie directe en unité
                theo = float(l["quantite_theorique"])
                unite = l["unite_theorique"]
                st.caption(f"Théorique : **{fr(theo)} {unite}**")
                default = float(l.get("quantite_reelle") or theo)
                saisi = st.number_input(
                    f"Réellement utilisé ({unite})",
                    min_value=0.0,
                    max_value=100000.0,
                    value=default,
                    step=0.1,
                    key=f"reel_{l['id']}",
                    disabled=(prod["statut"] == "terminee"),
                )
                ec = ecart_quantite(theo, saisi)
                hors = abs(ec["ecart_pct"]) > SEUIL_ECART_ALERTE_PCT
                msg = (
                    f"Écart : **{fr_signe(ec['ecart_absolu'])} {unite}** · "
                    f"**{fr_signe(ec['ecart_pct'])} %**"
                )
                (st.error if hors else st.success)(("⚠️  " if hors else "✅ ") + msg)
                inputs_reels[l["id"]] = {
                    "quantite_reelle": saisi,
                    "nb_godets_reel": None,
                    "nb_sacs_reel": None,
                    "ecart_absolu": ec["ecart_absolu"],
                    "ecart_pct": ec["ecart_pct"],
                }

    st.markdown("---")

    if prod["statut"] != "terminee":
        col_a, col_b = st.columns([1, 2])
        with col_a:
            if st.button("🗑️  Annuler la production", use_container_width=True):
                annuler_production(prod_active)
                st.session_state.prod_active = None
                st.warning("Production annulée.")
                st.rerun()
        with col_b:
            if st.button(
                "💾  Enregistrer et terminer",
                type="primary",
                use_container_width=True,
            ):
                for ligne_id, vals in inputs_reels.items():
                    maj_ligne_reels(ligne_id, **vals)
                terminer_production(prod_active, volume_reel_m3=vol_reel)
                st.session_state.prod_active = None
                st.success("✅ Production terminée !")
                st.balloons()
                st.rerun()

else:
    # ==============================================================
    # MODE LISTE
    # ==============================================================
    st.subheader("Filtrer par date")
    d = st.date_input("Date", value=date.today())
    prods = lister_productions_par_date(d.isoformat())

    if not prods:
        st.info("Aucune production pour cette date.")
    else:
        # Résumé
        col1, col2, col3 = st.columns(3)
        col1.metric("Préparations", f"{len(prods)}")
        vol_tot = sum(p.get("volume_reel_m3") or p["volume_prevu_m3"] for p in prods)
        col2.metric("Volume total", f"{fr(vol_tot)} m³")
        col3.metric("Terminées", f"{sum(1 for p in prods if p['statut']=='terminee')}")

        st.markdown("---")

        # Charger les noms de formules
        formules = {}

        st.subheader("Liste des productions")
        for p in prods:
            if p["formule_id"] not in formules:
                f = formule_par_id(p["formule_id"])
                formules[p["formule_id"]] = f["nom"] if f else p["formule_id"]

            statut_icon = "✅" if p["statut"] == "terminee" else "🟠"
            statut_txt = "TERMINÉE" if p["statut"] == "terminee" else ("ANNULÉE" if p["statut"] == "annulee" else "EN COURS")
            vol = p.get("volume_reel_m3") or p["volume_prevu_m3"]

            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"**{statut_icon} {formules[p['formule_id']]}**  ·  `{statut_txt}`")
                    st.caption(
                        f"{p['heure']}  ·  {fr(vol)} m³"
                        + (f"  ·  📍 {p['zone_mise_en_oeuvre']}" if p.get('zone_mise_en_oeuvre') else "")
                        + (f"  ·  👤 {p['operateur']}" if p.get('operateur') else "")
                    )
                with col_btn:
                    if st.button("Ouvrir →", key=f"open_{p['id']}", use_container_width=True):
                        st.session_state.prod_active = p["id"]
                        st.rerun()
