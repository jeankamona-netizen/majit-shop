(function () {
    var fond = document.getElementById("sondage-fond");
    var carte = fond ? fond.querySelector(".sondage-carte") : null;
    var formulaire = document.getElementById("sondage-formulaire");
    var conteneur = document.getElementById("suivi-conteneur");
    if (!fond || !formulaire || !conteneur) return;

    var valeurs = { note_articles: 0, note_procedure: 0 };
    var dejaOuvert = false;

    document.querySelectorAll(".etoiles").forEach(function (groupe) {
        var champ = groupe.dataset.champ;
        var etoiles = groupe.querySelectorAll(".etoile");
        etoiles.forEach(function (etoile) {
            etoile.addEventListener("click", function () {
                var valeur = parseInt(etoile.dataset.valeur, 10);
                valeurs[champ] = valeur;
                etoiles.forEach(function (e) {
                    e.classList.toggle("etoile-active", parseInt(e.dataset.valeur, 10) <= valeur);
                });
            });
        });
    });

    function fermer() {
        fond.classList.remove("sondage-ouvert");
    }

    document.getElementById("sondage-fermer").addEventListener("click", fermer);
    document.getElementById("sondage-passer").addEventListener("click", fermer);

    formulaire.addEventListener("submit", function (e) {
        e.preventDefault();
        if (!valeurs.note_articles || !valeurs.note_procedure) {
            alert("Merci de donner une note aux deux critères.");
            return;
        }
        var donnees = new FormData(formulaire);
        donnees.set("note_articles", valeurs.note_articles);
        donnees.set("note_procedure", valeurs.note_procedure);
        var numero = donnees.get("numero");

        fetch("/avis/" + encodeURIComponent(numero), {
            method: "POST",
            body: donnees,
        }).then(function () {
            carte.classList.add("sondage-envoye");
            setTimeout(fermer, 2000);
        }).catch(function () {
            fermer();
        });
    });

    window.ouvrirSondageSiEligible = function () {
        if (dejaOuvert) return;
        var eligible = conteneur.dataset.statut === "livree"
            && conteneur.dataset.avisAutorise === "true"
            && conteneur.dataset.avisDonne !== "true";
        if (!eligible) return;
        dejaOuvert = true;
        setTimeout(function () {
            fond.classList.add("sondage-ouvert");
        }, 600);
    };

    window.ouvrirSondageSiEligible();
})();
