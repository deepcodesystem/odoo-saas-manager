/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

patch(WebClient.prototype, {
    setup() {
        super.setup();
        // "zopenerp" est la clé de titre globale du web client
        this.title.setParts({ zopenerp: session.deep_system_name || "DeepOS" });
    },
});
