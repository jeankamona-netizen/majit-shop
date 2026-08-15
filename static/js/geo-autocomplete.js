// Widget d'autocomplétion générique (province / ville / commune).
// Ne fait jamais confiance au texte tapé : seule une suggestion réellement
// cliquée (ou validée au clavier) remplit le champ caché "*_id" envoyé au
// serveur, qui revérifie toujours la hiérarchie de son côté.
(function () {
    "use strict";

    function debounce(fn, delai) {
        var minuteur = null;
        return function () {
            var args = arguments;
            clearTimeout(minuteur);
            minuteur = setTimeout(function () { fn.apply(null, args); }, delai);
        };
    }

    function creerAutocompletionGeo(config) {
        var input = config.input;
        var hidden = config.hidden;

        var liste = document.createElement("ul");
        liste.className = "geo-autocomplete-liste";
        liste.setAttribute("role", "listbox");
        liste.hidden = true;
        input.insertAdjacentElement("afterend", liste);
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-autocomplete", "list");
        input.setAttribute("aria-expanded", "false");

        var resultats = [];
        var indexActif = -1;

        function fermer() {
            liste.hidden = true;
            liste.innerHTML = "";
            resultats = [];
            indexActif = -1;
            input.setAttribute("aria-expanded", "false");
        }

        function afficher(items) {
            resultats = items;
            indexActif = -1;
            liste.innerHTML = "";
            if (!items.length) {
                fermer();
                return;
            }
            items.forEach(function (item, i) {
                var li = document.createElement("li");
                li.textContent = item.nom;
                li.setAttribute("role", "option");
                li.addEventListener("mousedown", function (e) {
                    e.preventDefault();
                    choisir(i);
                });
                liste.appendChild(li);
            });
            liste.hidden = false;
            input.setAttribute("aria-expanded", "true");
        }

        function choisir(i) {
            var item = resultats[i];
            if (!item) return;
            input.value = item.nom;
            hidden.value = item.id;
            fermer();
            if (config.onSelect) config.onSelect(item);
        }

        function surligner() {
            Array.prototype.forEach.call(liste.children, function (li, i) {
                li.classList.toggle("geo-autocomplete-actif", i === indexActif);
            });
            if (indexActif >= 0 && liste.children[indexActif]) {
                liste.children[indexActif].scrollIntoView({ block: "nearest" });
            }
        }

        var chercher = debounce(function () {
            var params = config.extraParams ? config.extraParams() : {};
            if (params === null) {
                fermer();
                return;
            }
            params.q = input.value.trim();
            var url = config.endpoint + "?" + Object.keys(params).map(function (k) {
                return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
            }).join("&");
            fetch(url).then(function (r) { return r.json(); }).then(function (data) {
                var resultats = data.resultats || [];
                afficher(resultats);
                if (config.onRecherche) config.onRecherche(resultats, input.value.trim());
            }).catch(function () { fermer(); });
        }, 200);

        input.addEventListener("input", function () {
            hidden.value = "";
            if (config.onClear) config.onClear();
            if (input.disabled) return;
            chercher();
        });

        input.addEventListener("focus", function () {
            if (!input.disabled && input.value.trim() && !hidden.value) chercher();
        });

        input.addEventListener("keydown", function (e) {
            if (liste.hidden) return;
            if (e.key === "ArrowDown") {
                e.preventDefault();
                indexActif = Math.min(indexActif + 1, resultats.length - 1);
                surligner();
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                indexActif = Math.max(indexActif - 1, 0);
                surligner();
            } else if (e.key === "Enter") {
                if (indexActif >= 0) {
                    e.preventDefault();
                    choisir(indexActif);
                }
            } else if (e.key === "Escape") {
                fermer();
            }
        });

        document.addEventListener("click", function (e) {
            if (e.target !== input) fermer();
        });

        return {
            desactiver: function (placeholder) {
                input.value = "";
                hidden.value = "";
                input.disabled = true;
                if (placeholder) input.placeholder = placeholder;
                fermer();
            },
            activer: function (placeholder) {
                input.disabled = false;
                if (placeholder) input.placeholder = placeholder;
            },
            definir: function (nom, id) {
                input.value = nom;
                hidden.value = id;
            },
        };
    }

    window.creerAutocompletionGeo = creerAutocompletionGeo;
})();
