(function () {
    var conteneur = document.getElementById("suivi-conteneur");
    if (!conteneur) return;

    var numero = conteneur.dataset.numero;
    var barre = document.getElementById("suivi-barre");
    var illustration = document.getElementById("suivi-illustration");
    var msgLivraison = document.getElementById("suivi-message-livraison");
    var msgLivree = document.getElementById("suivi-message-livree");
    var blocAnnulee = document.getElementById("suivi-annulee");
    var spanLivreurNom = document.getElementById("suivi-livreur-nom");
    var spanDateLivraison = document.getElementById("suivi-date-livraison");

    var intervalle = null;
    var etapeMaxAffichee = 0;

    function appliquerEtapes(n) {
        if (n < etapeMaxAffichee) {
            n = etapeMaxAffichee;
        } else {
            etapeMaxAffichee = n;
        }
        barre.querySelectorAll(".suivi-etape").forEach(function (el) {
            var num = parseInt(el.dataset.n, 10);
            el.classList.toggle("suivi-fait", num <= n);
        });
        barre.querySelectorAll(".suivi-trait").forEach(function (el, i) {
            el.classList.toggle("suivi-trait-rempli", (i + 2) <= n);
        });
    }

    function appliquerEtat(statut, etape, livreurNom, dateLivraison) {
        if (statut === "annulee") {
            barre.hidden = true;
            illustration.hidden = true;
            msgLivraison.hidden = true;
            msgLivree.hidden = true;
            blocAnnulee.hidden = false;
            arreterSondage();
            return;
        }

        barre.hidden = false;
        blocAnnulee.hidden = true;
        appliquerEtapes(etape);

        msgLivraison.hidden = statut !== "en_livraison";
        if (statut === "en_livraison") {
            spanLivreurNom.textContent = livreurNom ? " avec " + livreurNom : "";
        }

        msgLivree.hidden = statut !== "livree";
        if (statut === "livree") {
            spanDateLivraison.textContent = dateLivraison ? " le " + dateLivraison.replace("T", " ") : "";
            arreterSondage();
        }
    }

    function sonder() {
        fetch("/suivi/" + encodeURIComponent(numero) + "/etat")
            .then(function (reponse) { return reponse.ok ? reponse.json() : null; })
            .then(function (donnees) {
                if (donnees) {
                    appliquerEtat(donnees.statut, donnees.etape, donnees.livreur_nom, donnees.date_livraison);
                }
            })
            .catch(function () {});
    }

    function arreterSondage() {
        if (intervalle) {
            clearInterval(intervalle);
            intervalle = null;
        }
    }

    var statutInitial = conteneur.dataset.statut;
    var etapeInitiale = parseInt(conteneur.dataset.etape, 10);
    appliquerEtat(statutInitial, etapeInitiale, conteneur.dataset.livreurNom || null, conteneur.dataset.dateLivraison || null);

    if (etapeInitiale === 1 && statutInitial !== "annulee") {
        illustration.classList.add("suivi-illustration-visible");
        setTimeout(function () {
            appliquerEtapes(2);
            illustration.classList.remove("suivi-illustration-visible");
        }, 2000);
    }

    if (statutInitial !== "livree" && statutInitial !== "annulee") {
        intervalle = setInterval(sonder, 8000);
    }
})();
