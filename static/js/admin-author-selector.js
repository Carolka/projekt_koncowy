"use strict";

document.addEventListener("DOMContentLoaded", () => {
    if (document.documentElement.lang.split("-")[0] !== "pl") {
        return;
    }

    // Django buduje selektor po załadowaniu strony.
    window.addEventListener("load", () => {
        const teksty = {
            "#id_autorzy_from_title label": "Dostępni autorzy",
            "#id_autorzy_to_title label": "Wybrani autorzy",
            "#id_autorzy_from_title .helptext":
                "Aby dodać autorów, zaznacz ich i kliknij strzałkę „Wybierz”.",
            "#id_autorzy_to_title .helptext":
                "Aby usunąć autorów, zaznacz ich i kliknij strzałkę „Usuń”.",
            "#id_autorzy_add_all": "Wybierz wszystkich autorów",
            "#id_autorzy_add": "Wybierz zaznaczonych autorów",
            "#id_autorzy_remove": "Usuń zaznaczonych autorów",
            "#id_autorzy_remove_all": "Usuń wszystkich autorów",
        };

        for (const [selektor, tekst] of Object.entries(teksty)) {
            const element = document.querySelector(selektor);
            if (element) {
                element.textContent = tekst;
            }
        }

        const filtry = {
            "#id_autorzy_filter .search-label-icon": "Filtruj listę dostępnych autorów.",
            "#id_autorzy_filter_selected .search-label-icon": "Filtruj listę wybranych autorów.",
        };

        for (const [selektor, opis] of Object.entries(filtry)) {
            document.querySelector(selektor)?.setAttribute("aria-label", opis);
        }
    });
});
