package com.shop.oms.common;

import java.math.BigDecimal;

/** Totals of an order's lines as computed by item-service. */
public record ItemsSummary(BigDecimal total, int itemCount, int confirmedCount) {
}
