"""Base de données : PostgreSQL (Supabase) OU SQLite (local).

Détection auto :
  - Si [postgres] url dans les secrets Streamlit → PostgreSQL (Supabase, cloud)
  - Si DATABASE_URL en variable d'env → PostgreSQL
  - Sinon → SQLite local (fichier fabrication_beton.db à côté d'app.py)

Cela permet :
  - Test local sans Supabase (marche direct après INSTALLER.bat)
  - Déploiement cloud avec Supabase (via secrets Streamlit)
  - Utilisation locale connectée à Supabase (via .streamlit/secrets.toml)
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH_SQLITE = PROJECT_DIR / "fabrication_beton.db"


# ==================================================================
# Détection du backend
# ==================================================================
def _use_postgres() -> bool:
    """True si une URL Postgres est configurée (secrets ou env)."""
    try:
        import streamlit as st  # type: ignore
        if hasattr(st, "secrets") and "postgres" in st.secrets:
            return True
    except Exception:
        pass
    return bool(os.getenv("DATABASE_URL"))


def _get_pg_url() -> str:
    try:
        import streamlit as st  # type: ignore
        if hasattr(st, "secrets") and "postgres" in st.secrets:
            return st.secrets["postgres"]["url"]
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "")


# ==================================================================
# Wrapper Postgres (compat sqlite3)
# ==================================================================
class _Row(dict):
    """dict avec accès index numérique aussi (compat sqlite3.Row)."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, pg_cursor):
        self._c = pg_cursor
    def fetchone(self):
        r = self._c.fetchone()
        return _Row(r) if r else None
    def fetchall(self):
        return [_Row(r) for r in self._c.fetchall()]
    @property
    def rowcount(self):
        return self._c.rowcount
    def __iter__(self):
        for r in self._c:
            yield _Row(r)
    def close(self):
        try:
            self._c.close()
        except Exception:
            pass


class _PgConnection:
    """Wrapper sqlite3-like autour d'une connexion psycopg2."""
    def __init__(self):
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore
        self._pg = psycopg2.connect(_get_pg_url())
        self._factory = psycopg2.extras.RealDictCursor

    def _translate(self, sql: str) -> str:
        # Placeholders : ? → %s (psycopg2 utilise %s)
        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        cur = self._pg.cursor(cursor_factory=self._factory)
        cur.execute(self._translate(sql), params)
        return _Cursor(cur)

    def executemany(self, sql, seq_params):
        cur = self._pg.cursor()
        try:
            cur.executemany(self._translate(sql), list(seq_params))
        finally:
            cur.close()

    def executescript(self, script):
        cur = self._pg.cursor()
        try:
            cur.execute(self._translate(script))
        finally:
            cur.close()

    def commit(self):
        self._pg.commit()

    def rollback(self):
        self._pg.rollback()

    def close(self):
        try:
            self._pg.close()
        except Exception:
            pass


# Alias pour type hint
Connection = _PgConnection  # (peut aussi être sqlite3.Connection)


# ==================================================================
# Point d'entrée : get_conn
# ==================================================================
def get_conn():
    """Retourne une connexion selon le backend actif."""
    if _use_postgres():
        return _PgConnection()
    # SQLite local
    conn = sqlite3.connect(str(DB_PATH_SQLITE), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ==================================================================
# Initialisation BD
# ==================================================================
def init_db(force_reseed: bool = False) -> None:
    conn = get_conn()
    try:
        if _use_postgres():
            r = conn.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='types_beton'"
            ).fetchone()
        else:
            r = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='types_beton'"
            ).fetchone()
        deja_cree = r is not None

        if not deja_cree:
            _creer_schema(conn)
            from data.seed import inserer_seed
            inserer_seed(conn)
            conn.commit()
        elif force_reseed:
            from data.seed import inserer_seed
            _vider_seed(conn)
            inserer_seed(conn)
            conn.commit()
    finally:
        conn.close()


def _creer_schema(conn) -> None:
    """Schéma commun. Différences Postgres/SQLite gérées par variables."""
    if _use_postgres():
        autoinc = "BIGSERIAL PRIMARY KEY"
        float_type = "DOUBLE PRECISION"
    else:
        autoinc = "INTEGER PRIMARY KEY AUTOINCREMENT"
        float_type = "REAL"

    schema = f"""
    CREATE TABLE IF NOT EXISTS types_beton (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        description TEXT,
        actif INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS materiaux (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL UNIQUE,
        categorie TEXT NOT NULL,
        unite_stock TEXT NOT NULL,
        densite_apparente {float_type},
        poids_sac_defaut {float_type},
        actif INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS formules (
        id TEXT PRIMARY KEY,
        type_beton_id TEXT NOT NULL REFERENCES types_beton(id),
        nom TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        statut TEXT NOT NULL DEFAULT 'brouillon',
        volume_reference_m3 {float_type} NOT NULL DEFAULT 1.0,
        date_validation TEXT,
        valide_par TEXT,
        observations TEXT,
        formule_parent_id TEXT REFERENCES formules(id),
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_formules_type ON formules(type_beton_id);
    CREATE INDEX IF NOT EXISTS idx_formules_statut ON formules(statut);

    CREATE TABLE IF NOT EXISTS formule_composition (
        id {autoinc},
        formule_id TEXT NOT NULL REFERENCES formules(id) ON DELETE CASCADE,
        materiau_id TEXT NOT NULL REFERENCES materiaux(id),
        quantite {float_type} NOT NULL,
        unite TEXT NOT NULL,
        ordre_ajout INTEGER
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_compo_unique
        ON formule_composition(formule_id, materiau_id);

    CREATE TABLE IF NOT EXISTS engins (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        type_engin TEXT NOT NULL,
        marque TEXT,
        modele TEXT,
        immatriculation TEXT,
        actif INTEGER NOT NULL DEFAULT 1,
        observations TEXT
    );

    CREATE TABLE IF NOT EXISTS godets (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        engin_id TEXT NOT NULL REFERENCES engins(id),
        materiau_id TEXT NOT NULL REFERENCES materiaux(id),
        capacite_nominale_l {float_type},
        capacite_mesuree_l {float_type} NOT NULL,
        coef_remplissage {float_type} NOT NULL DEFAULT 1.0,
        type_remplissage TEXT DEFAULT 'ras',
        date_mesure TEXT,
        observations TEXT,
        actif INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS idx_godets_materiau ON godets(materiau_id);

    CREATE TABLE IF NOT EXISTS productions (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        heure TEXT NOT NULL,
        formule_id TEXT NOT NULL REFERENCES formules(id),
        formule_snapshot_json TEXT NOT NULL,
        volume_prevu_m3 {float_type} NOT NULL,
        volume_reel_m3 {float_type},
        engin_id TEXT REFERENCES engins(id),
        zone_melange TEXT,
        zone_mise_en_oeuvre TEXT,
        operateur TEXT,
        poids_sac_ciment_kg {float_type} NOT NULL DEFAULT 50.0,
        observation TEXT,
        statut TEXT NOT NULL DEFAULT 'en_cours',
        materiaux_confirmes INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_prod_date ON productions(date);

    CREATE TABLE IF NOT EXISTS production_materiaux (
        id {autoinc},
        production_id TEXT NOT NULL REFERENCES productions(id) ON DELETE CASCADE,
        materiau_id TEXT NOT NULL REFERENCES materiaux(id),
        godet_id TEXT REFERENCES godets(id),
        quantite_theorique {float_type} NOT NULL,
        unite_theorique TEXT NOT NULL,
        nb_godets_theorique {float_type},
        godets_complets_theorique INTEGER,
        pct_dernier_godet_theorique {float_type},
        qte_dernier_godet_l_theorique {float_type},
        nb_sacs_theorique {float_type},
        quantite_reelle {float_type},
        nb_godets_reel {float_type},
        nb_sacs_reel {float_type},
        confirme INTEGER NOT NULL DEFAULT 0,
        confirme_at TEXT,
        ecart_absolu {float_type},
        ecart_pct {float_type}
    );
    CREATE INDEX IF NOT EXISTS idx_pm_prod ON production_materiaux(production_id);

    CREATE TABLE IF NOT EXISTS parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS journal_modifications (
        id {autoinc},
        timestamp TEXT NOT NULL,
        utilisateur TEXT,
        table_nom TEXT NOT NULL,
        enregistrement_id TEXT NOT NULL,
        action TEXT NOT NULL,
        ancienne_valeur TEXT,
        nouvelle_valeur TEXT,
        motif TEXT
    );

    CREATE TABLE IF NOT EXISTS stock_config (
        materiau_id TEXT PRIMARY KEY REFERENCES materiaux(id),
        unite TEXT NOT NULL,
        seuil_alerte {float_type},
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS mouvements_stock (
        id {autoinc},
        materiau_id TEXT NOT NULL REFERENCES materiaux(id),
        date_mouvement TEXT NOT NULL,
        type_mouvement TEXT NOT NULL,
        quantite {float_type} NOT NULL,
        unite TEXT NOT NULL,
        production_id TEXT,
        observation TEXT,
        utilisateur TEXT,
        cree_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_mvt_mat ON mouvements_stock(materiau_id);
    CREATE INDEX IF NOT EXISTS idx_mvt_date ON mouvements_stock(date_mouvement);
    CREATE INDEX IF NOT EXISTS idx_mvt_prod ON mouvements_stock(production_id);
    """
    conn.executescript(schema)


def _vider_seed(conn) -> None:
    """Efface les tables de seed (dev/reset). Ne touche PAS aux productions."""
    for t in [
        "formule_composition",
        "formules",
        "types_beton",
        "godets",
        "engins",
        "materiaux",
        "parametres",
    ]:
        conn.execute(f"DELETE FROM {t}")
