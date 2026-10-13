package com.shop.oms.common;

/** Raised when a call to the other service fails; carries the MySQL error the remote side hit. */
public class RemoteCallException extends RuntimeException {
    private final int status;
    private final int mysqlError;

    public RemoteCallException(String message, int status, int mysqlError) {
        super(message);
        this.status = status;
        this.mysqlError = mysqlError;
    }

    public int getStatus() {
        return status;
    }

    public int getMysqlError() {
        return mysqlError;
    }
}
