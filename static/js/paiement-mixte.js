document.addEventListener("DOMContentLoaded", function () {
    function initGroupe(conteneur) {
        var total = parseFloat(conteneur.dataset.total || "0");
        var taux = parseFloat(conteneur.dataset.taux || "0");
        var champCdf = conteneur.querySelector('input[name="montant_verse_cdf"]');
        var champUsd = conteneur.querySelector('input[name="montant_verse_usd"]');
        if (!champCdf || !champUsd || !taux) return;

        champUsd.addEventListener("input", function () {
            var usd = parseFloat(champUsd.value);
            if (!champUsd.value || isNaN(usd) || usd <= 0) {
                champCdf.value = "";
                return;
            }
            var reste = total - usd * taux;
            champCdf.value = reste > 0 ? Math.round(reste) : 0;
        });

        champCdf.addEventListener("input", function () {
            var cdf = parseFloat(champCdf.value);
            if (!champCdf.value || isNaN(cdf) || cdf <= 0) {
                champUsd.value = "";
                return;
            }
            var reste = (total - cdf) / taux;
            champUsd.value = reste > 0 ? reste.toFixed(2) : "0.00";
        });
    }

    document.querySelectorAll(".paiement-mixte, .paiement-mixte-inline").forEach(initGroupe);
});
