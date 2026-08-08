# Majt Shop

Site de vente en ligne (vêtements, chaussures, sacs à main, téléphones portables) construit avec Flask.

## Fonctionnalités

- Catalogue par catégorie (Vêtements, Chaussures, Sacs à main, Électroniques) et public (Homme / Femme / Enfant / Tous), avec tailles/couleurs et réductions
- Panier, commande (nom, téléphone, adresse) et confirmation, paiement à la livraison, prix en CDF
- Espace administrateur protégé : gestion des produits (photos, stock, réapprovisionnement), suivi des commandes (statut, montant versé), revenus filtrables (date/semaine/article/catégorie), visiteurs par jour, notifications de nouvelles commandes

## Installation locale

```bash
python -m pip install -r requirements.txt
python app.py
```

Le site est disponible sur http://127.0.0.1:5000

## Configuration (variables d'environnement)

Copier `.env.example` en `.env` et adapter les valeurs (ou définir les variables directement sur la plateforme d'hébergement) :

| Variable | Rôle | Par défaut (dev uniquement) |
|---|---|---|
| `SECRET_KEY` | Clé de session Flask | `dev-majt-shop-secret-key` |
| `ADMIN_UTILISATEUR` | Identifiant admin | `admin` |
| `ADMIN_MOT_DE_PASSE` | Mot de passe admin | `MajtAdmin2026!` |
| `FLASK_DEBUG` | Mode debug (`1`/`0`) | `1` |
| `PORT` | Port d'écoute | `5000` |

**Important** : changer `SECRET_KEY` et `ADMIN_MOT_DE_PASSE` avant toute mise en ligne.

## Déploiement (Render)

1. Pousser ce dépôt sur GitHub.
2. Sur [render.com](https://render.com) : New → Web Service → connecter le dépôt GitHub.
3. Render détecte `render.yaml` et propose automatiquement la configuration (build `pip install -r requirements.txt`, start `gunicorn app:app`).
4. Définir les variables d'environnement `SECRET_KEY` et `ADMIN_MOT_DE_PASSE` (valeurs personnalisées) dans les réglages du service.
5. Déployer.

### Limite à connaître

Les données (`data/produits.json`, photos ajoutées via l'admin) sont stockées sur le disque du serveur. Sur l'offre gratuite de Render, ce disque n'est **pas persistant** : un redéploiement peut réinitialiser les changements faits depuis l'admin (nouveaux produits, photos, stock). Pour un usage en production durable, prévoir un disque persistant (offre payante) ou migrer vers une vraie base de données.
