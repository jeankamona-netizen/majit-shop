import json
from pathlib import Path

from db import obtenir_connexion

DATA_DIR = Path(__file__).parent / "data"


def charger_json(nom_fichier, defaut):
    chemin = DATA_DIR / nom_fichier
    if not chemin.exists():
        return defaut
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def migrer_livreurs(cur):
    livreurs = charger_json("livreurs.json", [])
    for l in livreurs:
        cur.execute(
            """
            INSERT INTO livreurs (numero, nom, prenom, sexe, adresse, telephone, mot_de_passe_hash, actif, date_creation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE nom=VALUES(nom), prenom=VALUES(prenom), sexe=VALUES(sexe),
                adresse=VALUES(adresse), telephone=VALUES(telephone),
                mot_de_passe_hash=VALUES(mot_de_passe_hash), actif=VALUES(actif)
            """,
            (
                l["numero"], l["nom"], l["prenom"], l.get("sexe", "homme"), l.get("adresse", ""),
                l.get("telephone", ""), l["mot_de_passe_hash"], int(l.get("actif", True)), l["date_creation"],
            ),
        )
    print(f"{len(livreurs)} livreur(s) migré(s).")


def migrer_produits(cur):
    produits = charger_json("produits.json", [])
    for p in produits:
        cur.execute(
            """
            INSERT INTO produits (id, nom, categorie, prix, reduction, image, images, description, tailles, couleurs, stock, public)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE nom=VALUES(nom), categorie=VALUES(categorie), prix=VALUES(prix),
                reduction=VALUES(reduction), image=VALUES(image), images=VALUES(images),
                description=VALUES(description), tailles=VALUES(tailles), couleurs=VALUES(couleurs),
                stock=VALUES(stock), public=VALUES(public)
            """,
            (
                p["id"], p["nom"], p["categorie"], p.get("prix", 0), p.get("reduction", 0),
                p.get("image", "placeholder.jpg"), json.dumps(p.get("images", []), ensure_ascii=False),
                p.get("description", ""), json.dumps(p.get("tailles", []), ensure_ascii=False),
                json.dumps(p.get("couleurs", []), ensure_ascii=False), p.get("stock", 0),
                p.get("public", "unisexe"),
            ),
        )
    print(f"{len(produits)} produit(s) migré(s).")


def migrer_commandes(cur):
    commandes = charger_json("commandes.json", [])
    for c in commandes:
        cur.execute(
            """
            INSERT INTO commandes (numero, date, nom, telephone, adresse, latitude, longitude, lignes, total,
                statut, montant_verse, date_livraison, vue, livreur_numero, livreur_nom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE statut=VALUES(statut), montant_verse=VALUES(montant_verse),
                date_livraison=VALUES(date_livraison), vue=VALUES(vue),
                livreur_numero=VALUES(livreur_numero), livreur_nom=VALUES(livreur_nom)
            """,
            (
                c["numero"], c["date"], c["nom"], c["telephone"], c["adresse"],
                c.get("latitude"), c.get("longitude"), json.dumps(c.get("lignes", []), ensure_ascii=False),
                c.get("total", 0), c.get("statut", "en_attente"), c.get("montant_verse"),
                c.get("date_livraison"), int(c.get("vue", True)), c.get("livreur_numero"), c.get("livreur_nom"),
            ),
        )
    print(f"{len(commandes)} commande(s) migrée(s).")


def migrer_avis(cur):
    avis = charger_json("avis.json", [])
    for a in avis:
        cur.execute(
            """
            INSERT INTO avis (numero, date, note_articles, note_procedure, commentaire)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (a["numero"], a["date"], a["note_articles"], a["note_procedure"], a.get("commentaire", "")),
        )
    print(f"{len(avis)} avis migré(s).")


def migrer_visites(cur):
    visites = charger_json("visites.json", [])
    for v in visites:
        cur.execute(
            "INSERT INTO visites (date, heure, ip) VALUES (%s, %s, %s)",
            (v["date"], v["heure"], v.get("ip", "")),
        )
    print(f"{len(visites)} visite(s) migrée(s).")


def migrer_geoloc_cache(cur):
    cache = charger_json("geoloc_cache.json", {})
    for ip, localisation in cache.items():
        cur.execute(
            """
            INSERT INTO geoloc_cache (ip, localisation) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE localisation=VALUES(localisation)
            """,
            (ip, localisation),
        )
    print(f"{len(cache)} entrée(s) de géolocalisation migrée(s).")


def main():
    connexion = obtenir_connexion()
    try:
        with connexion.cursor() as cur:
            # Ordre important : livreurs avant commandes (clé étrangère)
            migrer_livreurs(cur)
            migrer_produits(cur)
            migrer_commandes(cur)
            migrer_avis(cur)
            migrer_visites(cur)
            migrer_geoloc_cache(cur)
    finally:
        connexion.close()
    print("Migration terminée.")


if __name__ == "__main__":
    main()
