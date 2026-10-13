package com.shop.oms.order;

import java.math.BigDecimal;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderMapper {

    @Select("SELECT id, order_no, customer_id, status, total_amount, item_count, confirmed_count, version "
            + "FROM orders WHERE id = #{id}")
    OrderRecord findById(@Param("id") long id);

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
