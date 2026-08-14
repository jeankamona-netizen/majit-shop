import os

import pymysql
import pymysql.cursors

# FLASK_ENV=development est le seul moyen d'autoriser une valeur de secours
# pour le mot de passe MySQL. Par défaut, l'absence de MYSQL_MOT_DE_PASSE
# empêche l'application de démarrer (voir exiger_secret() dans app.py pour
# la même règle appliquée à SECRET_KEY et ADMIN_MOT_DE_PASSE).
_EST_DEV = os.environ.get("FLASK_ENV", "").strip().lower() == "development"


def _exiger_secret(nom_variable, valeur_dev):
    valeur = os.environ.get(nom_variable)
    if valeur:
        return valeur
    if _EST_DEV:
        return valeur_dev
    raise RuntimeError(
        f"{nom_variable} doit être définie via une variable d'environnement pour démarrer "
        "l'application. En local, définissez FLASK_ENV=development pour utiliser une valeur "
        "de secours de développement."
    )


MYSQL_HOTE = os.environ.get("MYSQL_HOTE", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_UTILISATEUR = os.environ.get("MYSQL_UTILISATEUR", "majtshop")
MYSQL_MOT_DE_PASSE = _exiger_secret("MYSQL_MOT_DE_PASSE", "MajtShop2026!")
MYSQL_BASE = os.environ.get("MYSQL_BASE", "majt_shop")


def obtenir_connexion():
    return pymysql.connect(
        host=MYSQL_HOTE,
        port=MYSQL_PORT,
        user=MYSQL_UTILISATEUR,
        password=MYSQL_MOT_DE_PASSE,
        database=MYSQL_BASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
