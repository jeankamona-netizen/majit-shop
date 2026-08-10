import os

import pymysql
import pymysql.cursors

MYSQL_HOTE = os.environ.get("MYSQL_HOTE", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_UTILISATEUR = os.environ.get("MYSQL_UTILISATEUR", "majtshop")
MYSQL_MOT_DE_PASSE = os.environ.get("MYSQL_MOT_DE_PASSE", "MajtShop2026!")
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
