(function () {
    var piste = document.getElementById("carrousel-categories");
    if (!piste) return;

    setInterval(function () {
        var tuile = piste.querySelector(".tuile-categorie");
        if (!tuile) return;

        var style = getComputedStyle(piste);
        var ecart = parseFloat(style.columnGap || style.gap || "16");
        var pas = tuile.getBoundingClientRect().width + ecart;
        var maxDefilement = piste.scrollWidth - piste.clientWidth;

        if (piste.scrollLeft >= maxDefilement - 5) {
            piste.scrollTo({ left: 0, behavior: "smooth" });
        } else {
            piste.scrollBy({ left: pas, behavior: "smooth" });
        }
    }, 5000);
})();
