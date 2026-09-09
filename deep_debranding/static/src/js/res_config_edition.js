/** @odoo-module **/

import { session } from "@web/session";
import { registry } from "@web/core/registry";
import { Setting } from "@web/views/form/setting/setting";

import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Remplace le widget natif "res_config_edition" (section "À propos" des
 * réglages) pour afficher le nom système configuré via Debranding au lieu
 * de "Odoo". Le template natif référence des variables indisponibles dans
 * le contexte de rendu OWL ; on fournit donc notre propre composant qui
 * expose explicitement les valeurs.
 */
class DeepResConfigEdition extends Component {
    static template = "deep_debranding.ResConfigEdition";
    static components = { Setting };
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.systemName = session.deep_system_name || "DeepOS";
        this.serverVersion = session.server_version || "";
    }
}

registry.category("view_widgets").add(
    "res_config_edition",
    { component: DeepResConfigEdition },
    { force: true },
);
