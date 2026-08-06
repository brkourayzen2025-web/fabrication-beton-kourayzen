# Fabrication Béton — Chantier Kourayzen

Application **Streamlit** locale (hors-ligne) pour suivre la **fabrication du béton**
sur le chantier du barrage Kourayzen. Marché n° 30/2024/DAH.

**⚠️ Cette application est TOTALEMENT INDÉPENDANTE de `materiaux_kourayzen`.**
Base de données distincte (`fabrication_beton.db`), stock séparé, aucun lien
technique avec ton app existante.

**Ce qu'elle fait :**
- Bibliothèque de formules de béton (validées LPEE) avec versionnage
- Calcul des dosages : quantités par matériau, nb godets chargeur, nb sacs ciment
- Fiche de préparation "aide-mémoire chantier"
- Enregistrement des productions + saisie des quantités réelles + écarts
- **Suivi du stock** : entrées manuelles, sorties automatiques à la fin de chaque mélange
- Tableau de bord des consommations par période, export Excel
- Journal complet des modifications (audit)

## Installation sur ton PC (Windows)

### En 2 clics — Méthode automatique 🚀

**Étape 1 — Prérequis : Python installé**

Si Python n'est pas déjà installé, télécharge-le :
👉 https://www.python.org/downloads/

⚠️ **IMPORTANT** : lors de l'installation, coche impérativement la case :
> ☑ **Add Python to PATH**

**Étape 2 — Copier le dossier**

Copie le dossier `fabrication_beton_kourayzen` sur ton Bureau,
à côté de `materiaux_kourayzen`.

**Étape 3 — Installer (une seule fois)**

Double-clique sur **`INSTALLER.bat`**.
Une fenêtre noire s'ouvre, ça installe les dépendances (1 à 3 min).

**Étape 4 — Lancer l'application (tous les jours)**

Double-clique sur **`LANCER_APP.bat`**.
Ton navigateur s'ouvre automatiquement sur `http://localhost:8501`.

## Structure du projet

```
fabrication_beton_kourayzen/
├── INSTALLER.bat                       Installation Windows (1 fois)
├── LANCER_APP.bat                      Lancement Windows (tous les jours)
├── LIRE_MOI.txt                        Instructions français
├── app.py                              Accueil + statistiques du jour
├── requirements.txt                    streamlit, pandas, openpyxl
├── README.md
├── .streamlit/
│   └── config.toml                     Thème
├── data/
│   ├── database.py                     Schéma SQLite + init
│   └── seed.py                         Formules validées + matériaux + godets
├── services/
│   ├── calcul.py                       ⭐ Cœur métier (godets, sacs, écarts)
│   ├── repositories.py                 Accès données (lecture + CRUD)
│   ├── formules_service.py             Édition + versionnage + workflow statuts
│   ├── stock.py                        Stock : entrées, sorties, situation
│   └── journal.py                      Audit log
├── models/
│   └── constants.py                    Constantes globales
├── pages/
│   ├── 1_🏗️_Préparer_un_mélange.py    Formulaire + fiche + save
│   ├── 2_📋_Productions.py             Liste + saisie des réels
│   ├── 3_📦_Stock.py                   Entrées + situation + historique
│   ├── 4_🚚_Engins_et_godets.py        CRUD Engins/Godets
│   ├── 5_🧪_Formules.py                Consultation + édition + versionnage + matériaux (densités)
│   ├── 6_📊_Tableau_de_bord.py         Analytics + export Excel
│   └── 7_📝_Journal.py                 Journal des modifications
└── fabrication_beton.db                SQLite locale (créée au 1er run)
```

## Comment marche le stock

**Une seule règle simple :**
```
stock_actuel = stock_initial
             + entrées manuelles
             + ajustements positifs
             − sorties (automatiques quand une production est terminée)
             − ajustements négatifs
```

### Configuration (une fois)
Page **📦 Stock → ⚙️ Configuration** : pour chaque matériau utilisé, renseigne
l'unité (kg / L), le stock initial déjà en place, et un seuil d'alerte.

### Utilisation quotidienne

1. **Un camion arrive** → Page **📦 Stock → ➕ Entrée** → tu saisis la quantité
2. **Tu prépares un mélange** → Page **🏗️ Préparer** → fiche calculée
3. **Tu termines la production** → Page **📋 Productions → Enregistrer et terminer**
   → le stock est **automatiquement déduit**
4. **Voir la situation** → Page **📦 Stock → 📊 Situation** en temps réel

### Ajustements
Casse d'un sac, inventaire, oubli d'une entrée : Page **📦 Stock → ✏️ Ajustement**
(motif obligatoire, tracé dans le journal).

## Données validées (seed automatique)

### Formules BCV (RM 06-2026, LPEE) — par m³

| Type | Sable | G1 | G2 | Ciment | Eau | Adjuvant |
|------|-------|-----|-----|--------|-----|----------|
| BCV D/27 (structure) | 870 | 610 | 510 | 350 | 170 | 1,2 % |
| Contact D/23 (fondation) | 855 | 590 | 500 | 280 | 175 | 1,2 % |
| Mortier de liaison BCR | 1060 | 850 | — | 350 | 180 | 1,6 % |

### Densités apparentes (t/m³)
- Sable : 1,53 · G1 (4/16) : 1,40 · G2 (16/25) : 1,38 · Adjuvant SUDAK : 1,10

### Godets chargeur
- Sable : 85 × 27 = **2 295 L**
- G1 : 74 × 27 = **1 998 L**
- G2 : 71 × 27 = **1 917 L**

## Règles de calcul strictes

**Nb godets = quantité litres ÷ capacité utile godet**
- 2 décimales, jamais arrondi au demi-godet
- Exemple : 2,48 godets = 2 godets complets + 48 % du dernier

**Nb sacs = quantité ciment ÷ poids sac**

**Écarts** : calculés en direct pendant la saisie. Rouge si |écart| > 15 %.

## Sauvegarde

Copie régulièrement le fichier `fabrication_beton.db` sur une clé USB ou Google Drive
pour éviter la perte de données en cas de crash disque.
