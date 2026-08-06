"""Page "Stock" — gestion locale du stock des matériaux.

Interface simplifiée :
  - 📊 Situation : état actuel de chaque matériau
  - ➕ Entrée matériau : livraison arrivée sur chantier
  - ✏️ Ajustement : inventaire, casse, correction manuelle
  - ⚙️ Configuration : stock initial + seuil d'alerte
  - 📜 Historique : tous les mouvements

Les SORTIES sont créées AUTOMATIQUEMENT quand une production est terminée
(à partir de la page Productions).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services.calcul import fr  # noqa: E402
from services.repositories import lister_materiaux  # noqa: E402
from services.stock import (  # noqa: E402
    TYPE_AJUSTEMENT_NEG,
    TYPE_AJUSTEMENT_POS,
    TYPE_ENTREE,
    TYPE_SORTIE,
    TYPE_STOCK_INITIAL,
    config_par_id,
    config_materiau,
    enregistrer_ajustement,
    enregistrer_entree,
    enregistrer_stock_initial,
    lister_configs,
    lister_mouvements,
    situation,
    situations_toutes,
)

from services import auth  # noqa: E402

st.set_page_config(page_title="Stock", page_icon="📦", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_connexion()
auth.afficher_barre_utilisateur()

st.title("📦 Stock des matériaux")
st.caption(
    "Suivi indépendant du stock utilisé par la fabrication du béton. "
    "Les sorties sont déduites automatiquement quand tu termines une production."
)


materiaux = lister_materiaux(actifs_seulement=True)
mat_by_id = {m["id"]: m for m in materiaux}

if not materiaux:
    st.error("Aucun matériau enregistré.")
    st.stop()

if auth.est_admin():
    tab_vue, tab_entree, tab_ajust, tab_config, tab_hist = st.tabs(
        ["📊 Situation", "➕ Entrée", "✏️ Ajustement", "⚙️ Configuration", "📜 Historique"]
    )
else:
    tab_vue, tab_entree, tab_ajust, tab_hist = st.tabs(
        ["📊 Situation", "➕ Entrée", "✏️ Ajustement", "📜 Historique"]
    )
    tab_config = None


# ==================================================================
# ONGLET 1 : SITUATION ACTUELLE
# ==================================================================
with tab_vue:
    st.subheader("État actuel du stock")

    situations = situations_toutes()
    if not situations:
        st.info(
            "Aucun matériau configuré pour le stock. "
            "Va sur l'onglet **⚙️ Configuration** pour commencer."
        )
    else:
        # Alertes
        alertes = [
            mat_by_id.get(s["materiau_id"], {}).get("nom", s["materiau_id"])
            for s in situations if s["sous_seuil"]
        ]
        if alertes:
            st.error(f"🔴 **Sous seuil d'alerte** : {', '.join(alertes)}")

        # Cartes visuelles pour chaque matériau
        for s in situations:
            m = mat_by_id.get(s["materiau_id"], {})
            nom = m.get("nom", s["materiau_id"])

            if s["sous_seuil"]:
                couleur = "#C62828"  # rouge
                statut = "🔴"
            elif s["seuil_alerte"] and s["stock_actuel"] < s["seuil_alerte"] * 1.2:
                couleur = "#EF6C00"  # orange
                statut = "🟠"
            else:
                couleur = "#2E7D32"  # vert
                statut = "🟢"

            with st.container(border=True):
                col_nom, col_val, col_det = st.columns([2, 2, 3])
                with col_nom:
                    st.markdown(f"### {statut} {nom}")
                    if s["seuil_alerte"]:
                        st.caption(f"Seuil d'alerte : {fr(s['seuil_alerte'])} {s['unite']}")
                with col_val:
                    st.markdown(
                        f"<h2 style='color:{couleur}; margin:0;'>{fr(s['stock_actuel'])} {s['unite']}</h2>",
                        unsafe_allow_html=True,
                    )
                    st.caption("Stock actuel")
                with col_det:
                    st.markdown(
                        f"""
                        - **Stock initial** : {fr(s['stock_initial'])}
                        - **Entrées** : +{fr(s['entrees'])}
                        - **Sorties** (productions) : −{fr(s['sorties'])}
                        - **Ajustements** : +{fr(s['ajustements_pos'])} / −{fr(s['ajustements_neg'])}
                        """
                    )


# ==================================================================
# ONGLET 2 : ENTRÉE (livraison)
# ==================================================================
with tab_entree:
    st.subheader("➕ Enregistrer une entrée de matériau")
    st.caption("Utilise ce formulaire chaque fois qu'un camion de sable, ciment, etc. arrive sur le chantier.")

    configs = lister_configs()
    if not configs:
        st.warning("Configure d'abord au moins un matériau dans l'onglet **⚙️ Configuration**.")
    else:
        with st.form("form_entree"):
            mat_ids = [c["materiau_id"] for c in configs]

            col1, col2 = st.columns(2)
            with col1:
                mat_id = st.selectbox(
                    "Matériau",
                    options=mat_ids,
                    format_func=lambda x: mat_by_id.get(x, {}).get("nom", x),
                )
                unite_cfg = next(c["unite"] for c in configs if c["materiau_id"] == mat_id)
                date_e = st.date_input("Date de l'entrée", value=date.today())
            with col2:
                quantite = st.number_input(
                    f"Quantité reçue ({unite_cfg})",
                    min_value=0.0,
                    max_value=10_000_000.0,
                    value=1000.0,
                    step=100.0,
                )
                obs = st.text_input(
                    "Observations (facultatif)",
                    placeholder="ex: BL n°123 - Fournisseur ABC",
                )

            if st.form_submit_button("Enregistrer l'entrée", type="primary"):
                if quantite <= 0:
                    st.error("La quantité doit être > 0.")
                else:
                    enregistrer_entree(
                        materiau_id=mat_id,
                        quantite=quantite,
                        unite=unite_cfg,
                        date_str=date_e.isoformat(),
                        observation=obs.strip() or None,
                        utilisateur=auth.username_pour_journal(),
                    )
                    s = situation(mat_id)
                    st.success(
                        f"✅ +{fr(quantite)} {unite_cfg} pour **{mat_by_id[mat_id]['nom']}**\n\n"
                        f"Stock actuel : **{fr(s['stock_actuel'])} {s['unite']}**"
                    )
                    st.rerun()


# ==================================================================
# ONGLET 3 : AJUSTEMENT MANUEL
# ==================================================================
with tab_ajust:
    st.subheader("✏️ Ajuster manuellement un stock")
    st.caption("Pour inventaire physique, casse d'un sac, sac ouvert non utilisé, etc. Motif obligatoire.")

    configs = lister_configs()
    if not configs:
        st.warning("Configure d'abord au moins un matériau.")
    else:
        with st.form("form_ajust"):
            mat_id = st.selectbox(
                "Matériau",
                options=[c["materiau_id"] for c in configs],
                format_func=lambda x: mat_by_id.get(x, {}).get("nom", x),
                key="aj_mat",
            )
            unite_cfg = next(c["unite"] for c in configs if c["materiau_id"] == mat_id)
            s_actuel = situation(mat_id)
            st.info(f"Stock actuel : **{fr(s_actuel['stock_actuel'])} {s_actuel['unite']}**")

            col1, col2 = st.columns(2)
            with col1:
                sens = st.radio(
                    "Sens de l'ajustement",
                    options=["Ajouter au stock (+)", "Retirer du stock (−)"],
                    horizontal=False,
                )
                quantite = st.number_input(
                    f"Quantité ({unite_cfg})",
                    min_value=0.0,
                    value=100.0,
                    step=10.0,
                )
            with col2:
                date_a = st.date_input("Date", value=date.today(), key="aj_date")

            motif = st.text_area(
                "Motif (obligatoire) *",
                placeholder="ex: inventaire physique du 25/07, casse d'un sac ciment...",
                height=68,
            )

            if st.form_submit_button("Enregistrer l'ajustement", type="primary"):
                if not motif.strip():
                    st.error("Le motif est obligatoire.")
                elif quantite <= 0:
                    st.error("La quantité doit être > 0.")
                else:
                    signe = 1 if sens.startswith("Ajouter") else -1
                    enregistrer_ajustement(
                        materiau_id=mat_id,
                        quantite=signe * quantite,
                        unite=unite_cfg,
                        date_str=date_a.isoformat(),
                        motif=motif.strip(),
                        utilisateur=auth.username_pour_journal(),
                    )
                    s = situation(mat_id)
                    st.success(
                        f"✅ Ajustement {'+' if signe > 0 else '−'}{fr(quantite)} {unite_cfg}\n\n"
                        f"Stock actuel : **{fr(s['stock_actuel'])} {s['unite']}**"
                    )
                    st.rerun()


# ==================================================================
# ONGLET 4 : CONFIGURATION
# ==================================================================
with tab_config:
    st.subheader("⚙️ Configurer un matériau pour le suivi de stock")
    st.caption(
        "À faire une fois par matériau, au démarrage. "
        "Renseigne l'unité, le stock initial disponible et le seuil d'alerte."
    )

    with st.form("form_config"):
        mat_id_cfg = st.selectbox(
            "Matériau à configurer",
            options=[m["id"] for m in materiaux],
            format_func=lambda x: mat_by_id[x]["nom"],
        )
        existant = config_par_id(mat_id_cfg)
        unite_defaut = mat_by_id[mat_id_cfg]["unite_stock"]

        col1, col2, col3 = st.columns(3)
        with col1:
            unite = st.text_input(
                "Unité",
                value=(existant["unite"] if existant else unite_defaut),
                help="kg pour granulats/ciment, L pour eau/adjuvant",
            )
        with col2:
            seuil = st.number_input(
                "Seuil d'alerte",
                min_value=0.0,
                max_value=10_000_000.0,
                value=float(existant["seuil_alerte"]) if (existant and existant["seuil_alerte"]) else 0.0,
                step=100.0,
                help="Alerte affichée si stock < seuil. 0 = pas d'alerte.",
            )
        with col3:
            deja_init = False
            if existant:
                # Vérifier si stock initial déjà enregistré
                mvts = lister_mouvements(
                    materiau_id=mat_id_cfg,
                    types=[TYPE_STOCK_INITIAL],
                    limite=1,
                )
                deja_init = len(mvts) > 0

            stock_init = st.number_input(
                "Stock initial déjà en place",
                min_value=0.0,
                max_value=10_000_000.0,
                value=0.0,
                step=100.0,
                help="À renseigner UNE SEULE FOIS. Pour les ajustements ultérieurs, utilise l'onglet Ajustement.",
                disabled=deja_init,
            )
            if deja_init:
                st.caption("✓ Stock initial déjà enregistré")

        if st.form_submit_button("Enregistrer la configuration", type="primary"):
            config_materiau(
                materiau_id=mat_id_cfg,
                unite=unite.strip() or unite_defaut,
                seuil_alerte=seuil if seuil > 0 else None,
            )
            if stock_init > 0 and not deja_init:
                try:
                    enregistrer_stock_initial(
                        materiau_id=mat_id_cfg,
                        quantite=stock_init,
                        unite=unite.strip() or unite_defaut,
                        date_str=date.today().isoformat(),
                        utilisateur=auth.username_pour_journal(),
                    )
                    st.success(f"Config + stock initial enregistrés pour **{mat_by_id[mat_id_cfg]['nom']}**")
                except ValueError as e:
                    st.warning(f"Config enregistrée. Stock initial : {e}")
            else:
                st.success(f"Configuration enregistrée pour **{mat_by_id[mat_id_cfg]['nom']}**")
            st.rerun()

    st.markdown("---")
    st.markdown("**Matériaux déjà configurés :**")
    configs = lister_configs()
    if configs:
        df = pd.DataFrame([
            {
                "Matériau": mat_by_id.get(c["materiau_id"], {}).get("nom", c["materiau_id"]),
                "Unité": c["unite"],
                "Seuil alerte": fr(c["seuil_alerte"]) if c["seuil_alerte"] else "-",
            }
            for c in configs
        ])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.caption("Aucun matériau configuré.")


# ==================================================================
# ONGLET 5 : HISTORIQUE
# ==================================================================
with tab_hist:
    st.subheader("📜 Historique des mouvements")

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 2])
    with col_f1:
        mat_f = st.selectbox(
            "Matériau",
            options=[None] + [m["id"] for m in materiaux],
            format_func=lambda x: "Tous" if x is None else mat_by_id[x]["nom"],
        )
    with col_f2:
        depuis = st.date_input("Depuis", value=date.today() - timedelta(days=30), key="hist_depuis")
    with col_f3:
        jusqua = st.date_input("Jusqu'à", value=date.today(), key="hist_jusqua")
    with col_f4:
        types_choix = st.multiselect(
            "Types",
            options=[TYPE_ENTREE, TYPE_SORTIE, TYPE_AJUSTEMENT_POS, TYPE_AJUSTEMENT_NEG, TYPE_STOCK_INITIAL],
            default=[TYPE_ENTREE, TYPE_SORTIE, TYPE_AJUSTEMENT_POS, TYPE_AJUSTEMENT_NEG],
            format_func=lambda x: {
                TYPE_ENTREE: "➕ Entrées",
                TYPE_SORTIE: "🏗️ Sorties (prod)",
                TYPE_AJUSTEMENT_POS: "🔧 Ajust. +",
                TYPE_AJUSTEMENT_NEG: "🔧 Ajust. −",
                TYPE_STOCK_INITIAL: "🆕 Stock initial",
            }[x],
        )

    mvts = lister_mouvements(
        materiau_id=mat_f,
        depuis=depuis.isoformat(),
        jusqua=jusqua.isoformat(),
        types=types_choix or None,
        limite=1000,
    )

    if not mvts:
        st.info("Aucun mouvement pour ces filtres.")
    else:
        icones = {
            TYPE_ENTREE: "➕",
            TYPE_SORTIE: "🏗️",
            TYPE_AJUSTEMENT_POS: "🔧+",
            TYPE_AJUSTEMENT_NEG: "🔧−",
            TYPE_STOCK_INITIAL: "🆕",
        }
        rows = []
        for m in mvts:
            signe = "+" if m["type_mouvement"] in [TYPE_ENTREE, TYPE_AJUSTEMENT_POS, TYPE_STOCK_INITIAL] else "−"
            rows.append({
                "Date": m["date_mouvement"],
                "Type": f"{icones.get(m['type_mouvement'], '')} {m['type_mouvement']}",
                "Matériau": mat_by_id.get(m["materiau_id"], {}).get("nom", m["materiau_id"]),
                "Quantité": f"{signe}{fr(m['quantite'])} {m['unite']}",
                "Production": (m.get("production_id") or "")[:16] or "-",
                "Observation": (m.get("observation") or "")[:80],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
