document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".bouton-oeil").forEach(function (bouton) {
        var champ = bouton.closest(".champ-mot-de-passe");
        var input = champ.querySelector("input");
        var iconeOuvert = bouton.querySelector(".icone-oeil-ouvert");
        var iconeFerme = bouton.querySelector(".icone-oeil-ferme");

        bouton.addEventListener("click", function () {
            var visible = input.type === "text";
            input.type = visible ? "password" : "text";
            iconeOuvert.style.display = visible ? "" : "none";
            iconeFerme.style.display = visible ? "none" : "";
            bouton.setAttribute("aria-label", visible ? "Afficher le mot de passe" : "Masquer le mot de passe");
        });
    });
});
