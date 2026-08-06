"""Constantes globales de l'application Fabrication Béton.

Chantier Kourayzen — Marché n° 30/2024/DAH.
"""
from pathlib import Path

# === Application ===
APP_NOM = "Fabrication Béton"
APP_NOM_COMPLET = "Fabrication Béton — Chantier Kourayzen"

# === Chantier ===
CHANTIER_NOM = "Barrage Kourayzen"
CHANTIER_MARCHE = "Marché n° 30/2024/DAH"

# === Base de données ===
# La BD SQLite est stockée à côté du fichier app.py.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "fabrication_beton.db"

# === Défauts métier ===
POIDS_SAC_CIMENT_DEFAUT_KG = 50.0
SEUIL_ECART_ALERTE_PCT = 15.0
DECIMALES_GODETS = 2

# === Statuts formule ===
STATUT_BROUILLON = "brouillon"
STATUT_A_VALIDER = "a_valider"
STATUT_VALIDEE = "validee"
STATUT_DESACTIVEE = "desactivee"

# === Statuts production ===
PROD_EN_COURS = "en_cours"
PROD_TERMINEE = "terminee"
PROD_ANNULEE = "annulee"

# === Catégories matériau ===
CAT_GRANULAT = "granulat"
CAT_LIANT = "liant"
CAT_EAU = "eau"
CAT_ADJUVANT = "adjuvant"
CAT_AUTRE = "autre"

# === Unités formule ===
UNITE_KG = "kg"
UNITE_LITRE = "L"
UNITE_PCT_CIMENT = "pct_ciment"

# === Couleurs (pour markdown/HTML si besoin) ===
COULEUR_PRIMAIRE = "#1565C0"
COULEUR_ACCENT = "#FF8F00"
COULEUR_VALIDEE = "#2E7D32"
COULEUR_A_VALIDER = "#EF6C00"
COULEUR_ALERTE = "#C62828"
