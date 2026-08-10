document.querySelectorAll(".qte-bouton").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
        var input = document.getElementById("quantite");
        var delta = parseInt(bouton.dataset.delta, 10);
        var valeur = Math.max(1, (parseInt(input.value, 10) || 1) + delta);
        input.value = valeur;
    });
});

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
    if (typeof VARIANTES_STOCK === "undefined") return;

    var form = document.querySelector(".form-panier");
    var stockTexte = document.getElementById("detail-stock");
    var boutons = document.querySelectorAll(".bouton-ajouter, .bouton-acheter");
    if (!form) return;

    function valeurCochee(nom) {
        var champ = form.querySelector('input[name="' + nom + '"]:checked');
        return champ ? champ.value : "";
    }

    function actualiser() {
        var couleur = valeurCochee("couleur");
        var taille = valeurCochee("taille");
        var cle = couleur + "::" + taille;
        var disponible = VARIANTES_STOCK[cle] || 0;

        if (stockTexte) {
            if (disponible > 0) {
                stockTexte.textContent = "En stock : " + disponible + " disponible" + (disponible > 1 ? "s" : "") + " pour cette combinaison";
                stockTexte.classList.remove("detail-stock-vide");
            } else {
                stockTexte.textContent = "Rupture de stock pour cette combinaison";
                stockTexte.classList.add("detail-stock-vide");
            }
        }

        boutons.forEach(function (bouton) { bouton.disabled = disponible <= 0; });

        var quantite = document.getElementById("quantite");
        if (quantite) quantite.max = disponible || 1;
    }

    form.querySelectorAll('input[name="couleur"], input[name="taille"]').forEach(function (champ) {
        champ.addEventListener("change", actualiser);
    });

    actualiser();
})();
