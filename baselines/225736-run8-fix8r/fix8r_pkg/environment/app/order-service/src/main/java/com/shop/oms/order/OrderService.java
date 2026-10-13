package com.shop.oms.order;

import java.util.List;

import org.springframework.stereotype.Service;

import com.shop.oms.common.BusinessException;
import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;
import com.shop.oms.common.TxRunner;

/** Owns the orders table; order lines live in item-service. */
@Service
public class OrderService {

    private final OrderMapper orders;
    private final ItemClient items;
    private final TxRunner tx;

    public OrderService(OrderMapper orders, ItemClient items, TxRunner tx) {
        this.orders = orders;
        this.items = items;
        this.tx = tx;
    }

    /** Customer edits an open order: header first, then the lines, then the totals. */
    public OrderRecord edit(long orderId, List<Line> lines) {
        tx.run("order.edit", () -> {
            if (orders.touchOpen(orderId) == 0) {
                throw new BusinessException("order " + orderId + " is not open");
            }
            ItemsSummary s = items.replace(orderId, lines);
            orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount());
        });
        return orders.findById(orderId);
    }

    /** Customer cancels an open order: lines and reservation are released, then the header is closed. */
    public OrderRecord cancel(long orderId) {
        tx.run("order.cancel", () -> {
            OrderRecord current = orders.findById(orderId);
            if (current == null || !"OPEN".equals(current.getStatus())) {
                throw new BusinessException("order " + orderId + " is not open");
            }
            items.release(orderId);
            orders.markCancelled(orderId);
        });
        return orders.findById(orderId);
    }

    /** item-service reports new line totals (price campaign). */
    public void applyTotals(long orderId, ItemsSummary s) {
        tx.run("order.totals", () -> {
            orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount());
        });
    }

    /** item-service reports that lines were confirmed. */
    public void applyConfirmed(long orderId, ItemsSummary s) {
        tx.run("order.confirmed", () -> {
            orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount());
        });
    }

    public OrderRecord get(long orderId) {
        return orders.findById(orderId);
    }
}
