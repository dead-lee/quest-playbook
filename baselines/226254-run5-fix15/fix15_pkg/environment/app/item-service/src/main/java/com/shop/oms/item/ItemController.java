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

    @GetMapping("/items/{orderId}")
    public List<OrderItem> lines(@PathVariable long orderId) {
        return service.lines(orderId);
    }
}
