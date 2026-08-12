-- Schéma MySQL pour Majt Shop
--
-- Choix de conception, pour coller au comportement exact de l'ancien
-- stockage JSON (dates ISO en texte, nombres en float) sans devoir modifier
-- toute la logique métier existante :
--   - Les dates/heures restent en VARCHAR au format ISO 8601, exactement
--     comme dans les fichiers JSON (évite les pièges de conversion
--     datetime/Decimal qui casseraient les comparaisons, le tri par
--     préfixe des numéros de commande, ou la sérialisation en session).
--   - Les listes courtes toujours manipulées comme un tout (couleurs,
--     tailles, photos supplémentaires, lignes de commande) sont stockées
--     en colonnes JSON plutôt qu'en tables séparées : l'application ne
--     les filtre jamais côté SQL, uniquement côté Python.

CREATE TABLE IF NOT EXISTS livreurs (
    numero VARCHAR(20) PRIMARY KEY,
    nom VARCHAR(255) NOT NULL,
    prenom VARCHAR(255) NOT NULL,
    sexe VARCHAR(10) NOT NULL DEFAULT 'homme',
    adresse TEXT,
    telephone VARCHAR(50),
    mot_de_passe_hash VARCHAR(255) NOT NULL,
    actif TINYINT(1) NOT NULL DEFAULT 1,
    date_creation VARCHAR(30) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS produits (
    id INT PRIMARY KEY,
    nom VARCHAR(255) NOT NULL,
    categorie VARCHAR(50) NOT NULL,
    sous_categorie VARCHAR(50),
    prix DECIMAL(12,2) NOT NULL DEFAULT 0,
    reduction INT NOT NULL DEFAULT 0,
    image VARCHAR(255) NOT NULL DEFAULT 'placeholder.jpg',
    images JSON,
    description TEXT,
    tailles JSON,
    couleurs JSON,
    variantes JSON,
    stock INT NOT NULL DEFAULT 0,
    public VARCHAR(20) NOT NULL DEFAULT 'unisexe',
    vues INT NOT NULL DEFAULT 0,
    INDEX idx_categorie (categorie),
    INDEX idx_public (public)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS commandes (
    numero VARCHAR(20) PRIMARY KEY,
    date VARCHAR(30) NOT NULL,
    nom VARCHAR(255) NOT NULL,
    telephone VARCHAR(50) NOT NULL,
    adresse TEXT NOT NULL,
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    lignes JSON NOT NULL,
    total DECIMAL(12,2) NOT NULL,
    statut VARCHAR(20) NOT NULL DEFAULT 'en_attente',
    montant_verse DECIMAL(12,2),
    montant_verse_cdf DECIMAL(12,2),
    montant_verse_usd DECIMAL(12,2),
    code_livraison VARCHAR(10),
    date_livraison VARCHAR(30),
    vue TINYINT(1) NOT NULL DEFAULT 0,
    livreur_numero VARCHAR(20),
    livreur_nom VARCHAR(255),
    INDEX idx_statut (statut),
    INDEX idx_date (date),
    INDEX idx_livreur_numero (livreur_numero)
    -- Pas de clé étrangère vers livreurs : commandes et livreurs sont chacun
    -- réécrits intégralement à chaque sauvegarde (voir sauvegarder_commandes
    -- / sauvegarder_livreurs dans app.py), ce qui déclencherait des
    -- suppressions en cascade indésirables avec une contrainte FK stricte.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS avis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero VARCHAR(20) NOT NULL,
    date VARCHAR(30) NOT NULL,
    note_articles INT NOT NULL,
    note_procedure INT NOT NULL,
    commentaire TEXT,
    INDEX idx_numero (numero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS visites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date VARCHAR(10) NOT NULL,
    heure VARCHAR(8) NOT NULL,
    ip VARCHAR(45) NOT NULL,
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS geoloc_cache (
    ip VARCHAR(45) PRIMARY KEY,
    localisation VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS parametres (
    id INT PRIMARY KEY,
    taux_usd DECIMAL(10,2) NOT NULL DEFAULT 2800
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
