package com.shop.oms.item;

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

    public void reportConfirmed(long orderId, ItemsSummary summary) {
        Http.post(client, "/internal/orders/" + orderId + "/confirmed", summary, Void.class);
    }

    public void reportTotals(long orderId, ItemsSummary summary) {
        Http.post(client, "/internal/orders/" + orderId + "/totals", summary, Void.class);
    }
}
