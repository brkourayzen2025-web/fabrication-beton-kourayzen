"""Page "Préparer un mélange".

Flux :
 1. Formulaire : formule + volume + engin + poids sac + zones
 2. Bouton "Calculer la fiche" → affiche la fiche gros caractères
 3. Confirmations (une case par matériau)
 4. Bouton "Enregistrer la production" → crée la prod en BD
 5. Redirection vers la page "Saisie des réels"
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import init_db  # noqa: E402
from services.calcul import (  # noqa: E402
    construire_fiche,
    fr,
    snapshot_formule_json,
)
from services.repositories import (  # noqa: E402
    creer_production,
    godets_par_materiau,
    lister_engins,
    lister_formules,
    materiaux_par_id,
)

from services import auth  # noqa: E402

st.set_page_config(page_title="Préparer un mélange", page_icon="🏗️", layout="wide")
init_db()

# --- Gate authentification ---
auth.exiger_connexion()
auth.afficher_barre_utilisateur()

st.title("🏗️ Préparer un mélange")


# ==================================================================
# Chargement des données
# ==================================================================
@st.cache_data(ttl=30)
def _charger_donnees():
    return {
        "formules": lister_formules(),
        "engins": lister_engins(),
        "materiaux": materiaux_par_id(),
    }


donnees = _charger_donnees()
formules = donnees["formules"]
engins = donnees["engins"]
materiaux = donnees["materiaux"]

if not formules:
    st.error("Aucune formule disponible. Créez au moins une formule dans 'Formules'.")
    st.stop()


# ==================================================================
# État de session
# ==================================================================
if "fiche_lignes" not in st.session_state:
    st.session_state.fiche_lignes = None
    st.session_state.fiche_input = None

# Cache matériaux pour la section d'ajustement
st.session_state._materiaux_cache = materiaux

# État d'ajustement
if "est_ajuste" not in st.session_state:
    st.session_state.est_ajuste = False


# ==================================================================
# BLOC 1 : Formulaire de saisie
# ==================================================================
st.subheader("1. Paramètres du mélange")

with st.form("form_preparation"):
    col1, col2 = st.columns(2)

    with col1:
        # Formule (marquer visuellement les non validées)
        f_options = {
            f["id"]: f"{'🟢' if f['statut']=='validee' else '🟠'}  {f['nom']}"
            for f in formules
        }
        formule_id = st.selectbox(
            "Formule",
            options=list(f_options.keys()),
            format_func=lambda x: f_options[x],
        )
        volume = st.number_input(
            "Volume à préparer (m³)",
            min_value=0.1,
            max_value=100.0,
            value=10.0,
            step=0.5,
        )
        date_val = st.date_input("Date")
        heure_val = st.time_input("Heure", value=datetime.now().time())

    with col2:
        engin_options = {e["id"]: f"{e['nom']} ({e['type_engin']})" for e in engins}
        if engin_options:
            engin_id = st.selectbox(
                "Engin",
                options=list(engin_options.keys()),
                format_func=lambda x: engin_options[x],
            )
        else:
            engin_id = None
            st.warning("Aucun engin actif. Configurez-en un dans 'Engins et godets'.")

        poids_sac = st.number_input(
            "Poids d'un sac de ciment (kg)",
            min_value=5.0,
            max_value=100.0,
            value=50.0,
            step=5.0,
        )
        zone_melange = st.text_input("Zone de mélange (facultatif)")
        zone_mise = st.text_input("Zone de mise en œuvre (facultatif)")
        operateur = st.text_input("Opérateur (facultatif)")

    observation = st.text_area("Observations (facultatif)", height=68)

    calculer = st.form_submit_button("🧮 Calculer la fiche", type="primary", use_container_width=True)

if calculer:
    # Récupérer la formule choisie
    formule = next(f for f in formules if f["id"] == formule_id)

    # Alerte si formule non validée
    if formule["statut"] != "validee":
        st.warning(
            f"⚠️ Formule **{formule['nom']}** en statut **À VALIDER**. "
            "Ne pas utiliser en production réelle sans confirmation admin."
        )

    godets = godets_par_materiau(engin_id=engin_id)

    try:
        lignes = construire_fiche(
            composition=formule["composition"],
            volume_prevu_m3=volume,
            volume_reference_m3=formule.get("volume_reference_m3") or 1.0,
            materiaux_by_id=materiaux,
            godets_by_materiau_id=godets,
            poids_sac_ciment_kg=poids_sac,
        )
    except Exception as e:
        st.error(f"Erreur de calcul : {e}")
        st.stop()

    # Sauvegarder dans la session pour affichage hors form
    st.session_state.fiche_lignes = lignes
    st.session_state.fiche_input = {
        "formule": formule,
        "volume_prevu_m3": volume,
        "date": date_val.isoformat(),
        "heure": heure_val.strftime("%H:%M"),
        "engin_id": engin_id,
        "poids_sac": poids_sac,
        "zone_melange": zone_melange or None,
        "zone_mise_en_oeuvre": zone_mise or None,
        "operateur": operateur or None,
        "observation": observation or None,
    }
    # Initialiser les confirmations à False
    st.session_state.confirmes = {l.materiau_id: False for l in lignes}
    # Réinitialiser l'état d'ajustement + copie de la composition
    st.session_state.est_ajuste = False
    st.session_state.composition_active = [dict(c) for c in formule["composition"]]
    st.rerun()


# ==================================================================
# BLOC 2 : Affichage de la fiche
# ==================================================================
if st.session_state.fiche_lignes:
    lignes = st.session_state.fiche_lignes
    inp = st.session_state.fiche_input

    st.markdown("---")
    st.subheader("2. Fiche de préparation")

    # En-tête récapitulatif
    st.info(
        f"**{inp['formule']['nom'].upper()}** · "
        f"Volume **{fr(inp['volume_prevu_m3'])} m³** · "
        f"{inp['date']} à {inp['heure']}"
        + (f" · 📍 {inp['zone_mise_en_oeuvre']}" if inp['zone_mise_en_oeuvre'] else "")
    )

    # Avertissements sur les données manquantes
    for l in lignes:
        if l.avertissement:
            st.warning(f"⚠️ {l.avertissement}")

    # Badge si mélange ajusté
    if st.session_state.get("est_ajuste"):
        st.warning(
            "🔧 **Mélange AJUSTÉ** — la composition a été modifiée par rapport à la formule d'origine. "
            "Ces ajustements seront enregistrés dans le snapshot de la production."
        )

    # ==================================================================
    # SECTION AJUSTEMENT (dépliable)
    # ==================================================================
    materiaux_all = st.session_state._materiaux_cache
    with st.expander("🔧 Ajuster ce mélange (modifier / ajouter / supprimer un composant)"):
        st.caption(
            "Modifie ce mélange sans toucher à la formule. "
            "Utile si tu veux mettre un peu plus de ciment, retirer l'adjuvant sur ce mélange, "
            "ou ajouter un composant ponctuel."
        )

        # ---- État courant de la composition (ajustable) ----
        if "composition_active" not in st.session_state:
            # Copie profonde de la composition originale pour permettre la modif
            st.session_state.composition_active = [
                dict(c) for c in inp["formule"]["composition"]
            ]

        composition_active = st.session_state.composition_active
        volume = inp["volume_prevu_m3"]
        volume_ref = inp["formule"].get("volume_reference_m3") or 1.0
        facteur = volume / volume_ref

        st.markdown("**Composants actuels** (quantités pour ce mélange complet)")

        composants_a_supprimer = []
        poids_sac_ciment = inp.get("poids_sac") or 50.0

        for idx, c in enumerate(composition_active):
            mat = materiaux_all.get(c["materiau_id"], {})
            nom_mat = mat.get("nom", c["materiau_id"])
            categorie = mat.get("categorie", "")
            densite = mat.get("densite_apparente")
            unite_bd = c["unite"]
            unite_lbl_bd = {
                "kg": "kg",
                "L": "L",
                "pct_ciment": "% du ciment",
            }.get(unite_bd, unite_bd)
            qte_finale_actuelle = c["quantite"] * facteur  # dans l'unité BD

            # ---- Déterminer les unités de saisie possibles ----
            if categorie == "liant" and unite_bd == "kg":
                # Ciment : kg ou sacs
                unites_saisie = ["kg", "sacs"]
            elif categorie == "granulat" and unite_bd == "kg" and densite:
                # Granulat avec densité connue : kg ou L
                unites_saisie = ["kg", "L"]
            else:
                # Autres cas (eau L, adjuvant pct, matériau sans densité) : pas de conversion
                unites_saisie = [unite_bd]

            col_n, col_q, col_us, col_del = st.columns([3, 2, 2, 1])
            with col_n:
                st.markdown(f"**{nom_mat}**")
                st.caption(f"Formule : {fr(c['quantite'])} {unite_lbl_bd} par m³")

            with col_us:
                unite_choisie = st.selectbox(
                    "Saisir en",
                    options=unites_saisie,
                    format_func=lambda x: {
                        "kg": "kg",
                        "L": "litres",
                        "sacs": f"sacs (× {fr(poids_sac_ciment)} kg)",
                        "pct_ciment": "% du ciment",
                    }.get(x, x),
                    key=f"adj_uni_{idx}",
                    label_visibility="collapsed",
                )

            # ---- Convertir la valeur affichée selon l'unité choisie ----
            if unite_choisie == unite_bd:
                valeur_affichee = qte_finale_actuelle
                step = 1.0
            elif unite_choisie == "L" and unite_bd == "kg" and densite:
                # kg → L : kg / densité (t/m³ = kg/L)
                valeur_affichee = qte_finale_actuelle / densite if densite > 0 else 0
                step = 10.0
            elif unite_choisie == "sacs" and unite_bd == "kg":
                valeur_affichee = qte_finale_actuelle / poids_sac_ciment if poids_sac_ciment > 0 else 0
                step = 1.0
            else:
                valeur_affichee = qte_finale_actuelle
                step = 1.0

            with col_q:
                nouvelle_valeur_saisie = st.number_input(
                    f"Quantité pour ce mélange",
                    min_value=0.0,
                    max_value=1_000_000.0,
                    value=float(valeur_affichee),
                    step=step,
                    key=f"adj_qte_{idx}_{unite_choisie}",
                    label_visibility="collapsed",
                )

            with col_del:
                if st.button("🗑️", key=f"adj_del_{idx}", help=f"Supprimer {nom_mat} de ce mélange"):
                    composants_a_supprimer.append(idx)

            # ---- Reconvertir vers l'unité BD (kg pour granulat/liant) ----
            if unite_choisie == unite_bd:
                nouvelle_qte_finale_bd = nouvelle_valeur_saisie
            elif unite_choisie == "L" and unite_bd == "kg" and densite:
                # L → kg : L × densité
                nouvelle_qte_finale_bd = nouvelle_valeur_saisie * densite
            elif unite_choisie == "sacs" and unite_bd == "kg":
                nouvelle_qte_finale_bd = nouvelle_valeur_saisie * poids_sac_ciment
            else:
                nouvelle_qte_finale_bd = nouvelle_valeur_saisie

            # Détection de modification
            if abs(nouvelle_qte_finale_bd - qte_finale_actuelle) > 0.001:
                c["quantite"] = nouvelle_qte_finale_bd / facteur if facteur > 0 else nouvelle_qte_finale_bd
                st.session_state.est_ajuste = True

            # Affichage de la conversion en info
            if unite_choisie != unite_bd:
                st.caption(
                    f"    ↳ = **{fr(nouvelle_qte_finale_bd)} {unite_lbl_bd}** "
                    f"(conversion : {fr(nouvelle_valeur_saisie)} {unite_choisie})"
                )

        # Traiter les suppressions
        if composants_a_supprimer:
            for idx in sorted(composants_a_supprimer, reverse=True):
                composition_active.pop(idx)
            st.session_state.est_ajuste = True
            st.session_state.composition_active = composition_active

        # ---- Ajouter un composant ----
        st.markdown("---")
        st.markdown("**➕ Ajouter un composant à ce mélange**")

        # Matériaux non déjà présents
        deja_presents = {c["materiau_id"] for c in composition_active}
        mats_disponibles = [
            (mid, m["nom"]) for mid, m in materiaux_all.items()
            if mid not in deja_presents and m.get("actif", 1) == 1
        ]

        if mats_disponibles:
            # Sélecteur de matériau en premier
            new_mat_id = st.selectbox(
                "Matériau à ajouter",
                options=[mid for mid, _ in mats_disponibles],
                format_func=lambda x: materiaux_all[x]["nom"],
                key="add_mat_id",
            )

            # Déterminer les unités de saisie possibles pour ce matériau
            mat_ajout = materiaux_all[new_mat_id]
            cat_ajout = mat_ajout.get("categorie", "")
            densite_ajout = mat_ajout.get("densite_apparente")

            if cat_ajout == "liant":
                unites_ajout = ["kg", "sacs"]
                unite_bd_ajout = "kg"
            elif cat_ajout == "granulat" and densite_ajout:
                unites_ajout = ["kg", "L"]
                unite_bd_ajout = "kg"
            elif cat_ajout == "adjuvant":
                unites_ajout = ["pct_ciment", "L"]
                unite_bd_ajout = "pct_ciment"
            elif cat_ajout == "eau":
                unites_ajout = ["L"]
                unite_bd_ajout = "L"
            else:
                unites_ajout = ["kg", "L", "pct_ciment"]
                unite_bd_ajout = "kg"

            col_aq, col_au, col_ao, col_ab = st.columns([2, 2, 1, 1])
            with col_aq:
                new_qte = st.number_input(
                    "Qté pour ce mélange",
                    min_value=0.0,
                    max_value=1_000_000.0,
                    value=10.0,
                    step=1.0,
                    key="add_mat_qte",
                    label_visibility="collapsed",
                )
            with col_au:
                new_unite = st.selectbox(
                    "Saisir en",
                    options=unites_ajout,
                    format_func=lambda x: {
                        "kg": "kg",
                        "L": "litres",
                        "sacs": f"sacs (× {fr(poids_sac_ciment)} kg)",
                        "pct_ciment": "% du ciment",
                    }.get(x, x),
                    key="add_mat_unite",
                    label_visibility="collapsed",
                )
            with col_ao:
                new_ordre = st.number_input(
                    "Ordre",
                    min_value=1,
                    max_value=99,
                    value=len(composition_active) + 1,
                    step=1,
                    key="add_mat_ordre",
                    label_visibility="collapsed",
                )
            with col_ab:
                if st.button("Ajouter", type="primary", key="btn_add_composant"):
                    # Conversion vers l'unité BD
                    if new_unite == unite_bd_ajout:
                        qte_finale_bd = new_qte
                    elif new_unite == "L" and unite_bd_ajout == "kg" and densite_ajout:
                        qte_finale_bd = new_qte * densite_ajout
                    elif new_unite == "sacs" and unite_bd_ajout == "kg":
                        qte_finale_bd = new_qte * poids_sac_ciment
                    elif new_unite == "L" and unite_bd_ajout == "pct_ciment":
                        # L d'adjuvant → % ciment : L*densite / masse_ciment_totale * 100
                        # On applique à la quantité pour le mélange
                        # Trouver masse ciment ajusté totale
                        masse_ciment_totale = 0
                        for cc in composition_active:
                            mm = materiaux_all.get(cc["materiau_id"], {})
                            if mm.get("categorie") == "liant" and cc["unite"] == "kg":
                                masse_ciment_totale = cc["quantite"] * facteur
                                break
                        dens_adj = mat_ajout.get("densite_apparente") or 1.1
                        masse_adj_kg = new_qte * dens_adj
                        qte_finale_bd = (
                            masse_adj_kg / masse_ciment_totale * 100
                            if masse_ciment_totale > 0
                            else new_qte
                        )
                    else:
                        qte_finale_bd = new_qte

                    # Convertir en valeur par m³ de référence
                    qte_par_m3 = qte_finale_bd / facteur if facteur > 0 else qte_finale_bd
                    composition_active.append({
                        "materiau_id": new_mat_id,
                        "quantite": qte_par_m3,
                        "unite": unite_bd_ajout,
                        "ordre_ajout": new_ordre,
                    })
                    st.session_state.composition_active = composition_active
                    st.session_state.est_ajuste = True
                    st.rerun()
        else:
            st.caption("Tous les matériaux disponibles sont déjà dans le mélange.")

        # ---- Boutons ----
        st.markdown("---")
        col_r, col_a = st.columns(2)
        with col_r:
            if st.button("🔄 Réinitialiser (revenir à la formule d'origine)", use_container_width=True):
                st.session_state.composition_active = [
                    dict(c) for c in inp["formule"]["composition"]
                ]
                st.session_state.est_ajuste = False
                # Reset lignes → prochain recalcul
                st.session_state.fiche_lignes = None
                st.rerun()
        with col_a:
            if st.button("✅ Appliquer les ajustements", type="primary", use_container_width=True):
                # Recalculer la fiche avec la composition ajustée
                try:
                    godets_ajust = godets_par_materiau(engin_id=inp["engin_id"])
                    nouvelles_lignes = construire_fiche(
                        composition=st.session_state.composition_active,
                        volume_prevu_m3=inp["volume_prevu_m3"],
                        volume_reference_m3=inp["formule"].get("volume_reference_m3") or 1.0,
                        materiaux_by_id=materiaux_all,
                        godets_by_materiau_id=godets_ajust,
                        poids_sac_ciment_kg=inp["poids_sac"],
                    )
                    st.session_state.fiche_lignes = nouvelles_lignes
                    # Ré-initialiser les confirmations
                    st.session_state.confirmes = {
                        l.materiau_id: False for l in nouvelles_lignes
                    }
                    st.success("Ajustements appliqués — fiche recalculée")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur de recalcul : {e}")

    # ==================================================================
    # RÉSUMÉ EN UNE LIGNE — vue rapide pour le chantier
    # ==================================================================
    st.markdown("### 📌 Résumé — quantités à ajouter")
    cols = st.columns(len(lignes))
    for col, l in zip(cols, lignes):
        with col:
            # Choisir la valeur principale à afficher
            if l.sac:
                valeur = f"{fr(l.sac.nb_sacs_theorique)}"
                unite = "sacs"
                sous_ligne = f"{fr(l.sac.quantite_kg)} kg"
            elif l.godet:
                valeur = f"{fr(l.godet.nb_godets)}"
                unite = "godets"
                sous_ligne = f"{fr(l.quantite_theorique)} kg"
            else:
                valeur = f"{fr(l.quantite_theorique)}"
                unite = l.unite_theorique
                sous_ligne = ""

            # Nom court du matériau
            nom_court = l.materiau_nom.split("(")[0].strip().split(" ")[0]

            st.markdown(
                f"""<div style='text-align:center; padding:8px; background-color:#F0F4F8;
                    border-radius:6px; border-left:4px solid #1565C0;'>
                    <div style='font-size:12px; color:#555; font-weight:600;'>{nom_court}</div>
                    <div style='font-size:24px; font-weight:bold; color:#1565C0; line-height:1.1;'>{valeur}</div>
                    <div style='font-size:11px; color:#666;'>{unite}</div>
                    <div style='font-size:10px; color:#999; margin-top:2px;'>{sous_ligne}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("")

    # Progression
    nb_ok = sum(1 for v in st.session_state.confirmes.values() if v)
    total = len(lignes)
    st.markdown(f"**Progression : {nb_ok} / {total} matériaux ajoutés**")
    st.progress(nb_ok / total if total else 0)

    st.markdown("")

    # Une carte par matériau
    for l in lignes:
        with st.container(border=True):
            icone = {
                "granulat": "🪨",
                "liant": "🧱",
                "eau": "💧",
                "adjuvant": "🧪",
            }.get(l.categorie, "•")

            col_head, col_check = st.columns([4, 1])
            with col_head:
                st.markdown(f"### {icone} {l.materiau_nom.upper()}")

            # Détail selon le type
            if l.sac:
                s = l.sac
                st.markdown(
                    f"## <span style='color:#1565C0'>{fr(s.quantite_kg)} kg</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{s.instruction_courte}**")
                if not s.est_sacs_pile:
                    st.caption(
                        f"{s.nb_sacs_complets} sacs de {fr(s.poids_sac_kg)} kg "
                        f"+ {fr(s.kg_supplementaires)} kg"
                    )
            elif l.godet:
                g = l.godet
                st.caption(
                    f"Masse théorique : {fr(l.quantite_theorique)} kg · "
                    f"Volume apparent : {fr(l.volume_apparent_l or 0)} L"
                )
                st.markdown(
                    f"## <span style='color:#1565C0'>{fr(g.nb_godets)} godets</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{g.instruction_courte}**")
                if not g.est_godet_pile:
                    st.caption(
                        f"Dernier godet ≈ {fr(g.qte_dernier_godet_l)} L "
                        f"(capacité utile {fr(g.capacite_utile_l)} L)"
                    )
            else:
                st.markdown(
                    f"## <span style='color:#1565C0'>{fr(l.quantite_theorique)} {l.unite_theorique}</span>",
                    unsafe_allow_html=True,
                )

            with col_check:
                # Case à cocher
                cle = f"conf_{l.materiau_id}"
                st.session_state.confirmes[l.materiau_id] = st.checkbox(
                    "✅ Ajouté",
                    value=st.session_state.confirmes.get(l.materiau_id, False),
                    key=cle,
                )

    # ==================================================================
    # BLOC 3 : Enregistrement
    # ==================================================================
    st.markdown("---")
    st.subheader("3. Enregistrer la production")

    tous_ok = all(st.session_state.confirmes.values())
    non_conf = [
        l.materiau_nom for l in lignes if not st.session_state.confirmes.get(l.materiau_id)
    ]

    col_annul, col_save = st.columns([1, 2])

    with col_annul:
        if st.button("❌ Annuler", use_container_width=True):
            st.session_state.fiche_lignes = None
            st.session_state.fiche_input = None
            st.session_state.confirmes = {}
            st.session_state.est_ajuste = False
            if "composition_active" in st.session_state:
                del st.session_state.composition_active
            st.rerun()

    with col_save:
        if not tous_ok:
            st.warning(f"Non confirmés : **{', '.join(non_conf)}**")
            justif = st.text_input(
                "Justification (obligatoire pour forcer l'enregistrement)",
                key="justif_force",
            )
            btn_disabled = not justif.strip()
        else:
            justif = None
            btn_disabled = False

        if st.button(
            "💾 Enregistrer la production" if tous_ok else "⚠️ Forcer et enregistrer",
            type="primary",
            use_container_width=True,
            disabled=btn_disabled,
        ):
            # Construction des lignes ProductionMateriau
            formule = inp["formule"]
            # Utiliser la composition ajustée si le mélange a été ajusté
            composition_finale = (
                st.session_state.composition_active
                if st.session_state.get("est_ajuste")
                else formule["composition"]
            )
            snapshot = snapshot_formule_json(formule, composition_finale)
            # Ajouter marqueur d'ajustement dans le snapshot
            if st.session_state.get("est_ajuste"):
                import json as _json
                snap_dict = _json.loads(snapshot)
                snap_dict["ajuste"] = True
                snap_dict["composition_originale"] = formule["composition"]
                snapshot = _json.dumps(snap_dict, ensure_ascii=False, default=str)

            now = datetime.now().isoformat()
            obs_parts = [inp["observation"]]
            if st.session_state.get("est_ajuste"):
                obs_parts.append("🔧 Mélange ajusté (composition modifiée pour ce mélange spécifique)")
            if justif:
                obs_parts.append(f"⚠️ Forcé : {justif}")
            obs = " | ".join(p for p in obs_parts if p)

            lignes_prod = []
            for l in lignes:
                lignes_prod.append({
                    "materiau_id": l.materiau_id,
                    "godet_id": l.godet_id,
                    "quantite_theorique": l.quantite_theorique,
                    "unite_theorique": l.unite_theorique,
                    "nb_godets_theorique": l.godet.nb_godets if l.godet else None,
                    "godets_complets_theorique": l.godet.godets_complets if l.godet else None,
                    "pct_dernier_godet_theorique": l.godet.pct_dernier_godet if l.godet else None,
                    "qte_dernier_godet_l_theorique": l.godet.qte_dernier_godet_l if l.godet else None,
                    "nb_sacs_theorique": l.sac.nb_sacs_theorique if l.sac else None,
                    "confirme": st.session_state.confirmes.get(l.materiau_id, False),
                    "confirme_at": now if st.session_state.confirmes.get(l.materiau_id) else None,
                })

            try:
                pid = creer_production(
                    formule_id=formule["id"],
                    formule_snapshot_json=snapshot,
                    volume_prevu_m3=inp["volume_prevu_m3"],
                    date_str=inp["date"],
                    heure_str=inp["heure"],
                    poids_sac_ciment_kg=inp["poids_sac"],
                    engin_id=inp["engin_id"],
                    zone_melange=inp["zone_melange"],
                    zone_mise_en_oeuvre=inp["zone_mise_en_oeuvre"],
                    operateur=inp["operateur"],
                    observation=obs or None,
                    materiaux_lignes=lignes_prod,
                )

                # Reset state, stocker prod_id pour la page suivante
                st.session_state.fiche_lignes = None
                st.session_state.fiche_input = None
                st.session_state.confirmes = {}
                st.session_state.est_ajuste = False
                if "composition_active" in st.session_state:
                    del st.session_state.composition_active
                st.session_state.prod_active = pid

                st.success(f"✅ Production enregistrée (ID {pid[:12]}…)")
                st.info("Redirection vers la saisie des quantités réelles…")
                st.switch_page("pages/2_📋_Productions.py")
            except Exception as e:
                st.error(f"Erreur d'enregistrement : {e}")
