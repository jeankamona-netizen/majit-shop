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

    function afficherBanniereActualisation() {
        if (document.getElementById("activite-banniere")) return;
        var contenu = document.querySelector(".admin-contenu");
        if (!contenu) return;
        var banniere = document.createElement("div");
        banniere.id = "activite-banniere";
        banniere.className = "activite-banniere";

        var texte = document.createElement("span");
        texte.textContent = "De nouvelles informations sont disponibles.";

        var bouton = document.createElement("button");
        bouton.type = "button";
        bouton.textContent = "Actualiser";
        bouton.addEventListener("click", function () { location.reload(); });

        var fermer = document.createElement("button");
        fermer.type = "button";
        fermer.className = "activite-banniere-fermer";
        fermer.setAttribute("aria-label", "Fermer");
        fermer.textContent = "✕";
        fermer.addEventListener("click", function () { banniere.remove(); });

        banniere.appendChild(texte);
        banniere.appendChild(bouton);
        banniere.appendChild(fermer);
        contenu.prepend(banniere);
    }

    var compteursPrecedents = null;

    function verifierActivite() {
        fetch("/admin/activite/etat")
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (donnees) {
                if (!donnees) return;
                reconstruireNotifications(donnees.nouvelles_commandes);
                majBadge(donnees.nouvelles_commandes.length);
                if (compteursPrecedents) {
                    var change = Object.keys(donnees.compteurs).some(function (cle) {
                        return donnees.compteurs[cle] !== compteursPrecedents[cle];
                    });
                    if (change) afficherBanniereActualisation();
                }
                compteursPrecedents = donnees.compteurs;
            })
            .catch(function () {});
    }

    verifierActivite();
    setInterval(verifierActivite, 10000);
})();
