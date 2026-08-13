document.addEventListener("DOMContentLoaded", function () {
    function formaterNombre(valeur) {
        return Math.round(valeur).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    }

    function initGroupe(conteneur) {
        var total = parseFloat(conteneur.dataset.total || "0");
        var taux = parseFloat(conteneur.dataset.taux || "0");
        var champCdf = conteneur.querySelector('input[name="montant_verse_cdf"]');
        var champUsd = conteneur.querySelector('input[name="montant_verse_usd"]');
        if (!champCdf || !champUsd || !taux) return;

        var rendu = document.createElement("p");
        rendu.className = "paiement-rendu";
        rendu.hidden = true;
        conteneur.insertAdjacentElement("afterend", rendu);

        function afficherRendu(texte) {
            rendu.textContent = "À rendre au client : " + texte;
            rendu.hidden = false;
        }

        function masquerRendu() {
            rendu.hidden = true;
        }

        champUsd.addEventListener("input", function () {
            var usd = parseFloat(champUsd.value);
            if (!champUsd.value || isNaN(usd) || usd <= 0) {
                champCdf.value = "";
                masquerRendu();
                return;
            }
            var reste = total - usd * taux;
            if (reste >= 0) {
                champCdf.value = Math.round(reste);
                masquerRendu();
            } else {
                champCdf.value = 0;
                afficherRendu((-reste / taux).toFixed(2) + " $");
            }
        });

        champCdf.addEventListener("input", function () {
            var cdf = parseFloat(champCdf.value);
            if (!champCdf.value || isNaN(cdf) || cdf <= 0) {
                champUsd.value = "";
                masquerRendu();
                return;
            }
            var reste = (total - cdf) / taux;
            if (reste >= 0) {
                champUsd.value = reste.toFixed(2);
                masquerRendu();
            } else {
                champUsd.value = "0.00";
                afficherRendu(formaterNombre(cdf - total) + " CDF");
            }
        });
    }

    document.querySelectorAll(".paiement-mixte, .paiement-mixte-inline").forEach(initGroupe);
});
