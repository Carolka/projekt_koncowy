"use strict";

const formularzRezerwacji = document.getElementById("reservation-filters");

formularzRezerwacji?.addEventListener("submit", (event) => {
    event.preventDefault();
    const parametry = new URLSearchParams(new FormData(formularzRezerwacji));

    for (const filtr of formularzRezerwacji.querySelectorAll("select[data-params]")) {
        const wybrane = new URLSearchParams(filtr.value);
        for (const nazwa of filtr.dataset.params.split(" ")) {
            parametry.delete(nazwa);
            for (const wartosc of wybrane.getAll(nazwa)) {
                parametry.append(nazwa, wartosc);
            }
        }
    }

    window.location.search = parametry.toString();
});
