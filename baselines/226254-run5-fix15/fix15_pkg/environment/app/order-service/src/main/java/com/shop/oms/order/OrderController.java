package com.shop.oms.order;

import java.util.List;

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

    @PostMapping("/internal/orders/{id}/totals")
    public void totals(@PathVariable long id, @RequestBody ItemsSummary s) {
        service.applyTotals(id, s);
    }

    @PostMapping("/internal/orders/{id}/confirmed")
    public void confirmed(@PathVariable long id, @RequestBody ItemsSummary s) {
        service.applyConfirmed(id, s);
    }
}
