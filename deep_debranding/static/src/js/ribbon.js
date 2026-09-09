/** @odoo-module **/
/* Copyright 2015 Sylvain Calador, 2015 Javi Melendez, 2016 Antonio Espinosa,
   2017 Thomas Binsfeld, 2017 Xavier Jiménez.
   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

import { Component, xml } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class WebEnvironmentRibbon extends Component {
    setup() {
        this.orm = useService("orm");
        useBus(this.env.bus, "WEB_CLIENT_READY", this.showRibbon.bind(this));
    }

    // Code from: http://jsfiddle.net/WK_of_Angmar/xgA5C/
    validStrColour(strToTest) {
        if (strToTest === "") {
            return false;
        }
        if (strToTest === "inherit" || strToTest === "transparent") {
            return true;
        }
        const image = document.createElement("img");
        image.style.color = "rgb(0, 0, 0)";
        image.style.color = strToTest;
        if (image.style.color !== "rgb(0, 0, 0)") {
            return true;
        }
        image.style.color = "rgb(255, 255, 255)";
        image.style.color = strToTest;
        return image.style.color !== "rgb(255, 255, 255)";
    }

    showRibbon() {
        const ribbon = document.querySelector(".test-ribbon");
        const self = this;
        ribbon.classList.add("o_hidden");
        this.orm.call("web.environment.ribbon.backend", "get_environment_ribbon").then(
            function (ribbon_data) {
                if (ribbon_data.name && ribbon_data.name !== "False" && ribbon_data.name !== "0") {
                    ribbon.classList.remove("o_hidden");
                    ribbon.innerHTML = ribbon_data.name;
                }
                if (ribbon_data.color && self.validStrColour(ribbon_data.color)) {
                    ribbon.style.color = ribbon_data.color;
                }
                if (
                    ribbon_data.background_color &&
                    self.validStrColour(ribbon_data.background_color)
                ) {
                    ribbon.style.backgroundColor = ribbon_data.background_color;
                }
            }
        );
    }
}

WebEnvironmentRibbon.props = {};
WebEnvironmentRibbon.template = xml`<div class="test-ribbon" />`;

// Le composant peut déjà être enregistré par un autre module (ex. web_environment_ribbon OCA)
const mainComponents = registry.category("main_components");
if (!mainComponents.contains("WebEnvironmentRibbon")) {
    mainComponents.add("WebEnvironmentRibbon", {
        Component: WebEnvironmentRibbon,
    });
}
