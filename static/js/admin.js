(function () {
    var cloche = document.getElementById("admin-cloche");
    var panneau = document.getElementById("admin-notif-panneau");
    if (!cloche || !panneau) return;

    cloche.addEventListener("click", function (e) {
        e.stopPropagation();
        var ouvert = panneau.classList.toggle("admin-notif-ouvert");
        if (ouvert) {
            var badge = document.getElementById("admin-cloche-badge");
            if (badge) badge.remove();
            fetch("/admin/notifications/marquer-vues", { method: "POST" });
        }
    });

    document.addEventListener("click", function (e) {
        if (!panneau.contains(e.target) && e.target !== cloche) {
            panneau.classList.remove("admin-notif-ouvert");
        }
    });

    var menuBouton = document.getElementById("admin-menu-bouton");
    var nav = document.getElementById("admin-nav");
    if (menuBouton && nav) {
        menuBouton.addEventListener("click", function () {
            var ouvert = nav.classList.toggle("admin-nav-ouvert");
            menuBouton.setAttribute("aria-expanded", ouvert ? "true" : "false");
        });
    }
})();
