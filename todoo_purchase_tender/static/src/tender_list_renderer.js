import { onWillStart, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";
import {
    provideViewButtonHandler,
    useViewButtonHandler,
} from "@web/views/view_button/view_button_hook";

/**
 * Tender ro'yxatida eng yaxshi takliflarni yashil qiladi.
 *
 * Tuzilishi core'ning solishtirish renderer'idan olingan
 * (purchase_alternative/static/src/views/purchase_order_line_compare_list_renderer.js),
 * lekin u yerga hech qanday bog'liqlik yo'q — hisob-kitob o'z serverimizdagi
 * `purchase.order.line.get_tender_best_lines` metodida.
 */
export class TenderListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.action = useService("action");
        this.bestFields = proxy({
            price_ids: [],
            date_ids: [],
            qty_ids: [],
        });
        onWillStart(async () => {
            await this.updateBestFields();
        });
        // Choose/Cancel bosilgach ro'yxat o'zgaradi — ranglar qayta hisoblanadi.
        // Odoo 20: tugma ishlovchisi env'da emas, plugin orqali beriladi
        // (web/static/src/views/view_button/view_button_hook.js:64,71).
        const defaultOnClickViewButton = useViewButtonHandler();
        provideViewButtonHandler(async (params) => {
            await defaultOnClickViewButton(params);
            await this.updateBestFields();
        });
    }

    async updateBestFields() {
        const [priceIds, dateIds, qtyIds] = await this.props.list.model.orm.call(
            "purchase.order.line",
            "get_tender_best_lines",
            [],
            { context: this.props.list.context }
        );
        this.bestFields.price_ids = priceIds;
        this.bestFields.date_ids = dateIds;
        this.bestFields.qty_ids = qtyIds;
    }

    /**
     * Qatorni bosganda liniya emas, uning PARENT purchase.order formasi ochiladi
     * (Purchase ilovasi ichida). Choose/Cancel tugmalari o'z ishini qiladi —
     * onButtonCellClicked tugma ustida bosilganda onCellClicked'ni chaqirmaydi.
     */
    async onCellClicked(record, column, ev, newWindow) {
        const orderVal = record.data.order_id;
        const orderId = Array.isArray(orderVal)
            ? orderVal[0]
            : orderVal && orderVal.id;
        const plainOpen =
            !ev.target.special_click &&
            !this.props.list.selection.length &&
            !this.isInlineEditable(record) &&
            !this.props.archInfo.noOpen;
        if (orderId && plainOpen) {
            return this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "purchase.order",
                res_id: orderId,
                views: [[false, "form"]],
                target: "current",
            });
        }
        return super.onCellClicked(...arguments);
    }

    getCellClass(column, record) {
        let classNames = super.getCellClass(...arguments);
        const { resId } = record;
        const isBestPrice = this.bestFields.price_ids.includes(resId);
        if (
            ((column.name === "tender_price_label" ||
                column.name === "tender_price_unit_cc") &&
                isBestPrice) ||
            (column.name === "date_planned" && this.bestFields.date_ids.includes(resId)) ||
            (column.name === "product_qty" && this.bestFields.qty_ids.includes(resId))
        ) {
            classNames += " text-success fw-bold";
        }
        return classNames;
    }
}
