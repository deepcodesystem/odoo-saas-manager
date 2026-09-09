/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { user } from "@web/core/user";

const userMenuRegistry = registry.category("user_menuitems");

function customDocumentationItem(env) {
    const url = session.deep_documentation_url;
    return {
        type: "item",
        id: "documentation",
        description: _t("Documentation"),
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 10,
    };
}

function customSupportItem(env) {
    const url = session.deep_support_url;
    return {
        type: "item",
        id: "support",
        description: _t("Support"),
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 20,
    };
}

function customAccountItem(env) {
    const title = session.deep_account_title || _t("My Account");
    const url = session.deep_account_url;
    return {
        type: "item",
        id: "odoo_account",
        description: title,
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 60,
    };
}

function langSwitchItem(env, lang, userLang) {
    const name = lang.name || lang.code;
    return {
        type: "item",
        id: `lang_${lang.code.replace(/[^a-zA-Z0-9_]/g, "_")}`,
        description: userLang === lang.code ? `${name} ✓` : name,
        callback: async () => {
            if (lang.code === userLang) {
                return;
            }
            await env.services.orm.call("res.users", "write", [user.userId, { lang: lang.code }]);
            location.reload();
        },
        sequence: 3,
    };
}

function debugItem(env) {
    return {
        type: "item",
        id: "debug",
        description: _t("Activate the developer mode"),
        callback: () => {
            router.pushState({ debug: 1 }, { reload: true });
        },
        show: () => !env.debug || !env.debug.includes("assets"),
        sequence: 5,
    };
}

function assetsDebugItem(env) {
    return {
        type: "item",
        description: _t("Activate Assets Debugging"),
        callback: () => {
            router.pushState({ debug: "assets" }, { reload: true });
        },
        show: () => !env.debug.includes("assets"),
        sequence: 6,
    };
}

function leaveDebugItem(env) {
    return {
        type: "item",
        description: _t("Leave the Developer Tools"),
        callback: () => {
            router.pushState({ debug: 0 }, { reload: true });
        },
        show: () => !!env.debug,
        sequence: 7,
    };
}

/**
 * Remplace les items natifs pointant vers odoo.com par les valeurs
 * configurées dans Debranding, ou les masque si désactivés.
 */
export function applyDebrandingMenuItems() {
    if (session.deep_show_documentation === false) {
        try {
            userMenuRegistry.remove("documentation");
        } catch {
            // item déjà absent
        }
    } else if (session.deep_documentation_url) {
        userMenuRegistry.add("documentation", customDocumentationItem, { force: true });
    }

    if (session.deep_show_support === false) {
        try {
            userMenuRegistry.remove("support");
        } catch {
            // item déjà absent
        }
    } else if (session.deep_support_url) {
        userMenuRegistry.add("support", customSupportItem, { force: true });
    }

    if (session.deep_show_account === false) {
        try {
            userMenuRegistry.remove("odoo_account");
        } catch {
            // item déjà absent
        }
    } else if (session.deep_account_url) {
        userMenuRegistry.add("odoo_account", customAccountItem, { force: true });
    }

    // Sélecteur rapide de langues (items dynamiques par langue active)
    if (session.deep_show_lang && Array.isArray(session.deep_lang_list)) {
        const userLang = session.deep_user_lang;
        for (const lang of session.deep_lang_list) {
            userMenuRegistry.add(`lang_${lang.code.replace(/[^a-zA-Z0-9_]/g, "_")}`, (env) => langSwitchItem(env, lang, userLang), { force: true });
        }
    }

    // Mode développeur rapide (réservé aux gestionnaires)
    if (session.deep_show_debug && session.deep_is_erp_manager) {
        userMenuRegistry
            .add("debug", debugItem, { force: true })
            .add("asset_asset", assetsDebugItem, { force: true })
            .add("leave_debug", leaveDebugItem, { force: true })
            .add("deep_separator", () => ({ type: "separator", sequence: 8 }), { force: true });
    }
}

applyDebrandingMenuItems();
