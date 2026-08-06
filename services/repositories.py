"""Repositories (DAO) : accès aux données SQLite.

Toutes les fonctions retournent des dict/list de dict pour être
directement utilisables par Streamlit.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

from data.database import get_conn


# ==================================================================
# LECTURES : matériaux, formules, engins, godets
# ==================================================================
def lister_materiaux(actifs_seulement: bool = True) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        where = "WHERE actif = 1" if actifs_seulement else ""
        rows = conn.execute(f"SELECT * FROM materiaux {where} ORDER BY nom").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def materiaux_par_id() -> dict[str, dict[str, Any]]:
    """Dict {materiau_id: dict}."""
    return {m["id"]: m for m in lister_materiaux()}


def modifier_materiau(
    materiau_id: str,
    nom: str | None = None,
    densite_apparente: float | None = None,
    poids_sac_defaut: float | None = None,
    utilisateur: str | None = None,
) -> None:
    """Met à jour les propriétés d'un matériau existant.

    ⚠️  Une modification de densité affecte tous les NOUVEAUX calculs.
        Les productions déjà enregistrées ne sont pas recalculées
        (elles conservent leur snapshot immuable).
    """
    # Lire l'ancien état pour le journal
    conn = get_conn()
    try:
        old = conn.execute(
            "SELECT nom, densite_apparente, poids_sac_defaut FROM materiaux WHERE id = ?",
            (materiau_id,),
        ).fetchone()
        if not old:
            raise ValueError(f"Matériau introuvable : {materiau_id}")
        old_dict = dict(old)

        champs = {}
        if nom is not None and nom.strip() and nom != old_dict["nom"]:
            champs["nom"] = nom.strip()
        if densite_apparente is not None and densite_apparente != old_dict["densite_apparente"]:
            # 0 ou négatif interdit (sauf pour matériaux sans densité applicable)
            if densite_apparente < 0:
                raise ValueError("La densité doit être >= 0")
            champs["densite_apparente"] = densite_apparente if densite_apparente > 0 else None
        if poids_sac_defaut is not None and poids_sac_defaut != old_dict["poids_sac_defaut"]:
            if poids_sac_defaut < 0:
                raise ValueError("Le poids sac doit être >= 0")
            champs["poids_sac_defaut"] = poids_sac_defaut if poids_sac_defaut > 0 else None

        if not champs:
            return  # rien à faire

        sets = ", ".join(f"{k} = ?" for k in champs)
        conn.execute(
            f"UPDATE materiaux SET {sets} WHERE id = ?",
            (*champs.values(), materiau_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Journal
    from services import journal
    journal.log(
        action="modification_materiau",
        table_nom="materiaux",
        enregistrement_id=materiau_id,
        ancienne_valeur=old_dict,
        nouvelle_valeur=champs,
        utilisateur=utilisateur,
    )


def lister_types_beton() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM types_beton WHERE actif = 1 ORDER BY nom").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def lister_formules(inclure_desactivees: bool = False) -> list[dict[str, Any]]:
    """Retourne toutes les formules avec leur composition."""
    conn = get_conn()
    try:
        where = "" if inclure_desactivees else "WHERE statut != 'desactivee'"
        rows = conn.execute(f"SELECT * FROM formules {where} ORDER BY nom").fetchall()
        formules = []
        for r in rows:
            f = dict(r)
            f["composition"] = _charger_composition(conn, f["id"])
            formules.append(f)
        return formules
    finally:
        conn.close()


def formule_par_id(formule_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM formules WHERE id = ?", (formule_id,)).fetchone()
        if not r:
            return None
        f = dict(r)
        f["composition"] = _charger_composition(conn, formule_id)
        return f
    finally:
        conn.close()


def _charger_composition(conn: "Connection", formule_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT materiau_id, quantite, unite, ordre_ajout
           FROM formule_composition
           WHERE formule_id = ?
           ORDER BY COALESCE(ordre_ajout, 999)""",
        (formule_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def lister_engins(actifs_seulement: bool = True) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        where = "WHERE actif = 1" if actifs_seulement else ""
        rows = conn.execute(f"SELECT * FROM engins {where} ORDER BY nom").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def godets_par_materiau(engin_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Retourne un dict {materiau_id: godet} avec les godets actifs.
    Filtré optionnellement par engin_id.
    """
    conn = get_conn()
    try:
        sql = "SELECT * FROM godets WHERE actif = 1"
        args: tuple = ()
        if engin_id:
            sql += " AND engin_id = ?"
            args = (engin_id,)
        rows = conn.execute(sql, args).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            g = dict(r)
            result.setdefault(g["materiau_id"], g)  # premier trouvé pour chaque matériau
        return result
    finally:
        conn.close()


def lister_godets() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM godets ORDER BY nom").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ==================================================================
# CRUD Engin
# ==================================================================
def creer_engin(nom: str, type_engin: str, marque: str | None = None,
                modele: str | None = None, immatriculation: str | None = None,
                observations: str | None = None, actif: bool = True) -> str:
    conn = get_conn()
    try:
        eid = f"ENG-{uuid.uuid4().hex[:8].upper()}"
        conn.execute(
            """INSERT INTO engins (id, nom, type_engin, marque, modele, immatriculation, actif, observations)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, nom, type_engin, marque, modele, immatriculation, int(actif), observations),
        )
        conn.commit()
        return eid
    finally:
        conn.close()


def modifier_engin(eid: str, **champs) -> None:
    """Modifie un engin. Champs autorisés : nom, type_engin, marque, modele,
    immatriculation, actif, observations."""
    permis = {"nom", "type_engin", "marque", "modele", "immatriculation", "actif", "observations"}
    champs = {k: (int(v) if k == "actif" else v) for k, v in champs.items() if k in permis}
    if not champs:
        return
    conn = get_conn()
    try:
        sets = ", ".join(f"{k} = ?" for k in champs)
        conn.execute(f"UPDATE engins SET {sets} WHERE id = ?",
                     (*champs.values(), eid))
        conn.commit()
    finally:
        conn.close()


# ==================================================================
# CRUD Godet
# ==================================================================
def creer_godet(nom: str, engin_id: str, materiau_id: str,
                capacite_mesuree_l: float, coef_remplissage: float = 1.0,
                type_remplissage: str = "ras", observations: str | None = None,
                actif: bool = True) -> str:
    conn = get_conn()
    try:
        gid = f"GOD-{uuid.uuid4().hex[:8].upper()}"
        conn.execute(
            """INSERT INTO godets
               (id, nom, engin_id, materiau_id, capacite_mesuree_l,
                coef_remplissage, type_remplissage, observations, actif)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gid, nom, engin_id, materiau_id, capacite_mesuree_l,
             coef_remplissage, type_remplissage, observations, int(actif)),
        )
        conn.commit()
        return gid
    finally:
        conn.close()


def modifier_godet(gid: str, **champs) -> None:
    permis = {"nom", "engin_id", "materiau_id", "capacite_mesuree_l",
              "coef_remplissage", "type_remplissage", "observations", "actif"}
    champs = {k: (int(v) if k == "actif" else v) for k, v in champs.items() if k in permis}
    if not champs:
        return
    conn = get_conn()
    try:
        sets = ", ".join(f"{k} = ?" for k in champs)
        conn.execute(f"UPDATE godets SET {sets} WHERE id = ?", (*champs.values(), gid))
        conn.commit()
    finally:
        conn.close()


# ==================================================================
# CRUD Production
# ==================================================================
def creer_production(
    formule_id: str,
    formule_snapshot_json: str,
    volume_prevu_m3: float,
    date_str: str,
    heure_str: str,
    poids_sac_ciment_kg: float,
    engin_id: str | None = None,
    zone_melange: str | None = None,
    zone_mise_en_oeuvre: str | None = None,
    operateur: str | None = None,
    observation: str | None = None,
    materiaux_lignes: list[dict[str, Any]] | None = None,
) -> str:
    """Crée une production + ses lignes matériaux en une transaction.

    Retourne l'ID de la production créée.
    """
    conn = get_conn()
    try:
        pid = f"PROD-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO productions
               (id, date, heure, formule_id, formule_snapshot_json,
                volume_prevu_m3, engin_id, zone_melange, zone_mise_en_oeuvre,
                operateur, poids_sac_ciment_kg, observation, statut,
                materiaux_confirmes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'en_cours', 0, ?, ?)""",
            (pid, date_str, heure_str, formule_id, formule_snapshot_json,
             volume_prevu_m3, engin_id, zone_melange, zone_mise_en_oeuvre,
             operateur, poids_sac_ciment_kg, observation, now, now),
        )

        for ligne in (materiaux_lignes or []):
            conn.execute(
                """INSERT INTO production_materiaux
                   (production_id, materiau_id, godet_id,
                    quantite_theorique, unite_theorique,
                    nb_godets_theorique, godets_complets_theorique,
                    pct_dernier_godet_theorique, qte_dernier_godet_l_theorique,
                    nb_sacs_theorique, confirme, confirme_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    ligne["materiau_id"],
                    ligne.get("godet_id"),
                    ligne["quantite_theorique"],
                    ligne["unite_theorique"],
                    ligne.get("nb_godets_theorique"),
                    ligne.get("godets_complets_theorique"),
                    ligne.get("pct_dernier_godet_theorique"),
                    ligne.get("qte_dernier_godet_l_theorique"),
                    ligne.get("nb_sacs_theorique"),
                    int(ligne.get("confirme", False)),
                    ligne.get("confirme_at"),
                ),
            )
        conn.commit()
        return pid
    finally:
        conn.close()


def production_par_id(pid: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM productions WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def lignes_production(pid: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM production_materiaux WHERE production_id = ? ORDER BY id",
            (pid,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def lister_productions_par_date(date_str: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM productions WHERE date = ? ORDER BY heure DESC",
            (date_str,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def lister_productions(limite: int = 500) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM productions ORDER BY date DESC, heure DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def maj_ligne_reels(
    ligne_id: int,
    quantite_reelle: float | None,
    nb_godets_reel: float | None,
    nb_sacs_reel: float | None,
    ecart_absolu: float | None,
    ecart_pct: float | None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE production_materiaux SET
                 quantite_reelle = ?,
                 nb_godets_reel = ?,
                 nb_sacs_reel = ?,
                 ecart_absolu = ?,
                 ecart_pct = ?,
                 confirme = 1,
                 confirme_at = ?
               WHERE id = ?""",
            (quantite_reelle, nb_godets_reel, nb_sacs_reel,
             ecart_absolu, ecart_pct, datetime.now().isoformat(), ligne_id),
        )
        conn.commit()
    finally:
        conn.close()


def terminer_production(pid: str, volume_reel_m3: float | None = None) -> int:
    """Marque une production comme terminée + déduit automatiquement le stock.

    Retourne le nombre de mouvements de sortie créés.
    """
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE productions
               SET statut = 'terminee',
                   materiaux_confirmes = 1,
                   volume_reel_m3 = COALESCE(?, volume_reel_m3),
                   updated_at = ?
               WHERE id = ?""",
            (volume_reel_m3, datetime.now().isoformat(), pid),
        )
        conn.commit()
    finally:
        conn.close()

    # Auto-déduction du stock (idempotente)
    from services.stock import deduire_production
    return deduire_production(pid)


def annuler_production(pid: str) -> int:
    """Annule une production + supprime les mouvements de sortie associés."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE productions SET statut = 'annulee', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), pid),
        )
        conn.commit()
    finally:
        conn.close()

    from services.stock import annuler_deduction
    return annuler_deduction(pid)
