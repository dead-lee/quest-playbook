package com.shop.oms.order;

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
}
