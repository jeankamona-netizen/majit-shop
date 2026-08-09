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

(function () {
    var carrousel = document.getElementById("banniere-carrousel");
    if (!carrousel) return;

    var slides = carrousel.querySelectorAll(".banniere-slide");
    if (slides.length < 2) return;

    var index = 0;
    setInterval(function () {
        slides[index].classList.remove("actif");
        index = (index + 1) % slides.length;
        slides[index].classList.add("actif");
    }, 5000);
})();
