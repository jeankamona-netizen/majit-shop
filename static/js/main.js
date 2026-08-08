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
