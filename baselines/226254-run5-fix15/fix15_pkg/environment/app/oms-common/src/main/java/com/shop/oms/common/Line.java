package com.shop.oms.common;

/** One requested order line: product and quantity. */
public record Line(long productId, int qty) {
}
