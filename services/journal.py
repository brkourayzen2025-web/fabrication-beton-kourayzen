"""Journal des modifications : logging simple des actions importantes.

Toutes les fonctions écrivent dans `journal_modifications`.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from data.database import get_conn


def log(
    action: str,
    table_nom: str,
    enregistrement_id: str,
    ancienne_valeur: dict | list | str | None = None,
    nouvelle_valeur: dict | list | str | None = None,
    motif: str | None = None,
    utilisateur: str | None = None,
) -> None:
    """Enregistre une entrée dans le journal.

    Les valeurs old/new sont sérialisées en JSON si ce sont des objets.
    """
    def _serialize(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False, default=str)

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO journal_modifications
               (timestamp, utilisateur, table_nom, enregistrement_id, action,
                ancienne_valeur, nouvelle_valeur, motif)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                utilisateur or "anonyme",
                table_nom,
                enregistrement_id,
                action,
                _serialize(ancienne_valeur),
                _serialize(nouvelle_valeur),
                motif,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def lister(
    table_nom: str | None = None,
    enregistrement_id: str | None = None,
    action: str | None = None,
    depuis: str | None = None,
    jusqua: str | None = None,
    utilisateur: str | None = None,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Liste les entrées du journal avec filtres optionnels."""
    conn = get_conn()
    try:
        where = []
        args: list[Any] = []
        if table_nom:
            where.append("table_nom = ?")
            args.append(table_nom)
        if enregistrement_id:
            where.append("enregistrement_id = ?")
            args.append(enregistrement_id)
        if action:
            where.append("action = ?")
            args.append(action)
        if depuis:
            where.append("timestamp >= ?")
            args.append(depuis)
        if jusqua:
            where.append("timestamp <= ?")
            args.append(jusqua + "T23:59:59")
        if utilisateur:
            where.append("utilisateur = ?")
            args.append(utilisateur)
        sql = "SELECT * FROM journal_modifications"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limite)
        rows = conn.execute(sql, tuple(args)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def lister_utilisateurs() -> list[str]:
    """Liste les utilisateurs distincts ayant fait des modifs."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT utilisateur FROM journal_modifications ORDER BY utilisateur"
        ).fetchall()
        return [r["utilisateur"] for r in rows if r["utilisateur"]]
    finally:
        conn.close()
