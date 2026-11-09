import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { TenderListRenderer } from "./tender_list_renderer";

export const tenderListView = {
    ...listView,
    Renderer: TenderListRenderer,
};

registry.category("views").add("tender_list", tenderListView);
