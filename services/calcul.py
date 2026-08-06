"""Service de calcul métier — godets, sacs, écarts, fiche de préparation.

RÈGLES STRICTES :
  - Nb godets = quantité litres ÷ capacité utile godet
  - Résultat conservé à 2 décimales, JAMAIS arrondi au 1/2 ou 1/4 de godet
  - Partie décimale = pourcentage direct du dernier godet
    Exemple : 3,45 godets = 3 godets complets + 45 % du dernier godet
  - Ne PAS transformer 0,40 en 0,50 automatiquement

Conversions :
  - masse (kg) → volume apparent (L) : masse ÷ densité apparente (t/m³)
    Justification : densité en t/m³ = kg/L
  - adjuvant en % du poids ciment → kg → L via sa densité
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from models.constants import (
    CAT_ADJUVANT,
    CAT_EAU,
    CAT_GRANULAT,
    CAT_LIANT,
    DECIMALES_GODETS,
    UNITE_KG,
    UNITE_LITRE,
    UNITE_PCT_CIMENT,
)


# ==================================================================
# Dataclasses de résultats
# ==================================================================
@dataclass
class CalculGodet:
    """Résultat du calcul des godets pour un matériau granulaire."""
    nb_godets: float           # ex. 3.45, 2 décimales, non arrondi
    godets_complets: int       # 3
    pct_dernier_godet: float   # 45.0
    qte_dernier_godet_l: float # 704.7 L
    capacite_utile_l: float    # 1566.0
    quantite_totale_l: float   # 5400.0

    @property
    def est_godet_pile(self) -> bool:
        return float(self.godets_complets) == self.nb_godets

    @property
    def instruction_courte(self) -> str:
        if self.est_godet_pile:
            return f"{self.godets_complets} godets complets"
        return f"{self.godets_complets} godets complets + {self.pct_dernier_godet:.0f} % du dernier"


@dataclass
class CalculSac:
    """Résultat du calcul des sacs pour le ciment."""
    quantite_kg: float
    poids_sac_kg: float
    nb_sacs_theorique: float
    nb_sacs_complets: int
    kg_supplementaires: float

    @property
    def est_sacs_pile(self) -> bool:
        return self.kg_supplementaires == 0.0

    @property
    def instruction_courte(self) -> str:
        if self.est_sacs_pile:
            return f"{self.nb_sacs_complets} sacs de {self.poids_sac_kg:.0f} kg"
        return f"{self.nb_sacs_complets} sacs + {self.kg_supplementaires:.1f} kg"


@dataclass
class LigneFiche:
    """Une ligne de la fiche de préparation (un matériau)."""
    materiau_id: str
    materiau_nom: str
    categorie: str
    quantite_theorique: float
    unite_theorique: str
    volume_apparent_l: float | None = None
    godet: CalculGodet | None = None
    sac: CalculSac | None = None
    godet_id: str | None = None
    avertissement: str | None = None


# ==================================================================
# 1. GODETS
# ==================================================================
def calculer_godets(quantite_litres: float, capacite_utile_litres: float) -> CalculGodet:
    """Calcule le nombre de godets pour une quantité en litres.

    Arrondi à 2 décimales, JAMAIS au demi-godet.
    """
    if capacite_utile_litres <= 0:
        raise ValueError("La capacité utile doit être > 0 L")
    if quantite_litres < 0:
        raise ValueError("La quantité doit être >= 0")

    nb_brut = quantite_litres / capacite_utile_litres
    nb_godets = round(nb_brut, DECIMALES_GODETS)
    godets_complets = int(nb_godets)  # partie entière (floor pour >= 0)
    partie_dec = round(nb_godets - godets_complets, DECIMALES_GODETS)
    pct_dernier = round(partie_dec * 100, DECIMALES_GODETS)
    qte_dernier = round(capacite_utile_litres * partie_dec, DECIMALES_GODETS)

    return CalculGodet(
        nb_godets=nb_godets,
        godets_complets=godets_complets,
        pct_dernier_godet=pct_dernier,
        qte_dernier_godet_l=qte_dernier,
        capacite_utile_l=round(capacite_utile_litres, 2),
        quantite_totale_l=round(quantite_litres, 2),
    )


def ecart_godets(
    godets_theorique: float,
    godets_reel: float,
    capacite_utile_litres: float,
) -> dict[str, float]:
    """Écart en godets + litres + %."""
    ec_g = round(godets_reel - godets_theorique, DECIMALES_GODETS)
    ec_l = round(ec_g * capacite_utile_litres, 2)
    ec_p = 0.0 if godets_theorique == 0 else round((ec_g / godets_theorique) * 100, 2)
    return {"ecart_godets": ec_g, "ecart_litres": ec_l, "ecart_pct": ec_p}


# ==================================================================
# 2. SACS DE CIMENT
# ==================================================================
def calculer_sacs(quantite_kg: float, poids_sac_kg: float) -> CalculSac:
    if poids_sac_kg <= 0:
        raise ValueError("Poids sac doit être > 0")
    if quantite_kg < 0:
        raise ValueError("Quantité doit être >= 0")

    nb_th = round(quantite_kg / poids_sac_kg, 2)
    nb_complets = int(nb_th)
    kg_supp = round(quantite_kg - (nb_complets * poids_sac_kg), 1)
    return CalculSac(
        quantite_kg=round(quantite_kg, 2),
        poids_sac_kg=poids_sac_kg,
        nb_sacs_theorique=nb_th,
        nb_sacs_complets=nb_complets,
        kg_supplementaires=kg_supp,
    )


def ecart_sacs(
    sacs_theorique: float,
    sacs_reel: float,
    poids_sac_kg: float,
) -> dict[str, float]:
    ec_s = round(sacs_reel - sacs_theorique, 2)
    ec_kg = round(ec_s * poids_sac_kg, 2)
    ec_p = 0.0 if sacs_theorique == 0 else round((ec_s / sacs_theorique) * 100, 2)
    return {"ecart_sacs": ec_s, "ecart_kg": ec_kg, "ecart_pct": ec_p}


def ecart_quantite(qte_theorique: float, qte_reelle: float) -> dict[str, float]:
    """Écart générique en unité de la quantité."""
    ec = round(qte_reelle - qte_theorique, 2)
    ec_p = 0.0 if qte_theorique == 0 else round((ec / qte_theorique) * 100, 2)
    return {"ecart_absolu": ec, "ecart_pct": ec_p}


# ==================================================================
# 3. CONVERSIONS
# ==================================================================
def masse_vers_litres(masse_kg: float, densite_t_m3: float) -> float:
    """Masse (kg) → volume apparent (L) via densité apparente en t/m³.

    Densité t/m³ = kg/L (1 t/m³ = 1000 kg / 1000 L = 1 kg/L).
    """
    if densite_t_m3 <= 0:
        raise ValueError("Densité doit être > 0")
    return masse_kg / densite_t_m3


# ==================================================================
# 4. CONSTRUCTION DE LA FICHE DE PRÉPARATION
# ==================================================================
def construire_fiche(
    composition: list[dict[str, Any]],  # [{materiau_id, quantite, unite, ordre_ajout}, ...]
    volume_prevu_m3: float,
    volume_reference_m3: float,
    materiaux_by_id: dict[str, dict[str, Any]],  # {id: {nom, categorie, densite_apparente, ...}}
    godets_by_materiau_id: dict[str, dict[str, Any]],  # {mat_id: {id, capacite_mesuree_l, coef_remplissage, ...}}
    poids_sac_ciment_kg: float,
) -> list[LigneFiche]:
    """Génère la liste des lignes prêtes à afficher pour un mélange."""
    if volume_prevu_m3 <= 0:
        raise ValueError("Volume prévu doit être > 0")

    facteur = volume_prevu_m3 / volume_reference_m3

    # Trier par ordre d'ajout
    compo_triee = sorted(
        composition, key=lambda c: c.get("ordre_ajout") or 999
    )

    # Trouver le total de ciment (utile pour l'adjuvant en % ciment)
    ciment_kg_total = None
    for c in compo_triee:
        mat = materiaux_by_id.get(c["materiau_id"])
        if mat and mat["categorie"] == CAT_LIANT and c["unite"] == UNITE_KG:
            ciment_kg_total = c["quantite"] * facteur
            break

    lignes: list[LigneFiche] = []

    for c in compo_triee:
        mat = materiaux_by_id.get(c["materiau_id"])
        if mat is None:
            lignes.append(LigneFiche(
                materiau_id=c["materiau_id"],
                materiau_nom=c["materiau_id"],
                categorie="autre",
                quantite_theorique=c["quantite"] * facteur,
                unite_theorique=c["unite"],
                avertissement="Matériau inconnu dans le référentiel",
            ))
            continue

        cat = mat["categorie"]

        # --- CIMENT ---
        if cat == CAT_LIANT and c["unite"] == UNITE_KG:
            qte_kg = c["quantite"] * facteur
            sac = calculer_sacs(qte_kg, poids_sac_ciment_kg)
            lignes.append(LigneFiche(
                materiau_id=mat["id"],
                materiau_nom=mat["nom"],
                categorie=cat,
                quantite_theorique=round(qte_kg, 2),
                unite_theorique=UNITE_KG,
                sac=sac,
            ))
            continue

        # --- EAU ---
        if cat == CAT_EAU:
            qte_l = c["quantite"] * facteur  # eau : kg = L
            lignes.append(LigneFiche(
                materiau_id=mat["id"],
                materiau_nom=mat["nom"],
                categorie=cat,
                quantite_theorique=round(qte_l, 2),
                unite_theorique=UNITE_LITRE,
            ))
            continue

        # --- ADJUVANT ---
        if cat == CAT_ADJUVANT:
            if c["unite"] == UNITE_PCT_CIMENT:
                if ciment_kg_total is None:
                    lignes.append(LigneFiche(
                        materiau_id=mat["id"],
                        materiau_nom=mat["nom"],
                        categorie=cat,
                        quantite_theorique=0,
                        unite_theorique="L",
                        avertissement="Adjuvant en % ciment mais aucun ciment trouvé dans la formule",
                    ))
                    continue
                qte_kg = ciment_kg_total * (c["quantite"] / 100.0)
            elif c["unite"] == UNITE_KG:
                qte_kg = c["quantite"] * facteur
            else:
                # déjà en L
                lignes.append(LigneFiche(
                    materiau_id=mat["id"],
                    materiau_nom=mat["nom"],
                    categorie=cat,
                    quantite_theorique=round(c["quantite"] * facteur, 2),
                    unite_theorique=UNITE_LITRE,
                ))
                continue

            densite = mat.get("densite_apparente")
            if densite and densite > 0:
                qte_l = masse_vers_litres(qte_kg, densite)
                lignes.append(LigneFiche(
                    materiau_id=mat["id"],
                    materiau_nom=mat["nom"],
                    categorie=cat,
                    quantite_theorique=round(qte_l, 2),
                    unite_theorique=UNITE_LITRE,
                ))
            else:
                lignes.append(LigneFiche(
                    materiau_id=mat["id"],
                    materiau_nom=mat["nom"],
                    categorie=cat,
                    quantite_theorique=round(qte_kg, 2),
                    unite_theorique=UNITE_KG,
                    avertissement="Densité adjuvant inconnue — affiché en kg",
                ))
            continue

        # --- GRANULAT ---
        if cat == CAT_GRANULAT:
            qte_kg = c["quantite"] * facteur
            densite = mat.get("densite_apparente")

            if not densite or densite <= 0:
                lignes.append(LigneFiche(
                    materiau_id=mat["id"],
                    materiau_nom=mat["nom"],
                    categorie=cat,
                    quantite_theorique=round(qte_kg, 2),
                    unite_theorique=UNITE_KG,
                    avertissement=f"Densité apparente non renseignée pour {mat['nom']} — calcul godets impossible",
                ))
                continue

            vol_l = masse_vers_litres(qte_kg, densite)
            godet = godets_by_materiau_id.get(mat["id"])
            if godet is None:
                lignes.append(LigneFiche(
                    materiau_id=mat["id"],
                    materiau_nom=mat["nom"],
                    categorie=cat,
                    quantite_theorique=round(qte_kg, 2),
                    unite_theorique=UNITE_KG,
                    volume_apparent_l=round(vol_l, 2),
                    avertissement=f"Aucun godet actif pour {mat['nom']} — configurer dans Engins et godets",
                ))
                continue

            capa_utile = godet["capacite_mesuree_l"] * godet["coef_remplissage"]
            g = calculer_godets(vol_l, capa_utile)
            lignes.append(LigneFiche(
                materiau_id=mat["id"],
                materiau_nom=mat["nom"],
                categorie=cat,
                quantite_theorique=round(qte_kg, 2),
                unite_theorique=UNITE_KG,
                volume_apparent_l=round(vol_l, 2),
                godet=g,
                godet_id=godet["id"],
            ))
            continue

        # --- AUTRE ---
        lignes.append(LigneFiche(
            materiau_id=mat["id"],
            materiau_nom=mat["nom"],
            categorie=cat,
            quantite_theorique=round(c["quantite"] * facteur, 2),
            unite_theorique=c["unite"],
        ))

    return lignes


def snapshot_formule_json(formule: dict[str, Any], composition: list[dict[str, Any]]) -> str:
    """Sérialise la formule + composition pour stockage immuable dans la prod."""
    return json.dumps({
        "formule_id": formule["id"],
        "nom": formule["nom"],
        "version": formule["version"],
        "statut": formule["statut"],
        "date_validation": formule.get("date_validation"),
        "valide_par": formule.get("valide_par"),
        "composition": composition,
    }, ensure_ascii=False)


# ==================================================================
# 5. Formatage FR
# ==================================================================
def fr(v: float) -> str:
    """Formate un nombre en FR (virgule décimale, sans zéros inutiles)."""
    if v == int(v):
        return f"{int(v):,}".replace(",", " ")
    return f"{v:.2f}".replace(".", ",")


def fr_signe(v: float) -> str:
    """Formate avec signe explicite pour les écarts."""
    if v > 0:
        return f"+{fr(v)}"
    return fr(v)
