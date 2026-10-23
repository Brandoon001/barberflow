(function () {
    "use strict";

    function iniciarMenu() {
        var botao = document.querySelector("[data-menu-toggle]");
        var menu = document.getElementById("menu-principal");
        if (!botao || !menu) {
            return;
        }

        botao.addEventListener("click", function () {
            var aberto = menu.classList.toggle("aberto");
            botao.setAttribute("aria-expanded", aberto ? "true" : "false");
        });

        menu.addEventListener("click", function (evento) {
            if (evento.target.closest("a")) {
                menu.classList.remove("aberto");
                botao.setAttribute("aria-expanded", "false");
            }
        });
    }

    function iniciarAlertas() {
        document.querySelectorAll("[data-fechar-alerta]").forEach(function (botao) {
            botao.addEventListener("click", function () {
                var alerta = botao.closest(".alerta");
                if (alerta) {
                    alerta.remove();
                }
            });
        });
    }

    function iniciarFiltros() {
        document.querySelectorAll("[data-auto-submit]").forEach(function (campo) {
            campo.addEventListener("change", function () {
                var formulario = campo.closest("form");
                if (!formulario) {
                    return;
                }

                if (typeof formulario.requestSubmit === "function") {
                    formulario.requestSubmit();
                } else {
                    formulario.submit();
                }
            });
        });
    }

    function iniciarConfirmacoes() {
        document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
            formulario.addEventListener("submit", function (evento) {
                if (!window.confirm(formulario.dataset.confirmar)) {
                    evento.preventDefault();
                }
            });
        });

        document.querySelectorAll("button[data-confirmar]").forEach(function (botao) {
            botao.addEventListener("click", function (evento) {
                if (!window.confirm(botao.dataset.confirmar)) {
                    evento.preventDefault();
                    return;
                }

                if (botao.form && !botao.form.hasAttribute("data-confirmar")) {
                    evento.preventDefault();
                    if (typeof botao.form.requestSubmit === "function") {
                        botao.form.requestSubmit();
                    } else {
                        botao.form.submit();
                    }
                }
            });
        });
    }

    function iniciarDetalhes() {
        document.addEventListener("click", function (evento) {
            document.querySelectorAll("details.menu-detalhes[open]").forEach(function (detalhe) {
                if (!detalhe.contains(evento.target)) {
                    detalhe.removeAttribute("open");
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        iniciarMenu();
        iniciarAlertas();
        iniciarFiltros();
        iniciarConfirmacoes();
        iniciarDetalhes();
    });
})();
