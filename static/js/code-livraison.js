document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".livreur-code-input").forEach(function (champ) {
        var form = champ.closest("form");
        if (!form) return;
        var bouton = form.querySelector('button[type="submit"]');
        if (!bouton) return;

        function verifier() {
            var complet = champ.value.replace(/\D/g, "").length === 4;
            bouton.disabled = !complet;
        }

        champ.addEventListener("input", verifier);
        verifier();
    });
});
