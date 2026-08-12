(function () {
    var imagePrincipale = document.getElementById("image-principale");
    var vignettes = document.querySelectorAll(".detail-vignette");
    if (!imagePrincipale || !vignettes.length) return;

    function afficher(vignette) {
        imagePrincipale.src = vignette.dataset.image;
        vignettes.forEach(function (v) { v.classList.remove("detail-vignette-actif"); });
        vignette.classList.add("detail-vignette-actif");
    }

    vignettes.forEach(function (vignette) {
        vignette.addEventListener("mouseenter", function () { afficher(vignette); });
        vignette.addEventListener("click", function () { afficher(vignette); });
    });
})();

(function () {
    var quantite = document.getElementById("quantite");
    if (!quantite) return;

    var form = document.querySelector(".form-panier");
    var stockTexte = document.getElementById("detail-stock");
    var stockAlerte = document.getElementById("stock-alerte");
    var boutons = document.querySelectorAll(".bouton-ajouter, .bouton-acheter");
    var variantes = typeof VARIANTES_STOCK !== "undefined" ? VARIANTES_STOCK : null;

    function valeurCochee(nom) {
        if (!form) return "";
        var champ = form.querySelector('input[name="' + nom + '"]:checked');
        return champ ? champ.value : "";
    }

    function disponibleActuel() {
        if (variantes) {
            var cle = valeurCochee("couleur") + "::" + valeurCochee("taille");
            return variantes[cle] || 0;
        }
        return parseInt(quantite.dataset.stock, 10) || 0;
    }

    function actualiserEtatStock() {
        var disponible = disponibleActuel();

        if (stockTexte) {
            if (disponible > 0) {
                stockTexte.textContent = variantes ? "En stock pour cette combinaison" : "En stock";
                stockTexte.classList.remove("detail-stock-vide");
            } else {
                stockTexte.textContent = variantes ? "Rupture de stock pour cette combinaison" : "Rupture de stock";
                stockTexte.classList.add("detail-stock-vide");
            }
        }

        boutons.forEach(function (bouton) { bouton.disabled = disponible <= 0; });
        return disponible;
    }

    function appliquerQuantite(valeurDemandee) {
        var disponible = actualiserEtatStock();

        if (disponible <= 0) {
            quantite.value = 1;
            if (stockAlerte) stockAlerte.hidden = true;
            return;
        }

        if (valeurDemandee > disponible) {
            quantite.value = disponible;
            if (stockAlerte) {
                stockAlerte.textContent = "Il ne reste que " + disponible + " en stock.";
                stockAlerte.hidden = false;
            }
        } else {
            if (valeurDemandee < 1) valeurDemandee = 1;
            quantite.value = valeurDemandee;
            if (stockAlerte) stockAlerte.hidden = true;
        }
    }

    document.querySelectorAll(".qte-bouton").forEach(function (bouton) {
        bouton.addEventListener("click", function () {
            var delta = parseInt(bouton.dataset.delta, 10);
            var valeur = (parseInt(quantite.value, 10) || 1) + delta;
            appliquerQuantite(valeur);
        });
    });

    quantite.addEventListener("input", function () {
        appliquerQuantite(parseInt(quantite.value, 10) || 1);
    });

    if (form) {
        form.querySelectorAll('input[name="couleur"], input[name="taille"]').forEach(function (champ) {
            champ.addEventListener("change", function () {
                appliquerQuantite(parseInt(quantite.value, 10) || 1);
            });
        });
    }

    actualiserEtatStock();
})();
