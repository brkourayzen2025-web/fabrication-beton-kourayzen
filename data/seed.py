"""Insertion des données de référence à la première ouverture.

Contient uniquement des valeurs validées :
  - Formules nominales BCV LPEE (RM 06-2026)  -> statut = validee
  - Étude BCR F3 (docx Formulation BCR)        -> statut = a_valider
  - Matériaux HOTRADI + densités
  - Adjuvant SUDAK SUPER PLAST 265
  - Chargeur : godets sable/G1/G2 mesurés (85/74/71 seaux de 27 L)
"""
from __future__ import annotations

from datetime import datetime

from models.constants import (
    CAT_ADJUVANT,
    CAT_EAU,
    CAT_GRANULAT,
    CAT_LIANT,
    CHANTIER_NOM,
    POIDS_SAC_CIMENT_DEFAUT_KG,
    SEUIL_ECART_ALERTE_PCT,
    STATUT_A_VALIDER,
    STATUT_VALIDEE,
)


def inserer_seed(conn: "Connection") -> None:
    """Insère toutes les données initiales dans la BD."""
    now = datetime.now().isoformat()

    # ==============================================================
    # 1. TYPES DE BÉTON
    # ==============================================================
    types = [
        ("TB-BCV", "BCV", "Béton conventionnel vibré — structure D/27 (350 kg/m³)"),
        ("TB-CONTACT", "Béton de contact", "Béton de contact fondation D/23 (280 kg/m³)"),
        ("TB-LIAISON", "Mortier de liaison", "Béton de liaison entre couches BCR (350 kg/m³)"),
        ("TB-BCR", "BCR", "Béton compacté au rouleau — Formule F3 (100 kg ciment)"),
    ]
    conn.executemany(
        "INSERT INTO types_beton (id, nom, description, actif, created_at) VALUES (?, ?, ?, 1, ?)",
        [(i, n, d, now) for i, n, d in types],
    )

    # ==============================================================
    # 2. MATÉRIAUX (référentiel)
    # Densités apparentes (t/m³ = kg/L) fournies par l'utilisateur.
    # Densité adjuvant SUDAK : 1,10 t/m³ (fiche technique + RM 06-2026).
    # ==============================================================
    materiaux = [
        # (id, nom, categorie, unite_stock, densite, poids_sac)
        ("MAT-SABLE", "Sable mélange 0/4", CAT_GRANULAT, "kg", 1.53, None),
        ("MAT-G1", "G1 (Gravillon 4/16)", CAT_GRANULAT, "kg", 1.40, None),
        ("MAT-G2", "G2 (Gravette 16/25)", CAT_GRANULAT, "kg", 1.38, None),
        # G3 pour le BCR : densité inconnue -> à renseigner par utilisateur
        ("MAT-G3", "G3 (Cailloux 31,5/63)", CAT_GRANULAT, "kg", None, None),
        ("MAT-CIMENT", "Ciment CPJ 45 (CEMOS)", CAT_LIANT, "kg", None, POIDS_SAC_CIMENT_DEFAUT_KG),
        ("MAT-EAU", "Eau de gâchage (puits chantier)", CAT_EAU, "L", 1.00, None),
        ("MAT-ADJ-SUDAK", "Adjuvant SUDAK SUPER PLAST 265", CAT_ADJUVANT, "L", 1.10, None),
    ]
    conn.executemany(
        """INSERT INTO materiaux
           (id, nom, categorie, unite_stock, densite_apparente, poids_sac_defaut, actif)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        materiaux,
    )

    # ==============================================================
    # 3. FORMULES + COMPOSITION
    # Toutes les quantités par m³ de béton.
    # ==============================================================
    # BCV D/27 structure (RM 06-2026, Nominale)
    _inserer_formule(
        conn, "F-BCV-D27-V1", "TB-BCV",
        "BCV D/27 — structure (nominale)",
        STATUT_VALIDEE, "2026-06-30", "LPEE",
        "RM 06-2026 §VII-2 - Rc28j moyen 29,7 MPa",
        [
            ("MAT-SABLE", 870.0, "kg", 1),
            ("MAT-G1", 610.0, "kg", 2),
            ("MAT-G2", 510.0, "kg", 3),
            ("MAT-CIMENT", 350.0, "kg", 4),
            ("MAT-EAU", 170.0, "L", 5),
            ("MAT-ADJ-SUDAK", 1.2, "pct_ciment", 6),
        ],
        now,
    )
    # Béton contact D/23 (RM 06-2026, Nominale)
    _inserer_formule(
        conn, "F-CONTACT-D23-V1", "TB-CONTACT",
        "Béton contact D/23 — fondation (nominale)",
        STATUT_VALIDEE, "2026-06-30", "LPEE",
        "RM 06-2026 §VII-1 - Rc28j moyen 24,3 MPa",
        [
            ("MAT-SABLE", 855.0, "kg", 1),
            ("MAT-G1", 590.0, "kg", 2),
            ("MAT-G2", 500.0, "kg", 3),
            ("MAT-CIMENT", 280.0, "kg", 4),
            ("MAT-EAU", 175.0, "L", 5),
            ("MAT-ADJ-SUDAK", 1.2, "pct_ciment", 6),
        ],
        now,
    )
    # Mortier de liaison BCR (RM 06-2026, Nominale) — pas de G2
    _inserer_formule(
        conn, "F-LIAISON-V1", "TB-LIAISON",
        "Mortier de liaison entre couches BCR (nominale)",
        STATUT_VALIDEE, "2026-06-30", "LPEE",
        "RM 06-2026 §VII-3 - Rc28j moyen 27,8 MPa. Pas de G2.",
        [
            ("MAT-SABLE", 1060.0, "kg", 1),
            ("MAT-G1", 850.0, "kg", 2),
            ("MAT-CIMENT", 350.0, "kg", 3),
            ("MAT-EAU", 180.0, "L", 4),
            ("MAT-ADJ-SUDAK", 1.6, "pct_ciment", 5),
        ],
        now,
    )
    # BCR F3 (étude) - statut à valider, données G3 manquantes
    _inserer_formule(
        conn, "F-BCR-F3-V1", "TB-BCR",
        "BCR F3 — 100 kg ciment (étude)",
        STATUT_A_VALIDER, None, None,
        ("Docx Formulation BCR — Étude, Rc28j 8,3 MPa. "
         "⚠️ Données manquantes : densité G3 (Cailloux 31,5/63), "
         "vérification densité Graviers 16/31,5 (BCR) vs 16/25 (BCV G2), "
         "densité sable mélange fillerisé BCR, mesures godets G2/G3."),
        [
            ("MAT-SABLE", 936.0, "kg", 1),
            ("MAT-G1", 580.0, "kg", 2),
            ("MAT-G2", 430.0, "kg", 3),
            ("MAT-G3", 480.0, "kg", 4),
            ("MAT-CIMENT", 100.0, "kg", 5),
            ("MAT-EAU", 105.0, "L", 6),
            ("MAT-ADJ-SUDAK", 1.0, "pct_ciment", 7),
        ],
        now,
    )

    # ==============================================================
    # 4. ENGIN + GODETS chargeur
    # Sable = 85 seaux × 27 L = 2 295 L
    # G1    = 74 × 27 = 1 998 L
    # G2    = 71 × 27 = 1 917 L
    # ==============================================================
    conn.execute("""
        INSERT INTO engins (id, nom, type_engin, actif, observations)
        VALUES ('ENG-CHARGEUR-01', 'Chargeur principal', 'chargeur', 1,
                'Engin par défaut du chantier')
    """)

    godets = [
        ("GOD-CHARG-SABLE", "Godet chargeur — Sable", "MAT-SABLE", 85 * 27.0, "85 seaux de 27 L"),
        ("GOD-CHARG-G1", "Godet chargeur — G1", "MAT-G1", 74 * 27.0, "74 seaux de 27 L"),
        ("GOD-CHARG-G2", "Godet chargeur — G2", "MAT-G2", 71 * 27.0, "71 seaux de 27 L"),
    ]
    for gid, nom, mat, capa, obs in godets:
        conn.execute("""
            INSERT INTO godets
              (id, nom, engin_id, materiau_id, capacite_mesuree_l,
               coef_remplissage, type_remplissage, observations, actif)
            VALUES (?, ?, 'ENG-CHARGEUR-01', ?, ?, 1.0, 'ras', ?, 1)
        """, (gid, nom, mat, capa, obs))

    # ==============================================================
    # 5. PARAMÈTRES
    # ==============================================================
    params = [
        ("chantier_nom", CHANTIER_NOM, "Nom du chantier"),
        ("poids_sac_ciment_kg", str(POIDS_SAC_CIMENT_DEFAUT_KG), "Poids d'un sac de ciment (kg)"),
        ("seuil_ecart_pct", str(SEUIL_ECART_ALERTE_PCT), "Seuil d'écart (%) au-delà duquel on alerte"),
    ]
    conn.executemany(
        "INSERT INTO parametres (cle, valeur, description) VALUES (?, ?, ?)",
        params,
    )


def _inserer_formule(
    conn: "Connection",
    id_: str,
    type_id: str,
    nom: str,
    statut: str,
    date_validation: str | None,
    valide_par: str | None,
    observations: str,
    composition: list[tuple],
    now: str,
) -> None:
    """Insère une formule + sa composition."""
    conn.execute(
        """INSERT INTO formules
           (id, type_beton_id, nom, version, statut, volume_reference_m3,
            date_validation, valide_par, observations, created_at)
           VALUES (?, ?, ?, 1, ?, 1.0, ?, ?, ?, ?)""",
        (id_, type_id, nom, statut, date_validation, valide_par, observations, now),
    )
    for mat_id, qte, unite, ordre in composition:
        conn.execute(
            """INSERT INTO formule_composition
               (formule_id, materiau_id, quantite, unite, ordre_ajout)
               VALUES (?, ?, ?, ?, ?)""",
            (id_, mat_id, qte, unite, ordre),
        )
