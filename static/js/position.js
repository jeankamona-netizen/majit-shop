(function () {
    var bouton = document.getElementById("bouton-position");
    var statut = document.getElementById("position-statut");
    var latitude = document.getElementById("latitude");
    var longitude = document.getElementById("longitude");
    if (!bouton) return;

    bouton.addEventListener("click", function () {
        if (!navigator.geolocation) {
            statut.textContent = "La géolocalisation n'est pas disponible sur cet appareil.";
            return;
        }
        bouton.disabled = true;
        statut.textContent = "Localisation en cours...";

        navigator.geolocation.getCurrentPosition(
            function (position) {
                latitude.value = position.coords.latitude;
                longitude.value = position.coords.longitude;
                statut.textContent = "✓ Position partagée avec succès.";
                bouton.disabled = false;
            },
            function () {
                statut.textContent = "Position non partagée (autorisation refusée ou indisponible). Ce n'est pas obligatoire.";
                bouton.disabled = false;
            },
            { enableHighAccuracy: true, timeout: 10000 }
        );
    });
})();
