/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";

function hideEnterpriseBadges() {
    const selector = ".o_module_manager .o_badge, .o_kanban_view .badge, .o_kanban_record .badge";
    document.querySelectorAll(selector).forEach((badge) => {
        if (badge.textContent.trim() === "Enterprise") {
            badge.classList.add("d-none");
        }
    });
}

/**
 * Masquage des tags Enterprise / boutons Share selon les paramètres
 * Debranding : les toggles posent des classes CSS sur <body> et un scan
 * DOM masque les badges textuels "Enterprise".
 */
patch(WebClient.prototype, {
    setup() {
        super.setup();
        if (session.deep_show_share === false) {
            document.body.classList.add("o_deep_hide_share");
        }
        if (session.deep_show_enterprise === false) {
            document.body.classList.add("o_deep_hide_enterprise");
            browser.addEventListener("hashchange", () => {
                setTimeout(hideEnterpriseBadges, 500);
            });
            const observer = new MutationObserver(() => hideEnterpriseBadges());
            const start = () => {
                const kanban = document.querySelector(".o_module_manager");
                if (kanban) {
                    observer.observe(kanban, { childList: true, subtree: true });
                }
                hideEnterpriseBadges();
            };
            setTimeout(start, 1500);
        }
    },
});
