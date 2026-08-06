"""Page "Import Excel" — restauration ou fusion de données depuis un fichier Excel.

Réservée à l'admin. Permet de :
  - Recharger des productions perdues depuis un backup Excel
  - Migrer des données d'une autre source

⚠️ Attention : opération sensible. Toujours faire un backup AVANT d'importer.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.database import get_conn, init_db  # noqa: E402
from services import auth, journal  # noqa: E402
from services.repositories import (  # noqa: E402
    lister_formules,
    lister_materiaux,
    materiaux_par_id,
)
from services.stock import deduire_production  # noqa: E402


# ==================================================================
# HELPERS
# ==================================================================
def _to_float(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _to_date_iso(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return datetime.now().date().isoformat()
    try:
        d = pd.to_datetime(v)
        return d.date().isoformat()
    except Exception:
        return str(v)[:10]


def _to_heure_str(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "00:00"
    try:
        s = str(v)
        if ":" in s:
            return s[:5]
        return "00:00"
    except Exception:
        return "00:00"


# ==================================================================
# LOGIQUE D'IMPORT
# ==================================================================
def importer_donnees(
    df_prod,
    df_details,
    formules_par_nom,
    mats_par_nom,
    ids_existants,
    mode_remplacement,
    deduire_stock,
    utilisateur,
):
    """Exécute l'import. Retourne un rapport."""
    rapport = {
        "importees": 0,
        "ignorees": 0,
        "details_ok": 0,
        "erreurs": 0,
        "messages": [],
    }

    conn = get_conn()
    try:
        # Mode remplacement : effacer toutes les productions
        if mode_remplacement:
            conn.execute("DELETE FROM production_materiaux")
            conn.execute("DELETE FROM mouvements_stock WHERE type_mouvement = 'sortie'")
            conn.execute("DELETE FROM productions")
            conn.commit()
            ids_existants = set()
            rapport["messages"].append("🗑️ Productions existantes supprimées")

        # Grouper les détails par production_id
        details_par_prod = {}
        if not df_details.empty and "Production ID" in df_details.columns:
            for _, row in df_details.iterrows():
                pid = str(row.get("Production ID", "")).strip()
                if pid:
                    details_par_prod.setdefault(pid, []).append(row)

        now = datetime.now().isoformat()

        for _, row in df_prod.iterrows():
            try:
                pid = str(row.get("ID", "")).strip()
                if not pid or pid == "nan":
                    rapport["erreurs"] += 1
                    rapport["messages"].append("❌ Ligne sans ID ignorée")
                    continue

                if pid in ids_existants and not mode_remplacement:
                    rapport["ignorees"] += 1
                    rapport["messages"].append(f"⏭️ {pid[:16]} déjà en base — ignoré")
                    continue

                nom_formule = str(row.get("Type de béton", "")).strip()
                formule = formules_par_nom.get(nom_formule)
                if not formule:
                    rapport["erreurs"] += 1
                    rapport["messages"].append(
                        f"❌ {pid[:16]} : formule '{nom_formule}' introuvable"
                    )
                    continue

                date_str = _to_date_iso(row.get("Date"))
                heure_str = _to_heure_str(row.get("Heure"))
                statut = str(row.get("Statut", "en_cours")).strip() or "en_cours"

                snapshot = json.dumps(
                    {
                        "formule_id": formule["id"],
                        "nom": formule["nom"],
                        "imported": True,
                        "source_excel": True,
                    },
                    ensure_ascii=False,
                )

                conn.execute(
                    """INSERT INTO productions
                       (id, date, heure, formule_id, formule_snapshot_json,
                        volume_prevu_m3, volume_reel_m3, engin_id,
                        zone_melange, zone_mise_en_oeuvre, operateur,
                        poids_sac_ciment_kg, observation, statut,
                        materiaux_confirmes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pid,
                        date_str,
                        heure_str,
                        formule["id"],
                        snapshot,
                        float(row.get("Volume prévu (m³)") or 0),
                        _to_float(row.get("Volume réel (m³)")),
                        None,
                        str(row.get("Zone mélange") or ""),
                        str(row.get("Zone mise en œuvre") or ""),
                        str(row.get("Opérateur") or ""),
                        50.0,
                        str(row.get("Observation") or ""),
                        statut,
                        1 if statut == "terminee" else 0,
                        now,
                        now,
                    ),
                )
                rapport["importees"] += 1

                # Détails matériaux
                for det_row in details_par_prod.get(pid, []):
                    nom_mat = str(det_row.get("Matériau", "")).strip()
                    mat = mats_par_nom.get(nom_mat)
                    if not mat:
                        continue
                    try:
                        qte_reel = _to_float(det_row.get("Qté réelle"))
                        conn.execute(
                            """INSERT INTO production_materiaux
                               (production_id, materiau_id, godet_id,
                                quantite_theorique, unite_theorique,
                                nb_godets_theorique, godets_complets_theorique,
                                pct_dernier_godet_theorique, qte_dernier_godet_l_theorique,
                                nb_sacs_theorique,
                                quantite_reelle, nb_godets_reel, nb_sacs_reel,
                                confirme, confirme_at,
                                ecart_absolu, ecart_pct)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                pid,
                                mat["id"],
                                None,
                                _to_float(det_row.get("Qté théorique")) or 0,
                                str(det_row.get("Unité") or "kg"),
                                _to_float(det_row.get("Nb godets théo")),
                                None,
                                None,
                                None,
                                _to_float(det_row.get("Nb sacs théo")),
                                qte_reel,
                                _to_float(det_row.get("Nb godets réel")),
                                _to_float(det_row.get("Nb sacs réel")),
                                1 if qte_reel is not None else 0,
                                now,
                                _to_float(det_row.get("Écart absolu")),
                                _to_float(det_row.get("Écart %")),
                            ),
                        )
                        rapport["details_ok"] += 1
                    except Exception as e_det:
                        rapport["messages"].append(
                            f"⚠️ Détail {nom_mat} pour {pid[:16]} : {e_det}"
                        )

                conn.commit()
                rapport["messages"].append(f"✅ {pid[:16]} importée ({nom_formule})")

                # Déduire du stock si demandé
                if deduire_stock and statut == "terminee":
                    try:
                        deduire_production(pid)
                    except Exception as e_stock:
                        rapport["messages"].append(
                            f"⚠️ Déduction stock {pid[:16]} : {e_stock}"
                        )

            except Exception as e:
                rapport["erreurs"] += 1
                rapport["messages"].append(f"❌ Erreur ligne : {e}")
                conn.rollback()

        # Journal
        journal.log(
            action="import_excel",
            table_nom="productions",
            enregistrement_id="import_batch",
            nouvelle_valeur={
                "importees": rapport["importees"],
                "ignorees": rapport["ignorees"],
                "erreurs": rapport["erreurs"],
                "mode": "remplacement" if mode_remplacement else "fusion",
            },
            motif=f"Import Excel — {rapport['importees']} productions",
            utilisateur=utilisateur,
        )

    finally:
        conn.close()

    return rapport


# ==================================================================
# UI
# ==================================================================
st.set_page_config(page_title="Import Excel", page_icon="📥", layout="wide")
init_db()

user = auth.exiger_admin()
auth.afficher_barre_utilisateur()

st.title("📥 Import depuis Excel")
st.caption(
    "Recharge des productions et détails matériaux depuis un fichier Excel "
    "généré par l'app (page Tableau de bord)."
)

with st.expander("⚠️ À lire AVANT d'importer", expanded=True):
    st.warning(
        """
        **Précautions :**
        - Fais d'abord un **export Excel des données actuelles** (Tableau de bord)
          — au cas où tu voudrais revenir en arrière.
        - Le fichier Excel doit être **au format généré par cette app** :
          onglets `Productions` et `Détails matériaux`.
        - Les **formules** et **matériaux** référencés dans l'Excel doivent
          exister dans la base actuelle (matching par nom).
        - En **Mode Fusion** (recommandé), les productions déjà présentes
          (même ID) sont **ignorées** — pas de doublon.
        - En **Mode Remplacement**, toutes les productions existantes sont
          **supprimées** avant l'import. ⚠️ Irréversible.
        """
    )

st.markdown("---")
st.subheader("1. Choisir le fichier Excel")

fichier = st.file_uploader(
    "Sélectionne le fichier .xlsx exporté par l'app",
    type=["xlsx"],
    help="Généralement nommé production_beton_kourayzen_YYYY-MM-DD_YYYY-MM-DD.xlsx",
)

if not fichier:
    st.info("👆 Choisis un fichier Excel pour continuer.")
    st.stop()

try:
    xl = pd.ExcelFile(fichier)
    sheets = xl.sheet_names
except Exception as e:
    st.error(f"❌ Impossible de lire le fichier : {e}")
    st.stop()

st.success(f"✅ Fichier lu — {len(sheets)} onglet(s) : {', '.join(sheets)}")

if "Productions" not in sheets:
    st.error(
        "❌ L'onglet **'Productions'** est manquant. "
        "Vérifie que le fichier a bien été généré par la page Tableau de bord."
    )
    st.stop()

df_prod = pd.read_excel(fichier, sheet_name="Productions")
df_details = pd.DataFrame()
if "Détails matériaux" in sheets:
    df_details = pd.read_excel(fichier, sheet_name="Détails matériaux")

st.markdown("---")
st.subheader("2. Prévisualisation")

col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    st.metric("Productions dans le fichier", len(df_prod))
with col_p2:
    st.metric("Lignes de détail matériaux", len(df_details))
with col_p3:
    if not df_prod.empty and "Date" in df_prod.columns:
        dates = pd.to_datetime(df_prod["Date"], errors="coerce").dropna()
        if not dates.empty:
            st.metric("Période", f"{dates.min().date()} → {dates.max().date()}")

with st.expander("👀 Voir les 10 premières productions"):
    st.dataframe(df_prod.head(10), use_container_width=True, hide_index=True)

if not df_details.empty:
    with st.expander("👀 Voir les 10 premières lignes détails"):
        st.dataframe(df_details.head(10), use_container_width=True, hide_index=True)

# ANALYSE PRÉ-IMPORT
st.markdown("---")
st.subheader("3. Analyse pré-import")

formules_existantes = {f["nom"]: f for f in lister_formules(inclure_desactivees=True)}
materiaux_existants_par_nom = {
    m["nom"]: m for m in lister_materiaux(actifs_seulement=False)
}

formules_manquantes = set()
materiaux_manquants = set()

for _, row in df_prod.iterrows():
    nom_formule = str(row.get("Type de béton", "")).strip()
    if nom_formule and nom_formule not in formules_existantes:
        formules_manquantes.add(nom_formule)

if not df_details.empty and "Matériau" in df_details.columns:
    for _, row in df_details.iterrows():
        nom_mat = str(row.get("Matériau", "")).strip()
        if nom_mat and nom_mat not in materiaux_existants_par_nom:
            materiaux_manquants.add(nom_mat)

ids_existants = set()
if not df_prod.empty and "ID" in df_prod.columns:
    conn = get_conn()
    try:
        ids_a_verifier = [
            str(v) for v in df_prod["ID"].dropna().tolist() if str(v).strip()
        ]
        for i in range(0, len(ids_a_verifier), 200):
            chunk = ids_a_verifier[i : i + 200]
            placeholders = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT id FROM productions WHERE id IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            ids_existants.update(r["id"] for r in rows)
    finally:
        conn.close()

col_r1, col_r2, col_r3 = st.columns(3)
with col_r1:
    st.metric("✅ Nouvelles productions à importer", len(df_prod) - len(ids_existants) - len(formules_manquantes))
with col_r2:
    st.metric("⏭️ Déjà en base", len(ids_existants))
with col_r3:
    st.metric("🚫 Formule manquante", len(formules_manquantes))

if formules_manquantes:
    st.error(
        f"❌ **{len(formules_manquantes)} formule(s) manquante(s)** : "
        f"{', '.join(sorted(formules_manquantes))}\n\n"
        "Ces productions seront ignorées. Crée ces formules dans l'app avant l'import."
    )

if materiaux_manquants:
    st.warning(
        f"⚠️ **{len(materiaux_manquants)} matériau(x) manquant(s)** : "
        f"{', '.join(sorted(materiaux_manquants))}"
    )

# OPTIONS
st.markdown("---")
st.subheader("4. Options d'import")

mode = st.radio(
    "Mode d'import",
    options=["Fusion (recommandé)", "Remplacement (⚠️ efface tout)"],
    horizontal=True,
)

deduire_stock = st.checkbox(
    "Déduire automatiquement du stock les productions terminées importées",
    value=False,
    help=(
        "Décoche si tu importes un backup sans vouloir toucher au stock actuel."
    ),
)

# CONFIRMATION + IMPORT
st.markdown("---")
st.subheader("5. Import")

if mode.startswith("Remplacement"):
    confirmation = st.text_input(
        "⚠️ Tape **SUPPRIMER TOUT** pour confirmer",
        placeholder="SUPPRIMER TOUT",
    )
    bouton_actif = confirmation == "SUPPRIMER TOUT"
    if not bouton_actif:
        st.info("Tape la phrase exacte ci-dessus pour activer l'import.")
else:
    bouton_actif = True

if st.button(
    "🚀 Lancer l'import",
    type="primary",
    disabled=not bouton_actif,
    use_container_width=True,
):
    with st.spinner("Import en cours..."):
        rapport = importer_donnees(
            df_prod=df_prod,
            df_details=df_details,
            formules_par_nom=formules_existantes,
            mats_par_nom=materiaux_existants_par_nom,
            ids_existants=ids_existants,
            mode_remplacement=mode.startswith("Remplacement"),
            deduire_stock=deduire_stock,
            utilisateur=user["nom"] if user else "admin",
        )

    st.success("✅ Import terminé")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Importées", rapport["importees"])
    col2.metric("Ignorées", rapport["ignorees"])
    col3.metric("Détails matériaux", rapport["details_ok"])
    col4.metric("Erreurs", rapport["erreurs"])

    if rapport["messages"]:
        with st.expander(f"📋 Détail ({len(rapport['messages'])} messages)"):
            for m in rapport["messages"][:200]:
                if m.startswith("✅"):
                    st.text(m)
                elif m.startswith("⏭️"):
                    st.caption(m)
                elif m.startswith("❌"):
                    st.error(m)
                else:
                    st.info(m)
