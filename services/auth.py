"""Authentification simple à 2 rôles : admin + pointeur.

Les identifiants sont dans `st.secrets["users"]` (Streamlit Cloud) ou
dans `.streamlit/secrets.toml` en local.

Format :
    [users.radouane]
    password = "monMotDePasse"
    role = "admin"

    [users.pointeur]
    password = "autreMotDePasse"
    role = "pointeur"

Rôles disponibles : "admin", "pointeur"
"""
from __future__ import annotations

import streamlit as st


ROLE_ADMIN = "admin"
ROLE_POINTEUR = "pointeur"


def _get_users() -> dict[str, dict]:
    """Charge les utilisateurs depuis les secrets."""
    try:
        raw = dict(st.secrets["users"])
        # Chaque entrée doit avoir password + role
        return {
            username: {
                "password": info.get("password", ""),
                "role": info.get("role", ROLE_POINTEUR),
            }
            for username, info in raw.items()
        }
    except Exception:
        # Fallback pour dev / premier lancement — À CHANGER en production !
        return {
            "admin": {"password": "admin", "role": ROLE_ADMIN},
            "pointeur": {"password": "pointeur", "role": ROLE_POINTEUR},
        }


def _verifier(username: str, password: str) -> dict | None:
    """Vérifie login/mdp. Retourne le user dict ou None."""
    users = _get_users()
    u = users.get(username)
    if not u:
        return None
    if password != u["password"]:
        return None
    return {"username": username, "role": u["role"]}


def utilisateur_actuel() -> dict | None:
    """Retourne le user actuellement connecté (None sinon)."""
    return st.session_state.get("user_auth")


def est_connecte() -> bool:
    return utilisateur_actuel() is not None


def est_admin() -> bool:
    u = utilisateur_actuel()
    return bool(u and u.get("role") == ROLE_ADMIN)


def est_pointeur() -> bool:
    u = utilisateur_actuel()
    return bool(u and u.get("role") == ROLE_POINTEUR)


def username_pour_journal() -> str:
    """Nom à utiliser dans le journal des modifications."""
    u = utilisateur_actuel()
    return u["username"] if u else "anonyme"


def deconnecter() -> None:
    st.session_state.pop("user_auth", None)


def afficher_page_login() -> None:
    """Affiche le formulaire de login (ou bloque la page)."""
    st.title("🔐 Fabrication Béton — Connexion")

    st.info(
        "Connecte-toi pour accéder à l'application.\n\n"
        "**Rôles :**\n"
        "- **Administrateur** : accès total (édition formules, matériaux, engins, journal)\n"
        "- **Pointeur** : préparation mélanges, saisie productions, gestion stock"
    )

    with st.form("form_login"):
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter", type="primary", use_container_width=True)

        if submit:
            u = _verifier(username.strip(), password)
            if u:
                st.session_state.user_auth = u
                st.rerun()
            else:
                st.error("❌ Identifiants incorrects.")

    # Alerte si en mode dev (identifiants par défaut)
    users = _get_users()
    if users.get("admin", {}).get("password") == "admin":
        st.warning(
            "⚠️ **Identifiants par défaut détectés.** "
            "Configure les vrais utilisateurs dans "
            "`.streamlit/secrets.toml` (voir `LIRE_MOI_CLOUD.txt`). "
            "En attendant, tu peux tester avec :\n\n"
            "- admin / admin\n"
            "- pointeur / pointeur"
        )


def exiger_connexion() -> dict:
    """Bloque la page si non connecté. À appeler en haut de chaque page.

    Retourne le user dict.
    """
    if not est_connecte():
        afficher_page_login()
        st.stop()
    return utilisateur_actuel()


def exiger_admin() -> dict:
    """Bloque la page si pas admin."""
    user = exiger_connexion()
    if not est_admin():
        st.error(
            "⛔ **Accès administrateur requis.**\n\n"
            "Cette page est réservée à l'administrateur. "
            f"Tu es connecté comme **{user['username']}** ({user['role']})."
        )
        st.stop()
    return user


def afficher_barre_utilisateur() -> None:
    """Affiche le bandeau utilisateur + bouton déconnexion dans le sidebar."""
    with st.sidebar:
        user = utilisateur_actuel()
        if user:
            role_badge = "👑 Admin" if user["role"] == ROLE_ADMIN else "👷 Pointeur"
            st.markdown(f"### {role_badge}")
            st.markdown(f"**{user['username']}**")
            if st.button("🚪 Se déconnecter", use_container_width=True):
                deconnecter()
                st.rerun()
            st.markdown("---")
