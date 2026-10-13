#!/bin/bash
# Reference fix: one lock order for the whole system and no gap/next-key locks.
#  * order-service coordinates every write: it locks the orders row(s) by primary key FOR UPDATE
#    (ascending) before item-service touches lines; confirm and reprice are routed through it.
#  * item-service writes only by primary key (order_items ascending id, then inventory ascending
#    product_id) and never calls back to order-service while holding locks.
set -e
cd /app
cat > 'order-service/src/main/java/com/shop/oms/order/OrderMapper.java' <<'JAVA_EOF'
package com.shop.oms.order;

import java.math.BigDecimal;
import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderMapper {

    @Select("SELECT id, order_no, customer_id, status, total_amount, item_count, confirmed_count, version "
            + "FROM orders WHERE id = #{id}")
    OrderRecord findById(@Param("id") long id);

    @Select("SELECT id, order_no, customer_id, status, total_amount, item_count, confirmed_count, version "
            + "FROM orders WHERE id = #{id} FOR UPDATE")
    OrderRecord lockById(@Param("id") long id);

    @Select({"<script>SELECT id FROM orders WHERE id IN "
            + "<foreach collection='ids' item='id' open='(' separator=',' close=')'>#{id}</foreach> "
            + "ORDER BY id FOR UPDATE</script>"})
    List<Long> lockByIds(@Param("ids") List<Long> ids);

    @Update("UPDATE orders SET version = version + 1, updated_at = NOW(6) WHERE id = #{id} AND status = 'OPEN'")
    int touchOpen(@Param("id") long id);

    @Update("UPDATE orders SET total_amount = #{total}, item_count = #{itemCount}, confirmed_count = #{confirmedCount}, "
            + "updated_at = NOW(6) WHERE id = #{id}")
    int updateSummary(@Param("id") long id, @Param("total") BigDecimal total, @Param("itemCount") int itemCount,
            @Param("confirmedCount") int confirmedCount);

    @Update("UPDATE orders SET status = 'CANCELLED', total_amount = 0, item_count = 0, confirmed_count = 0, "
            + "version = version + 1, updated_at = NOW(6) WHERE id = #{id}")
    int markCancelled(@Param("id") long id);
}
JAVA_EOF
cat > 'order-service/src/main/java/com/shop/oms/order/ItemClient.java' <<'JAVA_EOF'
package com.shop.oms.order;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import com.shop.oms.common.Http;
import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;

/** Calls item-service, which owns order_items and inventory. */
@Component
public class ItemClient {

    private final RestClient client;

    public ItemClient(@Value("${oms.item-service.url}") String baseUrl) {
        this.client = Http.client(baseUrl);
    }

    public ItemsSummary replace(long orderId, List<Line> lines) {
        return Http.post(client, "/internal/items/" + orderId + "/replace", Map.of("lines", lines), ItemsSummary.class);
    }

    public ItemsSummary release(long orderId) {
        return Http.post(client, "/internal/items/" + orderId + "/release", null, ItemsSummary.class);
    }

    public ItemsSummary confirmLines(long orderId) {
        return Http.post(client, "/internal/items/" + orderId + "/confirm", null, ItemsSummary.class);
    }

    public List<Long> ordersWithProducts(long fromId, long toId) {
        Long[] ids = Http.post(client, "/internal/items/orders-with-products",
                Map.of("fromProductId", fromId, "toProductId", toId), Long[].class);
        return Arrays.asList(ids);
    }

    public record RepriceLines(long fromProductId, long toProductId, BigDecimal delta, List<Long> orderIds) {
    }

    public record OrderTotals(long orderId, ItemsSummary summary) {
    }

    public Map<Long, ItemsSummary> repriceLines(long fromId, long toId, BigDecimal delta, List<Long> orderIds) {
        OrderTotals[] res = Http.post(client, "/internal/items/reprice",
                new RepriceLines(fromId, toId, delta, orderIds), OrderTotals[].class);
        Map<Long, ItemsSummary> out = new LinkedHashMap<>();
        for (OrderTotals t : res) {
            out.put(t.orderId(), t.summary());
        }
        return out;
    }
}
JAVA_EOF
cat > 'order-service/src/main/java/com/shop/oms/order/OrderService.java' <<'JAVA_EOF'
package com.shop.oms.order;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.shop.oms.common.BusinessException;
import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;
import com.shop.oms.common.TxRunner;

/**
 * Owns the orders table; order lines live in item-service.
 *
 * Lock protocol: every operation that changes an order's lines first locks the orders row(s)
 * by primary key (ascending when several), and only then lets item-service touch the lines.
 * item-service transactions only take primary-key record locks (items before inventory, each
 * in ascending key order) and never call back while holding locks.
 */
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

    private OrderRecord lockOpen(long orderId) {
        OrderRecord current = orders.lockById(orderId);
        if (current == null || !"OPEN".equals(current.getStatus())) {
            throw new BusinessException("order " + orderId + " is not open");
        }
        return current;
    }

    /** The response is the order row as written by this transaction (read before commit). */
    public OrderRecord edit(long orderId, List<Line> lines) {
        return tx.run("order.edit", () -> {
            lockOpen(orderId);
            orders.touchOpen(orderId);
            ItemsSummary s = items.replace(orderId, lines);
            orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount());
            return orders.findById(orderId);
        });
    }

    public OrderRecord cancel(long orderId) {
        return tx.run("order.cancel", () -> {
            lockOpen(orderId);
            items.release(orderId);
            orders.markCancelled(orderId);
            return orders.findById(orderId);
        });
    }

    public ItemsSummary confirm(long orderId) {
        return tx.run("order.confirm", () -> {
            OrderRecord current = orders.lockById(orderId);
            if (current == null) {
                throw new BusinessException("order " + orderId + " not found");
            }
            if (!"OPEN".equals(current.getStatus())) {
                return new ItemsSummary(BigDecimal.ZERO, 0, 0);  // cancelled: nothing to confirm
            }
            ItemsSummary s = items.confirmLines(orderId);
            orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount());
            return s;
        });
    }

    /**
     * Locks the candidate orders (ascending), then item-service locks the inventory rows and checks
     * that no other order has lines in the range; if one appeared concurrently, both transactions
     * are rolled back (nothing written, no lock waits held) and the reprice retries with it locked.
     */
    public int reprice(long fromId, long toId, BigDecimal delta) {
        TreeSet<Long> candidates = new TreeSet<>(items.ordersWithProducts(fromId, toId));
        for (int attempt = 0; ; attempt++) {
            List<Long> ids = new ArrayList<>(candidates);
            List<Long> missing = new ArrayList<>();
            Integer n;
            try {
                n = tx.run("order.reprice", () -> {
                List<Long> locked = ids.isEmpty() ? List.of() : orders.lockByIds(ids);
                Map<Long, ItemsSummary> totals = items.repriceLines(fromId, toId, delta, locked);
                totals.forEach((orderId, s) -> {
                    if (s == null) {
                        missing.add(orderId);
                    }
                });
                if (!missing.isEmpty()) {
                    throw new RetryReprice();
                }
                totals.forEach((orderId, s) -> orders.updateSummary(orderId, s.total(), s.itemCount(), s.confirmedCount()));
                int open = 0;
                for (ItemsSummary s : totals.values()) {
                    if (s.itemCount() > 0) {
                        open++;
                    }
                }
                return open;
                });
            } catch (RetryReprice r) {
                n = null;
            }
            if (n != null) {
                return n;
            }
            if (attempt >= 50) {
                throw new IllegalStateException("reprice could not settle its order set");
            }
            candidates.addAll(missing);
        }
    }

    static final class RetryReprice extends RuntimeException {
        RetryReprice() {
            super("retry reprice", null, false, false);
        }
    }

    public OrderRecord get(long orderId) {
        return orders.findById(orderId);
    }
}
JAVA_EOF
cat > 'order-service/src/main/java/com/shop/oms/order/OrderController.java' <<'JAVA_EOF'
package com.shop.oms.order;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;

@RestController
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public record EditRequest(List<Line> lines) {
    }

    public record RepriceRequest(long fromProductId, long toProductId, BigDecimal delta) {
    }

    @PostMapping("/orders/{id}/edit")
    public OrderRecord edit(@PathVariable long id, @RequestBody EditRequest req) {
        return service.edit(id, req.lines());
    }

    @PostMapping("/orders/{id}/cancel")
    public OrderRecord cancel(@PathVariable long id) {
        return service.cancel(id);
    }

    @GetMapping("/orders/{id}")
    public OrderRecord get(@PathVariable long id) {
        return service.get(id);
    }

    @PostMapping("/internal/orders/{id}/confirm")
    public ItemsSummary confirm(@PathVariable long id) {
        return service.confirm(id);
    }

    @PostMapping("/internal/orders/reprice")
    public Map<String, Object> reprice(@RequestBody RepriceRequest req) {
        return Map.of("orders", service.reprice(req.fromProductId(), req.toProductId(), req.delta()));
    }
}
JAVA_EOF
cat > 'item-service/src/main/java/com/shop/oms/item/OrderItemMapper.java' <<'JAVA_EOF'
package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.List;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderItemMapper {

    @Select("SELECT id, order_id, product_id, qty, unit_price, status FROM order_items WHERE order_id = #{orderId} ORDER BY id")
    List<OrderItem> findByOrder(@Param("orderId") long orderId);

    @Delete("DELETE FROM order_items WHERE order_id = #{orderId}")
    int deleteByOrder(@Param("orderId") long orderId);

    @Delete("DELETE FROM order_items WHERE id = #{id}")
    int deleteById(@Param("id") long id);

    @Update("UPDATE order_items SET status = 'CONFIRMED' WHERE id = #{id}")
    int confirmById(@Param("id") long id);

    @Update("UPDATE order_items SET unit_price = unit_price + #{delta} WHERE id = #{id}")
    int repriceById(@Param("id") long id, @Param("delta") BigDecimal delta);

    @Insert("INSERT INTO order_items (order_id, product_id, qty, unit_price, status) "
            + "VALUES (#{orderId}, #{productId}, #{qty}, #{unitPrice}, 'PENDING')")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(OrderItem item);

    @Update("UPDATE order_items SET status = 'CONFIRMED' WHERE order_id = #{orderId} AND status = 'PENDING'")
    int confirmPending(@Param("orderId") long orderId);

    @Update("UPDATE order_items SET unit_price = unit_price + #{delta} "
            + "WHERE product_id BETWEEN #{fromId} AND #{toId}")
    int repriceProducts(@Param("fromId") long fromId, @Param("toId") long toId, @Param("delta") BigDecimal delta);

    @Select("SELECT DISTINCT order_id FROM order_items WHERE product_id BETWEEN #{fromId} AND #{toId} ORDER BY order_id")
    List<Long> ordersWithProducts(@Param("fromId") long fromId, @Param("toId") long toId);

    @Select("SELECT COALESCE(SUM(qty * unit_price), 0) FROM order_items WHERE order_id = #{orderId}")
    BigDecimal sumAmount(@Param("orderId") long orderId);

    @Select("SELECT COUNT(*) FROM order_items WHERE order_id = #{orderId}")
    int countItems(@Param("orderId") long orderId);

    @Select("SELECT COUNT(*) FROM order_items WHERE order_id = #{orderId} AND status = 'CONFIRMED'")
    int countConfirmed(@Param("orderId") long orderId);
}
JAVA_EOF
cat > 'item-service/src/main/java/com/shop/oms/item/InventoryMapper.java' <<'JAVA_EOF'
package com.shop.oms.item;

import java.math.BigDecimal;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface InventoryMapper {

    @Select("SELECT unit_price FROM inventory WHERE product_id = #{productId}")
    BigDecimal priceOf(@Param("productId") long productId);

    /** Locking read by primary key: the price seen is the latest committed one and cannot change
     *  (no concurrent reprice) until this transaction ends. */
    @Select("SELECT unit_price FROM inventory WHERE product_id = #{productId} FOR UPDATE")
    BigDecimal lockPrice(@Param("productId") long productId);

    @Update("UPDATE inventory SET reserved = reserved + #{delta} WHERE product_id = #{productId}")
    int addReserved(@Param("productId") long productId, @Param("delta") int delta);

    @Update("UPDATE inventory SET unit_price = unit_price + #{delta} WHERE product_id = #{productId}")
    int repriceOne(@Param("productId") long productId, @Param("delta") BigDecimal delta);

    @Update("UPDATE inventory SET unit_price = unit_price + #{delta} WHERE product_id BETWEEN #{fromId} AND #{toId}")
    int repriceRange(@Param("fromId") long fromId, @Param("toId") long toId, @Param("delta") BigDecimal delta);
}
JAVA_EOF
cat > 'item-service/src/main/java/com/shop/oms/item/ItemService.java' <<'JAVA_EOF'
package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.stereotype.Service;

import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;
import com.shop.oms.common.TxRunner;

/**
 * Owns order_items and inventory. Callers (order-service) hold the orders row lock of every
 * order whose lines are changed here. Inside a transaction only primary-key record locks are
 * taken: order_items rows in ascending id, then inventory rows in ascending product_id. No range
 * statement on a non-unique index is used for writes, so no gap / next-key locks are taken, and
 * no remote call is made while locks are held.
 */
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

    public ItemsSummary replaceLines(long orderId, List<Line> lines) {
        return tx.run("items.replace", () -> {
            Map<Long, Integer> reserveDelta = new TreeMap<>();
            List<OrderItem> old = items.findByOrder(orderId);
            for (OrderItem o : old) {
                reserveDelta.merge(o.getProductId(), -o.getQty(), Integer::sum);
            }
            for (Line line : lines) {
                reserveDelta.merge(line.productId(), line.qty(), Integer::sum);
            }
            // Lock every inventory row this edit touches first, in ascending product_id (the same
            // order reprice uses), so prices are current and stay current until commit.
            Map<Long, BigDecimal> price = new TreeMap<>();
            for (Long productId : reserveDelta.keySet()) {
                price.put(productId, inventory.lockPrice(productId));
            }
            old.sort(Comparator.comparing(OrderItem::getId));
            for (OrderItem o : old) {
                items.deleteById(o.getId());
            }
            for (Line line : lines) {
                OrderItem item = new OrderItem();
                item.setOrderId(orderId);
                item.setProductId(line.productId());
                item.setQty(line.qty());
                item.setUnitPrice(price.get(line.productId()));
                items.insert(item);
            }
            reserveDelta.forEach((productId, delta) -> {
                if (delta != 0) {
                    inventory.addReserved(productId, delta);
                }
            });
            return summary(orderId);
        });
    }

    /** Public entry point: confirmation is coordinated by order-service (it owns the order lock). */
    public ItemsSummary confirm(long orderId) {
        return orders.confirm(orderId);
    }

    /** Called by order-service while it holds the order lock. */
    public ItemsSummary confirmLines(long orderId) {
        return tx.run("items.confirm", () -> {
            for (OrderItem o : items.findByOrder(orderId)) {
                if ("PENDING".equals(o.getStatus())) {
                    items.confirmById(o.getId());
                }
            }
            return summary(orderId);
        });
    }

    public ItemsSummary release(long orderId) {
        return tx.run("items.release", () -> {
            Map<Long, Integer> reserveDelta = new TreeMap<>();
            for (OrderItem o : items.findByOrder(orderId)) {
                items.deleteById(o.getId());
                reserveDelta.merge(o.getProductId(), -o.getQty(), Integer::sum);
            }
            reserveDelta.forEach(inventory::addReserved);
            return summary(orderId);
        });
    }

    /** Public entry point: the campaign is coordinated by order-service. */
    public int reprice(long fromId, long toId, BigDecimal delta) {
        return orders.reprice(fromId, toId, delta);
    }

    public List<Long> ordersWithProducts(long fromId, long toId) {
        return items.ordersWithProducts(fromId, toId);
    }

    public record OrderTotals(long orderId, ItemsSummary summary) {
    }

    /** Thrown inside the reprice transaction (rolls it back) when lines of unlocked orders exist. */
    static final class MissingOrders extends RuntimeException {
        final List<Long> orderIds;

        MissingOrders(List<Long> orderIds) {
            super("reprice must also lock orders " + orderIds, null, false, false);
            this.orderIds = orderIds;
        }
    }

    /**
     * Called by order-service while it holds the locks of all orderIds (ascending). Inventory rows
     * are locked first (ascending product_id, same order as edit), so no edit can price a line with
     * the old price after this point; then the line set is re-read: if an order outside orderIds
     * got lines in the range meanwhile, nothing is changed and those order ids are returned with a
     * null summary so the caller retries with them locked too.
     */
    public List<OrderTotals> repriceLines(long fromId, long toId, BigDecimal delta, List<Long> orderIds) {
        try {
            return tx.run("items.reprice", () -> {
                for (long p = fromId; p <= toId; p++) {
                    inventory.lockPrice(p);
                }
                List<Long> missing = new ArrayList<>(items.ordersWithProducts(fromId, toId));
                missing.removeAll(orderIds);
                if (!missing.isEmpty()) {
                    throw new MissingOrders(missing);
                }
                List<OrderItem> hit = new ArrayList<>();
                for (Long orderId : orderIds) {
                    for (OrderItem o : items.findByOrder(orderId)) {
                        if (o.getProductId() >= fromId && o.getProductId() <= toId) {
                            hit.add(o);
                        }
                    }
                }
                hit.sort(Comparator.comparing(OrderItem::getId));
                for (long p = fromId; p <= toId; p++) {
                    inventory.repriceOne(p, delta);
                }
                for (OrderItem o : hit) {
                    items.repriceById(o.getId(), delta);
                }
                List<OrderTotals> out = new ArrayList<>();
                for (Long orderId : orderIds) {
                    out.add(new OrderTotals(orderId, summary(orderId)));
                }
                return out;
            });
        } catch (MissingOrders m) {
            List<OrderTotals> out = new ArrayList<>();
            for (Long orderId : m.orderIds) {
                out.add(new OrderTotals(orderId, null));
            }
            return out;
        }
    }

    public ItemsSummary summary(long orderId) {
        return new ItemsSummary(items.sumAmount(orderId), items.countItems(orderId), items.countConfirmed(orderId));
    }

    public List<OrderItem> lines(long orderId) {
        return items.findByOrder(orderId);
    }
}
JAVA_EOF
cat > 'item-service/src/main/java/com/shop/oms/item/OrderClient.java' <<'JAVA_EOF'
package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import com.shop.oms.common.Http;
import com.shop.oms.common.ItemsSummary;

/** Calls order-service, which owns the orders table. */
@Component
public class OrderClient {

    private final RestClient client;

    public OrderClient(@Value("${oms.order-service.url}") String baseUrl) {
        this.client = Http.client(baseUrl);
    }

    public ItemsSummary confirm(long orderId) {
        return Http.post(client, "/internal/orders/" + orderId + "/confirm", null, ItemsSummary.class);
    }

    @SuppressWarnings("unchecked")
    public int reprice(long fromId, long toId, BigDecimal delta) {
        Map<String, Object> r = Http.post(client, "/internal/orders/reprice",
                Map.of("fromProductId", fromId, "toProductId", toId, "delta", delta), Map.class);
        return ((Number) r.get("orders")).intValue();
    }
}
JAVA_EOF
cat > 'item-service/src/main/java/com/shop/oms/item/ItemController.java' <<'JAVA_EOF'
package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.shop.oms.common.ItemsSummary;
import com.shop.oms.common.Line;

@RestController
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    public record ReplaceRequest(List<Line> lines) {
    }

    public record RepriceRequest(long fromProductId, long toProductId, BigDecimal delta) {
    }

    @PostMapping("/internal/items/{orderId}/replace")
    public ItemsSummary replace(@PathVariable long orderId, @RequestBody ReplaceRequest req) {
        return service.replaceLines(orderId, req.lines());
    }

    @PostMapping("/internal/items/{orderId}/release")
    public ItemsSummary release(@PathVariable long orderId) {
        return service.release(orderId);
    }

    /** Public: warehouse confirms the pending lines of an order. */
    @PostMapping("/items/{orderId}/confirm")
    public ItemsSummary confirm(@PathVariable long orderId) {
        return service.confirm(orderId);
    }

    /** Public: pricing team runs a price campaign over a product id range. */
    @PostMapping("/items/reprice")
    public Map<String, Object> reprice(@RequestBody RepriceRequest req) {
        return Map.of("orders", service.reprice(req.fromProductId(), req.toProductId(), req.delta()));
    }

    @PostMapping("/internal/items/{orderId}/confirm")
    public ItemsSummary confirmLines(@PathVariable long orderId) {
        return service.confirmLines(orderId);
    }

    public record RangeRequest(long fromProductId, long toProductId) {
    }

    @PostMapping("/internal/items/orders-with-products")
    public List<Long> ordersWithProducts(@RequestBody RangeRequest req) {
        return service.ordersWithProducts(req.fromProductId(), req.toProductId());
    }

    public record RepriceLinesRequest(long fromProductId, long toProductId, BigDecimal delta, List<Long> orderIds) {
    }

    @PostMapping("/internal/items/reprice")
    public List<ItemService.OrderTotals> repriceLines(@RequestBody RepriceLinesRequest req) {
        return service.repriceLines(req.fromProductId(), req.toProductId(), req.delta(), req.orderIds());
    }

    @GetMapping("/items/{orderId}")
    public List<OrderItem> lines(@PathVariable long orderId) {
        return service.lines(orderId);
    }
}
JAVA_EOF
mvn -o -q -B package -DskipTests
rm -rf /app/*/target
echo 'reference fix applied'
