(function () {
    var barre = document.getElementById("suivi-barre");
    if (!barre) return;

    var illustration = document.getElementById("suivi-illustration");
    var etapeInitiale = parseInt(barre.dataset.etape, 10);

    function appliquer(n) {
        barre.querySelectorAll(".suivi-etape").forEach(function (el) {
            var num = parseInt(el.dataset.n, 10);
            el.classList.toggle("suivi-fait", num <= n);
        });
        barre.querySelectorAll(".suivi-trait").forEach(function (el, i) {
            el.classList.toggle("suivi-trait-rempli", (i + 2) <= n);
        });
    }

    appliquer(etapeInitiale);

    if (etapeInitiale === 1) {
        if (illustration) illustration.classList.add("suivi-illustration-visible");
        setTimeout(function () {
            appliquer(2);
            if (illustration) illustration.classList.remove("suivi-illustration-visible");
        }, 2000);
    }
})();
