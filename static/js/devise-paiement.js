document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".devise-form-paiement").forEach(function (form) {
        var taux = parseFloat(form.dataset.taux || "0");
        var deviseSelect = form.querySelector(".devise-select");
        var montantInput = form.querySelector('input[name="montant_verse"]');
        if (!deviseSelect || !montantInput || !taux) return;

        deviseSelect.addEventListener("change", function () {
            var valeur = parseFloat(montantInput.value) || 0;
            if (deviseSelect.value === "USD") {
                montantInput.value = (valeur / taux).toFixed(2);
                montantInput.step = "0.01";
            } else {
                montantInput.value = Math.round(valeur * taux);
                montantInput.step = "1";
            }
        });

        form.addEventListener("submit", function () {
            if (deviseSelect.value === "USD") {
                var valeurUsd = parseFloat(montantInput.value) || 0;
                montantInput.value = Math.round(valeurUsd * taux);
            }
        });
    });
});
