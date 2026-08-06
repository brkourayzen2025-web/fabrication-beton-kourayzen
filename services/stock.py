"""Service de gestion du stock — spécifique à cette application.

Base indépendante : ne touche pas à `materiaux_kourayzen`.

Principe :
  stock_actuel = entrees + ajustements_pos - sorties (auto-productions) - ajustements_neg

  Les sorties sont créées AUTOMATIQUEMENT quand une production est terminée.
  Les entrées sont saisies manuellement (livraisons).
  Les ajustements manuels servent pour inventaire, casse, correction.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from data.database import Connection, get_conn


# Types de mouvements
TYPE_ENTREE = "entree"                  # matériaux qui arrivent (livraisons)
TYPE_SORTIE = "sortie"                  # consommations auto par productions
TYPE_AJUSTEMENT_POS = "ajustement_pos"  # correction manuelle positive
TYPE_AJUSTEMENT_NEG = "ajustement_neg"  # correction manuelle négative
TYPE_STOCK_INITIAL = "stock_initial"    # une seule fois au démarrage


# ==================================================================
# Assurer que la table existe
# ==================================================================
def _assurer_tables(conn: Connection) -> None:
    """Placeholder — les tables stock_config et mouvements_stock sont créées
    dans data.database._creer_schema (init_db).
    Cette fonction reste pour compat mais ne fait plus rien.
    """
    return


# ==================================================================
# Configuration
# ==================================================================
def config_materiau(
    materiau_id: str,
    unite: str,
    seuil_alerte: float | None = None,
) -> None:
    """Enregistre / met à jour la config d'un matériau (unité + seuil)."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO stock_config
                 (materiau_id, unite, seuil_alerte, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (materiau_id) DO UPDATE SET
                 unite = EXCLUDED.unite,
                 seuil_alerte = EXCLUDED.seuil_alerte,
                 updated_at = EXCLUDED.updated_at""",
            (materiau_id, unite, seuil_alerte, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def lister_configs() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        _assurer_tables(conn)
        rows = conn.execute("SELECT * FROM stock_config").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def config_par_id(materiau_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        _assurer_tables(conn)
        r = conn.execute(
            "SELECT * FROM stock_config WHERE materiau_id = ?", (materiau_id,)
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


# ==================================================================
# Enregistrer une entrée (livraison)
# ==================================================================
def enregistrer_entree(
    materiau_id: str,
    quantite: float,
    unite: str,
    date_str: str,
    observation: str | None = None,
    utilisateur: str | None = None,
) -> int:
    """Enregistre une entrée de matériau (livraison arrivée sur chantier)."""
    if quantite <= 0:
        raise ValueError("La quantité doit être > 0")
    conn = get_conn()
    try:
        _assurer_tables(conn)
        cur = conn.execute(
            """INSERT INTO mouvements_stock
               (materiau_id, date_mouvement, type_mouvement, quantite, unite,
                observation, utilisateur, cree_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (materiau_id, date_str, TYPE_ENTREE, quantite, unite,
             observation, utilisateur, datetime.now().isoformat()),
        )
        mvt_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    from services import journal
    journal.log(
        action="entree_stock",
        table_nom="mouvements_stock",
        enregistrement_id=str(mvt_id),
        nouvelle_valeur={
            "materiau_id": materiau_id,
            "quantite": quantite,
            "unite": unite,
        },
        motif=observation,
        utilisateur=utilisateur,
    )
    return mvt_id


# ==================================================================
# Ajustement manuel
# ==================================================================
def enregistrer_ajustement(
    materiau_id: str,
    quantite: float,  # positive = ajout, négative = retrait
    unite: str,
    date_str: str,
    motif: str,
    utilisateur: str | None = None,
) -> int:
    """Ajustement manuel du stock (inventaire, casse, etc.). Motif obligatoire."""
    if not motif or not motif.strip():
        raise ValueError("Le motif est obligatoire pour un ajustement")
    if quantite == 0:
        raise ValueError("La quantité doit être non nulle")

    type_ = TYPE_AJUSTEMENT_POS if quantite > 0 else TYPE_AJUSTEMENT_NEG
    conn = get_conn()
    try:
        _assurer_tables(conn)
        cur = conn.execute(
            """INSERT INTO mouvements_stock
               (materiau_id, date_mouvement, type_mouvement, quantite, unite,
                observation, utilisateur, cree_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (materiau_id, date_str, type_, abs(quantite), unite,
             motif, utilisateur, datetime.now().isoformat()),
        )
        mvt_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    from services import journal
    journal.log(
        action="ajustement_stock",
        table_nom="mouvements_stock",
        enregistrement_id=str(mvt_id),
        nouvelle_valeur={
            "materiau_id": materiau_id,
            "type": type_,
            "quantite": abs(quantite),
            "unite": unite,
        },
        motif=motif,
        utilisateur=utilisateur,
    )
    return mvt_id


# ==================================================================
# Stock initial (bootstrap)
# ==================================================================
def enregistrer_stock_initial(
    materiau_id: str,
    quantite: float,
    unite: str,
    date_str: str,
    utilisateur: str | None = None,
) -> int:
    """Enregistre le stock initial d'un matériau (à faire 1 seule fois par matériau)."""
    conn = get_conn()
    try:
        _assurer_tables(conn)
        # Vérifier qu'aucun stock initial n'existe déjà
        deja = conn.execute(
            """SELECT COUNT(*) as c FROM mouvements_stock
               WHERE materiau_id = ? AND type_mouvement = ?""",
            (materiau_id, TYPE_STOCK_INITIAL),
        ).fetchone()
        if deja["c"] > 0:
            raise ValueError(
                "Le stock initial existe déjà pour ce matériau. "
                "Utiliser un ajustement pour corriger."
            )
        cur = conn.execute(
            """INSERT INTO mouvements_stock
               (materiau_id, date_mouvement, type_mouvement, quantite, unite,
                observation, utilisateur, cree_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (materiau_id, date_str, TYPE_STOCK_INITIAL, quantite, unite,
             "Stock initial à la mise en service",
             utilisateur, datetime.now().isoformat()),
        )
        row = cur.fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


# ==================================================================
# Auto-déduction à la fin d'une production
# ==================================================================
def deduire_production(production_id: str) -> int:
    """Insère les mouvements 'sortie' pour une production terminée.

    Idempotent : si des sorties existent déjà pour cette production, ne fait rien.
    Utilise quantite_reelle si disponible, sinon quantite_theorique.
    Retourne le nombre de mouvements insérés.
    """
    now = datetime.now().isoformat()
    conn = get_conn()
    try:
        _assurer_tables(conn)
        # Vérifier si déjà déduit
        deja = conn.execute(
            """SELECT COUNT(*) as c FROM mouvements_stock
               WHERE production_id = ? AND type_mouvement = ?""",
            (production_id, TYPE_SORTIE),
        ).fetchone()
        if deja["c"] > 0:
            return 0

        # Récupérer les lignes de la production avec catégorie + unité stock configurée
        lignes = conn.execute(
            """SELECT pm.*, m.unite_stock, sc.unite as unite_conf
               FROM production_materiaux pm
               JOIN materiaux m ON m.id = pm.materiau_id
               LEFT JOIN stock_config sc ON sc.materiau_id = pm.materiau_id
               WHERE pm.production_id = ?""",
            (production_id,),
        ).fetchall()

        prod = conn.execute(
            "SELECT date FROM productions WHERE id = ?", (production_id,)
        ).fetchone()
        date_str = prod["date"] if prod else now[:10]

        count = 0
        for l in lignes:
            # Choix qté à déduire
            qte = None
            note = ""
            if l["quantite_reelle"] is not None:
                qte = float(l["quantite_reelle"])
            elif l["quantite_theorique"] is not None:
                qte = float(l["quantite_theorique"])
                note = " (théorique — réel non saisi)"

            if qte is None or qte <= 0:
                continue

            unite = l["unite_conf"] or l["unite_stock"]
            obs = f"Production {production_id[:12]}{note}"

            conn.execute(
                """INSERT INTO mouvements_stock
                   (materiau_id, date_mouvement, type_mouvement, quantite, unite,
                    production_id, observation, cree_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (l["materiau_id"], date_str, TYPE_SORTIE, qte, unite,
                 production_id, obs, now),
            )
            count += 1

        conn.commit()
        return count
    finally:
        conn.close()


def annuler_deduction(production_id: str) -> int:
    """Supprime les mouvements 'sortie' d'une production annulée."""
    conn = get_conn()
    try:
        _assurer_tables(conn)
        cur = conn.execute(
            """DELETE FROM mouvements_stock
               WHERE production_id = ? AND type_mouvement = ?""",
            (production_id, TYPE_SORTIE),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ==================================================================
# Situation actuelle
# ==================================================================
def situation(materiau_id: str) -> dict[str, Any]:
    """Calcule dynamiquement la situation d'un matériau.

    Retourne :
      {
        'materiau_id', 'unite', 'seuil_alerte',
        'stock_initial', 'entrees', 'ajustements_pos',
        'sorties', 'ajustements_neg',
        'stock_actuel', 'sous_seuil'
      }
    """
    conn = get_conn()
    try:
        _assurer_tables(conn)
        cfg = conn.execute(
            "SELECT * FROM stock_config WHERE materiau_id = ?", (materiau_id,)
        ).fetchone()
        unite = cfg["unite"] if cfg else "?"
        seuil = cfg["seuil_alerte"] if cfg else None

        totaux = {t: 0.0 for t in [
            TYPE_STOCK_INITIAL, TYPE_ENTREE, TYPE_SORTIE,
            TYPE_AJUSTEMENT_POS, TYPE_AJUSTEMENT_NEG,
        ]}
        rows = conn.execute(
            """SELECT type_mouvement, SUM(quantite) as total
               FROM mouvements_stock WHERE materiau_id = ?
               GROUP BY type_mouvement""",
            (materiau_id,),
        ).fetchall()
        for r in rows:
            totaux[r["type_mouvement"]] = float(r["total"] or 0)

        actuel = (
            totaux[TYPE_STOCK_INITIAL]
            + totaux[TYPE_ENTREE]
            + totaux[TYPE_AJUSTEMENT_POS]
            - totaux[TYPE_SORTIE]
            - totaux[TYPE_AJUSTEMENT_NEG]
        )
        return {
            "materiau_id": materiau_id,
            "unite": unite,
            "seuil_alerte": seuil,
            "stock_initial": round(totaux[TYPE_STOCK_INITIAL], 2),
            "entrees": round(totaux[TYPE_ENTREE], 2),
            "ajustements_pos": round(totaux[TYPE_AJUSTEMENT_POS], 2),
            "sorties": round(totaux[TYPE_SORTIE], 2),
            "ajustements_neg": round(totaux[TYPE_AJUSTEMENT_NEG], 2),
            "stock_actuel": round(actuel, 2),
            "sous_seuil": (seuil is not None) and actuel < seuil,
        }
    finally:
        conn.close()


def situations_toutes() -> list[dict[str, Any]]:
    """Situation actuelle pour tous les matériaux configurés."""
    configs = lister_configs()
    return [situation(c["materiau_id"]) for c in configs]


def lister_mouvements(
    materiau_id: str | None = None,
    depuis: str | None = None,
    jusqua: str | None = None,
    types: list[str] | None = None,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Liste les mouvements avec filtres."""
    conn = get_conn()
    try:
        _assurer_tables(conn)
        where = []
        args: list[Any] = []
        if materiau_id:
            where.append("materiau_id = ?")
            args.append(materiau_id)
        if depuis:
            where.append("date_mouvement >= ?")
            args.append(depuis)
        if jusqua:
            where.append("date_mouvement <= ?")
            args.append(jusqua)
        if types:
            placeholders = ",".join("?" * len(types))
            where.append(f"type_mouvement IN ({placeholders})")
            args.extend(types)
        sql = "SELECT * FROM mouvements_stock"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date_mouvement DESC, id DESC LIMIT ?"
        args.append(limite)
        rows = conn.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
