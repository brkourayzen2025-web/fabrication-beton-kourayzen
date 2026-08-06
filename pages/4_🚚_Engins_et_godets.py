"""Page "Engins et Godets" : CRUD simple avec deux onglets."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services.calcul import fr  # noqa: E402
from services.repositories import (  # noqa: E402
    creer_engin,
    creer_godet,
    lister_engins,
    lister_godets,
    lister_materiaux,
    materiaux_par_id,
    modifier_engin,
    modifier_godet,
)

from services import auth  # noqa: E402

st.set_page_config(page_title="Engins et godets", page_icon="🚚", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_admin()
auth.afficher_barre_utilisateur()

st.title("🚚 Engins et godets")

tab_engins, tab_godets = st.tabs(["🚜  Engins", "🪣  Godets"])

# ==================================================================
# ONGLET ENGINS
# ==================================================================
with tab_engins:
    st.subheader("Liste des engins")

    engins = lister_engins(actifs_seulement=False)
    if engins:
        df_e = pd.DataFrame([
            {
                "ID": e["id"],
                "Nom": e["nom"],
                "Type": e["type_engin"],
                "Marque": e.get("marque") or "-",
                "Modèle": e.get("modele") or "-",
                "Immat.": e.get("immatriculation") or "-",
                "Actif": "✅" if e["actif"] else "❌",
            }
            for e in engins
        ])
        st.dataframe(df_e, hide_index=True, use_container_width=True)
    else:
        st.info("Aucun engin enregistré.")

    st.markdown("---")

    # Ajouter un engin
    with st.expander("➕ Ajouter un engin"):
        with st.form("form_add_engin"):
            col1, col2 = st.columns(2)
            with col1:
                nom_e = st.text_input("Nom *")
                type_e = st.selectbox(
                    "Type",
                    options=["chargeur", "pelleteuse", "autre"],
                )
                marque = st.text_input("Marque")
            with col2:
                modele = st.text_input("Modèle")
                immat = st.text_input("Immatriculation")
                actif = st.checkbox("Actif", value=True)
            obs = st.text_area("Observations", height=68)

            if st.form_submit_button("Enregistrer", type="primary"):
                if not nom_e.strip():
                    st.error("Le nom est requis.")
                else:
                    creer_engin(
                        nom=nom_e.strip(),
                        type_engin=type_e,
                        marque=marque.strip() or None,
                        modele=modele.strip() or None,
                        immatriculation=immat.strip() or None,
                        observations=obs.strip() or None,
                        actif=actif,
                    )
                    st.success("Engin ajouté ✅")
                    st.rerun()

    # Modifier un engin
    if engins:
        with st.expander("✏️ Modifier un engin"):
            engin_id_edit = st.selectbox(
                "Engin à modifier",
                options=[e["id"] for e in engins],
                format_func=lambda x: next(e["nom"] for e in engins if e["id"] == x),
                key="edit_engin_sel",
            )
            e_sel = next(e for e in engins if e["id"] == engin_id_edit)
            with st.form("form_edit_engin"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_e = st.text_input("Nom *", value=e_sel["nom"])
                    type_e = st.selectbox(
                        "Type",
                        options=["chargeur", "pelleteuse", "autre"],
                        index=["chargeur", "pelleteuse", "autre"].index(e_sel["type_engin"]),
                    )
                    marque = st.text_input("Marque", value=e_sel.get("marque") or "")
                with col2:
                    modele = st.text_input("Modèle", value=e_sel.get("modele") or "")
                    immat = st.text_input(
                        "Immatriculation", value=e_sel.get("immatriculation") or ""
                    )
                    actif = st.checkbox("Actif", value=bool(e_sel["actif"]))
                obs = st.text_area("Observations", value=e_sel.get("observations") or "", height=68)

                if st.form_submit_button("Mettre à jour", type="primary"):
                    modifier_engin(
                        engin_id_edit,
                        nom=nom_e.strip(),
                        type_engin=type_e,
                        marque=marque.strip() or None,
                        modele=modele.strip() or None,
                        immatriculation=immat.strip() or None,
                        actif=actif,
                        observations=obs.strip() or None,
                    )
                    st.success("Modifications enregistrées ✅")
                    st.rerun()


# ==================================================================
# ONGLET GODETS
# ==================================================================
with tab_godets:
    st.subheader("Liste des godets")

    godets = lister_godets()
    engins_all = lister_engins(actifs_seulement=False)
    engins_by_id = {e["id"]: e for e in engins_all}
    materiaux = materiaux_par_id()

    if godets:
        df_g = pd.DataFrame([
            {
                "Nom": g["nom"],
                "Engin": engins_by_id.get(g["engin_id"], {}).get("nom", "?"),
                "Matériau": materiaux.get(g["materiau_id"], {}).get("nom", "?"),
                "Capa. mesurée (L)": fr(g["capacite_mesuree_l"]),
                "Coef.": fr(g["coef_remplissage"]),
                "Capa. utile (L)": fr(g["capacite_mesuree_l"] * g["coef_remplissage"]),
                "Type": g.get("type_remplissage") or "ras",
                "Actif": "✅" if g["actif"] else "❌",
            }
            for g in godets
        ])
        st.dataframe(df_g, hide_index=True, use_container_width=True)
    else:
        st.info("Aucun godet enregistré.")

    st.markdown("---")

    # Ajouter un godet
    engins_actifs = [e for e in engins_all if e["actif"]]
    mats_liste = lister_materiaux(actifs_seulement=True)

    if not engins_actifs:
        st.warning("Créez d'abord un engin actif dans l'onglet Engins.")
    else:
        with st.expander("➕ Ajouter un godet"):
            with st.form("form_add_godet"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_g = st.text_input("Nom *")
                    engin_id = st.selectbox(
                        "Engin *",
                        options=[e["id"] for e in engins_actifs],
                        format_func=lambda x: engins_by_id[x]["nom"],
                    )
                    mat_id = st.selectbox(
                        "Matériau *",
                        options=[m["id"] for m in mats_liste],
                        format_func=lambda x: materiaux[x]["nom"],
                    )
                with col2:
                    mode_saisie = st.radio(
                        "Mode de saisie de la capacité",
                        options=["Capacité directe (L)", "N seaux × V litres"],
                        horizontal=True,
                        help="Le mode 'seaux' permet de mesurer la capacité en comptant les seaux vidés dans le godet.",
                    )
                    if mode_saisie == "Capacité directe (L)":
                        capa = st.number_input(
                            "Capacité mesurée (L) *",
                            min_value=1.0,
                            max_value=100000.0,
                            value=1000.0,
                            step=10.0,
                        )
                    else:
                        col_ns, col_vs = st.columns(2)
                        with col_ns:
                            nb_seaux = st.number_input(
                                "Nombre de seaux",
                                min_value=1.0,
                                max_value=1000.0,
                                value=85.0,
                                step=1.0,
                            )
                        with col_vs:
                            vol_seau = st.number_input(
                                "Volume d'un seau (L)",
                                min_value=1.0,
                                max_value=200.0,
                                value=27.0,
                                step=1.0,
                                help="Par défaut 27 L (seau de chantier standard). Modifier si tu utilises un autre seau.",
                            )
                        capa = nb_seaux * vol_seau
                        st.info(f"→ Capacité calculée : **{fr(capa)} L** ({fr(nb_seaux)} × {fr(vol_seau)} L)")
                    coef = st.number_input(
                        "Coefficient de remplissage",
                        min_value=0.1,
                        max_value=1.5,
                        value=1.0,
                        step=0.05,
                    )
                    type_r = st.selectbox(
                        "Type de remplissage",
                        options=["ras", "bombe_leger", "bombe", "personnalise"],
                    )
                obs = st.text_area("Observations", height=68)

                if st.form_submit_button("Enregistrer", type="primary"):
                    if not nom_g.strip():
                        st.error("Le nom est requis.")
                    else:
                        creer_godet(
                            nom=nom_g.strip(),
                            engin_id=engin_id,
                            materiau_id=mat_id,
                            capacite_mesuree_l=capa,
                            coef_remplissage=coef,
                            type_remplissage=type_r,
                            observations=obs.strip() or None,
                        )
                        st.success(f"Godet ajouté (capa utile {fr(capa * coef)} L) ✅")
                        st.rerun()

    # Modifier un godet
    if godets:
        with st.expander("✏️ Modifier un godet"):
            gid = st.selectbox(
                "Godet à modifier",
                options=[g["id"] for g in godets],
                format_func=lambda x: next(g["nom"] for g in godets if g["id"] == x),
                key="edit_godet_sel",
            )
            g_sel = next(g for g in godets if g["id"] == gid)
            with st.form("form_edit_godet"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_g = st.text_input("Nom *", value=g_sel["nom"])
                    engin_id = st.selectbox(
                        "Engin *",
                        options=[e["id"] for e in engins_actifs],
                        format_func=lambda x: engins_by_id[x]["nom"],
                        index=next(
                            (i for i, e in enumerate(engins_actifs) if e["id"] == g_sel["engin_id"]),
                            0,
                        ),
                    )
                    mat_ids = [m["id"] for m in mats_liste]
                    mat_id = st.selectbox(
                        "Matériau *",
                        options=mat_ids,
                        format_func=lambda x: materiaux[x]["nom"],
                        index=mat_ids.index(g_sel["materiau_id"]) if g_sel["materiau_id"] in mat_ids else 0,
                    )
                with col2:
                    mode_saisie_ed = st.radio(
                        "Mode de saisie",
                        options=["Capacité directe (L)", "N seaux × V litres"],
                        horizontal=True,
                        key=f"mode_ed_{gid}",
                    )
                    if mode_saisie_ed == "Capacité directe (L)":
                        capa = st.number_input(
                            "Capacité mesurée (L) *",
                            min_value=1.0,
                            max_value=100000.0,
                            value=float(g_sel["capacite_mesuree_l"]),
                            step=10.0,
                        )
                    else:
                        col_ns2, col_vs2 = st.columns(2)
                        with col_ns2:
                            nb_seaux_ed = st.number_input(
                                "Nombre de seaux",
                                min_value=1.0,
                                max_value=1000.0,
                                value=float(g_sel["capacite_mesuree_l"]) / 27.0,
                                step=1.0,
                                key=f"ns_ed_{gid}",
                            )
                        with col_vs2:
                            vol_seau_ed = st.number_input(
                                "Volume d'un seau (L)",
                                min_value=1.0,
                                max_value=200.0,
                                value=27.0,
                                step=1.0,
                                key=f"vs_ed_{gid}",
                            )
                        capa = nb_seaux_ed * vol_seau_ed
                        st.info(f"→ Capacité calculée : **{fr(capa)} L**")
                    coef = st.number_input(
                        "Coef. remplissage",
                        min_value=0.1,
                        max_value=1.5,
                        value=float(g_sel["coef_remplissage"]),
                        step=0.05,
                    )
                    types_r = ["ras", "bombe_leger", "bombe", "personnalise"]
                    type_r = st.selectbox(
                        "Type de remplissage",
                        options=types_r,
                        index=types_r.index(g_sel.get("type_remplissage") or "ras"),
                    )
                    actif = st.checkbox("Actif", value=bool(g_sel["actif"]))
                obs = st.text_area("Observations", value=g_sel.get("observations") or "", height=68)

                if st.form_submit_button("Mettre à jour", type="primary"):
                    modifier_godet(
                        gid,
                        nom=nom_g.strip(),
                        engin_id=engin_id,
                        materiau_id=mat_id,
                        capacite_mesuree_l=capa,
                        coef_remplissage=coef,
                        type_remplissage=type_r,
                        observations=obs.strip() or None,
                        actif=actif,
                    )
                    st.success(f"Modifications enregistrées (capa utile {fr(capa * coef)} L) ✅")
                    st.rerun()
