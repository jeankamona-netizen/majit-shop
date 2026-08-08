document.querySelectorAll(".qte-bouton").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
        var input = document.getElementById("quantite");
        var delta = parseInt(bouton.dataset.delta, 10);
        var valeur = Math.max(1, (parseInt(input.value, 10) || 1) + delta);
        input.value = valeur;
    });
});
