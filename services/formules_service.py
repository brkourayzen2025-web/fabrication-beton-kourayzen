"""Service de gestion des formules : création, édition, versionnage, workflow.

RÈGLES DE VERSIONNAGE :
  - Une formule VALIDÉE ne peut plus être modifiée directement.
  - Une formule BROUILLON ou À_VALIDER peut être éditée directement à condition
    qu'AUCUNE production ne s'appuie dessus.
  - Sinon, l'édition crée une nouvelle version en statut "brouillon" avec
    `formule_parent_id` pointant vers la version précédente et version = N+1.
  - L'ID de la nouvelle version reprend la racine + numéro incrémenté
    (ex. F-BCV-D27-V1 -> F-BCV-D27-V2).

WORKFLOW STATUTS :
  brouillon  ->  a_valider  ->  validee  ->  desactivee
  (chaque transition est loggée dans le journal)

Toutes les fonctions loggent leurs actions via services.journal.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from data.database import get_conn
from models.constants import (
    STATUT_A_VALIDER,
    STATUT_BROUILLON,
    STATUT_DESACTIVEE,
    STATUT_VALIDEE,
)
from services import journal
from services.repositories import formule_par_id


# Transitions autorisées
TRANSITIONS = {
    STATUT_BROUILLON: {STATUT_A_VALIDER, STATUT_DESACTIVEE},
    STATUT_A_VALIDER: {STATUT_BROUILLON, STATUT_VALIDEE, STATUT_DESACTIVEE},
    STATUT_VALIDEE: {STATUT_DESACTIVEE},
    STATUT_DESACTIVEE: {STATUT_BROUILLON},  # réactivation possible en brouillon
}


# ==================================================================
# Helpers
# ==================================================================
def _formule_a_des_productions(formule_id: str) -> bool:
    """Vrai si au moins une production utilise cette version de formule."""
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT COUNT(*) as c FROM productions WHERE formule_id = ?",
            (formule_id,),
        ).fetchone()
        return r["c"] > 0
    finally:
        conn.close()


def _prochain_id_version(base_id: str, nouvelle_version: int) -> str:
    """Génère l'ID de la nouvelle version en incrémentant le suffixe -V<n>.

    Si l'ID ne matche pas le pattern, ajoute simplement -V<n> avec un hash court
    pour garantir l'unicité.
    """
    m = re.match(r"^(.*?)-V\d+$", base_id)
    racine = m.group(1) if m else base_id
    candidat = f"{racine}-V{nouvelle_version}"
    # Vérifier unicité
    if formule_par_id(candidat) is None:
        return candidat
    # Fallback : suffixe hash
    return f"{racine}-V{nouvelle_version}-{uuid.uuid4().hex[:4].upper()}"


def _remonter_a_racine(formule_id: str) -> str:
    """Remonte la chaîne de parents jusqu'à la formule racine (parent_id = NULL)."""
    conn = get_conn()
    try:
        current = formule_id
        visites: set[str] = set()
        while True:
            if current in visites:
                # Boucle : sécurité
                return current
            visites.add(current)
            r = conn.execute(
                "SELECT formule_parent_id FROM formules WHERE id = ?", (current,)
            ).fetchone()
            if not r or not r["formule_parent_id"]:
                return current
            current = r["formule_parent_id"]
    finally:
        conn.close()


def toutes_versions(formule_id: str) -> list[dict[str, Any]]:
    """Retourne toutes les versions d'une formule (racine + descendants).

    Tri par version croissante.
    """
    racine_id = _remonter_a_racine(formule_id)
    conn = get_conn()
    try:
        # Descente : BFS depuis la racine
        a_traiter = [racine_id]
        trouvees = []
        while a_traiter:
            ids_batch = a_traiter
            a_traiter = []
            placeholders = ",".join("?" * len(ids_batch))
            rows = conn.execute(
                f"""SELECT * FROM formules
                    WHERE id IN ({placeholders})
                       OR formule_parent_id IN ({placeholders})""",
                (*ids_batch, *ids_batch),
            ).fetchall()
            for r in rows:
                d = dict(r)
                if not any(t["id"] == d["id"] for t in trouvees):
                    trouvees.append(d)
                    if d["id"] not in ids_batch:
                        a_traiter.append(d["id"])
        # Tri version croissante
        trouvees.sort(key=lambda f: (f["version"], f["created_at"]))
        return trouvees
    finally:
        conn.close()


# ==================================================================
# Création d'une nouvelle formule (from scratch)
# ==================================================================
def creer_formule(
    nom: str,
    type_beton_id: str,
    composition: list[dict[str, Any]],
    observations: str | None = None,
    utilisateur: str | None = None,
    id_manuel: str | None = None,
) -> str:
    """Crée une nouvelle formule en statut BROUILLON (version 1, sans parent).

    `composition` = liste de dicts {materiau_id, quantite, unite, ordre_ajout}
    Retourne l'ID créé.
    """
    if not nom.strip():
        raise ValueError("Le nom de la formule est obligatoire.")
    if not composition:
        raise ValueError("Une formule doit avoir au moins un composant.")

    fid = id_manuel or f"F-{uuid.uuid4().hex[:12].upper()}-V1"

    conn = get_conn()
    try:
        # Vérifier unicité
        if conn.execute("SELECT 1 FROM formules WHERE id = ?", (fid,)).fetchone():
            raise ValueError(f"ID formule déjà utilisé : {fid}")

        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO formules
               (id, type_beton_id, nom, version, statut, volume_reference_m3,
                observations, created_at)
               VALUES (?, ?, ?, 1, ?, 1.0, ?, ?)""",
            (fid, type_beton_id, nom.strip(), STATUT_BROUILLON, observations, now),
        )
        for c in composition:
            conn.execute(
                """INSERT INTO formule_composition
                   (formule_id, materiau_id, quantite, unite, ordre_ajout)
                   VALUES (?, ?, ?, ?, ?)""",
                (fid, c["materiau_id"], c["quantite"], c["unite"], c.get("ordre_ajout")),
            )
        conn.commit()
    finally:
        conn.close()

    journal.log(
        action="creation",
        table_nom="formules",
        enregistrement_id=fid,
        nouvelle_valeur={"nom": nom, "type_beton_id": type_beton_id, "composition": composition},
        utilisateur=utilisateur,
    )
    return fid


# ==================================================================
# Édition d'une formule existante
# ==================================================================
def editer_formule(
    formule_id: str,
    nouvelle_composition: list[dict[str, Any]],
    nouveau_nom: str | None = None,
    nouvelles_observations: str | None = None,
    utilisateur: str | None = None,
    forcer_nouvelle_version: bool = False,
) -> tuple[str, bool]:
    """Édite une formule.

    Retourne (id_final, nouvelle_version_creee).

    Cas 1 : formule VALIDÉE, DÉSACTIVÉE, ou avec des productions
      -> Crée automatiquement une nouvelle version (brouillon) et laisse
         l'ancienne intacte. Retour: (id_v2, True).

    Cas 2 : formule BROUILLON ou À_VALIDER sans production
      -> Édition en place (sauf si forcer_nouvelle_version=True).
         Retour: (id_original, False).
    """
    formule = formule_par_id(formule_id)
    if not formule:
        raise ValueError(f"Formule introuvable : {formule_id}")

    a_prod = _formule_a_des_productions(formule_id)
    editable_en_place = (
        not forcer_nouvelle_version
        and formule["statut"] in (STATUT_BROUILLON, STATUT_A_VALIDER)
        and not a_prod
    )

    if editable_en_place:
        return _editer_en_place(
            formule, nouvelle_composition, nouveau_nom,
            nouvelles_observations, utilisateur,
        )
    else:
        return _creer_nouvelle_version(
            formule, nouvelle_composition, nouveau_nom,
            nouvelles_observations, utilisateur,
        )


def _editer_en_place(
    formule: dict,
    nouvelle_composition: list[dict],
    nouveau_nom: str | None,
    nouvelles_obs: str | None,
    utilisateur: str | None,
) -> tuple[str, bool]:
    fid = formule["id"]
    ancienne = {
        "nom": formule["nom"],
        "observations": formule.get("observations"),
        "composition": formule["composition"],
    }

    conn = get_conn()
    try:
        # Update ligne formule
        conn.execute(
            """UPDATE formules SET nom = ?, observations = ? WHERE id = ?""",
            (
                (nouveau_nom or formule["nom"]).strip(),
                nouvelles_obs if nouvelles_obs is not None else formule.get("observations"),
                fid,
            ),
        )
        # Rewrite composition
        conn.execute("DELETE FROM formule_composition WHERE formule_id = ?", (fid,))
        for c in nouvelle_composition:
            conn.execute(
                """INSERT INTO formule_composition
                   (formule_id, materiau_id, quantite, unite, ordre_ajout)
                   VALUES (?, ?, ?, ?, ?)""",
                (fid, c["materiau_id"], c["quantite"], c["unite"], c.get("ordre_ajout")),
            )
        conn.commit()
    finally:
        conn.close()

    journal.log(
        action="edition_en_place",
        table_nom="formules",
        enregistrement_id=fid,
        ancienne_valeur=ancienne,
        nouvelle_valeur={
            "nom": nouveau_nom or formule["nom"],
            "observations": nouvelles_obs,
            "composition": nouvelle_composition,
        },
        utilisateur=utilisateur,
    )
    return fid, False


def _creer_nouvelle_version(
    formule: dict,
    nouvelle_composition: list[dict],
    nouveau_nom: str | None,
    nouvelles_obs: str | None,
    utilisateur: str | None,
) -> tuple[str, bool]:
    old_id = formule["id"]

    # Chercher la version max dans l'arbre
    versions = toutes_versions(old_id)
    max_ver = max((v["version"] for v in versions), default=formule["version"])
    new_ver = max_ver + 1
    new_id = _prochain_id_version(old_id, new_ver)

    conn = get_conn()
    try:
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO formules
               (id, type_beton_id, nom, version, statut, volume_reference_m3,
                observations, formule_parent_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id,
                formule["type_beton_id"],
                (nouveau_nom or formule["nom"]).strip(),
                new_ver,
                STATUT_BROUILLON,
                formule.get("volume_reference_m3") or 1.0,
                nouvelles_obs if nouvelles_obs is not None else formule.get("observations"),
                old_id,
                now,
            ),
        )
        for c in nouvelle_composition:
            conn.execute(
                """INSERT INTO formule_composition
                   (formule_id, materiau_id, quantite, unite, ordre_ajout)
                   VALUES (?, ?, ?, ?, ?)""",
                (new_id, c["materiau_id"], c["quantite"], c["unite"], c.get("ordre_ajout")),
            )
        conn.commit()
    finally:
        conn.close()

    journal.log(
        action="nouvelle_version",
        table_nom="formules",
        enregistrement_id=new_id,
        ancienne_valeur={
            "id_source": old_id,
            "version_source": formule["version"],
        },
        nouvelle_valeur={
            "nom": nouveau_nom or formule["nom"],
            "observations": nouvelles_obs,
            "composition": nouvelle_composition,
            "version": new_ver,
        },
        motif=f"Édition de {old_id} → création de v{new_ver}",
        utilisateur=utilisateur,
    )
    return new_id, True


# ==================================================================
# Changement de statut
# ==================================================================
def changer_statut(
    formule_id: str,
    nouveau_statut: str,
    utilisateur: str | None = None,
    motif: str | None = None,
) -> None:
    """Change le statut d'une formule selon les transitions autorisées."""
    formule = formule_par_id(formule_id)
    if not formule:
        raise ValueError(f"Formule introuvable : {formule_id}")

    ancien = formule["statut"]
    if nouveau_statut == ancien:
        return  # no-op

    if nouveau_statut not in TRANSITIONS.get(ancien, set()):
        raise ValueError(
            f"Transition non autorisée : {ancien} → {nouveau_statut}. "
            f"Transitions possibles depuis {ancien} : "
            f"{', '.join(TRANSITIONS.get(ancien, [])) or 'aucune'}"
        )

    # Mise à jour
    conn = get_conn()
    try:
        now = datetime.now().isoformat()
        champs = {"statut": nouveau_statut}
        if nouveau_statut == STATUT_VALIDEE:
            champs["date_validation"] = now[:10]
            champs["valide_par"] = utilisateur or "?"
        sets = ", ".join(f"{k} = ?" for k in champs)
        conn.execute(
            f"UPDATE formules SET {sets} WHERE id = ?",
            (*champs.values(), formule_id),
        )
        conn.commit()
    finally:
        conn.close()

    journal.log(
        action=f"statut_{nouveau_statut}",
        table_nom="formules",
        enregistrement_id=formule_id,
        ancienne_valeur={"statut": ancien},
        nouvelle_valeur={"statut": nouveau_statut},
        motif=motif,
        utilisateur=utilisateur,
    )


# ==================================================================
# Suppression (pour brouillons uniquement)
# ==================================================================
def supprimer_brouillon(formule_id: str, utilisateur: str | None = None) -> None:
    """Supprime physiquement une formule si elle est en brouillon ET sans production.

    Sinon, refuse. Utiliser changer_statut(..., 'desactivee') pour les autres cas.
    """
    formule = formule_par_id(formule_id)
    if not formule:
        return
    if formule["statut"] != STATUT_BROUILLON:
        raise ValueError(
            "Seules les formules en statut brouillon peuvent être supprimées. "
            "Utiliser désactivation à la place."
        )
    if _formule_a_des_productions(formule_id):
        raise ValueError(
            "Cette formule a des productions associées et ne peut pas être supprimée. "
            "Utiliser désactivation à la place."
        )

    conn = get_conn()
    try:
        # composition partira via ON DELETE CASCADE
        conn.execute("DELETE FROM formules WHERE id = ?", (formule_id,))
        conn.commit()
    finally:
        conn.close()

    journal.log(
        action="suppression",
        table_nom="formules",
        enregistrement_id=formule_id,
        ancienne_valeur={
            "nom": formule["nom"],
            "composition": formule["composition"],
        },
        motif="Suppression brouillon",
        utilisateur=utilisateur,
    )
