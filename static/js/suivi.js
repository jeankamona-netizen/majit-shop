(function () {
    var conteneur = document.getElementById("suivi-conteneur");
    if (!conteneur) return;

    var token = conteneur.dataset.token;
    var barre = document.getElementById("suivi-barre");
    var illustration = document.getElementById("suivi-illustration");
    var msgLivraison = document.getElementById("suivi-message-livraison");
    var msgLivree = document.getElementById("suivi-message-livree");
    var blocAnnulee = document.getElementById("suivi-annulee");
    var spanDateLivraison = document.getElementById("suivi-date-livraison");
    var blocCode = document.getElementById("suivi-code");
    var spanCodeValeur = document.getElementById("suivi-code-valeur");
    var codeLivraison = conteneur.dataset.codeLivraison || "";

    var intervalle = null;
    var etapeMaxAffichee = 0;
    var statutPrecedent = conteneur.dataset.statut;

    function afficherNotificationFlottante(texte) {
        var toast = document.getElementById("suivi-toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "suivi-toast";
            toast.className = "suivi-toast";
            toast.addEventListener("click", function () {
                toast.classList.remove("suivi-toast-visible");
            });
            document.body.appendChild(toast);
        }
        toast.textContent = texte;
        toast.classList.add("suivi-toast-visible");
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
        clearTimeout(toast._minuteur);
        toast._minuteur = setTimeout(function () {
            toast.classList.remove("suivi-toast-visible");
        }, 9000);
    }

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

    function appliquerEtat(statut, etape, dateLivraison, codeLivraisonMaj) {
        if (codeLivraisonMaj) codeLivraison = codeLivraisonMaj;

        if (statut === "annulee") {
            barre.hidden = true;
            illustration.hidden = true;
            msgLivraison.hidden = true;
            msgLivree.hidden = true;
            if (blocCode) blocCode.hidden = true;
            blocAnnulee.hidden = false;
            arreterSondage();
            return;
        }

        barre.hidden = false;
        blocAnnulee.hidden = true;
        appliquerEtapes(etape);
        illustration.classList.toggle("suivi-illustration-visible", etape === 1);

        msgLivraison.hidden = statut !== "en_livraison";

        if (blocCode && spanCodeValeur) {
            var afficherCode = statut === "en_livraison" && codeLivraison;
            blocCode.hidden = !afficherCode;
            if (afficherCode) spanCodeValeur.textContent = codeLivraison;
        }

        msgLivree.hidden = statut !== "livree";
        if (statut === "livree") {
            spanDateLivraison.textContent = dateLivraison ? " le " + dateLivraison.replace("T", " ") : "";
            if (blocCode) blocCode.hidden = true;
            arreterSondage();
        }
    }

    function sonder() {
        fetch("/suivi/" + encodeURIComponent(token) + "/etat")
            .then(function (reponse) { return reponse.ok ? reponse.json() : null; })
            .then(function (donnees) {
                if (donnees) {
                    if (donnees.statut === "en_livraison" && statutPrecedent !== "en_livraison" && donnees.code_livraison) {
                        afficherNotificationFlottante("🚚 Votre livreur est en route ! Code à lui remettre à l'arrivée : " + donnees.code_livraison);
                    }
                    statutPrecedent = donnees.statut;
                    conteneur.dataset.statut = donnees.statut;
                    conteneur.dataset.avisDonne = donnees.avis_donne ? "true" : "false";
                    appliquerEtat(donnees.statut, donnees.etape, donnees.date_livraison, donnees.code_livraison);
                    if (window.ouvrirSondageSiEligible) window.ouvrirSondageSiEligible();
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
    appliquerEtat(statutInitial, etapeInitiale, conteneur.dataset.dateLivraison || null, codeLivraison);

    if (statutInitial !== "livree" && statutInitial !== "annulee") {
        intervalle = setInterval(sonder, 8000);
    }
})();
