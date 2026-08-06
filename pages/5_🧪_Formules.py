"""Page "Formules" : consultation + édition + versionnage.

Trois vues :
 1. Liste (filtrable par statut)
 2. Détail d'une formule (composants, versions, journal)
 3. Édition / création (formulaire dynamique)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from models.constants import (  # noqa: E402
    STATUT_A_VALIDER,
    STATUT_BROUILLON,
    STATUT_DESACTIVEE,
    STATUT_VALIDEE,
    UNITE_KG,
    UNITE_LITRE,
    UNITE_PCT_CIMENT,
)
from services import journal
from services.calcul import fr  # noqa: E402
from services.formules_service import (  # noqa: E402
    TRANSITIONS,
    changer_statut,
    creer_formule,
    editer_formule,
    supprimer_brouillon,
    toutes_versions,
)
from services.repositories import (  # noqa: E402
    formule_par_id,
    lister_formules,
    lister_materiaux,
    lister_types_beton,
    materiaux_par_id,
    modifier_materiau,
)

from services import auth  # noqa: E402

st.set_page_config(page_title="Formules", page_icon="🧪", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_admin()
auth.afficher_barre_utilisateur()


st.title("🧪 Formules")

types_beton = {t["id"]: t for t in lister_types_beton()}
materiaux_liste = lister_materiaux(actifs_seulement=True)
materiaux = {m["id"]: m for m in materiaux_liste}

BADGES = {
    STATUT_VALIDEE: "🟢 VALIDÉE",
    STATUT_A_VALIDER: "🟠 À VALIDER",
    STATUT_BROUILLON: "📝 BROUILLON",
    STATUT_DESACTIVEE: "❌ DÉSACTIVÉE",
}
STATUT_ORDRE = [STATUT_VALIDEE, STATUT_A_VALIDER, STATUT_BROUILLON, STATUT_DESACTIVEE]

# État de session : quelle formule est en cours d'édition/consultation ?
if "formule_ouverte" not in st.session_state:
    st.session_state.formule_ouverte = None
if "mode_page" not in st.session_state:
    st.session_state.mode_page = "liste"  # liste / detail / edition / creation


# ==================================================================
# ACTIONS
# ==================================================================
def ouvrir_detail(fid: str):
    st.session_state.formule_ouverte = fid
    st.session_state.mode_page = "detail"


def ouvrir_edition(fid: str):
    st.session_state.formule_ouverte = fid
    st.session_state.mode_page = "edition"
    _init_composition_editable(fid)


def ouvrir_creation():
    st.session_state.formule_ouverte = None
    st.session_state.mode_page = "creation"
    st.session_state.compo_edit = []
    st.session_state.nom_edit = ""
    st.session_state.type_edit = list(types_beton.keys())[0] if types_beton else None
    st.session_state.obs_edit = ""


def revenir_liste():
    st.session_state.formule_ouverte = None
    st.session_state.mode_page = "liste"


def _init_composition_editable(fid: str):
    """Charge la composition en session_state pour édition."""
    f = formule_par_id(fid)
    if not f:
        return
    st.session_state.compo_edit = [dict(c) for c in f["composition"]]
    st.session_state.nom_edit = f["nom"]
    st.session_state.type_edit = f["type_beton_id"]
    st.session_state.obs_edit = f.get("observations") or ""


# ==================================================================
# BARRE DE NAVIGATION
# ==================================================================
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 1, 1, 2])
with col_nav1:
    if st.button("← Liste", use_container_width=True):
        revenir_liste()
        st.rerun()
with col_nav2:
    if st.button("➕ Nouvelle formule", type="primary", use_container_width=True):
        ouvrir_creation()
        st.rerun()
with col_nav3:
    if st.button("🧱 Matériaux", use_container_width=True):
        st.session_state.mode_page = "materiaux"
        st.rerun()

st.markdown("---")


# ==================================================================
# MODE : LISTE
# ==================================================================
def afficher_liste():
    st.subheader("Formules")

    filtre = st.multiselect(
        "Filtrer par statut",
        options=STATUT_ORDRE,
        default=[STATUT_VALIDEE, STATUT_A_VALIDER, STATUT_BROUILLON],
        format_func=lambda x: BADGES[x],
    )

    formules = lister_formules(inclure_desactivees=True)
    formules = [f for f in formules if f["statut"] in filtre]
    formules.sort(key=lambda f: (STATUT_ORDRE.index(f["statut"]), f["nom"]))

    if not formules:
        st.info("Aucune formule pour ces filtres.")
        return

    for f in formules:
        badge = BADGES[f["statut"]]
        type_nom = types_beton.get(f["type_beton_id"], {}).get("nom", "?")
        with st.container(border=True):
            col_info, col_btn = st.columns([4, 1])
            with col_info:
                st.markdown(
                    f"**{badge}** &nbsp;·&nbsp; **{f['nom']}** &nbsp;·&nbsp; "
                    f"type: *{type_nom}* &nbsp;·&nbsp; v{f['version']} &nbsp;·&nbsp; "
                    f"{len(f['composition'])} composants",
                    unsafe_allow_html=True,
                )
                if f.get("date_validation"):
                    st.caption(f"📅 Validée le {f['date_validation']} par {f.get('valide_par') or '?'}")
                st.caption(f"🆔 `{f['id']}`")
            with col_btn:
                if st.button("Ouvrir →", key=f"open_{f['id']}", use_container_width=True):
                    ouvrir_detail(f["id"])
                    st.rerun()


# ==================================================================
# MODE : DÉTAIL
# ==================================================================
def afficher_detail():
    fid = st.session_state.formule_ouverte
    f = formule_par_id(fid) if fid else None
    if not f:
        st.error("Formule introuvable.")
        revenir_liste()
        return

    badge = BADGES[f["statut"]]
    type_nom = types_beton.get(f["type_beton_id"], {}).get("nom", "?")

    st.subheader(f"{badge}  ·  {f['nom']}")
    st.caption(
        f"Type de béton : **{type_nom}** · Version {f['version']} · ID `{f['id']}`"
    )
    if f.get("date_validation"):
        st.caption(f"📅 Validée le {f['date_validation']} par {f.get('valide_par') or '?'}")
    if f.get("observations"):
        st.info(f["observations"])

    # ---- Composition ----
    st.markdown("#### Composition (par m³)")
    rows = []
    for c in f["composition"]:
        m = materiaux.get(c["materiau_id"], {})
        unite_disp = {
            UNITE_KG: "kg",
            UNITE_LITRE: "L",
            UNITE_PCT_CIMENT: "% du poids ciment",
        }.get(c["unite"], c["unite"])
        rows.append({
            "Ordre": c.get("ordre_ajout") or "-",
            "Matériau": m.get("nom", c["materiau_id"]),
            "Catégorie": m.get("categorie", "?"),
            "Quantité / m³": f"{fr(c['quantite'])} {unite_disp}",
            "Densité (t/m³)": fr(m["densite_apparente"]) if m.get("densite_apparente") else "-",
        })
    st.dataframe(pd.DataFrame(rows).sort_values("Ordre"), hide_index=True, use_container_width=True)

    # ---- Actions ----
    st.markdown("---")
    st.markdown("#### Actions")

    col_e, col_s, col_v, col_d = st.columns(4)

    with col_e:
        if st.button("✏️ Éditer", use_container_width=True):
            ouvrir_edition(fid)
            st.rerun()

    with col_s:
        # Transitions autorisées
        transitions_ok = TRANSITIONS.get(f["statut"], set())
        if transitions_ok:
            with st.popover("🔄 Changer statut", use_container_width=True):
                st.write(f"Statut actuel : **{f['statut']}**")
                for nv in transitions_ok:
                    label = {
                        STATUT_A_VALIDER: "Soumettre à validation",
                        STATUT_VALIDEE: "✅ Valider",
                        STATUT_BROUILLON: "Renvoyer en brouillon",
                        STATUT_DESACTIVEE: "❌ Désactiver",
                    }.get(nv, nv)
                    motif_key = f"motif_{fid}_{nv}"
                    motif = st.text_input(
                        f"Motif ({label})",
                        key=motif_key,
                        placeholder="Optionnel sauf pour désactivation",
                    )
                    if st.button(label, key=f"trans_{fid}_{nv}", type="primary"):
                        try:
                            changer_statut(
                                fid, nv,
                                utilisateur=auth.username_pour_journal(),
                                motif=motif or None,
                            )
                            st.success(f"Statut changé → {nv}")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

    with col_v:
        if st.button("📜 Versions", use_container_width=True):
            st.session_state.montrer_versions = not st.session_state.get("montrer_versions", False)
            st.rerun()

    with col_d:
        # Suppression uniquement pour brouillons
        if f["statut"] == STATUT_BROUILLON:
            with st.popover("🗑️ Supprimer", use_container_width=True):
                st.warning("Suppression définitive de ce brouillon.")
                if st.button("Confirmer la suppression", type="primary"):
                    try:
                        supprimer_brouillon(
                            fid, utilisateur=auth.username_pour_journal(),
                        )
                        st.success("Brouillon supprimé.")
                        revenir_liste()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    # ---- Historique versions ----
    if st.session_state.get("montrer_versions"):
        st.markdown("#### Historique des versions")
        versions = toutes_versions(fid)
        if len(versions) <= 1:
            st.caption("Aucune autre version — cette formule n'a pas été révisée.")
        else:
            for v in versions:
                marqueur = "◀" if v["id"] == fid else ""
                st.markdown(
                    f"- {marqueur} **v{v['version']}** · {BADGES[v['statut']]} · "
                    f"`{v['id']}` · créée le {v['created_at'][:10]}"
                )
                if st.button(f"Ouvrir cette version", key=f"open_v_{v['id']}"):
                    ouvrir_detail(v["id"])
                    st.rerun()

    # ---- Journal de cette formule ----
    with st.expander("📝 Journal de cette formule"):
        entries = journal.lister(table_nom="formules", enregistrement_id=fid, limite=50)
        if not entries:
            st.caption("Aucune entrée dans le journal.")
        else:
            for e in entries:
                st.markdown(
                    f"- `{e['timestamp'][:19]}` · **{e['action']}** · "
                    f"par *{e['utilisateur']}*"
                    + (f" · motif : _{e['motif']}_" if e.get("motif") else "")
                )


# ==================================================================
# MODE : ÉDITION / CRÉATION
# ==================================================================
def afficher_edition(mode: str):
    """mode = 'edition' ou 'creation'."""
    creation = mode == "creation"
    f = None
    if not creation:
        fid = st.session_state.formule_ouverte
        f = formule_par_id(fid)
        if not f:
            st.error("Formule introuvable.")
            revenir_liste()
            return

    st.subheader("➕ Nouvelle formule" if creation else f"✏️ Édition — {f['nom']}")

    # Avertissement si édition d'une formule non-modifiable directement
    if not creation:
        from services.formules_service import _formule_a_des_productions
        prod_liees = _formule_a_des_productions(f["id"])
        editable_place = (
            f["statut"] in (STATUT_BROUILLON, STATUT_A_VALIDER) and not prod_liees
        )
        if not editable_place:
            reasons = []
            if f["statut"] not in (STATUT_BROUILLON, STATUT_A_VALIDER):
                reasons.append(f"statut = *{f['statut']}*")
            if prod_liees:
                reasons.append("des productions y sont liées")
            st.warning(
                f"⚠️ Cette formule ne peut pas être modifiée directement ({', '.join(reasons)}). "
                "**Enregistrer** créera une nouvelle version en brouillon."
            )
        else:
            st.info("🟢 Cette formule est modifiable directement (brouillon sans production liée).")

    # Nom + type + observations
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.nom_edit = st.text_input(
            "Nom de la formule *",
            value=st.session_state.get("nom_edit", ""),
            key="input_nom",
        )
    with col2:
        type_ids = list(types_beton.keys())
        idx = 0
        cur_type = st.session_state.get("type_edit")
        if cur_type in type_ids:
            idx = type_ids.index(cur_type)
        st.session_state.type_edit = st.selectbox(
            "Type de béton *",
            options=type_ids,
            index=idx,
            format_func=lambda x: types_beton[x]["nom"],
            key="input_type",
        )
    st.session_state.obs_edit = st.text_area(
        "Observations",
        value=st.session_state.get("obs_edit", ""),
        key="input_obs",
        height=68,
    )

    # ---- Composition dynamique ----
    st.markdown("#### Composition (par m³ de béton)")

    if "compo_edit" not in st.session_state:
        st.session_state.compo_edit = []

    # Boutons ajouter ligne
    col_add, col_reset = st.columns([1, 5])
    with col_add:
        if st.button("➕ Ajouter un composant"):
            st.session_state.compo_edit.append({
                "materiau_id": materiaux_liste[0]["id"] if materiaux_liste else "",
                "quantite": 0.0,
                "unite": UNITE_KG,
                "ordre_ajout": len(st.session_state.compo_edit) + 1,
            })
            st.rerun()

    # Rendre chaque ligne comme un container editable
    if not st.session_state.compo_edit:
        st.caption("Aucun composant. Cliquer sur ➕ pour en ajouter.")
    else:
        a_supprimer = None
        for i, c in enumerate(st.session_state.compo_edit):
            with st.container(border=True):
                col_mat, col_q, col_u, col_ord, col_del = st.columns([4, 2, 2, 1, 1])
                with col_mat:
                    mat_ids = [m["id"] for m in materiaux_liste]
                    idx_m = mat_ids.index(c["materiau_id"]) if c["materiau_id"] in mat_ids else 0
                    c["materiau_id"] = st.selectbox(
                        "Matériau",
                        options=mat_ids,
                        index=idx_m,
                        format_func=lambda x: materiaux[x]["nom"],
                        key=f"compo_mat_{i}",
                        label_visibility="collapsed",
                    )
                with col_q:
                    c["quantite"] = st.number_input(
                        "Qté",
                        min_value=0.0,
                        max_value=100000.0,
                        value=float(c.get("quantite", 0)),
                        step=1.0,
                        key=f"compo_q_{i}",
                        label_visibility="collapsed",
                    )
                with col_u:
                    unites = [UNITE_KG, UNITE_LITRE, UNITE_PCT_CIMENT]
                    idx_u = unites.index(c["unite"]) if c["unite"] in unites else 0
                    c["unite"] = st.selectbox(
                        "Unité",
                        options=unites,
                        index=idx_u,
                        format_func=lambda x: {
                            UNITE_KG: "kg", UNITE_LITRE: "L",
                            UNITE_PCT_CIMENT: "% ciment",
                        }[x],
                        key=f"compo_u_{i}",
                        label_visibility="collapsed",
                    )
                with col_ord:
                    c["ordre_ajout"] = st.number_input(
                        "Ordre",
                        min_value=1,
                        max_value=99,
                        value=int(c.get("ordre_ajout") or (i + 1)),
                        step=1,
                        key=f"compo_ord_{i}",
                        label_visibility="collapsed",
                    )
                with col_del:
                    if st.button("🗑️", key=f"del_{i}"):
                        a_supprimer = i
        if a_supprimer is not None:
            st.session_state.compo_edit.pop(a_supprimer)
            st.rerun()

    # ---- Enregistrement ----
    st.markdown("---")
    col_c, col_s = st.columns([1, 3])
    with col_c:
        if st.button("Annuler", use_container_width=True):
            revenir_liste()
            st.rerun()
    with col_s:
        if st.button(
            "💾 Enregistrer",
            type="primary",
            use_container_width=True,
        ):
            if not st.session_state.nom_edit.strip():
                st.error("Nom obligatoire.")
                return
            if not st.session_state.compo_edit:
                st.error("Au moins un composant est requis.")
                return

            user = auth.username_pour_journal()
            try:
                if creation:
                    fid = creer_formule(
                        nom=st.session_state.nom_edit,
                        type_beton_id=st.session_state.type_edit,
                        composition=st.session_state.compo_edit,
                        observations=st.session_state.obs_edit or None,
                        utilisateur=user,
                    )
                    st.success(f"Formule créée : `{fid}` (statut brouillon)")
                    ouvrir_detail(fid)
                    st.rerun()
                else:
                    new_id, nouvelle_v = editer_formule(
                        formule_id=f["id"],
                        nouvelle_composition=st.session_state.compo_edit,
                        nouveau_nom=st.session_state.nom_edit,
                        nouvelles_observations=st.session_state.obs_edit or None,
                        utilisateur=user,
                    )
                    if nouvelle_v:
                        st.success(
                            f"Nouvelle version créée : `{new_id}` (statut brouillon). "
                            "L'ancienne version reste inchangée pour les productions passées."
                        )
                    else:
                        st.success("Formule modifiée en place ✅")
                    ouvrir_detail(new_id)
                    st.rerun()
            except ValueError as e:
                st.error(str(e))


# ==================================================================
# MODE : MATÉRIAUX (édition densités et propriétés)
# ==================================================================
def afficher_materiaux():
    st.subheader("🧱 Matériaux")
    st.caption(
        "Modification des propriétés physiques des matériaux "
        "(densité apparente, nom, poids sac par défaut). "
        "⚠️ Les modifications de densité affectent tous les NOUVEAUX calculs. "
        "Les productions déjà enregistrées ne sont PAS recalculées (snapshot immuable)."
    )

    for m in materiaux_liste:
        badge_cat = {
            "granulat": "🪨 Granulat",
            "liant": "🧱 Liant",
            "eau": "💧 Eau",
            "adjuvant": "🧪 Adjuvant",
        }.get(m["categorie"], m["categorie"])

        # Alerte visuelle si densité manquante
        densite_manquante = (
            m["categorie"] in ("granulat", "adjuvant") and not m.get("densite_apparente")
        )
        titre = f"**{m['nom']}** · {badge_cat}"
        if densite_manquante:
            titre += "  🔴 densité manquante"

        with st.expander(titre, expanded=densite_manquante):
            with st.form(f"form_mat_{m['id']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    nom_edit = st.text_input(
                        "Nom",
                        value=m["nom"],
                        key=f"nom_{m['id']}",
                    )
                with col2:
                    # Densité — désactivée pour l'eau (toujours 1.0)
                    densite_edit = st.number_input(
                        "Densité apparente (t/m³ = kg/L)",
                        min_value=0.0,
                        max_value=10.0,
                        value=float(m["densite_apparente"]) if m["densite_apparente"] else 0.0,
                        step=0.01,
                        format="%.3f",
                        key=f"dens_{m['id']}",
                        help=(
                            "Densité en vrac du matériau. "
                            "0 = non applicable (ciment dosé au sac, eau)."
                        ),
                    )
                with col3:
                    # Poids sac (seulement pour liants)
                    if m["categorie"] == "liant":
                        poids_sac_edit = st.number_input(
                            "Poids d'un sac (kg)",
                            min_value=0.0,
                            max_value=100.0,
                            value=float(m["poids_sac_defaut"]) if m["poids_sac_defaut"] else 50.0,
                            step=1.0,
                            key=f"sac_{m['id']}",
                        )
                    else:
                        st.text_input(
                            "Unité de stock",
                            value=m["unite_stock"],
                            disabled=True,
                            help="Modifier depuis le code (models/constants.py) — rare.",
                        )
                        poids_sac_edit = None

                st.caption(f"🆔 `{m['id']}`")

                if st.form_submit_button("💾 Enregistrer", type="primary"):
                    try:
                        modifier_materiau(
                            materiau_id=m["id"],
                            nom=nom_edit,
                            densite_apparente=densite_edit,
                            poids_sac_defaut=poids_sac_edit,
                            utilisateur=auth.username_pour_journal(),
                        )
                        st.success(f"✅ **{nom_edit}** mis à jour")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))



mode = st.session_state.mode_page
if mode == "liste":
    afficher_liste()
elif mode == "detail":
    afficher_detail()
elif mode == "edition":
    afficher_edition("edition")
elif mode == "creation":
    afficher_edition("creation")
elif mode == "materiaux":
    afficher_materiaux()
