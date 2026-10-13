package com.shop.oms.common;

import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

import javax.sql.DataSource;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Runs a unit of work in a local transaction, logs BEGIN / COMMIT / ROLLBACK for every
 * attempt, and retries when MySQL reports a deadlock (1213) or a lock wait timeout (1205).
 * On those errors the LATEST DETECTED DEADLOCK section of SHOW ENGINE INNODB STATUS is
 * written to the log so incidents can be analysed afterwards.
 */
@Component
public class TxRunner {

    private static final Logger log = LoggerFactory.getLogger("oms.tx");
    private static final int MAX_ATTEMPTS = 3;
    private static final AtomicLong SEQ = new AtomicLong();

    private final TransactionTemplate template;
    private final JdbcTemplate jdbc;

    public TxRunner(PlatformTransactionManager txManager, DataSource dataSource) {
        this.template = new TransactionTemplate(txManager);
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public <T> T run(String name, Supplier<T> work) {
        for (int attempt = 1; ; attempt++) {
            long txId = SEQ.incrementAndGet();
            log.info("BEGIN tx={} name={} attempt={}", txId, name, attempt);
            try {
                T result = template.execute((TransactionStatus status) -> work.get());
                log.info("COMMIT tx={} name={}", txId, name);
                return result;
            } catch (RuntimeException e) {
                int code = mysqlErrorCode(e);
                log.warn("ROLLBACK tx={} name={} attempt={} mysqlError={} cause={}", txId, name, attempt,
                        code, rootMessage(e));
                if (code == 1213 || code == 1205) {
                    log.warn("LOCK_CONFLICT tx={} name={} code={}\n{}", txId, name, code, latestDeadlock());
                    if (attempt < MAX_ATTEMPTS) {
                        sleepQuietly(20L * attempt);
                        continue;
                    }
                }
                throw e;
            }
        }
    }

    public void run(String name, Runnable work) {
        run(name, () -> {
            work.run();
            return null;
        });
    }

    static int mysqlErrorCode(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof SQLException sql && sql.getErrorCode() != 0) {
                return sql.getErrorCode();
            }
            if (t instanceof RemoteCallException rc && rc.getMysqlError() != 0) {
                return rc.getMysqlError();
            }
        }
        return 0;
    }

    private static String rootMessage(Throwable e) {
        Throwable t = e;
        while (t.getCause() != null) {
            t = t.getCause();
        }
        return t.getClass().getSimpleName() + ": " + t.getMessage();
    }

    private String latestDeadlock() {
        try {
            String status = jdbc.queryForList("SHOW ENGINE INNODB STATUS").get(0).get("Status").toString();
            int start = status.indexOf("LATEST DETECTED DEADLOCK");
            if (start < 0) {
                return "(no deadlock recorded by InnoDB yet)";
            }
            int end = status.indexOf("------------\nTRANSACTIONS", start);
            return status.substring(start, end > start ? end : status.length());
        } catch (RuntimeException ex) {
            return "(could not read InnoDB status: " + ex.getMessage() + ")";
        }
    }

    private static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }
}
