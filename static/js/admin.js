(function () {
    var cloche = document.getElementById("admin-cloche");
    var panneau = document.getElementById("admin-notif-panneau");
    var metaCsrf = document.querySelector('meta[name="csrf-token"]');
    var jetonCsrf = metaCsrf ? metaCsrf.content : "";

    if (cloche && panneau) {
        cloche.addEventListener("click", function (e) {
            e.stopPropagation();
            var ouvert = panneau.classList.toggle("admin-notif-ouvert");
            if (ouvert) {
                var badge = document.getElementById("admin-cloche-badge");
                if (badge) badge.remove();
                fetch("/admin/notifications/marquer-vues", {
                    method: "POST",
                    headers: { "X-CSRFToken": jetonCsrf },
                });
            }
        });
    }

    var menuBouton = document.getElementById("admin-menu-bouton");
    var nav = document.getElementById("admin-nav");

    if (menuBouton && nav) {
        menuBouton.addEventListener("click", function (e) {
            e.stopPropagation();
            var ouvert = nav.classList.toggle("admin-nav-ouvert");
            menuBouton.setAttribute("aria-expanded", ouvert ? "true" : "false");
        });

        nav.querySelectorAll("a").forEach(function (lien) {
            lien.addEventListener("click", function () {
                nav.classList.remove("admin-nav-ouvert");
                menuBouton.setAttribute("aria-expanded", "false");
            });
        });
    }

    document.addEventListener("click", function (e) {
        if (panneau && cloche && !panneau.contains(e.target) && e.target !== cloche) {
            panneau.classList.remove("admin-notif-ouvert");
        }
        if (nav && menuBouton && !nav.contains(e.target) && e.target !== menuBouton) {
            nav.classList.remove("admin-nav-ouvert");
            menuBouton.setAttribute("aria-expanded", "false");
        }
    });

    // --- Activité en direct (commandes, livraisons, prises en charge...) ---
    function formaterCdf(valeur) {
        var nombre = Math.round(valeur).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
        return nombre + ' <span class="cdf-suffixe">CDF</span>';
    }

    function libelleArticle(l) {
        var precisions = [];
        if (l.couleur) precisions.push(l.couleur);
        if (l.taille) precisions.push(l.taille);
        return l.nom + (precisions.length ? " (" + precisions.join(", ") + ")" : "") + " × " + l.quantite;
    }

    function echapper(texte) {
        var div = document.createElement("div");
        div.textContent = texte == null ? "" : texte;
        return div.innerHTML;
    }

    function reconstruireNotifications(commandes) {
        if (!panneau || panneau.classList.contains("admin-notif-ouvert")) return;
        var html = '<div class="admin-notif-entete">Nouvelles commandes</div>';
        if (!commandes.length) {
            html += '<p class="admin-notif-vide">Aucune nouvelle commande.</p>';
        } else {
            commandes.forEach(function (c) {
                html += '<a href="/admin/commandes#commande-' + encodeURIComponent(c.numero) + '" class="admin-notif-commande">';
                html += '<div class="admin-notif-ligne1"><strong>' + echapper(c.numero) + '</strong><span class="admin-notif-date">' + echapper(c.date.replace("T", " ")) + '</span></div>';
                html += '<div class="admin-notif-client">' + echapper(c.nom) + ' — ' + echapper(c.telephone) + '</div>';
                html += '<div class="admin-notif-adresse">' + echapper(c.adresse) + '</div>';
                html += '<ul class="admin-notif-articles">';
                c.lignes.forEach(function (l) {
                    html += '<li>' + echapper(libelleArticle(l)) + ' — ' + formaterCdf(l.sous_total) + '</li>';
                });
                html += '</ul>';
                html += '<div class="admin-notif-total">Total : ' + formaterCdf(c.total) + '</div>';
                html += '</a>';
            });
        }
        panneau.innerHTML = html;
    }

    function majBadge(nb) {
        if (!cloche) return;
        var badge = document.getElementById("admin-cloche-badge");
        if (nb > 0) {
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "admin-cloche-badge";
                badge.id = "admin-cloche-badge";
                cloche.appendChild(badge);
            }
            badge.textContent = nb;
        } else if (badge) {
            badge.remove();
        }
    }

    var STATUT_LABELS = {
        en_attente: "en attente",
        en_preparation: "en préparation",
        en_livraison: "en livraison",
        livree: "livrée",
        annulee: "annulée",
    };

    function detecterEvenements(actuelles, precedentes) {
        var precedentesParNumero = {};
        precedentes.forEach(function (c) { precedentesParNumero[c.numero] = c; });
        var evenements = [];
        actuelles.forEach(function (c) {
            var avant = precedentesParNumero[c.numero];
            if (!avant) {
                evenements.push({ type: "nouvelle", commande: c });
            } else if (avant.statut !== c.statut) {
                evenements.push({ type: "statut", commande: c });
            }
        });
        return evenements;
    }

    function texteEvenement(evt) {
        var c = evt.commande;
        if (evt.type === "nouvelle") {
            return "Nouvelle commande émise : " + c.nom + " — " + c.numero;
        }
        if (c.statut === "en_livraison") {
            return "Commande " + c.numero + " (" + c.nom + ") prise en charge" + (c.livreur_nom ? " par " + c.livreur_nom : "");
        }
        if (c.statut === "livree") {
            return "Commande " + c.numero + " (" + c.nom + ") livrée";
        }
        if (c.statut === "annulee") {
            return "Commande " + c.numero + " (" + c.nom + ") annulée";
        }
        return "Commande " + c.numero + " : " + (STATUT_LABELS[c.statut] || c.statut);
    }

    function afficherBanniereActualisation(evenements) {
        var ancienne = document.getElementById("activite-banniere");
        if (ancienne) ancienne.remove();

        var commandesUrl = document.body.dataset.commandesUrl || "";
        var premier = evenements[0];
        var texte = texteEvenement(premier);
        if (evenements.length > 1) {
            texte += " (+" + (evenements.length - 1) + " autre" + (evenements.length > 2 ? "s" : "") + ")";
        }

        var banniere = document.createElement("div");
        banniere.id = "activite-banniere";
        banniere.className = "activite-banniere";

        var texteEl = document.createElement("span");
        texteEl.textContent = texte;

        var lien = document.createElement("a");
        lien.textContent = "Voir";
        lien.href = commandesUrl + "#commande-" + encodeURIComponent(premier.commande.numero);

        var fermer = document.createElement("button");
        fermer.type = "button";
        fermer.className = "activite-banniere-fermer";
        fermer.setAttribute("aria-label", "Fermer");
        fermer.textContent = "✕";
        fermer.addEventListener("click", function () { banniere.remove(); });

        banniere.appendChild(texteEl);
        banniere.appendChild(lien);
        banniere.appendChild(fermer);
        document.body.appendChild(banniere);
    }

    var recentesPrecedentes = null;

    function verifierActivite() {
        fetch("/admin/activite/etat")
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (donnees) {
                if (!donnees) return;
                reconstruireNotifications(donnees.nouvelles_commandes);
                majBadge(donnees.nouvelles_commandes.length);
                if (recentesPrecedentes) {
                    var evenements = detecterEvenements(donnees.recentes, recentesPrecedentes);
                    if (evenements.length) afficherBanniereActualisation(evenements);
                }
                recentesPrecedentes = donnees.recentes;
            })
            .catch(function () {});
    }

    verifierActivite();
    setInterval(verifierActivite, 10000);
})();
