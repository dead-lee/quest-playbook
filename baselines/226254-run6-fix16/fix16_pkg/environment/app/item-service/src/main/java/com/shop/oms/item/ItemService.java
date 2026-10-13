package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;
import com.shop.oms.common.TxRunner;

/** Owns order_items and inventory. */
@Service
public class ItemService {

    private final OrderItemMapper items;
    private final InventoryMapper inventory;
    private final OrderClient orders;
    private final TxRunner tx;

    public ItemService(OrderItemMapper items, InventoryMapper inventory, OrderClient orders, TxRunner tx) {
        this.items = items;
        this.inventory = inventory;
        this.orders = orders;
        this.tx = tx;
    }

    /** Replace all lines of an order and move the inventory reservation accordingly. */
    public ItemsSummary replaceLines(long orderId, List<Line> lines) {
        return tx.run("items.replace", () -> {
            Map<Long, Integer> reserveDelta = new LinkedHashMap<>();
            for (OrderItem old : items.findByOrder(orderId)) {
                reserveDelta.merge(old.getProductId(), -old.getQty(), Integer::sum);
            }
            items.deleteByOrder(orderId);
            for (Line line : lines) {
                OrderItem item = new OrderItem();
                item.setOrderId(orderId);
                item.setProductId(line.productId());
                item.setQty(line.qty());
                item.setUnitPrice(inventory.priceOf(line.productId()));
                items.insert(item);
                reserveDelta.merge(line.productId(), line.qty(), Integer::sum);
            }
            reserveDelta.forEach((productId, delta) -> {
                if (delta != 0) {
                    inventory.addReserved(productId, delta);
                }
            });
            return summary(orderId);
        });
    }

    /** Confirm all pending lines and report the new confirmed count to order-service. */
    public ItemsSummary confirm(long orderId) {
        return tx.run("items.confirm", () -> {
            items.confirmPending(orderId);
            ItemsSummary summary = summary(orderId);
            orders.reportConfirmed(orderId, summary);
            return summary;
        });
    }

    /** Remove all lines of a cancelled order and release their reservation. */
    public ItemsSummary release(long orderId) {
        return tx.run("items.release", () -> {
            List<OrderItem> old = items.findByOrder(orderId);
            items.deleteByOrder(orderId);
            for (OrderItem item : old) {
                inventory.addReserved(item.getProductId(), -item.getQty());
            }
            return summary(orderId);
        });
    }

    /** Price campaign: change the price of a product range, including lines already on orders. */
    public int reprice(long fromId, long toId, BigDecimal delta) {
        return tx.run("items.reprice", () -> {
            inventory.repriceRange(fromId, toId, delta);
            items.repriceProducts(fromId, toId, delta);
            List<Long> affected = items.ordersWithProducts(fromId, toId);
            for (Long orderId : affected) {
                orders.reportTotals(orderId, summary(orderId));
            }
            return affected.size();
        });
    }

    public ItemsSummary summary(long orderId) {
        return new ItemsSummary(items.sumAmount(orderId), items.countItems(orderId), items.countConfirmed(orderId));
    }

    public List<OrderItem> lines(long orderId) {
        return items.findByOrder(orderId);
    }
}
