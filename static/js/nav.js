(function () {
    var bouton = document.getElementById("menu-bouton");
    var nav = document.getElementById("nav-categories");
    if (!bouton || !nav) return;

    bouton.addEventListener("click", function () {
        var ouvert = nav.classList.toggle("nav-ouverte");
        bouton.setAttribute("aria-expanded", ouvert ? "true" : "false");
    });

    nav.querySelectorAll("a").forEach(function (lien) {
        lien.addEventListener("click", function () {
            nav.classList.remove("nav-ouverte");
            bouton.setAttribute("aria-expanded", "false");
        });
    });
})();
