package com.shop.oms.common;

/** Rejected business request (e.g. order not open); mapped to HTTP 409. */
public class BusinessException extends RuntimeException {
    public BusinessException(String message) {
        super(message);
    }
}
