(function () {
    var cloche = document.getElementById("admin-cloche");
    var panneau = document.getElementById("admin-notif-panneau");

    if (cloche && panneau) {
        cloche.addEventListener("click", function (e) {
            e.stopPropagation();
            var ouvert = panneau.classList.toggle("admin-notif-ouvert");
            if (ouvert) {
                var badge = document.getElementById("admin-cloche-badge");
                if (badge) badge.remove();
                fetch("/admin/notifications/marquer-vues", { method: "POST" });
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
})();
