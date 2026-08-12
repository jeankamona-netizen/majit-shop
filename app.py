import os
import json
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, abort, request, redirect, url_for, session
from markupsafe import Markup, escape
from werkzeug.security import generate_password_hash, check_password_hash

from db import obtenir_connexion

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-majt-shop-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 Mo max par photo

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
# (ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE). Valeurs par défaut pour le développement local uniquement.
ADMIN_UTILISATEUR = os.environ.get("ADMIN_UTILISATEUR", "admin")
ADMIN_MOT_DE_PASSE_HASH = generate_password_hash(os.environ.get("ADMIN_MOT_DE_PASSE", "MajtAdmin2026!"))

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


def sauvegarder_produits(produits):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM produits")
            for p in produits:
                cur.execute(
                    """
                    INSERT INTO produits (id, nom, categorie, sous_categorie, prix, reduction, image, images,
                        description, tailles, couleurs, variantes, stock, public, vues)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        p["id"], p["nom"], p["categorie"], p.get("sous_categorie") or None,
                        p.get("prix", 0), p.get("reduction", 0),
                        p.get("image", "placeholder.jpg"), json.dumps(p.get("images", []), ensure_ascii=False),
                        p.get("description", ""), json.dumps(p.get("tailles", []), ensure_ascii=False),
                        json.dumps(p.get("couleurs", []), ensure_ascii=False),
                        json.dumps(p.get("variantes", {}), ensure_ascii=False) if p.get("variantes") else None,
                        p.get("stock", 0), p.get("public", "unisexe"), p.get("vues", 0),
                    ),
                )
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


def sauvegarder_commandes(commandes):
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM commandes")
            for c in commandes:
                cur.execute(
                    """
                    INSERT INTO commandes (numero, date, nom, telephone, adresse, latitude, longitude, lignes,
                        total, statut, montant_verse, date_livraison, vue, livreur_numero, livreur_nom)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        c["numero"], c["date"], c["nom"], c["telephone"], c["adresse"],
                        c.get("latitude"), c.get("longitude"), json.dumps(c.get("lignes", []), ensure_ascii=False),
                        c.get("total", 0), c.get("statut", "en_attente"), c.get("montant_verse"),
                        c.get("date_livraison"), int(bool(c.get("vue", True))), c.get("livreur_numero"),
                        c.get("livreur_nom"),
                    ),
                )
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


def prix_final(produit):
    reduction = produit.get("reduction", 0) or 0
    if reduction:
        return round(produit["prix"] * (1 - reduction / 100))
    return produit["prix"]


def extension_autorisee(nom_fichier):
    return "." in nom_fichier and nom_fichier.rsplit(".", 1)[1].lower() in EXTENSIONS_AUTORISEES


def enregistrer_photos_produit(fichiers, produit_id):
    valides = [f for f in fichiers if f and f.filename and extension_autorisee(f.filename)]
    if not valides:
        return None, None

    principal = valides[0]
    extension = principal.filename.rsplit(".", 1)[1].lower()
    nom_image = f"produit-{produit_id}.{extension}"
    principal.save(IMAGES_DIR / nom_image)

    images = []
    for i, fichier in enumerate(valides[1:4], start=2):
        extension = fichier.filename.rsplit(".", 1)[1].lower()
        nom_fichier = f"produit-{produit_id}-{i}.{extension}"
        fichier.save(IMAGES_DIR / nom_fichier)
        images.append(nom_fichier)

    return nom_image, images


def admin_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_connecte"):
            return redirect(url_for("connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def livreur_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (session.get("admin_connecte") or session.get("livreur_numero")):
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


def marquer_commande_livree(commande, montant_form):
    if commande["statut"] == "annulee":
        return False
    deja_solde = commande["statut"] == "livree" and (commande.get("montant_verse") or 0) >= commande["total"]
    if deja_solde:
        return False
    try:
        montant = float(montant_form or commande["total"])
    except ValueError:
        montant = commande["total"]
    commande["statut"] = "livree"
    commande["montant_verse"] = montant
    if not commande.get("date_livraison"):
        commande["date_livraison"] = datetime.now().isoformat(timespec="seconds")
    return True


def annuler_commande(commande):
    if commande["statut"] not in ("en_attente", "en_livraison"):
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


@app.context_processor
def injecter_globals():
    panier = session.get("panier", {})
    admin_connecte = session.get("admin_connecte", False)
    nouvelles_commandes = []
    if admin_connecte:
        nouvelles_commandes = [c for c in charger_commandes() if not c.get("vue", True)]
        nouvelles_commandes.sort(key=lambda c: c["date"], reverse=True)
    return {
        "nombre_panier": sum(panier.values()),
        "admin_connecte": admin_connecte,
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

    return render_template(
        "categorie.html",
        produits=produits,
        categories=CATEGORIES,
        categorie_active=slug,
        nom_categorie=CATEGORIES[slug],
        publics=publics,
        public_filtre=public_filtre,
        public_labels=PUBLICS,
        sous_categories_options=sous_categories_options,
        sous_categories_presentes=sous_categories_presentes,
        sous_categorie_filtre=sous_categorie_filtre,
    )


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
    return render_template(
        "categorie.html",
        produits=produits,
        categories=CATEGORIES,
        categorie_active=None,
        nom_categorie=f"Résultats pour « {q} »" if q else "Recherche",
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
        adresse = request.form.get("adresse", "").strip()

        if not nom:
            erreurs["nom"] = "Merci d'indiquer votre nom."
        if not telephone:
            erreurs["telephone"] = "Merci d'indiquer un numéro de téléphone."
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
            try:
                latitude = float(request.form.get("latitude") or "")
                longitude = float(request.form.get("longitude") or "")
            except ValueError:
                latitude = longitude = None

            numero = generer_numero_commande()
            commande = {
                "numero": numero,
                "date": datetime.now().isoformat(timespec="seconds"),
                "nom": nom,
                "telephone": telephone,
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
                "total": total,
                "statut": "en_attente",
                "montant_verse": None,
                "date_livraison": None,
                "vue": False,
            }

            commandes = charger_commandes()
            commandes.append(commande)
            sauvegarder_commandes(commandes)

            produits = charger_produits()
            for ligne in lignes:
                p = next((x for x in produits if x["id"] == ligne["produit"]["id"]), None)
                if p:
                    ajuster_stock_variante(p, ligne["couleur"], ligne["taille"], -ligne["quantite"])
            sauvegarder_produits(produits)

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
    )


def etape_suivi(statut):
    if statut == "livree":
        return 4
    if statut == "en_livraison":
        return 3
    return 1


@app.route("/commande/confirmation")
def confirmation_commande():
    commande = session.pop("derniere_commande", None)
    if not commande:
        return redirect(url_for("accueil"))
    return render_template(
        "confirmation.html", commande=commande, categories=CATEGORIES, initial_etape=etape_suivi(commande["statut"])
    )


@app.route("/suivi/<numero>")
def suivi_commande(numero):
    commande = next((c for c in charger_commandes() if c["numero"] == numero), None)
    if not commande:
        abort(404)
    return render_template(
        "suivi.html", commande=commande, categories=CATEGORIES, initial_etape=etape_suivi(commande["statut"])
    )


@app.route("/suivi/<numero>/etat")
def suivi_commande_etat(numero):
    commande = next((c for c in charger_commandes() if c["numero"] == numero), None)
    if not commande:
        abort(404)
    return {
        "statut": commande["statut"],
        "etape": etape_suivi(commande["statut"]),
        "livreur_nom": commande.get("livreur_nom"),
        "date_livraison": commande.get("date_livraison"),
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

    try:
        note_articles = max(1, min(5, int(request.form.get("note_articles", 0))))
        note_procedure = max(1, min(5, int(request.form.get("note_procedure", 0))))
    except ValueError:
        abort(400)

    ajouter_avis({
        "numero": numero,
        "date": datetime.now().isoformat(timespec="seconds"),
        "note_articles": note_articles,
        "note_procedure": note_procedure,
        "commentaire": request.form.get("commentaire", "").strip(),
    })
    return ("", 204)


# --- Administration ---

@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    erreur = None
    if request.method == "POST":
        identifiant = request.form.get("identifiant", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")

        if identifiant == ADMIN_UTILISATEUR and check_password_hash(ADMIN_MOT_DE_PASSE_HASH, mot_de_passe):
            session.pop("livreur_numero", None)
            session["admin_connecte"] = True
            suivant = request.args.get("suivant") or ""
            if not suivant.startswith("/admin"):
                suivant = ""
            return redirect(suivant or url_for("admin_tableau_de_bord"))

        livreur_trouve = next((l for l in charger_livreurs() if l["numero"] == identifiant.upper()), None)
        if livreur_trouve and livreur_trouve.get("actif", True) and check_password_hash(livreur_trouve["mot_de_passe_hash"], mot_de_passe):
            session.pop("admin_connecte", None)
            session["livreur_numero"] = livreur_trouve["numero"]
            suivant = request.args.get("suivant") or ""
            if not suivant.startswith("/livreur"):
                suivant = ""
            return redirect(suivant or url_for("livreur"))

        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("connexion.html", erreur=erreur)


@app.route("/admin/connexion")
def admin_connexion():
    return redirect(url_for("connexion", suivant=request.args.get("suivant")))


@app.route("/admin/deconnexion")
def admin_deconnexion():
    session.pop("admin_connecte", None)
    return redirect(url_for("connexion"))


@app.route("/admin")
@admin_requis
def admin_tableau_de_bord():
    produits = charger_produits()
    commandes = charger_commandes()
    visites = charger_visites()

    aujourd_hui = date.today().isoformat()
    commandes_en_attente = [c for c in commandes if c["statut"] == "en_attente"]
    commandes_en_livraison = [c for c in commandes if c["statut"] == "en_livraison"]
    commandes_livrees = [c for c in commandes if c["statut"] == "livree"]
    commandes_livrees_en_ligne = [c for c in commandes_livrees if not c["numero"].startswith("FAC")]
    chiffre_affaires_en_ligne = sum(c.get("montant_verse") or 0 for c in commandes_livrees_en_ligne)
    chiffre_affaires_boutique = sum(
        c.get("montant_verse") or 0 for c in commandes_livrees if c["numero"].startswith("FAC")
    )

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

    return render_template(
        "admin/tableau_de_bord.html",
        categories=CATEGORIES,
        visiteurs_jour=sum(1 for v in visites if v.get("date") == aujourd_hui),
        nb_commandes_attente=len(commandes_en_attente),
        nb_commandes_en_livraison=len(commandes_en_livraison),
        nb_commandes_livrees=len(commandes_livrees_en_ligne),
        chiffre_affaires_en_ligne=chiffre_affaires_en_ligne,
        chiffre_affaires_boutique=chiffre_affaires_boutique,
        nb_produits=len(produits),
        nb_rupture=len([p for p in produits if p.get("stock", 0) <= 0]),
        livreurs_en_mission=livreurs_en_mission,
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

    facture = {
        "numero": numero,
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
        "montant_verse": total,
        "date_livraison": maintenant,
        "vue": True,
    }

    commandes = charger_commandes()
    commandes.append(facture)
    sauvegarder_commandes(commandes)

    produits = charger_produits()
    for ligne in lignes:
        p = next((x for x in produits if x["id"] == ligne["produit"]["id"]), None)
        if p:
            ajuster_stock_variante(p, ligne["couleur"], ligne["taille"], -ligne["quantite"])
    sauvegarder_produits(produits)

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
    elif statut_filtre in ("en_attente", "en_livraison", "annulee"):
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
    moi = livreur_courant()
    commandes = charger_commandes()
    for c in commandes:
        for ligne in c["lignes"]:
            if ligne.get("prix_unitaire") is None and ligne.get("quantite"):
                ligne["prix_unitaire"] = round(ligne["sous_total"] / ligne["quantite"])
    disponibles = sorted((c for c in commandes if c["statut"] == "en_attente"), key=lambda c: c["date"])
    if moi:
        en_cours = [c for c in commandes if c["statut"] == "en_livraison" and c.get("livreur_numero") == moi["numero"]]
    else:
        en_cours = [c for c in commandes if c["statut"] == "en_livraison"]
    en_cours.sort(key=lambda c: c["date"])
    return render_template("livreur.html", categories=CATEGORIES, disponibles=disponibles, en_cours=en_cours, moi=moi)


@app.route("/livreur/profil")
@livreur_seul_requis
def livreur_profil():
    return render_template("livreur_profil.html", moi=livreur_courant(), sexes=SEXES)


@app.route("/livreur/commandes/<numero>/prendre", methods=["POST"])
@livreur_seul_requis
def livreur_prendre_commande(numero):
    moi = livreur_courant()
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if commande["statut"] == "en_attente":
        commande["statut"] = "en_livraison"
        commande["livreur_numero"] = moi["numero"]
        commande["livreur_nom"] = f"{moi['prenom']} {moi['nom']}"
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/livrer", methods=["POST"])
@livreur_seul_requis
def livreur_livrer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if marquer_commande_livree(commande, request.form.get("montant_verse")):
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/annuler", methods=["POST"])
@livreur_seul_requis
def livreur_annuler_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if annuler_commande(commande):
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/lignes/<int:index>/modifier", methods=["POST"])
@livreur_seul_requis
def livreur_modifier_ligne_commande(numero, index):
    moi = livreur_courant()
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
    return render_template("admin/livreurs.html", categories=CATEGORIES, livreurs=livreurs, sexes=SEXES)


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
    return redirect(url_for("admin_livreurs"))


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


@app.route("/admin/commandes/<numero>/livrer", methods=["POST"])
@admin_requis
def admin_livrer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if marquer_commande_livree(commande, request.form.get("montant_verse")):
        sauvegarder_commandes(commandes)
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
    if commande["statut"] in ("en_attente", "en_livraison"):
        if modifier_quantite_ligne(commande, index, request.form.get("quantite")):
            sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


@app.route("/admin/migrations/ajouter-colonne-vues", methods=["POST"])
@admin_requis
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
@admin_requis
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
@admin_requis
def admin_migration_vider_cache_geoloc():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            cur.execute("DELETE FROM geoloc_cache")
    finally:
        connexion.close()
    return {"statut": "cache vide"}


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

    destination = request.referrer
    if destination and destination.startswith(request.host_url):
        return redirect(destination)
    return redirect(url_for("admin_produits"))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
