import os
import json
import unicodedata
import urllib.request
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, abort, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-majt-shop-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 Mo max par photo

DATA_FILE = Path(__file__).parent / "data" / "produits.json"
COMMANDES_FILE = Path(__file__).parent / "data" / "commandes.json"
VISITES_FILE = Path(__file__).parent / "data" / "visites.json"
GEOLOC_CACHE_FILE = Path(__file__).parent / "data" / "geoloc_cache.json"
AVIS_FILE = Path(__file__).parent / "data" / "avis.json"
IMAGES_DIR = Path(__file__).parent / "static" / "images"
EXTENSIONS_AUTORISEES = {"png", "jpg", "jpeg", "webp", "gif"}

CATEGORIES = {
    "vetements": "Vêtements",
    "chaussures": "Chaussures",
    "sacs": "Sacs",
    "telephones": "Électroniques",
    "accessoires": "Accessoires",
    "automobiles": "Automobiles",
    "jouets": "Jouets",
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
    "article": "Article",
    "categorie": "Catégorie",
}

MOTS_VIDES = {"le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "et", "ou", "pour", "avec", "en", "au", "aux"}

# Identifiants administrateur : configurables via variables d'environnement
# (ADMIN_UTILISATEUR, ADMIN_MOT_DE_PASSE). Valeurs par défaut pour le développement local uniquement.
ADMIN_UTILISATEUR = os.environ.get("ADMIN_UTILISATEUR", "admin")
ADMIN_MOT_DE_PASSE_HASH = generate_password_hash(os.environ.get("ADMIN_MOT_DE_PASSE", "MajtAdmin2026!"))

# Identifiants livreur : compte distinct de l'administrateur, configurable via
# variables d'environnement (LIVREUR_UTILISATEUR, LIVREUR_MOT_DE_PASSE).
LIVREUR_UTILISATEUR = os.environ.get("LIVREUR_UTILISATEUR", "livreur")
LIVREUR_MOT_DE_PASSE_HASH = generate_password_hash(os.environ.get("LIVREUR_MOT_DE_PASSE", "MajtLivreur2026!"))


def charger_produits():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_produits(produits):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(produits, f, ensure_ascii=False, indent=2)


def charger_commandes():
    if COMMANDES_FILE.exists():
        with open(COMMANDES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def sauvegarder_commandes(commandes):
    with open(COMMANDES_FILE, "w", encoding="utf-8") as f:
        json.dump(commandes, f, ensure_ascii=False, indent=2)


def generer_numero_commande():
    prefixe = f"MJT{date.today().strftime('%y%m%d')}"
    commandes_du_jour = [c for c in charger_commandes() if c["numero"].startswith(prefixe)]
    return f"{prefixe}{len(commandes_du_jour) + 1}"


def construire_lignes_ventes():
    produits_par_id = {p["id"]: p for p in charger_produits()}
    lignes_ventes = []
    for c in charger_commandes():
        if c["statut"] != "livree":
            continue
        jour = (c.get("date_livraison") or c["date"])[:10]
        annee, semaine, _ = date.fromisoformat(jour).isocalendar()
        for ligne in c["lignes"]:
            p = produits_par_id.get(ligne.get("produit_id"))
            categorie_nom = CATEGORIES.get(p["categorie"], "Autre") if p else "Autre"
            lignes_ventes.append({
                "date": jour,
                "semaine": f"{annee} - semaine {semaine:02d}",
                "article": ligne["nom"],
                "categorie": categorie_nom,
                "commande": c["numero"],
                "quantite": ligne["quantite"],
                "montant": ligne["sous_total"],
            })
    return lignes_ventes


def charger_visites():
    if VISITES_FILE.exists():
        with open(VISITES_FILE, encoding="utf-8") as f:
            donnees = json.load(f)
            return donnees if isinstance(donnees, list) else []
    return []


def sauvegarder_visites(visites):
    with open(VISITES_FILE, "w", encoding="utf-8") as f:
        json.dump(visites, f, ensure_ascii=False, indent=2)


def charger_avis():
    if AVIS_FILE.exists():
        with open(AVIS_FILE, encoding="utf-8") as f:
            donnees = json.load(f)
            return donnees if isinstance(donnees, list) else []
    return []


def sauvegarder_avis(avis):
    with open(AVIS_FILE, "w", encoding="utf-8") as f:
        json.dump(avis, f, ensure_ascii=False, indent=2)


def obtenir_ip_client():
    transmise = request.headers.get("X-Forwarded-For", "")
    if transmise:
        return transmise.split(",")[0].strip()
    return request.remote_addr or ""


def charger_cache_geoloc():
    if GEOLOC_CACHE_FILE.exists():
        with open(GEOLOC_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_cache_geoloc(cache):
    with open(GEOLOC_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


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
            parties = [v for v in (resultat.get("city"), resultat.get("country")) if v]
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


def prix_final(produit):
    reduction = produit.get("reduction", 0) or 0
    if reduction:
        return round(produit["prix"] * (1 - reduction / 100))
    return produit["prix"]


def extension_autorisee(nom_fichier):
    return "." in nom_fichier and nom_fichier.rsplit(".", 1)[1].lower() in EXTENSIONS_AUTORISEES


def enregistrer_photos_supplementaires(fichiers, produit_id):
    noms = []
    for i, fichier in enumerate(fichiers[:3], start=2):
        if fichier and fichier.filename and extension_autorisee(fichier.filename):
            extension = fichier.filename.rsplit(".", 1)[1].lower()
            nom_fichier = f"produit-{produit_id}-{i}.{extension}"
            fichier.save(IMAGES_DIR / nom_fichier)
            noms.append(nom_fichier)
    return noms


def admin_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_connecte"):
            return redirect(url_for("admin_connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


def livreur_requis(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (session.get("admin_connecte") or session.get("livreur_connecte")):
            return redirect(url_for("livreur_connexion", suivant=request.path))
        return f(*args, **kwargs)
    return wrapper


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
            p["stock"] = p.get("stock", 0) + ligne["quantite"]
    sauvegarder_produits(produits)
    commande["statut"] = "annulee"
    commande["montant_verse"] = None
    return True


@app.template_filter("cdf")
def formater_cdf(valeur):
    return f"{round(valeur):,}".replace(",", " ") + " CDF"


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
        "livreur_connecte": session.get("livreur_connecte", False),
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
        visites = charger_visites()
        visites.append({
            "date": aujourd_hui,
            "heure": datetime.now().strftime("%H:%M:%S"),
            "ip": obtenir_ip_client(),
        })
        sauvegarder_visites(visites)


# --- Boutique ---

@app.route("/")
def accueil():
    tous_produits = [p for p in charger_produits() if p.get("stock", 0) > 0]
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
    produits = [p for p in charger_produits() if p["categorie"] == slug and p.get("stock", 0) > 0]
    publics = publics_presents_tries(produits)
    public_filtre = request.args.get("public", "")
    if public_filtre in PUBLICS:
        produits = [p for p in produits if p.get("public", "unisexe") == public_filtre]
    return render_template(
        "categorie.html",
        produits=produits,
        categories=CATEGORIES,
        categorie_active=slug,
        nom_categorie=CATEGORIES[slug],
        publics=publics,
        public_filtre=public_filtre,
        public_labels=PUBLICS,
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
    galerie = [p["image"]] + [img for img in p.get("images", []) if img != p["image"]]
    galerie = galerie[:4]
    return render_template("produit.html", produit=p, categories=CATEGORIES, galerie=galerie)


@app.route("/panier")
def panier():
    lignes, total = obtenir_lignes_panier()
    return render_template("panier.html", lignes=lignes, total=total, categories=CATEGORIES)


@app.route("/panier/ajouter/<int:produit_id>", methods=["POST"])
def ajouter_au_panier(produit_id):
    produit_cible = trouver_produit(produit_id)
    if not produit_cible:
        abort(404)
    try:
        quantite = max(1, int(request.form.get("quantite", 1)))
    except ValueError:
        quantite = 1

    stock_disponible = produit_cible.get("stock", 0)
    if stock_disponible <= 0:
        return redirect(url_for("produit", produit_id=produit_id))
    quantite = min(quantite, stock_disponible)

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

    panier_session = session.get("panier", {})
    cle = f"{produit_id}|{taille}|{couleur}"
    panier_session[cle] = panier_session.get(cle, 0) + quantite
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
                    p["stock"] = max(0, p.get("stock", 0) - ligne["quantite"])
            sauvegarder_produits(produits)

            session["derniere_commande"] = commande
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


@app.route("/commande/confirmation")
def confirmation_commande():
    commande = session.pop("derniere_commande", None)
    if not commande:
        return redirect(url_for("accueil"))
    return render_template("confirmation.html", commande=commande, categories=CATEGORIES)


@app.route("/guide/commande")
def guide_commande():
    return render_template("guide_commande.html", categories=CATEGORIES)


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

    avis = charger_avis()
    avis.append({
        "numero": numero,
        "date": datetime.now().isoformat(timespec="seconds"),
        "note_articles": note_articles,
        "note_procedure": note_procedure,
        "commentaire": request.form.get("commentaire", "").strip(),
    })
    sauvegarder_avis(avis)
    return ("", 204)


# --- Administration ---

@app.route("/admin/connexion", methods=["GET", "POST"])
def admin_connexion():
    erreur = None
    if request.method == "POST":
        utilisateur = request.form.get("utilisateur", "")
        mot_de_passe = request.form.get("mot_de_passe", "")
        if utilisateur == ADMIN_UTILISATEUR and check_password_hash(ADMIN_MOT_DE_PASSE_HASH, mot_de_passe):
            session["admin_connecte"] = True
            suivant = request.args.get("suivant") or url_for("admin_tableau_de_bord")
            return redirect(suivant)
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("admin/connexion.html", erreur=erreur, categories=CATEGORIES)


@app.route("/admin/deconnexion")
def admin_deconnexion():
    session.pop("admin_connecte", None)
    return redirect(url_for("admin_connexion"))


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
    chiffre_affaires = sum(c.get("montant_verse") or 0 for c in commandes_livrees)

    return render_template(
        "admin/tableau_de_bord.html",
        categories=CATEGORIES,
        visiteurs_jour=sum(1 for v in visites if v.get("date") == aujourd_hui),
        nb_commandes_attente=len(commandes_en_attente),
        nb_commandes_en_livraison=len(commandes_en_livraison),
        nb_commandes_livrees=len(commandes_livrees),
        chiffre_affaires=chiffre_affaires,
        nb_produits=len(produits),
        nb_rupture=len([p for p in produits if p.get("stock", 0) <= 0]),
    )


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
    if statut_filtre in ("en_attente", "en_livraison", "livree", "annulee"):
        commandes = [c for c in commandes if c["statut"] == statut_filtre]
    commandes = sorted(commandes, key=lambda c: c["date"], reverse=True)
    return render_template(
        "admin/commandes.html",
        commandes=commandes,
        categories=CATEGORIES,
        statut_filtre=statut_filtre,
    )


@app.route("/livreur/connexion", methods=["GET", "POST"])
def livreur_connexion():
    erreur = None
    if request.method == "POST":
        utilisateur = request.form.get("utilisateur", "")
        mot_de_passe = request.form.get("mot_de_passe", "")
        if utilisateur == LIVREUR_UTILISATEUR and check_password_hash(LIVREUR_MOT_DE_PASSE_HASH, mot_de_passe):
            session["livreur_connecte"] = True
            suivant = request.args.get("suivant") or url_for("livreur")
            return redirect(suivant)
        erreur = "Identifiant ou mot de passe incorrect."
    return render_template("livreur_connexion.html", erreur=erreur)


@app.route("/livreur/deconnexion")
def livreur_deconnexion():
    session.pop("livreur_connecte", None)
    return redirect(url_for("livreur_connexion"))


@app.route("/livreur")
@livreur_requis
def livreur():
    commandes = charger_commandes()
    for c in commandes:
        for ligne in c["lignes"]:
            if ligne.get("prix_unitaire") is None and ligne.get("quantite"):
                ligne["prix_unitaire"] = round(ligne["sous_total"] / ligne["quantite"])
    disponibles = sorted((c for c in commandes if c["statut"] == "en_attente"), key=lambda c: c["date"])
    en_cours = sorted((c for c in commandes if c["statut"] == "en_livraison"), key=lambda c: c["date"])
    return render_template("livreur.html", categories=CATEGORIES, disponibles=disponibles, en_cours=en_cours)


@app.route("/livreur/commandes/<numero>/prendre", methods=["POST"])
@livreur_requis
def livreur_prendre_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if commande["statut"] == "en_attente":
        commande["statut"] = "en_livraison"
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/livrer", methods=["POST"])
@livreur_requis
def livreur_livrer_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if marquer_commande_livree(commande, request.form.get("montant_verse")):
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/livreur/commandes/<numero>/annuler", methods=["POST"])
@livreur_requis
def livreur_annuler_commande(numero):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande:
        abort(404)
    if annuler_commande(commande):
        sauvegarder_commandes(commandes)
    return redirect(url_for("livreur"))


@app.route("/admin/revenus")
@admin_requis
def admin_revenus():
    lignes = construire_lignes_ventes()
    total = sum(l["montant"] for l in lignes)

    type_filtre = request.args.get("type", "")
    valeur_filtre = request.args.get("valeur", "")

    valeurs_disponibles = []
    resultats = []
    sous_total = 0

    if type_filtre in FILTRES_REVENUS:
        valeurs_disponibles = sorted({l[type_filtre] for l in lignes}, reverse=(type_filtre in ("date", "semaine")))
        if valeur_filtre:
            resultats = [l for l in lignes if l[type_filtre] == valeur_filtre]
            sous_total = sum(l["montant"] for l in resultats)

    return render_template(
        "admin/revenus.html",
        categories=CATEGORIES,
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
    visites = sorted(charger_visites(), key=lambda v: (v.get("date", ""), v.get("heure", "")), reverse=True)
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


@app.route("/admin/commandes/<numero>/lignes/<int:index>/modifier", methods=["POST"])
@admin_requis
def admin_modifier_ligne_commande(numero, index):
    commandes = charger_commandes()
    commande = next((c for c in commandes if c["numero"] == numero), None)
    if not commande or index < 0 or index >= len(commande["lignes"]):
        abort(404)
    if commande["statut"] != "en_attente":
        return redirect(url_for("admin_commandes"))

    ligne = commande["lignes"][index]
    try:
        nouvelle_quantite = max(0, int(request.form.get("quantite", ligne["quantite"])))
    except ValueError:
        nouvelle_quantite = ligne["quantite"]
    nouvelle_quantite = min(nouvelle_quantite, ligne["quantite"])

    delta = ligne["quantite"] - nouvelle_quantite
    if delta > 0:
        produits = charger_produits()
        p = next((x for x in produits if x["id"] == ligne.get("produit_id")), None)
        if p:
            p["stock"] = p.get("stock", 0) + delta
            sauvegarder_produits(produits)

    prix_unitaire = ligne.get("prix_unitaire") or (round(ligne["sous_total"] / ligne["quantite"]) if ligne["quantite"] else 0)
    if nouvelle_quantite == 0:
        commande["lignes"].pop(index)
    else:
        ligne["quantite"] = nouvelle_quantite
        ligne["prix_unitaire"] = prix_unitaire
        ligne["sous_total"] = prix_unitaire * nouvelle_quantite

    commande["total"] = sum(l["sous_total"] for l in commande["lignes"])
    sauvegarder_commandes(commandes)
    return redirect(url_for("admin_commandes"))


@app.route("/admin/produits/ajouter", methods=["GET", "POST"])
@admin_requis
def admin_ajouter_produit():
    if request.method == "POST":
        produits = charger_produits()
        nouvel_id = max((p["id"] for p in produits), default=0) + 1
        nom_image = "placeholder.jpg"
        fichier = request.files.get("photo")
        if fichier and fichier.filename and extension_autorisee(fichier.filename):
            extension = fichier.filename.rsplit(".", 1)[1].lower()
            nom_image = f"produit-{nouvel_id}.{extension}"
            fichier.save(IMAGES_DIR / nom_image)

        try:
            reduction = max(0, min(90, int(request.form.get("reduction", 0) or 0)))
        except ValueError:
            reduction = 0

        try:
            stock = max(0, int(request.form.get("stock", 0) or 0))
        except ValueError:
            stock = 0

        photos_supplementaires = enregistrer_photos_supplementaires(
            request.files.getlist("photos_supplementaires"), nouvel_id
        )

        nouveau_produit = {
            "id": nouvel_id,
            "nom": request.form.get("nom", "").strip(),
            "categorie": request.form.get("categorie"),
            "prix": float(request.form.get("prix", 0) or 0),
            "reduction": reduction,
            "public": request.form.get("public") if request.form.get("public") in PUBLICS else "unisexe",
            "stock": stock,
            "image": nom_image,
            "images": photos_supplementaires,
            "description": request.form.get("description", "").strip(),
            "couleurs": parser_liste(request.form.get("couleurs", "")),
            "tailles": parser_liste(request.form.get("tailles", "")),
        }
        produits.append(nouveau_produit)
        sauvegarder_produits(produits)
        return redirect(url_for("admin_produits"))

    return render_template("admin/formulaire_produit.html", produit=None, categories=CATEGORIES, publics_options=PUBLICS)


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

        fichier = request.files.get("photo")
        if fichier and fichier.filename and extension_autorisee(fichier.filename):
            extension = fichier.filename.rsplit(".", 1)[1].lower()
            nom_image = f"produit-{produit_id}.{extension}"
            fichier.save(IMAGES_DIR / nom_image)
            produit_cible["image"] = nom_image

        photos_supplementaires = enregistrer_photos_supplementaires(
            request.files.getlist("photos_supplementaires"), produit_id
        )
        if photos_supplementaires:
            produit_cible["images"] = photos_supplementaires

        sauvegarder_produits(produits)
        return redirect(url_for("admin_produits"))

    return render_template("admin/formulaire_produit.html", produit=produit_cible, categories=CATEGORIES, publics_options=PUBLICS)


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
