(function () {
    var INTERVALLE = 20000;

    function enSaisie() {
        var actif = document.activeElement;
        return actif && ["INPUT", "TEXTAREA", "SELECT"].includes(actif.tagName);
    }

    function planifier() {
        setTimeout(function () {
            if (document.hidden || enSaisie()) {
                planifier();
            } else {
                location.reload();
            }
        }, INTERVALLE);
    }

    planifier();
})();
