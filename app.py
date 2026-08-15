import logging
import os
import json
import random
import secrets
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

import pymysql
from flask import Flask, render_template, abort, request, redirect, url_for, session, Response, send_from_directory, g
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import Markup, escape
from werkzeug.security import generate_password_hash, check_password_hash

from db import obtenir_connexion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("majt_shop")

# FLASK_ENV=development est le SEUL moyen d'autoriser des valeurs de secours
# pour les secrets (SECRET_KEY, mots de passe). Par défaut (variable absente),
# l'application se comporte comme en production et refuse de démarrer si un
# secret requis n'est pas défini — voir exiger_secret() ci-dessous.
EST_DEV = os.environ.get("FLASK_ENV", "").strip().lower() == "development"


def exiger_secret(nom_variable, valeur_dev):
    valeur = os.environ.get(nom_variable)
    if valeur:
        return valeur
    if EST_DEV:
        logger.warning(
            "%s n'est pas définie : valeur de secours utilisée (développement local uniquement, "
            "FLASK_ENV=development détecté).",
            nom_variable,
        )
        return valeur_dev
    raise RuntimeError(
        f"{nom_variable} doit être définie via une variable d'environnement pour démarrer "
        "l'application. En local, définissez FLASK_ENV=development pour utiliser une valeur "
        "de secours de développement."
    )


app = Flask(__name__)
app.secret_key = exiger_secret("SECRET_KEY", "dev-majt-shop-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 Mo max par photo
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

csrf = CSRFProtect(app)
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])


@app.before_request
def _rendre_session_permanente():
    session.permanent = True


@app.before_request
def _journaliser_requetes_sensibles():
    if request.method == "POST" and request.path.startswith("/admin/migrations/"):
        journaliser(
            "migration",
            f"Migration déclenchée: {request.path} (admin={session.get('admin_connecte', False)}, ip={get_remote_address()})",
        )

IMAGES_DIR = Path(__file__).parent / "static" / "images"
EXTENSIONS_AUTORISEES = {"png", "jpg", "jpeg", "webp", "gif"}

CATEGORIES = {
    "vetements": "Vêtements",
    "chaussures": "Chaussures",
    "telephones": "Électroniques",
    "accessoires": "Accessoires",
    "automobiles": "Automobiles",
    "jouets": "Jouets",
    "bebes": "Bébés et Enfants",
}

PROVINCES_RDC = [
    "Kinshasa", "Kongo Central", "Kwango", "Kwilu", "Mai-Ndombe", "Kasaï",
    "Kasaï Central", "Kasaï Oriental", "Lomami", "Sankuru", "Maniema",
    "Sud-Kivu", "Nord-Kivu", "Ituri", "Haut-Uele", "Tshopo", "Bas-Uele",
    "Nord-Ubangi", "Mongala", "Sud-Ubangi", "Équateur", "Tshuapa",
    "Tanganyika", "Haut-Lomami", "Lualaba", "Haut-Katanga",
]

# Provinces couvertes par la livraison pour le moment. Liste volontairement
# restreinte par rapport à PROVINCES_RDC (qui reste la liste complète de
# référence) — à élargir plus tard sans toucher au reste du code.
PROVINCES_LIVRAISON_ACTIVES = ["Haut-Katanga", "Lualaba"]

# Données géographiques initiales de la hiérarchie province > ville > commune
# (voir tables `provinces`/`villes`/`communes`). Purement déclaratif : ajouter
# une province/ville/commune plus tard se fait ici (ou via l'admin), jamais
# en dur dans la logique métier.
DONNEES_GEOGRAPHIQUES_INITIALES = {
    "Haut-Katanga": {
        "Lubumbashi": ["Annexe", "Kamalondo", "Kampemba", "Katuba", "Kenya", "Lubumbashi", "Rwashi"],
        "Likasi": ["Kikula", "Likasi", "Panda", "Shituru"],
        "Kasumbalesa": ["Lwina", "Musoshi", "Musumali"],
    },
    "Lualaba": {
        "Kolwezi": ["Dilala", "Manika"],
        "Kasaji": ["Lueu", "Lukoji", "Tshimbundi"],
    },
}

SOUS_CATEGORIES = {
    "telephones": {
        "telephones_tablettes": "Téléphones et tablettes",
        "ordinateurs": "Ordinateurs",
        "consoles_gaming": "Consoles et gaming",
        "manettes": "Manettes",
        "tv_audio": "TV et audio",
        "accessoires_electroniques": "Accessoires électroniques",
    },
    "accessoires": {
        "sacs": "Sacs",
    },
}

PUBLICS = {
    "homme": "Homme",
    "femme": "Femme",
    "enfant": "Enfant",
    "unisexe": "Tous",
}
ORDRE_PUBLICS = ["homme", "femme", "enfant", "unisexe"]

FILTRES_REVENUS = {
    "date": "Date de livraison",
    "semaine": "Semaine",
    "mois": "Mois",
    "article": "Article",
    "categorie": "Catégorie",
}

PERIODES_PERFORMANCE = {
    "jour": "Aujourd'hui",
    "semaine": "Cette semaine",
    "mois": "Ce mois-ci",
    "annee": "Cette année",
}

MOTS_VIDES = {"le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "et", "ou", "pour", "avec", "en", "au", "aux"}

# Identifiants administrateur : configurables via variables d'environnement
# (ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE). Valeur de secours pour ADMIN_MOT_DE_PASSE
# réservée au développement local (voir exiger_secret ci-dessus).
ADMIN_UTILISATEUR = os.environ.get("ADMIN_UTILISATEUR", "admin")
ADMIN_MOT_DE_PASSE_HASH = generate_password_hash(exiger_secret("ADMIN_MOT_DE_PASSE", "MajtAdmin2026!"))

SEXES = {"homme": "Homme", "femme": "Femme"}


def _produit_depuis_ligne(ligne):
    ligne["prix"] = float(ligne["prix"])
    ligne["images"] = json.loads(ligne["images"]) if ligne["images"] else []
    ligne["tailles"] = json.loads(ligne["tailles"]) if ligne["tailles"] else []
    ligne["couleurs"] = json.loads(ligne["couleurs"]) if ligne["couleurs"] else []
    ligne["variantes"] = json.loads(ligne["variantes"]) if ligne.get("variantes") else {}
    return ligne


def charger_produits():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT * FROM produits ORDER BY id")
            return [_produit_depuis_ligne(l) for l in cur.fetchall()]
    finally:
        connexion.close()


COLONNES_PRODUITS_OPTIONNELLES = ["reduction_debut", "reduction_fin"]


def sauvegarder_produits(produits):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM produits")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            colonnes_optionnelles = [c for c in COLONNES_PRODUITS_OPTIONNELLES if c in colonnes_existantes]
            colonnes = [
                "id", "nom", "categorie", "sous_categorie", "prix", "reduction", "image", "images",
                "description", "tailles", "couleurs", "variantes", "stock", "public", "vues",
            ] + colonnes_optionnelles
            requete = "INSERT INTO produits ({}) VALUES ({})".format(
                ", ".join(colonnes), ", ".join(["%s"] * len(colonnes))
            )

            cur.execute("DELETE FROM produits")
            for p in produits:
                valeurs = [
                    p["id"], p["nom"], p["categorie"], p.get("sous_categorie") or None,
                    p.get("prix", 0), p.get("reduction", 0),
                    p.get("image", "placeholder.jpg"), json.dumps(p.get("images", []), ensure_ascii=False),
                    p.get("description", ""), json.dumps(p.get("tailles", []), ensure_ascii=False),
                    json.dumps(p.get("couleurs", []), ensure_ascii=False),
                    json.dumps(p.get("variantes", {}), ensure_ascii=False) if p.get("variantes") else None,
                    p.get("stock", 0), p.get("public", "unisexe"), p.get("vues", 0),
                ] + [p.get(c) or None for c in colonnes_optionnelles]
                cur.execute(requete, tuple(valeurs))
    finally:
        connexion.close()


def incrementer_vues_produit(produit_id):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("UPDATE produits SET vues = vues + 1 WHERE id = %s", (produit_id,))
    finally:
        connexion.close()


def quantites_vendues_par_produit():
    totaux = {}
    for c in charger_commandes():
        if c["statut"] == "annulee":
            continue
        for ligne in c["lignes"]:
            pid = ligne.get("produit_id")
            if pid is not None:
                totaux[pid] = totaux.get(pid, 0) + ligne.get("quantite", 0)
    return totaux


def trier_par_popularite(produits):
    ventes = quantites_vendues_par_produit()

    def score(p):
        return ventes.get(p["id"], 0) * 5 + p.get("vues", 0)

    return sorted(produits, key=score, reverse=True)


def _commande_depuis_ligne(ligne):
    ligne["latitude"] = float(ligne["latitude"]) if ligne["latitude"] is not None else None
    ligne["longitude"] = float(ligne["longitude"]) if ligne["longitude"] is not None else None
    ligne["total"] = float(ligne["total"])
    ligne["montant_verse"] = float(ligne["montant_verse"]) if ligne["montant_verse"] is not None else None
    ligne["montant_verse_cdf"] = float(ligne["montant_verse_cdf"]) if ligne.get("montant_verse_cdf") is not None else None
    ligne["montant_verse_usd"] = float(ligne["montant_verse_usd"]) if ligne.get("montant_verse_usd") is not None else None
    ligne["code_livraison"] = ligne.get("code_livraison")
    ligne["vue"] = bool(ligne["vue"])
    ligne["lignes"] = json.loads(ligne["lignes"]) if ligne["lignes"] else []
    return ligne


def charger_commandes():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT * FROM commandes ORDER BY date")
            return [_commande_depuis_ligne(l) for l in cur.fetchall()]
    finally:
        connexion.close()


COLONNES_COMMANDES_BASE = [
    "numero", "date", "nom", "telephone", "adresse", "latitude", "longitude", "lignes",
    "total", "statut", "montant_verse", "date_livraison", "vue", "livreur_numero", "livreur_nom",
]
COLONNES_COMMANDES_OPTIONNELLES = [
    "montant_verse_cdf", "montant_verse_usd", "code_livraison", "province", "ville", "commune",
    "zone_livraison", "frais_livraison", "coupon_code", "reduction_coupon", "tracking_token",
]


def _valeur_colonne_commande(c, colonne):
    if colonne == "lignes":
        return json.dumps(c.get("lignes", []), ensure_ascii=False)
    if colonne == "vue":
        return int(bool(c.get("vue", True)))
    if colonne == "total":
        return c.get("total", 0)
    if colonne == "statut":
        return c.get("statut", "en_attente")
    return c.get(colonne)


def sauvegarder_commandes(commandes):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            colonnes = COLONNES_COMMANDES_BASE + [
                c for c in COLONNES_COMMANDES_OPTIONNELLES if c in colonnes_existantes
            ]
            requete = "INSERT INTO commandes ({}) VALUES ({})".format(
                ", ".join(colonnes), ", ".join(["%s"] * len(colonnes))
            )

            cur.execute("DELETE FROM commandes")
            for c in commandes:
                cur.execute(requete, tuple(_valeur_colonne_commande(c, col) for col in colonnes))
    finally:
        connexion.close()


def generer_numero_commande():
    prefixe = f"MJT{date.today().strftime('%y%m%d')}"
    commandes_du_jour = [c for c in charger_commandes() if c["numero"].startswith(prefixe)]
    return f"{prefixe}{len(commandes_du_jour) + 1}"


def generer_numero_facture():
    prefixe = f"FAC{date.today().strftime('%y%m%d')}"
    factures_du_jour = [c for c in charger_commandes() if c["numero"].startswith(prefixe)]
    return f"{prefixe}{len(factures_du_jour) + 1}"


def generer_tracking_token():
    # Jeton long et non prédictible : contrairement au numéro de commande
    # (séquentiel, devinable), c'est ce jeton qui donne accès au suivi
    # public — il ne doit jamais pouvoir être reconstitué par énumération.
    return secrets.token_urlsafe(24)


def charger_livreurs():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT * FROM livreurs ORDER BY numero")
            livreurs = list(cur.fetchall())
            for l in livreurs:
                l["actif"] = bool(l["actif"])
            return livreurs
    finally:
        connexion.close()


def sauvegarder_livreurs(livreurs):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM livreurs")
            for l in livreurs:
                cur.execute(
                    """
                    INSERT INTO livreurs (numero, nom, prenom, sexe, adresse, telephone, mot_de_passe_hash,
                        actif, date_creation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        l["numero"], l["nom"], l["prenom"], l.get("sexe", "homme"), l.get("adresse", ""),
                        l.get("telephone", ""), l["mot_de_passe_hash"], int(bool(l.get("actif", True))),
                        l["date_creation"],
                    ),
                )
    finally:
        connexion.close()


def generer_numero_livreur():
    prefixe = f"LV{date.today().strftime('%y%m')}"
    livreurs_du_mois = [l for l in charger_livreurs() if l["numero"].startswith(prefixe)]
    return f"{prefixe}{len(livreurs_du_mois) + 1:02d}"


def charger_gestionnaires():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT * FROM gestionnaires ORDER BY numero")
            return list(cur.fetchall())
    finally:
        connexion.close()


def sauvegarder_gestionnaires(gestionnaires):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM gestionnaires")
            for g in gestionnaires:
                cur.execute(
                    """
                    INSERT INTO gestionnaires (numero, nom, prenom, telephone, mot_de_passe_hash, date_creation)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        g["numero"], g["nom"], g["prenom"], g.get("telephone", ""),
                        g["mot_de_passe_hash"], g["date_creation"],
                    ),
                )
    finally:
        connexion.close()


def generer_numero_gestionnaire():
    prefixe = f"GS{date.today().strftime('%y%m')}"
    gestionnaires_du_mois = [g for g in charger_gestionnaires() if g["numero"].startswith(prefixe)]
    return f"{prefixe}{len(gestionnaires_du_mois) + 1:02d}"


def journaliser(type_evenement, message):
    logger.info("%s: %s", type_evenement, message)
    try:
        connexion = obtenir_connexion()
        try:
            with connexion.cursor() as cur:
                cur.execute(
                    "INSERT INTO journal_activite (date, type, message) VALUES (%s, %s, %s)",
                    (datetime.now().isoformat(timespec="seconds"), type_evenement, message),
                )
        finally:
            connexion.close()
    except pymysql.err.ProgrammingError:
        pass


def construire_lignes_ventes(canal=None):
    produits_par_id = {p["id"]: p for p in charger_produits()}
    lignes_ventes = []
    for c in charger_commandes():
        if c["statut"] != "livree":
            continue
        est_boutique = c["numero"].startswith("FAC")
        if canal == "en_ligne" and est_boutique:
            continue
        if canal == "boutique" and not est_boutique:
            continue
        jour = (c.get("date_livraison") or c["date"])[:10]
        annee, semaine, _ = date.fromisoformat(jour).isocalendar()
        for ligne in c["lignes"]:
            p = produits_par_id.get(ligne.get("produit_id"))
            categorie_nom = CATEGORIES.get(p["categorie"], "Autre") if p else "Autre"
            lignes_ventes.append({
                "date": jour,
                "semaine": f"{annee} - semaine {semaine:02d}",
                "mois": jour[:7],
                "article": ligne["nom"],
                "categorie": categorie_nom,
                "commande": c["numero"],
                "quantite": ligne["quantite"],
                "montant": ligne["sous_total"],
            })
    return lignes_ventes


def charger_visites():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT date, heure, ip FROM visites ORDER BY id")
            return list(cur.fetchall())
    finally:
        connexion.close()


def ajouter_visite(visite):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "INSERT INTO visites (date, heure, ip) VALUES (%s, %s, %s)",
                (visite["date"], visite["heure"], visite["ip"]),
            )
    finally:
        connexion.close()


def charger_avis():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT numero, date, note_articles, note_procedure, commentaire FROM avis ORDER BY id")
            return list(cur.fetchall())
    finally:
        connexion.close()


def ajouter_avis(avis):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                INSERT INTO avis (numero, date, note_articles, note_procedure, commentaire)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (avis["numero"], avis["date"], avis["note_articles"], avis["note_procedure"], avis["commentaire"]),
            )
    finally:
        connexion.close()


def obtenir_ip_client():
    transmise = request.headers.get("X-Forwarded-For", "")
    if transmise:
        return transmise.split(",")[0].strip()
    return request.remote_addr or ""


def obtenir_taux_usd():
    # Mis en cache dans g : le taux est le même pour tous les produits d'une
    # même requête, inutile d'ouvrir une connexion DB par article affiché.
    if "taux_usd" in g:
        return g.taux_usd

    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT taux_usd FROM parametres WHERE id = 1")
            ligne = cur.fetchone()
            taux = float(ligne["taux_usd"]) if ligne else 2800.0
    except pymysql.err.ProgrammingError:
        taux = 2800.0
    finally:
        connexion.close()

    g.taux_usd = taux
    return taux


def definir_taux_usd(valeur):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parametres (id, taux_usd) VALUES (1, %s)
                ON DUPLICATE KEY UPDATE taux_usd = VALUES(taux_usd)
                """,
                (valeur,),
            )
    finally:
        connexion.close()


def charger_zones_livraison(actives_seulement=False):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            requete = "SELECT id, nom, frais, actif FROM zones_livraison"
            if actives_seulement:
                requete += " WHERE actif = 1"
            requete += " ORDER BY nom"
            cur.execute(requete)
            zones = list(cur.fetchall())
            for z in zones:
                z["frais"] = float(z["frais"])
                z["actif"] = bool(z["actif"])
            return zones
    except pymysql.err.ProgrammingError:
        return []
    finally:
        connexion.close()


# --- Hiérarchie géographique province > ville > commune ---------------------
# Utilisée par l'autocomplétion du checkout (recherche limitée à quelques
# résultats) et par la validation serveur des commandes. La comparaison
# LIKE + collation utf8mb4_unicode_ci de la base est déjà insensible à la
# casse et aux accents, donc aucun traitement Python supplémentaire n'est
# nécessaire ici.

def charger_provinces(recherche=None, actives_seulement=True, limite=8):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            requete = "SELECT id, nom, actif FROM provinces WHERE 1=1"
            params = []
            if actives_seulement:
                requete += " AND actif = 1"
            if recherche:
                requete += " AND nom LIKE %s"
                params.append(f"%{recherche}%")
            requete += " ORDER BY nom LIMIT %s"
            params.append(limite)
            cur.execute(requete, params)
            return list(cur.fetchall())
    except pymysql.err.ProgrammingError:
        return []
    finally:
        connexion.close()


def charger_villes(province_id, recherche=None, actives_seulement=True, limite=8):
    if not province_id:
        return []
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            requete = "SELECT id, province_id, nom, actif FROM villes WHERE province_id = %s"
            params = [province_id]
            if actives_seulement:
                requete += " AND actif = 1"
            if recherche:
                requete += " AND nom LIKE %s"
                params.append(f"%{recherche}%")
            requete += " ORDER BY nom LIMIT %s"
            params.append(limite)
            cur.execute(requete, params)
            return list(cur.fetchall())
    except pymysql.err.ProgrammingError:
        return []
    finally:
        connexion.close()


def charger_communes(ville_id, recherche=None, actives_seulement=True, limite=8):
    if not ville_id:
        return []
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            requete = "SELECT id, ville_id, nom, actif FROM communes WHERE ville_id = %s"
            params = [ville_id]
            if actives_seulement:
                requete += " AND actif = 1"
            if recherche:
                requete += " AND nom LIKE %s"
                params.append(f"%{recherche}%")
            requete += " ORDER BY nom LIMIT %s"
            params.append(limite)
            cur.execute(requete, params)
            return list(cur.fetchall())
    except pymysql.err.ProgrammingError:
        return []
    finally:
        connexion.close()


def valider_hierarchie_geographique(province_id, ville_id, commune_id):
    """Vérifie côté serveur que province_id/ville_id/commune_id existent,
    sont actifs, et forment une hiérarchie réellement cohérente (la ville
    appartient à la province, la commune appartient à la ville). Ne fait
    jamais confiance au texte affiché ni aux ids envoyés par le navigateur.
    Retourne (province, ville, commune, erreur)."""
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT id, nom, actif FROM provinces WHERE id = %s", (province_id,))
            province = cur.fetchone()
            if not province or not province["actif"]:
                return None, None, None, "Province invalide."

            cur.execute("SELECT id, province_id, nom, actif FROM villes WHERE id = %s", (ville_id,))
            ville = cur.fetchone()
            if not ville or not ville["actif"] or ville["province_id"] != province["id"]:
                return None, None, None, "Ville invalide pour cette province."

            cur.execute("SELECT id, ville_id, nom, actif FROM communes WHERE id = %s", (commune_id,))
            commune = cur.fetchone()
            if not commune or not commune["actif"] or commune["ville_id"] != ville["id"]:
                return None, None, None, "Commune invalide pour cette ville."

            return province, ville, commune, None
    except pymysql.err.ProgrammingError:
        return None, None, None, "Système géographique indisponible."
    finally:
        connexion.close()


def charger_coupons():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "SELECT id, code, type, valeur, date_fin, actif, usage_max, usage_compte "
                "FROM coupons ORDER BY code"
            )
            coupons = list(cur.fetchall())
            for c in coupons:
                c["valeur"] = float(c["valeur"])
                c["actif"] = bool(c["actif"])
            return coupons
    except pymysql.err.ProgrammingError:
        return []
    finally:
        connexion.close()


def valider_coupon(code, sous_total):
    if not code:
        return None, None, 0

    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "SELECT id, code, type, valeur, date_fin, actif, usage_max, usage_compte "
                "FROM coupons WHERE code = %s",
                (code,),
            )
            coupon = cur.fetchone()
    except pymysql.err.ProgrammingError:
        return None, "Code promo invalide.", 0
    finally:
        connexion.close()

    if not coupon or not coupon["actif"]:
        return None, "Code promo invalide.", 0
    if coupon["date_fin"] and date.today().isoformat() > coupon["date_fin"]:
        return None, "Ce code promo a expiré.", 0
    if coupon["usage_max"] is not None and coupon["usage_compte"] >= coupon["usage_max"]:
        return None, "Ce code promo a atteint sa limite d'utilisation.", 0

    valeur = float(coupon["valeur"])
    if coupon["type"] == "pourcentage":
        reduction = round(sous_total * valeur / 100)
    else:
        reduction = round(valeur)
    reduction = min(reduction, sous_total)
    return coupon, None, reduction


def incrementer_usage_coupon(coupon_id):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("UPDATE coupons SET usage_compte = usage_compte + 1 WHERE id = %s", (coupon_id,))
    finally:
        connexion.close()


def charger_cache_geoloc():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT ip, localisation FROM geoloc_cache")
            return {l["ip"]: l["localisation"] for l in cur.fetchall()}
    finally:
        connexion.close()


def sauvegarder_cache_geoloc(cache):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            for ip, localisation in cache.items():
                cur.execute(
                    """
                    INSERT INTO geoloc_cache (ip, localisation) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE localisation = VALUES(localisation)
                    """,
                    (ip, localisation),
                )
    finally:
        connexion.close()


def localiser_ip(ip, cache):
    if not ip:
        return "Inconnue"
    if ip in cache:
        return cache[ip]
    if ip in ("127.0.0.1", "::1") or ip.startswith(("10.", "192.168.", "172.")):
        cache[ip] = "Local"
        return cache[ip]
    localisation = "Inconnue"
    try:
        with urllib.request.urlopen(
            f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country", timeout=3
        ) as reponse:
            resultat = json.loads(reponse.read().decode())
        if resultat.get("status") == "success":
            ville = resultat.get("city")
            region = resultat.get("regionName")
            pays = resultat.get("country")
            parties = [v for v in (ville, region if region != ville else None, pays) if v]
            if parties:
                localisation = ", ".join(parties)
    except Exception:
        pass
    cache[ip] = localisation
    return localisation


def trouver_produit(produit_id):
    return next((p for p in charger_produits() if p["id"] == produit_id), None)


def publics_presents_tries(produits):
    presents = {p.get("public", "unisexe") for p in produits}
    return [pub for pub in ORDRE_PUBLICS if pub in presents]




def obtenir_lignes_panier():
    panier_session = session.get("panier", {})
    produits = charger_produits()
    lignes = []
    total = 0
    for cle, quantite in panier_session.items():
        pid_str, taille, couleur = (cle.split("|", 2) + ["", ""])[:3]
        p = next((x for x in produits if x["id"] == int(pid_str)), None)
        if p:
            sous_total = prix_final(p) * quantite
            total += sous_total
            lignes.append({
                "cle": cle,
                "produit": p,
                "taille": taille,
                "couleur": couleur,
                "quantite": quantite,
                "sous_total": sous_total,
            })
    return lignes, total


def parser_liste(chaine):
    return [v.strip() for v in chaine.split(",") if v.strip()]


def parser_variantes(form, couleurs, tailles):
    if not couleurs and not tailles:
        return {}
    if couleurs and tailles:
        combinaisons = [(c, t) for c in couleurs for t in tailles]
    elif couleurs:
        combinaisons = [(c, "") for c in couleurs]
    else:
        combinaisons = [("", t) for t in tailles]

    variantes = {}
    for couleur, taille in combinaisons:
        try:
            quantite = max(0, int(form.get(f"variante::{couleur}::{taille}", 0) or 0))
        except ValueError:
            quantite = 0
        variantes[cle_variante(couleur, taille)] = quantite
    return variantes


def cle_variante(couleur, taille):
    return f"{couleur or ''}::{taille or ''}"


def stock_variante(produit, couleur, taille):
    variantes = produit.get("variantes") or {}
    if not variantes:
        return produit.get("stock", 0)
    return variantes.get(cle_variante(couleur, taille), 0)


def ajuster_stock_variante(produit, couleur, taille, delta):
    variantes = produit.get("variantes") or {}
    if variantes:
        cle = cle_variante(couleur, taille)
        variantes[cle] = max(0, variantes.get(cle, 0) + delta)
        produit["variantes"] = variantes
        produit["stock"] = sum(variantes.values())
    else:
        produit["stock"] = max(0, produit.get("stock", 0) + delta)


def reserver_stock_commande(lignes_panier):
    """
    Vérifie puis décrémente le stock de façon atomique pour toutes les
    lignes d'un panier, en verrouillant les lignes produits concernées
    (SELECT ... FOR UPDATE) le temps d'une même transaction MySQL. Empêche
    la survente lorsque deux commandes concurrentes visent le même produit.

    Retourne (True, None) si la réservation a réussi (le stock est déjà
    décrémenté en base au retour), ou (False, message_erreur) si le stock
    est insuffisant pour au moins une ligne (aucune modification n'est
    alors appliquée).
    """
    # Verrouille toujours les produits dans le même ordre (par id croissant)
    # pour éviter les interblocages (deadlocks) entre commandes concurrentes
    # portant sur les mêmes produits dans un ordre différent.
    lignes_triees = sorted(lignes_panier, key=lambda l: l["produit"]["id"])

    connexion = obtenir_connexion()
    try:
        connexion.autocommit(False)
        with connexion.cursor() as cur:
            for ligne in lignes_triees:
                produit_id = ligne["produit"]["id"]
                cur.execute("SELECT * FROM produits WHERE id = %s FOR UPDATE", (produit_id,))
                ligne_db = cur.fetchone()
                if not ligne_db:
                    connexion.rollback()
                    return False, f"{ligne['produit']['nom']} n'est plus disponible."

                p = _produit_depuis_ligne(ligne_db)
                disponible = stock_variante(p, ligne["couleur"], ligne["taille"])
                if ligne["quantite"] > disponible:
                    connexion.rollback()
                    variante = (
                        " (" + ", ".join(v for v in (ligne["couleur"], ligne["taille"]) if v) + ")"
                        if (ligne["couleur"] or ligne["taille"]) else ""
                    )
                    return False, (
                        f"Stock insuffisant pour {ligne['produit']['nom']}{variante} — il ne reste que "
                        f"{disponible} en stock. Merci d'ajuster votre panier."
                    )

                ajuster_stock_variante(p, ligne["couleur"], ligne["taille"], -ligne["quantite"])
                cur.execute(
                    "UPDATE produits SET stock = %s, variantes = %s WHERE id = %s",
                    (p["stock"], json.dumps(p.get("variantes") or {}, ensure_ascii=False), produit_id),
                )
            connexion.commit()
        return True, None
    except Exception:
        connexion.rollback()
        raise
    finally:
        connexion.autocommit(True)
        connexion.close()


def reduction_active(produit):
    reduction = produit.get("reduction", 0) or 0
    if not reduction:
        return False
    aujourd_hui = date.today().isoformat()
    debut = produit.get("reduction_debut")
    fin = produit.get("reduction_fin")
    if debut and aujourd_hui < debut:
        return False
    if fin and aujourd_hui > fin:
        return False
    return True


def prix_final(produit):
    if reduction_active(produit):
        return round(produit["prix"] * (1 - produit["reduction"] / 100))
    return produit["prix"]


def extension_autorisee(nom_fichier):
    return "." in nom_fichier and nom_fichier.rsplit(".", 1)[1].lower() in EXTENSIONS_AUTORISEES


SIGNATURES_IMAGES = (
    (b"\x89PNG\r\n\x1a\n", 0),
    (b"\xff\xd8\xff", 0),
    (b"GIF87a", 0),
    (b"GIF89a", 0),
)


def contenu_image_valide(fichier):
    entete = fichier.stream.read(16)
    fichier.stream.seek(0)
    if entete[:4] == b"RIFF" and entete[8:12] == b"WEBP":
        return True
    return any(entete[decalage:decalage + len(signature)] == signature for signature, decalage in SIGNATURES_IMAGES)


EXTENSIONS_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp",
}


def sauvegarder_image_db(nom, chemin):
    # Le disque local des serveurs (Render, machines Fly.io) n'est pas
    # partagé et est réinitialisé à chaque déploiement : sans copie en base,
    # une photo ajoutée depuis l'admin peut disparaître ou n'être visible
    # que sur l'hébergeur/la machine qui a traité l'upload.
    extension = nom.rsplit(".", 1)[1].lower()
    type_mime = EXTENSIONS_MIME.get(extension, "application/octet-stream")
    contenu = chemin.read_bytes()
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "INSERT INTO fichiers_images (nom, contenu, type_mime) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE contenu = VALUES(contenu), type_mime = VALUES(type_mime)",
                (nom, contenu, type_mime),
            )
    except pymysql.err.ProgrammingError:
        pass
    finally:
        connexion.close()


def charger_image_db(nom):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT contenu, type_mime FROM fichiers_images WHERE nom = %s", (nom,))
            return cur.fetchone()
    except pymysql.err.ProgrammingError:
        return None
    finally:
        connexion.close()


def enregistrer_photos_produit(fichiers, produit_id):
    valides = [
        f for f in fichiers
        if f and f.filename and extension_autorisee(f.filename) and contenu_image_valide(f)
    ]
    if not valides:
        return None, None

    principal = valides[0]
    extension = principal.filename.rsplit(".", 1)[1].lower()
    nom_image = f"produit-{produit_id}.{extension}"
    principal.save(IMAGES_DIR / nom_image)
    sauvegarder_image_db(nom_image, IMAGES_DIR / nom_image)

    images = []
    for i, fichier in enumerate(valides[1:4], start=2):
        extension = fichier.filename.rsplit(".", 1)[1].lower()
        nom_fichier = f"produit-{produit_id}-{i}.{extension}"
        fichier.save(IMAGES_DIR / nom_fichier)
        sauvegarder_image_db(nom_fichier, IMAGES_DIR / nom_fichier)
        images.append(nom_fichier)

    return nom_image, images


def admin_requis(f):
    # Autorise l'ADMIN et le GESTIONNAIRE : accès complet au back-office,
    # sauf les routes protégées séparément par super_admin_requis.
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (session.get("admin_connecte") or session.get("gestionnaire_numero")):
            return redirect(url_for("connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def super_admin_requis(f):
    # Réservé au véritable ADMIN : gestion des gestionnaires, journal
    # d'activité, migrations de schéma.
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_connecte"):
            if session.get("gestionnaire_numero"):
                abort(403)
            return redirect(url_for("connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def livreur_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (session.get("admin_connecte") or session.get("gestionnaire_numero") or session.get("livreur_numero")):
            return redirect(url_for("connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def livreur_seul_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("livreur_numero"):
            return redirect(url_for("connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def livreur_courant():
    numero = session.get("livreur_numero")
    if not numero:
        return None
    return next((l for l in charger_livreurs() if l["numero"] == numero), None)


def personne_livraison_courante():
    # Permet à un gestionnaire (ou à l'admin) de prendre en charge une
    # livraison lui-même, en cas de manque de livreurs disponibles.
    if session.get("livreur_numero"):
        return livreur_courant()
    if session.get("gestionnaire_numero"):
        numero = session.get("gestionnaire_numero")
        g = next((x for x in charger_gestionnaires() if x["numero"] == numero), None)
        if g:
            return {"numero": g["numero"], "nom": g["nom"], "prenom": g["prenom"]}
    if session.get("admin_connecte"):
        return {"numero": "ADMIN", "nom": "", "prenom": "Admin"}
    return None


def peut_agir_sur_livraison(commande):
    # Admin et gestionnaire gardent leurs pouvoirs actuels. Un livreur ne
    # peut agir (livrer/annuler) que sur une commande non assignée (pool
    # partagé, comportement existant) ou assignée à lui-même — jamais sur
    # une commande assignée à un autre livreur.
    if session.get("admin_connecte") or session.get("gestionnaire_numero"):
        return True
    livreur_session = session.get("livreur_numero")
    if not livreur_session:
        return False
    assigne = commande.get("livreur_numero")
    return not assigne or assigne == livreur_session


def marquer_commande_livree(commande, montant_cdf_form, montant_usd_form=None):
    if commande["statut"] == "annulee":
        return False
    deja_solde = commande["statut"] == "livree" and (commande.get("montant_verse") or 0) >= commande["total"]
    if deja_solde:
        return False

    try:
        montant_usd = float(montant_usd_form or 0)
    except ValueError:
        montant_usd = 0

    try:
        if montant_cdf_form in (None, ""):
            montant_cdf = 0 if montant_usd else commande["total"]
        else:
            montant_cdf = float(montant_cdf_form)
    except ValueError:
        montant_cdf = commande["total"]

    taux = obtenir_taux_usd()
    commande["statut"] = "livree"
    commande["montant_verse"] = montant_cdf + montant_usd * taux
    commande["montant_verse_cdf"] = montant_cdf
    commande["montant_verse_usd"] = montant_usd
    if not commande.get("date_livraison"):
        commande["date_livraison"] = datetime.now().isoformat(timespec="seconds")
    return True


def marquer_en_preparation(commande):
    if commande["statut"] != "en_attente":
        return False
    commande["statut"] = "en_preparation"
    return True


def annuler_commande(commande):
    if commande["statut"] not in ("en_attente", "en_preparation", "en_livraison"):
        return False
    produits = charger_produits()
    for ligne in commande["lignes"]:
        p = next((x for x in produits if x["id"] == ligne.get("produit_id")), None)
        if p:
            ajuster_stock_variante(p, ligne.get("couleur"), ligne.get("taille"), ligne["quantite"])
    sauvegarder_produits(produits)
    commande["statut"] = "annulee"
    commande["montant_verse"] = None
    return True


def restaurer_commande(commande):
    if commande["statut"] != "annulee":
        return False
    produits = charger_produits()
    for ligne in commande["lignes"]:
        p = next((x for x in produits if x["id"] == ligne.get("produit_id")), None)
        if p:
            ajuster_stock_variante(p, ligne.get("couleur"), ligne.get("taille"), -ligne["quantite"])
    sauvegarder_produits(produits)
    commande["statut"] = "en_attente"
    commande["montant_verse"] = None
    commande["livreur_numero"] = None
    commande["livreur_nom"] = None
    return True


@app.template_filter("cdf")
def formater_cdf(valeur):
    nombre = f"{round(valeur):,}".replace(",", " ")
    return Markup(f"{escape(nombre)} <span class=\"cdf-suffixe\">CDF</span>")


@app.template_filter("prix_final")
def prix_final_filter(produit):
    return prix_final(produit)


@app.template_filter("reduction_active")
def reduction_active_filter(produit):
    return reduction_active(produit)


@app.template_filter("usd")
def formater_usd(valeur_cdf):
    taux = obtenir_taux_usd()
    if not taux:
        return ""
    montant = valeur_cdf / taux
    return f"≈ {montant:,.2f} $".replace(",", " ")


@app.context_processor
def injecter_globals():
    panier = session.get("panier", {})
    # admin_connecte couvre tout membre du back-office (ADMIN + GESTIONNAIRE).
    # est_super_admin distingue le véritable ADMIN (seul à gérer les
    # gestionnaires et à voir le journal d'activité).
    est_super_admin = bool(session.get("admin_connecte", False))
    gestionnaire_connecte = bool(session.get("gestionnaire_numero"))
    admin_connecte = est_super_admin or gestionnaire_connecte
    nouvelles_commandes = []
    if admin_connecte:
        nouvelles_commandes = [c for c in charger_commandes() if not c.get("vue", True)]
        nouvelles_commandes.sort(key=lambda c: c["date"], reverse=True)
    return {
        "nombre_panier": sum(panier.values()),
        "admin_connecte": admin_connecte,
        "est_super_admin": est_super_admin,
        "gestionnaire_connecte": gestionnaire_connecte,
        "livreur_connecte": bool(session.get("livreur_numero")),
        "nouvelles_commandes": nouvelles_commandes,
    }


@app.before_request
def compter_visite():
    if request.method != "GET":
        return
    if not request.endpoint or request.endpoint == "static" or request.endpoint.startswith("admin") or request.endpoint.startswith("livreur"):
        return
    aujourd_hui = date.today().isoformat()
    if session.get("visite_comptee_le") != aujourd_hui:
        session["visite_comptee_le"] = aujourd_hui
        ajouter_visite({
            "date": aujourd_hui,
            "heure": datetime.now().strftime("%H:%M:%S"),
            "ip": obtenir_ip_client(),
        })


# --- Boutique ---

@app.route("/img/<path:nom>")
def image_produit(nom):
    chemin_local = IMAGES_DIR / nom
    if chemin_local.is_file():
        return send_from_directory(IMAGES_DIR, nom)

    ligne = charger_image_db(nom)
    if not ligne:
        abort(404)
    try:
        chemin_local.write_bytes(ligne["contenu"])
    except OSError:
        pass
    return Response(ligne["contenu"], mimetype=ligne["type_mime"])


@app.template_filter("image_url")
def image_url_filter(nom, external=False):
    return url_for("image_produit", nom=nom, _external=external)


@app.route("/robots.txt")
def robots_txt():
    base = request.url_root.rstrip("/")
    contenu = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /livreur\nDisallow: /panier\nSitemap: {base}/sitemap.xml\n"
    return Response(contenu, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    base = request.url_root.rstrip("/")
    urls = [base + "/"]
    for slug in CATEGORIES:
        urls.append(base + url_for("categorie", slug=slug))
    for p in charger_produits():
        if p.get("stock", 0) > 0:
            urls.append(base + url_for("produit", produit_id=p["id"]))
    lignes = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lignes.append(f"<url><loc>{escape(u)}</loc></url>")
    lignes.append("</urlset>")
    return Response("\n".join(lignes), mimetype="application/xml")


@app.route("/")
def accueil():
    tous_produits = trier_par_popularite([p for p in charger_produits() if p.get("stock", 0) > 0])
    publics_presents = publics_presents_tries(tous_produits)
    categories_presentes = {p["categorie"] for p in tous_produits}

    categories_apercu = {}
    for slug in CATEGORIES:
        premier = next((p for p in tous_produits if p["categorie"] == slug), None)
        categories_apercu[slug] = premier["image"] if premier else "placeholder.jpg"

    public_filtre = request.args.get("public", "")
    categorie_filtre = request.args.get("categorie", "")

    produits = tous_produits
    if public_filtre in PUBLICS:
        produits = [p for p in produits if p.get("public", "unisexe") == public_filtre]
    elif categorie_filtre in CATEGORIES:
        produits = [p for p in produits if p["categorie"] == categorie_filtre]

    return render_template(
        "index.html",
        categories=CATEGORIES,
        produits=produits,
        public_filtre=public_filtre,
        categorie_filtre=categorie_filtre,
        public_labels=PUBLICS,
        publics_presents=publics_presents,
        categories_presentes=categories_presentes,
        categories_apercu=categories_apercu,
    )


@app.route("/categorie/<slug>")
def categorie(slug):
    if slug not in CATEGORIES:
        abort(404)
    produits_categorie = [p for p in charger_produits() if p["categorie"] == slug and p.get("stock", 0) > 0]
    publics = publics_presents_tries(produits_categorie)

    sous_categories_options = SOUS_CATEGORIES.get(slug, {})
    sous_categories_presentes = [
        sc for sc in sous_categories_options
        if any(p.get("sous_categorie") == sc for p in produits_categorie)
    ]

    produits = produits_categorie
    public_filtre = request.args.get("public", "")
    if public_filtre in PUBLICS:
        produits = [p for p in produits if p.get("public", "unisexe") == public_filtre]

    sous_categorie_filtre = request.args.get("sous_categorie", "")
    if sous_categorie_filtre in sous_categories_presentes:
        produits = [p for p in produits if p.get("sous_categorie") == sous_categorie_filtre]
    else:
        sous_categorie_filtre = ""

    produits_page, page, total_pages, total_produits = paginer(produits, request.args.get("page"))

    return render_template(
        "categorie.html",
        produits=produits_page,
        categories=CATEGORIES,
        categorie_active=slug,
        nom_categorie=CATEGORIES[slug],
        publics=publics,
        public_filtre=public_filtre,
        public_labels=PUBLICS,
        sous_categories_options=sous_categories_options,
        sous_categories_presentes=sous_categories_presentes,
        sous_categorie_filtre=sous_categorie_filtre,
        page=page,
        total_pages=total_pages,
        total_produits=total_produits,
    )


PRODUITS_PAR_PAGE = 24


def paginer(liste, page_form):
    try:
        page = max(1, int(page_form))
    except (TypeError, ValueError):
        page = 1
    total = len(liste)
    total_pages = max(1, -(-total // PRODUITS_PAR_PAGE))
    page = min(page, total_pages)
    debut = (page - 1) * PRODUITS_PAR_PAGE
    return liste[debut:debut + PRODUITS_PAR_PAGE], page, total_pages, total


def normaliser_recherche(texte):
    forme = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in forme if not unicodedata.combining(c))


def distance_levenshtein(a, b, max_dist=1):
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    precedent = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courant = [i]
        for j, cb in enumerate(b, 1):
            cout = 0 if ca == cb else 1
            courant.append(min(precedent[j] + 1, courant[j - 1] + 1, precedent[j - 1] + cout))
        precedent = courant
    return precedent[-1]


def extraire_mots_recherche(q):
    mots = []
    for mot in normaliser_recherche(q).replace("'", " ").split():
        mot = mot.strip(".,;:!?")
        if mot and mot not in MOTS_VIDES:
            mots.append(mot)
    return mots or ([normaliser_recherche(q)] if q else [])


def produit_correspond(produit, mots):
    texte_principal = normaliser_recherche(f"{produit['nom']} {produit.get('description', '')}")
    texte_complet = texte_principal + " " + normaliser_recherche(" ".join(produit.get("couleurs", [])))
    mots_principaux = texte_principal.split()
    for mot in mots:
        variantes = {mot}
        if mot.endswith("s") and len(mot) > 3:
            variantes.add(mot[:-1])
        else:
            variantes.add(mot + "s")
        if any(v in texte_complet for v in variantes):
            return True
        if len(mot) >= 6 and any(distance_levenshtein(mot, mt) <= 1 for mt in mots_principaux):
            return True
    return False


@app.route("/recherche")
def recherche():
    q = request.args.get("q", "").strip()
    mots = extraire_mots_recherche(q)
    produits = [
        p for p in charger_produits()
        if produit_correspond(p, mots)
    ] if mots else []
    produits_page, page, total_pages, total_produits = paginer(produits, request.args.get("page"))
    return render_template(
        "categorie.html",
        produits=produits_page,
        categories=CATEGORIES,
        categorie_active=None,
        nom_categorie=f"Résultats pour « {q} »" if q else "Recherche",
        q=q,
        page=page,
        total_pages=total_pages,
        total_produits=total_produits,
    )


@app.route("/produit/<int:produit_id>")
def produit(produit_id):
    p = trouver_produit(produit_id)
    if not p:
        abort(404)
    incrementer_vues_produit(produit_id)
    galerie = [p["image"]] + [img for img in p.get("images", []) if img != p["image"]]
    galerie = galerie[:4]
    return render_template(
        "produit.html", produit=p, categories=CATEGORIES, galerie=galerie, rupture_variante=request.args.get("rupture")
    )


@app.route("/panier")
def panier():
    lignes, total = obtenir_lignes_panier()
    numeros_suivis = session.get("mes_commandes", [])
    commandes_en_cours = []
    if numeros_suivis:
        toutes_commandes = {c["numero"]: c for c in charger_commandes()}
        for numero in numeros_suivis:
            commande = toutes_commandes.get(numero)
            if commande and commande["statut"] in ("en_attente", "en_livraison"):
                commandes_en_cours.append(commande)
        commandes_en_cours.sort(key=lambda c: c["date"], reverse=True)
    return render_template(
        "panier.html", lignes=lignes, total=total, categories=CATEGORIES, commandes_en_cours=commandes_en_cours
    )


@app.route("/panier/ajouter/<int:produit_id>", methods=["POST"])
def ajouter_au_panier(produit_id):
    produit_cible = trouver_produit(produit_id)
    if not produit_cible:
        abort(404)
    try:
        quantite = max(1, int(request.form.get("quantite", 1)))
    except ValueError:
        quantite = 1

    tailles = produit_cible.get("tailles") or []
    couleurs = produit_cible.get("couleurs") or []
    taille = request.form.get("taille", "")
    couleur = request.form.get("couleur", "")
    if tailles and taille not in tailles:
        taille = tailles[0]
    if couleurs and couleur not in couleurs:
        couleur = couleurs[0]
    if not tailles:
        taille = ""
    if not couleurs:
        couleur = ""

    stock_disponible = stock_variante(produit_cible, couleur, taille)
    if stock_disponible <= 0:
        return redirect(url_for("produit", produit_id=produit_id, rupture=1))
    quantite = min(quantite, stock_disponible)

    panier_session = session.get("panier", {})
    cle = f"{produit_id}|{taille}|{couleur}"
    panier_session[cle] = min(panier_session.get(cle, 0) + quantite, stock_disponible)
    session["panier"] = panier_session

    if request.form.get("acheter"):
        return redirect(url_for("panier"))
    return redirect(url_for("produit", produit_id=produit_id))


@app.route("/panier/supprimer", methods=["POST"])
def supprimer_du_panier():
    cle = request.form.get("cle", "")
    panier_session = session.get("panier", {})
    panier_session.pop(cle, None)
    session["panier"] = panier_session
    return redirect(url_for("panier"))


@app.route("/panier/commander", methods=["GET", "POST"])
def commander():
    lignes, total = obtenir_lignes_panier()
    if not lignes:
        return redirect(url_for("panier"))

    erreurs = {}
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        telephone = request.form.get("telephone", "").strip()
        province = request.form.get("province", "").strip()
        ville = request.form.get("ville", "").strip()
        commune = request.form.get("commune", "").strip()
        adresse = request.form.get("adresse", "").strip()

        zones_actives = charger_zones_livraison(actives_seulement=True)
        zone_choisie = None
        zone_id_form = request.form.get("zone_livraison_id", "").strip()
        if zone_id_form:
            zone_choisie = next((z for z in zones_actives if str(z["id"]) == zone_id_form), None)
            if not zone_choisie:
                erreurs["zone_livraison"] = "Zone de livraison invalide, merci de réessayer."
        frais_livraison = zone_choisie["frais"] if zone_choisie else 0

        coupon_code_form = request.form.get("coupon_code", "").strip().upper()
        coupon, message_coupon, reduction_coupon = valider_coupon(coupon_code_form, total)
        if message_coupon:
            erreurs["coupon"] = message_coupon

        if not nom:
            erreurs["nom"] = "Merci d'indiquer votre nom."
        if not telephone:
            erreurs["telephone"] = "Merci d'indiquer un numéro de téléphone."
        if province not in PROVINCES_LIVRAISON_ACTIVES:
            erreurs["province"] = "Merci de choisir votre province."
        if not ville:
            erreurs["ville"] = "Merci d'indiquer votre ville."
        if not adresse:
            erreurs["adresse"] = "Merci d'indiquer une adresse de livraison."

        produits_actuels = {p["id"]: p for p in charger_produits()}
        for ligne in lignes:
            p = produits_actuels.get(ligne["produit"]["id"])
            disponible = stock_variante(p, ligne["couleur"], ligne["taille"]) if p else 0
            if ligne["quantite"] > disponible:
                variante = " (" + ", ".join(v for v in (ligne["couleur"], ligne["taille"]) if v) + ")" if (ligne["couleur"] or ligne["taille"]) else ""
                erreurs["stock"] = f"Stock insuffisant pour {ligne['produit']['nom']}{variante} — il ne reste que {disponible} en stock. Merci d'ajuster votre panier."
                break

        if not erreurs:
            # Réservation atomique du stock : c'est cette vérification, pas
            # celle plus haut, qui fait foi en cas de commandes concurrentes
            # sur le même produit (verrouillage MySQL au niveau ligne).
            stock_ok, message_stock = reserver_stock_commande(lignes)
            if not stock_ok:
                erreurs["stock"] = message_stock

        if not erreurs:
            try:
                latitude = float(request.form.get("latitude") or "")
                longitude = float(request.form.get("longitude") or "")
            except ValueError:
                latitude = longitude = None

            numero = generer_numero_commande()
            commande = {
                "numero": numero,
                "tracking_token": generer_tracking_token(),
                "date": datetime.now().isoformat(timespec="seconds"),
                "nom": nom,
                "telephone": telephone,
                "province": province,
                "ville": ville,
                "commune": commune,
                "adresse": adresse,
                "latitude": latitude,
                "longitude": longitude,
                "lignes": [
                    {
                        "produit_id": ligne["produit"]["id"],
                        "nom": ligne["produit"]["nom"],
                        "taille": ligne["taille"],
                        "couleur": ligne["couleur"],
                        "quantite": ligne["quantite"],
                        "prix_unitaire": prix_final(ligne["produit"]),
                        "sous_total": ligne["sous_total"],
                    }
                    for ligne in lignes
                ],
                "zone_livraison": zone_choisie["nom"] if zone_choisie else None,
                "frais_livraison": frais_livraison,
                "coupon_code": coupon["code"] if coupon else None,
                "reduction_coupon": reduction_coupon,
                "total": total + frais_livraison - reduction_coupon,
                "statut": "en_attente",
                "montant_verse": None,
                "date_livraison": None,
                "vue": False,
            }

            commandes = charger_commandes()
            commandes.append(commande)
            sauvegarder_commandes(commandes)
            if coupon:
                incrementer_usage_coupon(coupon["id"])

            session["derniere_commande"] = commande
            mes_commandes = session.get("mes_commandes", [])
            if numero not in mes_commandes:
                mes_commandes.append(numero)
            session["mes_commandes"] = mes_commandes
            session["panier"] = {}
            return redirect(url_for("confirmation_commande"))

    return render_template(
        "commander.html",
        lignes=lignes,
        total=total,
        categories=CATEGORIES,
        erreurs=erreurs,
        valeurs=request.form,
        provinces=PROVINCES_LIVRAISON_ACTIVES,
        zones=charger_zones_livraison(actives_seulement=True),
    )


def etape_suivi(statut):
    if statut == "livree":
        return 4
    if statut == "en_livraison":
        return 3
    if statut == "en_preparation":
        return 2
    return 1


def avis_deja_donne(numero):
    return any(a["numero"] == numero for a in charger_avis())


@app.route("/commande/confirmation")
def confirmation_commande():
    commande = session.pop("derniere_commande", None)
    if not commande:
        return redirect(url_for("accueil"))
    return render_template(
        "confirmation.html",
        commande=commande,
        categories=CATEGORIES,
        initial_etape=etape_suivi(commande["statut"]),
        avis_donne=avis_deja_donne(commande["numero"]),
    )


@app.route("/suivi/<token>")
def suivi_commande(token):
    commande = next((c for c in charger_commandes() if c.get("tracking_token") == token), None)
    if not commande:
        abort(404)
    return render_template(
        "suivi.html",
        commande=commande,
        categories=CATEGORIES,
        initial_etape=etape_suivi(commande["statut"]),
        avis_donne=avis_deja_donne(commande["numero"]),
    )


@app.route("/suivi/<token>/etat")
def suivi_commande_etat(token):
    commande = next((c for c in charger_commandes() if c.get("tracking_token") == token), None)
    if not commande:
        abort(404)
    return {
        "statut": commande["statut"],
        "etape": etape_suivi(commande["statut"]),
        "date_livraison": commande.get("date_livraison"),
        "code_livraison": commande.get("code_livraison"),
        "avis_donne": avis_deja_donne(commande["numero"]),
    }


@app.route("/guide/commande")
def guide_commande():
    return render_template("guide_commande.html", categories=CATEGORIES)


@app.route("/aide/faq")
def faq():
    return render_template("faq.html", categories=CATEGORIES)


@app.route("/aide/retours")
def politique_retour():
    return render_template("politique_retour.html", categories=CATEGORIES)


@app.route("/aide/contact")
def contact():
    return render_template("contact.html", categories=CATEGORIES)


@app.route("/avis/<numero>", methods=["POST"])
def deposer_avis(numero):
    commande = next((c for c in charger_commandes() if c["numero"] == numero), None)
    if not commande:
        abort(404)

    if numero not in session.get("mes_commandes", []):
        journaliser("avis", f"Avis refusé (commande hors de la session du client) : {numero}")
        abort(403)

    if commande["statut"] != "livree":
        journaliser("avis", f"Avis refusé (commande non livrée, statut={commande['statut']}) : {numero}")
        abort(403)

    if any(a["numero"] == numero for a in charger_avis()):
        # Avis déjà enregistré pour cette commande : on n'affiche pas d'erreur au client.
        return ("", 204)

    try:
        note_articles = max(1, min(5, int(request.form.get("note_articles", 0))))
        note_procedure = max(1, min(5, int(request.form.get("note_procedure", 0))))
    except ValueError:
        abort(400)

    try:
        ajouter_avis({
            "numero": numero,
            "date": datetime.now().isoformat(timespec="seconds"),
            "note_articles": note_articles,
            "note_procedure": note_procedure,
            "commentaire": request.form.get("commentaire", "").strip(),
        })
    except pymysql.err.IntegrityError:
        # Requête concurrente ayant déjà inséré l'avis entre-temps : rien à faire.
        pass
    return ("", 204)


# --- Administration ---

@app.route("/connexion", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def connexion():
    erreur = None
    if request.method == "POST":
        identifiant = request.form.get("identifiant", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")

        if identifiant == ADMIN_UTILISATEUR and check_password_hash(ADMIN_MOT_DE_PASSE_HASH, mot_de_passe):
            session.pop("livreur_numero", None)
            session.pop("gestionnaire_numero", None)
            session["admin_connecte"] = True
            journaliser("connexion", f"Connexion admin réussie (ip={get_remote_address()})")
            suivant = request.args.get("suivant") or ""
            if not suivant.startswith("/admin"):
                suivant = ""
            return redirect(suivant or url_for("admin_tableau_de_bord"))

        gestionnaire_trouve = next((g for g in charger_gestionnaires() if g["numero"] == identifiant.upper()), None)
        if gestionnaire_trouve and check_password_hash(gestionnaire_trouve["mot_de_passe_hash"], mot_de_passe):
            session.pop("admin_connecte", None)
            session.pop("livreur_numero", None)
            session["gestionnaire_numero"] = gestionnaire_trouve["numero"]
            journaliser("connexion", f"Connexion gestionnaire réussie: {gestionnaire_trouve['numero']} (ip={get_remote_address()})")
            suivant = request.args.get("suivant") or ""
            if not suivant.startswith("/admin"):
                suivant = ""
            return redirect(suivant or url_for("admin_tableau_de_bord"))

        livreur_trouve = next((l for l in charger_livreurs() if l["numero"] == identifiant.upper()), None)
        if livreur_trouve and livreur_trouve.get("actif", True) and check_password_hash(livreur_trouve["mot_de_passe_hash"], mot_de_passe):
            session.pop("admin_connecte", None)
            session.pop("gestionnaire_numero", None)
            session["livreur_numero"] = livreur_trouve["numero"]
            journaliser("connexion", f"Connexion livreur réussie: {livreur_trouve['numero']} (ip={get_remote_address()})")
            suivant = request.args.get("suivant") or ""
            if not suivant.startswith("/livreur"):
                suivant = ""
            return redirect(suivant or url_for("livreur"))

        journaliser("connexion_echec", f"Échec de connexion pour identifiant={identifiant!r} (ip={get_remote_address()})")
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("connexion.html", erreur=erreur)


@app.route("/admin/connexion")
def admin_connexion():
    return redirect(url_for("connexion", suivant=request.args.get("suivant")))


@app.route("/admin/deconnexion")
def admin_deconnexion():
    session.pop("admin_connecte", None)
    session.pop("gestionnaire_numero", None)
    return redirect(url_for("connexion"))


COULEURS_CATEGORIES = {
    "vetements": "#8b5cf6", "chaussures": "#f97316", "telephones": "#0ea5e9",
    "accessoires": "#ec4899", "automobiles": "#22c55e", "jouets": "#eab308", "bebes": "#14b8a6",
}


def donnees_ventes_par_categorie(commandes, produits_par_id, jours=7):
    aujourd_hui = date.today()
    jours_liste = [(aujourd_hui - timedelta(days=i)).isoformat() for i in range(jours - 1, -1, -1)]
    quantites = {j: {} for j in jours_liste}
    categories_presentes = []

    for c in commandes:
        if c["statut"] == "annulee":
            continue
        jour = c["date"][:10]
        if jour not in quantites:
            continue
        for ligne in c["lignes"]:
            p = produits_par_id.get(ligne.get("produit_id"))
            cat = p["categorie"] if p else "accessoires"
            if cat not in categories_presentes:
                categories_presentes.append(cat)
            quantites[jour][cat] = quantites[jour].get(cat, 0) + ligne.get("quantite", 0)

    hauteur_graphique = 120
    largeur_graphique = (len(jours_liste) - 1) * 60 if len(jours_liste) > 1 else 120
    pas_x = largeur_graphique / max(len(jours_liste) - 1, 1)
    valeur_max = max(
        (quantites[j].get(cat, 0) for j in jours_liste for cat in categories_presentes),
        default=0,
    ) or 1

    courbes = []
    for cat in categories_presentes:
        points = []
        for idx, j in enumerate(jours_liste):
            qte = quantites[j].get(cat, 0)
            points.append({
                "x": round(idx * pas_x, 1),
                "y": round(hauteur_graphique - (qte / valeur_max) * hauteur_graphique, 1),
            })
        courbes.append({
            "categorie": CATEGORIES.get(cat, cat),
            "couleur": COULEURS_CATEGORIES.get(cat, "#999"),
            "points": points,
            "points_svg": " ".join(f"{pt['x']},{pt['y']}" for pt in points),
        })

    legende = [
        {"categorie": CATEGORIES.get(cat, cat), "couleur": COULEURS_CATEGORIES.get(cat, "#999")}
        for cat in categories_presentes
    ]
    labels_jours = [j[5:].replace("-", "/") for j in jours_liste]
    return courbes, legende, labels_jours, hauteur_graphique, largeur_graphique


@app.route("/admin")
@admin_requis
def admin_tableau_de_bord():
    produits = charger_produits()
    commandes = charger_commandes()
    visites = charger_visites()

    aujourd_hui = date.today().isoformat()
    commandes_en_attente = [c for c in commandes if c["statut"] == "en_attente"]
    commandes_en_preparation = [c for c in commandes if c["statut"] == "en_preparation"]
    commandes_en_livraison = [c for c in commandes if c["statut"] == "en_livraison"]
    commandes_livrees = [c for c in commandes if c["statut"] == "livree"]
    commandes_livrees_en_ligne = [c for c in commandes_livrees if not c["numero"].startswith("FAC")]
    commandes_livrees_boutique = [c for c in commandes_livrees if c["numero"].startswith("FAC")]
    chiffre_affaires_en_ligne = sum(c.get("montant_verse") or 0 for c in commandes_livrees_en_ligne)
    chiffre_affaires_boutique = sum(c.get("montant_verse") or 0 for c in commandes_livrees_boutique)
    chiffre_affaires_total = chiffre_affaires_en_ligne + chiffre_affaires_boutique

    livreurs_par_numero = {l["numero"]: l for l in charger_livreurs()}
    missions = {}
    for c in commandes_en_livraison:
        num = c.get("livreur_numero")
        if not num:
            continue
        if num not in missions:
            livreur = livreurs_par_numero.get(num)
            missions[num] = {
                "numero": num,
                "nom": f"{livreur['prenom']} {livreur['nom']}" if livreur else c.get("livreur_nom", num),
                "telephone": livreur["telephone"] if livreur else "",
                "nb_commandes": 0,
                "adresses": [],
            }
        missions[num]["nb_commandes"] += 1
        missions[num]["adresses"].append(c["adresse"])
    livreurs_en_mission = sorted(missions.values(), key=lambda m: m["nom"])

    # --- Widgets façon "tableau de bord des opérations" ---
    commandes_non_annulees = [c for c in commandes if c["statut"] != "annulee"]
    commandes_jour = [c for c in commandes_non_annulees if c["date"][:10] == aujourd_hui]
    produits_vendus_jour = sum(l.get("quantite", 0) for c in commandes_jour for l in c["lignes"])

    nb_en_ligne = sum(1 for c in commandes_non_annulees if not c["numero"].startswith("FAC"))
    nb_boutique = sum(1 for c in commandes_non_annulees if c["numero"].startswith("FAC"))
    total_canaux = nb_en_ligne + nb_boutique or 1
    part_en_ligne = round(nb_en_ligne / total_canaux * 100)
    part_boutique = 100 - part_en_ligne

    produits_par_id = {p["id"]: p for p in produits}
    courbes_categories, legende_categories, labels_jours_categories, hauteur_graphique, largeur_graphique = donnees_ventes_par_categorie(
        commandes, produits_par_id, jours=7
    )

    return render_template(
        "admin/tableau_de_bord.html",
        categories=CATEGORIES,
        visiteurs_jour=sum(1 for v in visites if v.get("date") == aujourd_hui),
        nb_commandes_attente=len(commandes_en_attente),
        nb_commandes_en_preparation=len(commandes_en_preparation),
        nb_commandes_en_livraison=len(commandes_en_livraison),
        nb_commandes_livrees=len(commandes_livrees_en_ligne),
        chiffre_affaires_en_ligne=chiffre_affaires_en_ligne,
        chiffre_affaires_boutique=chiffre_affaires_boutique,
        chiffre_affaires_total=chiffre_affaires_total,
        nb_produits=len(produits),
        nb_rupture=len([p for p in produits if p.get("stock", 0) <= 0]),
        livreurs_en_mission=livreurs_en_mission,
        taux_usd=obtenir_taux_usd(),
        produits_vendus_jour=produits_vendus_jour,
        nb_commandes_jour=len(commandes_jour),
        part_en_ligne=part_en_ligne,
        part_boutique=part_boutique,
        nb_en_ligne=nb_en_ligne,
        nb_boutique=nb_boutique,
        nb_commandes_livrees_boutique=len(commandes_livrees_boutique),
        courbes_categories=courbes_categories,
        legende_categories=legende_categories,
        labels_jours_categories=labels_jours_categories,
        hauteur_graphique=hauteur_graphique,
        largeur_graphique=largeur_graphique,
    )


def obtenir_lignes_facture_brouillon():
    brouillon = session.get("facture_brouillon", {})
    produits = charger_produits()
    lignes = []
    total = 0
    for cle, quantite in brouillon.items():
        pid_str, taille, couleur = (cle.split("|", 2) + ["", ""])[:3]
        p = next((x for x in produits if x["id"] == int(pid_str)), None)
        if p:
            sous_total = prix_final(p) * quantite
            total += sous_total
            lignes.append({
                "cle": cle, "produit": p, "taille": taille, "couleur": couleur,
                "quantite": quantite, "sous_total": sous_total,
            })
    return lignes, total


@app.route("/admin/facturation")
@admin_requis
def admin_facturation():
    lignes, total = obtenir_lignes_facture_brouillon()
    aujourd_hui = date.today().isoformat()
    factures = sorted(
        (c for c in charger_commandes() if c["numero"].startswith("FAC") and c["date"][:10] == aujourd_hui),
        key=lambda c: c["date"], reverse=True,
    )
    total_jour = sum(f["total"] for f in factures)
    return render_template(
        "admin/facturation.html", categories=CATEGORIES, produits=charger_produits(),
        lignes=lignes, total=total, factures=factures, total_jour=total_jour,
        taux_usd=obtenir_taux_usd(),
    )


@app.route("/admin/facturation/ajouter", methods=["POST"])
@admin_requis
def admin_facturation_ajouter():
    produit_id = request.form.get("produit_id", "")
    if not produit_id.isdigit():
        return redirect(url_for("admin_facturation"))

    produit_cible = next((p for p in charger_produits() if p["id"] == int(produit_id)), None)
    if not produit_cible:
        return redirect(url_for("admin_facturation"))

    try:
        quantite = max(1, int(request.form.get("quantite", 1)))
    except ValueError:
        quantite = 1

    tailles = produit_cible.get("tailles") or []
    couleurs = produit_cible.get("couleurs") or []
    taille = request.form.get("taille", "")
    couleur = request.form.get("couleur", "")
    if tailles and taille not in tailles:
        taille = tailles[0]
    if couleurs and couleur not in couleurs:
        couleur = couleurs[0]
    if not tailles:
        taille = ""
    if not couleurs:
        couleur = ""

    stock_disponible = stock_variante(produit_cible, couleur, taille)
    if stock_disponible > 0:
        brouillon = session.get("facture_brouillon", {})
        cle = f"{produit_id}|{taille}|{couleur}"
        brouillon[cle] = min(brouillon.get(cle, 0) + quantite, stock_disponible)
        session["facture_brouillon"] = brouillon

    return redirect(url_for("admin_facturation"))


@app.route("/admin/facturation/supprimer", methods=["POST"])
@admin_requis
def admin_facturation_supprimer():
    cle = request.form.get("cle", "")
    brouillon = session.get("facture_brouillon", {})
    brouillon.pop(cle, None)
    session["facture_brouillon"] = brouillon
    return redirect(url_for("admin_facturation"))


@app.route("/admin/facturation/vider", methods=["POST"])
@admin_requis
def admin_facturation_vider():
    session["facture_brouillon"] = {}
    return redirect(url_for("admin_facturation"))


@app.route("/admin/facturation/valider", methods=["POST"])
@admin_requis
def admin_facturation_valider():
    lignes, total = obtenir_lignes_facture_brouillon()
    if not lignes:
        return redirect(url_for("admin_facturation"))

    nom = request.form.get("nom", "").strip() or "Client de passage"
    telephone = request.form.get("telephone", "").strip()
    maintenant = datetime.now().isoformat(timespec="seconds")
    numero = generer_numero_facture()

    try:
        montant_usd = float(request.form.get("montant_verse_usd") or 0)
    except ValueError:
        montant_usd = 0
    try:
        montant_cdf_form = request.form.get("montant_verse_cdf")
        if montant_cdf_form in (None, ""):
            montant_cdf = 0 if montant_usd else total
        else:
            montant_cdf = float(montant_cdf_form)
    except ValueError:
        montant_cdf = total
    taux = obtenir_taux_usd()

    facture = {
        "numero": numero,
        "tracking_token": generer_tracking_token(),
        "date": maintenant,
        "nom": nom,
        "telephone": telephone or "—",
        "adresse": "Vente en boutique (facturation directe)",
        "latitude": None,
        "longitude": None,
        "lignes": [
            {
                "produit_id": ligne["produit"]["id"],
                "nom": ligne["produit"]["nom"],
                "taille": ligne["taille"],
                "couleur": ligne["couleur"],
                "quantite": ligne["quantite"],
                "prix_unitaire": prix_final(ligne["produit"]),
                "sous_total": ligne["sous_total"],
            }
            for ligne in lignes
        ],
        "total": total,
        "statut": "livree",
        "montant_verse": montant_cdf + montant_usd * taux,
        "montant_verse_cdf": montant_cdf,
        "montant_verse_usd": montant_usd,
        "date_livraison": maintenant,
        "vue": True,
    }

    stock_ok, message_stock = reserver_stock_commande(lignes)
    if not stock_ok:
        journaliser("stock", f"Facturation annulée (stock insuffisant) : {message_stock}")
        return redirect(url_for("admin_facturation", erreur_stock=message_stock))

    commandes = charger_commandes()
    commandes.append(facture)
    sauvegarder_commandes(commandes)

    session["facture_brouillon"] = {}
    return redirect(url_for("admin_facture_voir", numero=numero))


@app.route("/admin/facturation/<numero>")
@admin_requis
def admin_facture_voir(numero):
    facture = next((c for c in charger_commandes() if c["numero"] == numero and c["numero"].startswith("FAC")), None)
    if not facture:
        abort(404)
    return render_template("admin/facture.html", facture=facture, categories=CATEGORIES)


@app.route("/admin/facturation/<numero>/supprimer", methods=["POST"])
@admin_requis
def admin_facture_supprimer(numero):
    commandes = charger_commandes()
    facture = next((c for c in commandes if c["numero"] == numero and c["numero"].startswith("FAC")), None)
    if not facture:
        abort(404)

    produits = charger_produits()
    for ligne in facture["lignes"]:
        p = next((x for x in produits if x["id"] == ligne.get("produit_id")), None)
        if p:
            ajuster_stock_variante(p, ligne.get("couleur"), ligne.get("taille"), ligne["quantite"])
    sauvegarder_produits(produits)

    commandes = [c for c in commandes if c["numero"] != numero]
    sauvegarder_commandes(commandes)
    return redirect(url_for("admin_facturation"))


@app.route("/admin/produits")
@admin_requis
def admin_produits():
    produits = charger_produits()
    categorie_filtre = request.args.get("categorie", "")
    if categorie_filtre and categorie_filtre in CATEGORIES:
        produits = [p for p in produits if p["categorie"] == categorie_filtre]
    stock_filtre = request.args.get("stock", "")
    if stock_filtre == "rupture":
        produits = [p for p in produits if p.get("stock", 0) <= 0]
    return render_template(
        "admin/produits.html",
        produits=produits,
        categories=CATEGORIES,
        categorie_filtre=categorie_filtre,
        stock_filtre=stock_filtre,
    )


@app.route("/admin/commandes")
@admin_requis
def admin_commandes():
    commandes = charger_commandes()
    if any(not c.get("vue", True) for c in commandes):
        for c in commandes:
            c["vue"] = True
        sauvegarder_commandes(commandes)

    for c in commandes:
        for ligne in c["lignes"]:
            if ligne.get("prix_unitaire") is None and ligne.get("quantite"):
                ligne["prix_unitaire"] = round(ligne["sous_total"] / ligne["quantite"])

    statut_filtre = request.args.get("statut", "")
    if statut_filtre == "sur_place":
        commandes = [c for c in commandes if c["numero"].startswith("FAC")]
    elif statut_filtre == "livree":
        commandes = [c for c in commandes if c["statut"] == "livree" and not c["numero"].startswith("FAC")]
    elif statut_filtre in ("en_attente", "en_preparation", "en_livraison", "annulee"):
        commandes = [c for c in commandes if c["statut"] == statut_filtre]

    livreur_filtre = request.args.get("livreur", "")
    if livreur_filtre:
        commandes = [c for c in commandes if c.get("livreur_numero") == livreur_filtre]

    commandes = sorted(commandes, key=lambda c: c["date"], reverse=True)
    livreur_filtre_nom = None
    if livreur_filtre:
        livreur_objet = next((l for l in charger_livreurs() if l["numero"] == livreur_filtre), None)
        livreur_filtre_nom = f"{livreur_objet['prenom']} {livreur_objet['nom']}" if livreur_objet else livreur_filtre

    return render_template(
        "admin/commandes.html",
        commandes=commandes,
        categories=CATEGORIES,
        statut_filtre=statut_filtre,
        livreur_filtre=livreur_filtre,
        livreur_filtre_nom=livreur_filtre_nom,
        taux_usd=obtenir_taux_usd(),
    )


@app.route("/livreur/connexion")
def livreur_connexion():
    return redirect(url_for("connexion", suivant=request.args.get("suivant")))


@app.route("/livreur/deconnexion")
def livreur_deconnexion():
    session.pop("livreur_numero", None)
    return redirect(url_for("connexion"))


@app.route("/livreur")
@livreur_requis
def livreur():
    moi = personne_livraison_courante()
    commandes = charger_commandes()
    for c in commandes:
        for ligne in c["lignes"]:
            if ligne.get("prix_unitaire") is None and ligne.get("quantite"):
                ligne["prix_unitaire"] = round(ligne["sous_total"] / ligne["quantite"])
    disponibles = sorted(
        (c for c in commandes if c["statut"] in ("en_attente", "en_preparation")), key=lambda c: c["date"]
    )
    if moi:
        en_cours = [c for c in commandes if c["statut"] == "en_livraison" and c.get("livreur_numero") == moi["numero"]]
    else:
        en_cours = [c for c in commandes if c["statut"] == "en_livraison"]
    en_cours.sort(key=lambda c: c["date"])
    return render_template(
        "livreur.html", categories=CATEGORIES, disponibles=disponibles, en_cours=en_cours, moi=moi,
        taux_usd=obtenir_taux_usd(),
    )


@app.route("/livreur/performance")
@livreur_requis
def livreur_performance():
    moi = personne_livraison_courante()
    aujourd_hui = date.today().isoformat()
    commandes = charger_commandes()
    livrees_aujourdhui = [
        c for c in commandes
        if c.get("livreur_numero") == moi["numero"]
        and c["statut"] == "livree"
        and (c.get("date_livraison") or "").startswith(aujourd_hui)
    ]
    livrees_aujourdhui.sort(key=lambda c: c.get("date_livraison") or "", reverse=True)

    montant_cdf = sum(c.get("montant_verse_cdf") or 0 for c in livrees_aujourdhui)
    montant_usd = sum(c.get("montant_verse_usd") or 0 for c in livrees_aujourdhui)
    montant_total_cdf = sum(c.get("montant_verse") or 0 for c in livrees_aujourdhui)

    return render_template(
        "livreur_performance.html",
        categories=CATEGORIES,
        moi=moi,
        nb_courses=len(livrees_aujourdhui),
        montant_cdf=montant_cdf,
        montant_usd=montant_usd,
        montant_total_cdf=montant_total_cdf,
        commandes_jour=livrees_aujourdhui,
    )


@app.route("/livreur/profil")
@livreur_seul_requis
def livreur_profil():
    return render_template("livreur_profil.html", moi=livreur_courant(), sexes=SEXES)


@app.route("/livreur/commandes/<numero>/prendre", methods=["POST"])
@livreur_requis
def livreur_prendre_commande(numero):
    moi = personne_livraison_courante()
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if commande["statut"] in ("en_attente", "en_preparation"):
        commande["statut"] = "en_livraison"
        commande["livreur_numero"] = moi["numero"]
        commande["livreur_nom"] = f"{moi['prenom']} {moi['nom']}"
        commande["code_livraison"] = f"{random.randint(0, 9999):04d}"
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/livrer", methods=["POST"])
@livreur_requis
@limiter.limit("15 per minute")
def livreur_livrer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if not peut_agir_sur_livraison(commande):
        journaliser(
            "acces_livraison_refuse",
            f"Tentative de livraison de {numero} par un livreur non assigné "
            f"(livreur_session={session.get('livreur_numero')}, ip={get_remote_address()})",
        )
        abort(403)

    code_attendu = commande.get("code_livraison")
    code_saisi = request.form.get("code_livraison", "").strip()
    agent = personne_livraison_courante()
    if code_attendu and code_saisi != code_attendu:
        journaliser(
            "code_livraison_incorrect",
            f"Code de livraison incorrect pour {numero} (agent={agent['numero'] if agent else '?'}, ip={get_remote_address()})",
        )
        return redirect(url_for("livreur", erreur_code=numero))

    if marquer_commande_livree(commande, request.form.get("montant_verse_cdf"), request.form.get("montant_verse_usd")):
        journaliser("livraison", f"Commande {numero} livrée par {agent['numero'] if agent else '?'}")
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/annuler", methods=["POST"])
@livreur_requis
def livreur_annuler_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if not peut_agir_sur_livraison(commande):
        journaliser(
            "acces_annulation_refuse",
            f"Tentative d'annulation de {numero} par un livreur non assigné "
            f"(livreur_session={session.get('livreur_numero')}, ip={get_remote_address()})",
        )
        abort(403)
    if annuler_commande(commande):
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/lignes/<int:index>/modifier", methods=["POST"])
@livreur_requis
def livreur_modifier_ligne_commande(numero, index):
    moi = personne_livraison_courante()
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if commande["statut"] == "en_livraison" and commande.get("livreur_numero") == moi["numero"]:
        if modifier_quantite_ligne(commande, index, request.form.get("quantite")):
            sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/admin/revenus")
@admin_requis
def admin_revenus():
    canal = request.args.get("canal", "")
    if canal not in ("en_ligne", "boutique"):
        canal = "en_ligne"
    lignes = construire_lignes_ventes(canal=canal)
    total = sum(l["montant"] for l in lignes)

    encaisse_cdf = 0.0
    encaisse_usd = 0.0
    for c in charger_commandes():
        if c["statut"] != "livree":
            continue
        est_boutique = c["numero"].startswith("FAC")
        if canal == "en_ligne" and est_boutique:
            continue
        if canal == "boutique" and not est_boutique:
            continue
        encaisse_cdf += c.get("montant_verse_cdf") or 0
        encaisse_usd += c.get("montant_verse_usd") or 0

    type_filtre = request.args.get("type", "")
    valeur_filtre = request.args.get("valeur", "")

    valeurs_disponibles = []
    resultats = []
    sous_total = 0

    if type_filtre in FILTRES_REVENUS:
        valeurs_disponibles = sorted({l[type_filtre] for l in lignes}, reverse=(type_filtre in ("date", "semaine", "mois")))
        if valeur_filtre:
            resultats = [l for l in lignes if l[type_filtre] == valeur_filtre]
            sous_total = sum(l["montant"] for l in resultats)

    return render_template(
        "admin/revenus.html",
        categories=CATEGORIES,
        canal=canal,
        total=total,
        encaisse_cdf=encaisse_cdf,
        encaisse_usd=encaisse_usd,
        filtres=FILTRES_REVENUS,
        type_filtre=type_filtre,
        valeur_filtre=valeur_filtre,
        valeurs_disponibles=valeurs_disponibles,
        resultats=resultats,
        sous_total=sous_total,
    )


@app.route("/admin/visites")
@admin_requis
def admin_visites():
    aujourd_hui = date.today().isoformat()
    visites = sorted(
        (v for v in charger_visites() if v.get("date") == aujourd_hui),
        key=lambda v: (v.get("date", ""), v.get("heure", "")), reverse=True,
    )
    cache = charger_cache_geoloc()
    cache_modifie = False
    for v in visites:
        ip = v.get("ip", "")
        if ip not in cache:
            cache_modifie = True
        v["localisation"] = localiser_ip(ip, cache)
    if cache_modifie:
        sauvegarder_cache_geoloc(cache)
    return render_template("admin/visites.html", categories=CATEGORIES, visites=visites)


@app.route("/admin/avis")
@admin_requis
def admin_avis():
    avis = sorted(charger_avis(), key=lambda a: a.get("date", ""), reverse=True)
    noms_par_numero = {c["numero"]: c["nom"] for c in charger_commandes()}
    for a in avis:
        a["nom_client"] = noms_par_numero.get(a["numero"], "—")
    nb = len(avis)
    moyenne_articles = round(sum(a["note_articles"] for a in avis) / nb, 1) if nb else 0
    moyenne_procedure = round(sum(a["note_procedure"] for a in avis) / nb, 1) if nb else 0
    return render_template(
        "admin/avis.html",
        categories=CATEGORIES,
        avis=avis,
        nb=nb,
        moyenne_articles=moyenne_articles,
        moyenne_procedure=moyenne_procedure,
    )


@app.route("/admin/livreurs")
@admin_requis
def admin_livreurs():
    livreurs = sorted(charger_livreurs(), key=lambda l: l["numero"], reverse=True)
    commandes = charger_commandes()
    en_mission = {}
    for c in commandes:
        if c["statut"] == "en_livraison" and c.get("livreur_numero"):
            en_mission[c["livreur_numero"]] = en_mission.get(c["livreur_numero"], 0) + 1
    for l in livreurs:
        l["nb_en_mission"] = en_mission.get(l["numero"], 0)
    gestionnaires = []
    if session.get("admin_connecte"):
        try:
            gestionnaires = sorted(charger_gestionnaires(), key=lambda g: g["numero"], reverse=True)
        except pymysql.err.ProgrammingError:
            gestionnaires = []
    return render_template(
        "admin/livreurs.html", categories=CATEGORIES, livreurs=livreurs, sexes=SEXES, gestionnaires=gestionnaires,
    )


@app.route("/admin/livreurs/ajouter", methods=["GET", "POST"])
@admin_requis
def admin_ajouter_livreur():
    if request.method == "POST":
        livreurs = charger_livreurs()
        nouveau_livreur = {
            "numero": generer_numero_livreur(),
            "nom": request.form.get("nom", "").strip(),
            "prenom": request.form.get("prenom", "").strip(),
            "sexe": request.form.get("sexe") if request.form.get("sexe") in SEXES else "homme",
            "adresse": request.form.get("adresse", "").strip(),
            "telephone": request.form.get("telephone", "").strip(),
            "mot_de_passe_hash": generate_password_hash(request.form.get("mot_de_passe") or "MajtLivreur2026!"),
            "actif": True,
            "date_creation": datetime.now().isoformat(timespec="seconds"),
        }
        livreurs.append(nouveau_livreur)
        sauvegarder_livreurs(livreurs)
        journaliser("livreur", f"Livreur créé : {nouveau_livreur['numero']}")
        return redirect(url_for("admin_livreurs"))

    return render_template("admin/formulaire_livreur.html", livreur=None, categories=CATEGORIES, sexes=SEXES)


@app.route("/admin/livreurs/<numero>/modifier", methods=["GET", "POST"])
@admin_requis
def admin_modifier_livreur(numero):
    livreurs = charger_livreurs()
    livreur_cible = next((l for l in livreurs if l["numero"] == numero), None)
    if not livreur_cible:
        abort(404)

    if request.method == "POST":
        livreur_cible["nom"] = request.form.get("nom", "").strip()
        livreur_cible["prenom"] = request.form.get("prenom", "").strip()
        livreur_cible["sexe"] = request.form.get("sexe") if request.form.get("sexe") in SEXES else "homme"
        livreur_cible["adresse"] = request.form.get("adresse", "").strip()
        livreur_cible["telephone"] = request.form.get("telephone", "").strip()
        nouveau_mot_de_passe = request.form.get("mot_de_passe")
        if nouveau_mot_de_passe:
            livreur_cible["mot_de_passe_hash"] = generate_password_hash(nouveau_mot_de_passe)
        sauvegarder_livreurs(livreurs)
        return redirect(url_for("admin_livreurs"))

    return render_template("admin/formulaire_livreur.html", livreur=livreur_cible, categories=CATEGORIES, sexes=SEXES)


@app.route("/admin/livreurs/<numero>/basculer-actif", methods=["POST"])
@admin_requis
def admin_basculer_actif_livreur(numero):
    livreurs = charger_livreurs()
    livreur_cible = next((l for l in livreurs if l["numero"] == numero), None)
    if not livreur_cible:
        abort(404)
    livreur_cible["actif"] = not livreur_cible.get("actif", True)
    sauvegarder_livreurs(livreurs)
    journaliser("livreur", f"Livreur {'réactivé' if livreur_cible['actif'] else 'désactivé'} : {numero}")
    return redirect(url_for("admin_livreurs"))


@app.route("/admin/gestionnaires/ajouter", methods=["GET", "POST"])
@super_admin_requis
def admin_ajouter_gestionnaire():
    if request.method == "POST":
        gestionnaires = charger_gestionnaires()
        nouveau_gestionnaire = {
            "numero": generer_numero_gestionnaire(),
            "nom": request.form.get("nom", "").strip(),
            "prenom": request.form.get("prenom", "").strip(),
            "telephone": request.form.get("telephone", "").strip(),
            "mot_de_passe_hash": generate_password_hash(request.form.get("mot_de_passe") or "MajtGestion2026!"),
            "date_creation": datetime.now().isoformat(timespec="seconds"),
        }
        gestionnaires.append(nouveau_gestionnaire)
        sauvegarder_gestionnaires(gestionnaires)
        journaliser("gestionnaire", f"Gestionnaire créé : {nouveau_gestionnaire['numero']}")
        return redirect(url_for("admin_livreurs"))

    return render_template("admin/formulaire_gestionnaire.html", gestionnaire=None, categories=CATEGORIES)


@app.route("/admin/gestionnaires/<numero>/modifier", methods=["GET", "POST"])
@super_admin_requis
def admin_modifier_gestionnaire(numero):
    gestionnaires = charger_gestionnaires()
    gestionnaire_cible = next((g for g in gestionnaires if g["numero"] == numero), None)
    if not gestionnaire_cible:
        abort(404)

    if request.method == "POST":
        gestionnaire_cible["nom"] = request.form.get("nom", "").strip()
        gestionnaire_cible["prenom"] = request.form.get("prenom", "").strip()
        gestionnaire_cible["telephone"] = request.form.get("telephone", "").strip()
        nouveau_mot_de_passe = request.form.get("mot_de_passe")
        if nouveau_mot_de_passe:
            gestionnaire_cible["mot_de_passe_hash"] = generate_password_hash(nouveau_mot_de_passe)
        sauvegarder_gestionnaires(gestionnaires)
        journaliser("gestionnaire", f"Gestionnaire modifié : {numero}")
        return redirect(url_for("admin_livreurs"))

    return render_template("admin/formulaire_gestionnaire.html", gestionnaire=gestionnaire_cible, categories=CATEGORIES)


@app.route("/admin/gestionnaires/<numero>/supprimer", methods=["POST"])
@super_admin_requis
def admin_supprimer_gestionnaire(numero):
    gestionnaires = charger_gestionnaires()
    if not any(g["numero"] == numero for g in gestionnaires):
        abort(404)
    gestionnaires_restants = [g for g in gestionnaires if g["numero"] != numero]
    sauvegarder_gestionnaires(gestionnaires_restants)
    journaliser("gestionnaire", f"Gestionnaire supprimé : {numero}")
    if session.get("gestionnaire_numero") == numero:
        session.pop("gestionnaire_numero", None)
    return redirect(url_for("admin_livreurs"))


@app.route("/admin/journal")
@super_admin_requis
def admin_journal():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT date, type, message FROM journal_activite ORDER BY id DESC LIMIT 300")
            entrees = list(cur.fetchall())
    except pymysql.err.ProgrammingError:
        entrees = []
    finally:
        connexion.close()
    return render_template("admin/journal.html", categories=CATEGORIES, entrees=entrees)


@app.route("/admin/performance")
@admin_requis
def admin_performance():
    periode = request.args.get("periode", "jour")
    if periode not in PERIODES_PERFORMANCE:
        periode = "jour"

    aujourd_hui = date.today()
    if periode == "jour":
        debut = aujourd_hui
    elif periode == "semaine":
        debut = aujourd_hui - timedelta(days=aujourd_hui.weekday())
    elif periode == "mois":
        debut = aujourd_hui.replace(day=1)
    else:
        debut = aujourd_hui.replace(month=1, day=1)

    commandes = charger_commandes()
    livrees_periode = [
        c for c in commandes
        if c["statut"] == "livree" and c.get("date_livraison")
        and date.fromisoformat(c["date_livraison"][:10]) >= debut
    ]
    total_periode = len(livrees_periode)

    stats = []
    for l in charger_livreurs():
        commandes_livreur = [c for c in livrees_periode if c.get("livreur_numero") == l["numero"]]
        nb = len(commandes_livreur)
        montant = sum(c.get("montant_verse") or 0 for c in commandes_livreur)
        part = (nb / total_periode) if total_periode else 0
        stats.append({
            "numero": l["numero"],
            "nom": f"{l['prenom']} {l['nom']}",
            "nb_livrees": nb,
            "part": round(part * 100),
            "etoiles": round(part * 5),
            "montant": montant,
        })
    stats.sort(key=lambda s: s["nb_livrees"], reverse=True)

    return render_template(
        "admin/performance.html",
        categories=CATEGORIES,
        periodes=PERIODES_PERFORMANCE,
        periode=periode,
        stats=stats,
        total_periode=total_periode,
    )


@app.route("/admin/notifications/marquer-vues", methods=["POST"])
@admin_requis
def marquer_notifications_vues():
    commandes = charger_commandes()
    for c in commandes:
        c["vue"] = True
    sauvegarder_commandes(commandes)
    return ("", 204)


@app.route("/admin/activite/etat")
@livreur_requis
def admin_activite_etat():
    commandes = charger_commandes()
    compteurs = {
        "total": len(commandes),
        "en_attente": sum(1 for c in commandes if c["statut"] == "en_attente"),
        "en_preparation": sum(1 for c in commandes if c["statut"] == "en_preparation"),
        "en_livraison": sum(1 for c in commandes if c["statut"] == "en_livraison"),
        "livree": sum(1 for c in commandes if c["statut"] == "livree"),
        "annulee": sum(1 for c in commandes if c["statut"] == "annulee"),
    }
    nouvelles = sorted(
        (c for c in commandes if not c.get("vue", True)),
        key=lambda c: c["date"], reverse=True,
    )
    recentes = sorted(commandes, key=lambda c: c["date"], reverse=True)[:30]
    return {
        "compteurs": compteurs,
        "recentes": [
            {
                "numero": c["numero"], "nom": c["nom"], "statut": c["statut"],
                "livreur_nom": c.get("livreur_nom"),
            }
            for c in recentes
        ],
        "nouvelles_commandes": [
            {
                "numero": c["numero"], "date": c["date"], "nom": c["nom"],
                "telephone": c["telephone"], "adresse": c["adresse"], "total": c["total"],
                "lignes": [
                    {
                        "nom": l["nom"], "couleur": l.get("couleur"), "taille": l.get("taille"),
                        "quantite": l["quantite"], "sous_total": l["sous_total"],
                    }
                    for l in c["lignes"]
                ],
            }
            for c in nouvelles
        ],
    }


@app.route("/admin/commandes/<numero>/livrer", methods=["POST"])
@admin_requis
def admin_livrer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if marquer_commande_livree(commande, request.form.get("montant_verse_cdf"), request.form.get("montant_verse_usd")):
        journaliser("livraison", f"Commande {numero} livrée par admin/gestionnaire")
        sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


@app.route("/admin/commandes/<numero>/preparer", methods=["POST"])
@admin_requis
def admin_preparer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if marquer_en_preparation(commande):
        sauvegarder_commandes(commandes)
        journaliser("preparation", f"Commande {numero} marquée en préparation")
    return redirect(url_for("admin_commandes"))


@app.route("/admin/commandes/<numero>/annuler", methods=["POST"])
@admin_requis
def admin_annuler_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if annuler_commande(commande):
        sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


@app.route("/admin/commandes/<numero>/restaurer", methods=["POST"])
@admin_requis
def admin_restaurer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if restaurer_commande(commande):
        sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


def modifier_quantite_ligne(commande, index, quantite_form):
    if index < 0 or index >= len(commande["lignes"]):
        return False

    ligne = commande["lignes"][index]
    try:
        nouvelle_quantite = max(0, int(quantite_form if quantite_form is not None else ligne["quantite"]))
    except ValueError:
        nouvelle_quantite = ligne["quantite"]
    nouvelle_quantite = min(nouvelle_quantite, ligne["quantite"])

    delta = ligne["quantite"] - nouvelle_quantite
    if delta > 0:
        produits = charger_produits()
        p = next((x for x in produits if x["id"] == ligne.get("produit_id")), None)
        if p:
            ajuster_stock_variante(p, ligne.get("couleur"), ligne.get("taille"), delta)
            sauvegarder_produits(produits)

    prix_unitaire = ligne.get("prix_unitaire") or (round(ligne["sous_total"] / ligne["quantite"]) if ligne["quantite"] else 0)
    if nouvelle_quantite == 0:
        commande["lignes"].pop(index)
    else:
        ligne["quantite"] = nouvelle_quantite
        ligne["prix_unitaire"] = prix_unitaire
        ligne["sous_total"] = prix_unitaire * nouvelle_quantite

    commande["total"] = sum(l["sous_total"] for l in commande["lignes"])
    return True


@app.route("/admin/commandes/<numero>/lignes/<int:index>/modifier", methods=["POST"])
@admin_requis
def admin_modifier_ligne_commande(numero, index):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if commande["statut"] in ("en_attente", "en_preparation", "en_livraison"):
        if modifier_quantite_ligne(commande, index, request.form.get("quantite")):
            sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


@app.route("/admin/migrations/ajouter-colonne-vues", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_vues():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM produits LIKE 'vues'")
            if cur.fetchone():
                return {"statut": "colonne deja presente"}
            cur.execute("ALTER TABLE produits ADD COLUMN vues INT NOT NULL DEFAULT 0")
        return {"statut": "colonne ajoutee"}
    finally:
        connexion.close()


@app.route("/admin/migrations/fusionner-sacs-accessoires", methods=["POST"])
@super_admin_requis
def admin_migration_sacs_accessoires():
    produits = charger_produits()
    migres = []
    for p in produits:
        if p["categorie"] == "sacs":
            p["categorie"] = "accessoires"
            p["sous_categorie"] = "sacs"
            migres.append(p["id"])
    if migres:
        sauvegarder_produits(produits)
    return {"migres": migres}


@app.route("/admin/migrations/vider-cache-geoloc", methods=["POST"])
@super_admin_requis
def admin_migration_vider_cache_geoloc():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM geoloc_cache")
    finally:
        connexion.close()
    return {"statut": "cache vide"}


@app.route("/admin/migrations/ajouter-table-parametres", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_parametres():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parametres (
                    id INT PRIMARY KEY,
                    taux_usd DECIMAL(10,2) NOT NULL DEFAULT 2800
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cur.execute("INSERT IGNORE INTO parametres (id, taux_usd) VALUES (1, 2800)")
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonnes-devises", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonnes_devises():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            ajoutees = []
            if "montant_verse_cdf" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN montant_verse_cdf DECIMAL(12,2)")
                ajoutees.append("montant_verse_cdf")
            if "montant_verse_usd" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN montant_verse_usd DECIMAL(12,2)")
                ajoutees.append("montant_verse_usd")
        return {"colonnes_ajoutees": ajoutees}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonne-code-livraison", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonne_code_livraison():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            if "code_livraison" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN code_livraison VARCHAR(10)")
                return {"statut": "colonne ajoutee"}
        return {"statut": "colonne deja presente"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-table-gestionnaires", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_gestionnaires():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS gestionnaires (
                    numero VARCHAR(20) PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    prenom VARCHAR(255) NOT NULL,
                    telephone VARCHAR(50),
                    mot_de_passe_hash VARCHAR(255) NOT NULL,
                    date_creation VARCHAR(30) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-table-journal", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_journal():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_activite (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date VARCHAR(30) NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/uniciser-avis", methods=["POST"])
@super_admin_requis
def admin_migration_uniciser_avis():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "SELECT numero, COUNT(*) AS total FROM avis GROUP BY numero HAVING COUNT(*) > 1"
            )
            doublons = list(cur.fetchall())
            if doublons:
                return {
                    "statut": "doublons_presents",
                    "message": "Des commandes ont déjà plusieurs avis enregistrés. "
                    "La contrainte d'unicité n'a pas été appliquée pour ne rien supprimer "
                    "automatiquement. Merci de décider quoi faire de ces doublons.",
                    "doublons": doublons,
                }

            cur.execute("SHOW INDEX FROM avis WHERE Key_name = 'idx_avis_numero_unique'")
            if cur.fetchone():
                return {"statut": "deja_appliquee"}

            cur.execute("ALTER TABLE avis ADD UNIQUE INDEX idx_avis_numero_unique (numero)")
        return {"statut": "contrainte_ajoutee"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonnes-adresse", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonnes_adresse():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            ajoutees = []
            for colonne in ("province", "ville", "commune"):
                if colonne not in colonnes_existantes:
                    cur.execute(f"ALTER TABLE commandes ADD COLUMN {colonne} VARCHAR(100)")
                    ajoutees.append(colonne)
        return {"colonnes_ajoutees": ajoutees}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-table-zones-livraison", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_zones_livraison():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS zones_livraison (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(150) NOT NULL,
                    frais DECIMAL(12,2) NOT NULL DEFAULT 0,
                    actif TINYINT(1) NOT NULL DEFAULT 1
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonnes-frais-livraison", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonnes_frais_livraison():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            ajoutees = []
            if "zone_livraison" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN zone_livraison VARCHAR(150)")
                ajoutees.append("zone_livraison")
            if "frais_livraison" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN frais_livraison DECIMAL(12,2)")
                ajoutees.append("frais_livraison")
        return {"colonnes_ajoutees": ajoutees}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonnes-promotion", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonnes_promotion():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM produits")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            ajoutees = []
            for colonne in ("reduction_debut", "reduction_fin"):
                if colonne not in colonnes_existantes:
                    cur.execute(f"ALTER TABLE produits ADD COLUMN {colonne} VARCHAR(10)")
                    ajoutees.append(colonne)
        return {"colonnes_ajoutees": ajoutees}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-table-fichiers-images", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_fichiers_images():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fichiers_images (
                    nom VARCHAR(255) PRIMARY KEY,
                    contenu LONGBLOB NOT NULL,
                    type_mime VARCHAR(50) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-table-coupons", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_table_coupons():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS coupons (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    code VARCHAR(50) NOT NULL UNIQUE,
                    type VARCHAR(20) NOT NULL DEFAULT 'pourcentage',
                    valeur DECIMAL(12,2) NOT NULL DEFAULT 0,
                    date_fin VARCHAR(10),
                    actif TINYINT(1) NOT NULL DEFAULT 1,
                    usage_max INT,
                    usage_compte INT NOT NULL DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        return {"statut": "table prete"}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonnes-coupon", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonnes_coupon():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            ajoutees = []
            if "coupon_code" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN coupon_code VARCHAR(50)")
                ajoutees.append("coupon_code")
            if "reduction_coupon" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN reduction_coupon DECIMAL(12,2)")
                ajoutees.append("reduction_coupon")
        return {"colonnes_ajoutees": ajoutees}
    finally:
        connexion.close()


@app.route("/admin/migrations/ajouter-colonne-tracking-token", methods=["POST"])
@super_admin_requis
def admin_migration_ajouter_colonne_tracking_token():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM commandes")
            colonnes_existantes = {ligne["Field"] for ligne in cur.fetchall()}
            colonne_ajoutee = False
            if "tracking_token" not in colonnes_existantes:
                cur.execute("ALTER TABLE commandes ADD COLUMN tracking_token VARCHAR(40)")
                colonne_ajoutee = True
    finally:
        connexion.close()

    # Backfill : générer un jeton pour les commandes existantes qui n'en ont pas
    # encore (aucune commande n'est modifiée si elle a déjà un jeton).
    commandes = charger_commandes()
    a_completer = [c for c in commandes if not c.get("tracking_token")]
    for c in a_completer:
        c["tracking_token"] = generer_tracking_token()
    if a_completer:
        sauvegarder_commandes(commandes)

    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM commandes WHERE tracking_token IS NULL")
            restantes = cur.fetchone()["n"]
            index_ajoute = False
            if restantes == 0:
                cur.execute("SHOW INDEX FROM commandes WHERE Key_name = 'idx_tracking_token_unique'")
                if not cur.fetchone():
                    cur.execute(
                        "ALTER TABLE commandes ADD UNIQUE INDEX idx_tracking_token_unique (tracking_token)"
                    )
                    index_ajoute = True
    finally:
        connexion.close()

    return {
        "colonne_ajoutee": colonne_ajoutee,
        "commandes_completees": len(a_completer),
        "index_unique_ajoute": index_ajoute,
        "restantes_sans_token": restantes,
    }


@app.route("/admin/coupons", methods=["GET", "POST"])
@admin_requis
def admin_coupons():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        type_coupon = request.form.get("type") if request.form.get("type") in ("pourcentage", "montant") else "pourcentage"
        try:
            valeur = max(0, float(request.form.get("valeur", 0) or 0))
        except ValueError:
            valeur = 0
        date_fin = request.form.get("date_fin", "").strip() or None
        usage_max_form = request.form.get("usage_max", "").strip()
        try:
            usage_max = max(1, int(usage_max_form)) if usage_max_form else None
        except ValueError:
            usage_max = None
        if code and valeur > 0:
            connexion = obtenir_connexion()
            try:
                with connexion.cursor() as cur:
                    cur.execute(
                        "INSERT INTO coupons (code, type, valeur, date_fin, actif, usage_max) "
                        "VALUES (%s, %s, %s, %s, 1, %s)",
                        (code, type_coupon, valeur, date_fin, usage_max),
                    )
            except pymysql.err.IntegrityError:
                pass
            finally:
                connexion.close()
        return redirect(url_for("admin_coupons"))
    return render_template("admin/coupons.html", coupons=charger_coupons(), categories=CATEGORIES)


@app.route("/admin/coupons/<int:coupon_id>/modifier", methods=["POST"])
@admin_requis
def admin_modifier_coupon(coupon_id):
    type_coupon = request.form.get("type") if request.form.get("type") in ("pourcentage", "montant") else "pourcentage"
    try:
        valeur = max(0, float(request.form.get("valeur", 0) or 0))
    except ValueError:
        valeur = 0
    date_fin = request.form.get("date_fin", "").strip() or None
    usage_max_form = request.form.get("usage_max", "").strip()
    try:
        usage_max = max(1, int(usage_max_form)) if usage_max_form else None
    except ValueError:
        usage_max = None
    actif = 1 if request.form.get("actif") == "on" else 0
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "UPDATE coupons SET type=%s, valeur=%s, date_fin=%s, usage_max=%s, actif=%s WHERE id=%s",
                (type_coupon, valeur, date_fin, usage_max, actif, coupon_id),
            )
    finally:
        connexion.close()
    return redirect(url_for("admin_coupons"))


@app.route("/admin/coupons/<int:coupon_id>/supprimer", methods=["POST"])
@admin_requis
def admin_supprimer_coupon(coupon_id):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM coupons WHERE id=%s", (coupon_id,))
    finally:
        connexion.close()
    return redirect(url_for("admin_coupons"))


@app.route("/admin/zones-livraison", methods=["GET", "POST"])
@admin_requis
def admin_zones_livraison():
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        try:
            frais = max(0, float(request.form.get("frais", 0) or 0))
        except ValueError:
            frais = 0
        if nom:
            connexion = obtenir_connexion()
            try:
                with connexion.cursor() as cur:
                    cur.execute(
                        "INSERT INTO zones_livraison (nom, frais, actif) VALUES (%s, %s, 1)", (nom, frais)
                    )
            finally:
                connexion.close()
        return redirect(url_for("admin_zones_livraison"))
    return render_template("admin/zones_livraison.html", zones=charger_zones_livraison(), categories=CATEGORIES)


@app.route("/admin/zones-livraison/<int:zone_id>/modifier", methods=["POST"])
@admin_requis
def admin_modifier_zone_livraison(zone_id):
    nom = request.form.get("nom", "").strip()
    try:
        frais = max(0, float(request.form.get("frais", 0) or 0))
    except ValueError:
        frais = 0
    actif = 1 if request.form.get("actif") == "on" else 0
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute(
                "UPDATE zones_livraison SET nom=%s, frais=%s, actif=%s WHERE id=%s", (nom, frais, actif, zone_id)
            )
    finally:
        connexion.close()
    return redirect(url_for("admin_zones_livraison"))


@app.route("/admin/zones-livraison/<int:zone_id>/supprimer", methods=["POST"])
@admin_requis
def admin_supprimer_zone_livraison(zone_id):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM zones_livraison WHERE id=%s", (zone_id,))
    finally:
        connexion.close()
    return redirect(url_for("admin_zones_livraison"))


@app.route("/admin/parametres/taux-usd", methods=["POST"])
@admin_requis
def admin_definir_taux_usd():
    try:
        valeur = float(request.form.get("taux_usd", "0").replace(",", "."))
    except ValueError:
        valeur = 0
    if valeur > 0:
        definir_taux_usd(valeur)
    return redirect(url_for("admin_tableau_de_bord"))


@app.route("/admin/produits/importer-lot", methods=["POST"])
@admin_requis
def admin_importer_lot_produits():
    nom_fichier = request.args.get("fichier", "nouveaux_produits.json")
    if "/" in nom_fichier or "\\" in nom_fichier:
        return {"erreur": "nom de fichier invalide"}, 400
    chemin = Path(__file__).parent / "data" / nom_fichier
    if not chemin.exists():
        return {"erreur": "fichier introuvable"}, 404

    with open(chemin, encoding="utf-8") as f:
        nouveaux = json.load(f)

    produits = charger_produits()
    ids_existants = {p["id"] for p in produits}
    ajoutes = []
    for p in nouveaux:
        if p["id"] in ids_existants:
            continue
        produits.append(p)
        ajoutes.append(p["id"])

    if ajoutes:
        sauvegarder_produits(produits)

    return {"ajoutes": ajoutes, "deja_presents": [p["id"] for p in nouveaux if p["id"] not in ajoutes]}


@app.route("/admin/produits/ajouter", methods=["GET", "POST"])
@admin_requis
def admin_ajouter_produit():
    if request.method == "POST":
        produits = charger_produits()
        nouvel_id = max((p["id"] for p in produits), default=0) + 1

        try:
            reduction = max(0, min(90, int(request.form.get("reduction", 0) or 0)))
        except ValueError:
            reduction = 0

        reduction_debut = request.form.get("reduction_debut", "").strip() or None
        reduction_fin = request.form.get("reduction_fin", "").strip() or None

        try:
            stock = max(0, int(request.form.get("stock", 0) or 0))
        except ValueError:
            stock = 0

        nom_image, photos_supplementaires = enregistrer_photos_produit(
            request.files.getlist("photos"), nouvel_id
        )
        if nom_image is None:
            nom_image = "placeholder.jpg"
            photos_supplementaires = []

        categorie_choisie = request.form.get("categorie")
        sous_categorie_choisie = request.form.get("sous_categorie") or None
        if sous_categorie_choisie not in SOUS_CATEGORIES.get(categorie_choisie, {}):
            sous_categorie_choisie = None

        couleurs_liste = parser_liste(request.form.get("couleurs", ""))
        tailles_liste = parser_liste(request.form.get("tailles", ""))
        variantes = parser_variantes(request.form, couleurs_liste, tailles_liste)
        if variantes:
            stock = sum(variantes.values())

        nouveau_produit = {
            "id": nouvel_id,
            "nom": request.form.get("nom", "").strip(),
            "categorie": categorie_choisie,
            "sous_categorie": sous_categorie_choisie,
            "prix": float(request.form.get("prix", 0) or 0),
            "reduction": reduction,
            "reduction_debut": reduction_debut,
            "reduction_fin": reduction_fin,
            "public": request.form.get("public") if request.form.get("public") in PUBLICS else "unisexe",
            "stock": stock,
            "image": nom_image,
            "images": photos_supplementaires,
            "description": request.form.get("description", "").strip(),
            "couleurs": couleurs_liste,
            "tailles": tailles_liste,
            "variantes": variantes,
        }
        produits.append(nouveau_produit)
        sauvegarder_produits(produits)
        return redirect(url_for("admin_produits"))

    return render_template(
        "admin/formulaire_produit.html", produit=None, categories=CATEGORIES, publics_options=PUBLICS,
        sous_categories=SOUS_CATEGORIES,
    )


@app.route("/admin/produits/<int:produit_id>/modifier", methods=["GET", "POST"])
@admin_requis
def admin_modifier_produit(produit_id):
    produits = charger_produits()
    produit_cible = next((p for p in produits if p["id"] == produit_id), None)
    if not produit_cible:
        abort(404)

    if request.method == "POST":
        produit_cible["nom"] = request.form.get("nom", "").strip()
        produit_cible["categorie"] = request.form.get("categorie")
        sous_categorie_choisie = request.form.get("sous_categorie") or None
        if sous_categorie_choisie not in SOUS_CATEGORIES.get(produit_cible["categorie"], {}):
            sous_categorie_choisie = None
        produit_cible["sous_categorie"] = sous_categorie_choisie
        produit_cible["prix"] = float(request.form.get("prix", 0) or 0)
        try:
            produit_cible["reduction"] = max(0, min(90, int(request.form.get("reduction", 0) or 0)))
        except ValueError:
            produit_cible["reduction"] = 0
        produit_cible["reduction_debut"] = request.form.get("reduction_debut", "").strip() or None
        produit_cible["reduction_fin"] = request.form.get("reduction_fin", "").strip() or None
        produit_cible["description"] = request.form.get("description", "").strip()
        produit_cible["couleurs"] = parser_liste(request.form.get("couleurs", ""))
        produit_cible["tailles"] = parser_liste(request.form.get("tailles", ""))
        produit_cible["public"] = request.form.get("public") if request.form.get("public") in PUBLICS else "unisexe"
        try:
            produit_cible["stock"] = max(0, int(request.form.get("stock", 0) or 0))
        except ValueError:
            produit_cible["stock"] = 0

        variantes = parser_variantes(request.form, produit_cible["couleurs"], produit_cible["tailles"])
        produit_cible["variantes"] = variantes
        if variantes:
            produit_cible["stock"] = sum(variantes.values())

        nom_image, photos_supplementaires = enregistrer_photos_produit(
            request.files.getlist("photos"), produit_id
        )
        if nom_image is not None:
            produit_cible["image"] = nom_image
            produit_cible["images"] = photos_supplementaires

        sauvegarder_produits(produits)
        return redirect(url_for("admin_produits"))

    return render_template(
        "admin/formulaire_produit.html", produit=produit_cible, categories=CATEGORIES, publics_options=PUBLICS,
        sous_categories=SOUS_CATEGORIES,
    )


@app.route("/admin/produits/<int:produit_id>/supprimer", methods=["POST"])
@admin_requis
def admin_supprimer_produit(produit_id):
    produits = [p for p in charger_produits() if p["id"] != produit_id]
    sauvegarder_produits(produits)
    return redirect(url_for("admin_produits"))


@app.route("/admin/produits/<int:produit_id>/reapprovisionner", methods=["POST"])
@admin_requis
def admin_reapprovisionner_produit(produit_id):
    produits = charger_produits()
    produit_cible = next((p for p in produits if p["id"] == produit_id), None)
    if not produit_cible:
        abort(404)
    try:
        quantite_ajoutee = max(0, int(request.form.get("quantite_ajoutee", 0) or 0))
    except ValueError:
        quantite_ajoutee = 0
    produit_cible["stock"] = produit_cible.get("stock", 0) + quantite_ajoutee
    sauvegarder_produits(produits)
    journaliser("stock", f"Réapprovisionnement produit {produit_id} (+{quantite_ajoutee})")

    destination = request.referrer
    if destination and destination.startswith(request.host_url):
        return redirect(destination)
    return redirect(url_for("admin_produits"))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
