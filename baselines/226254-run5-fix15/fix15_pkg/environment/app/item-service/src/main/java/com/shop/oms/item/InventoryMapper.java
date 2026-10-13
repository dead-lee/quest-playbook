package com.shop.oms.item;

import java.math.BigDecimal;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface InventoryMapper {

    @Select("SELECT unit_price FROM inventory WHERE product_id = #{productId}")
    BigDecimal priceOf(@Param("productId") long productId);

    @Update("UPDATE inventory SET reserved = reserved + #{delta} WHERE product_id = #{productId}")
    int addReserved(@Param("productId") long productId, @Param("delta") int delta);

    @Update("UPDATE inventory SET unit_price = unit_price + #{delta} WHERE product_id BETWEEN #{fromId} AND #{toId}")
    int repriceRange(@Param("fromId") long fromId, @Param("toId") long toId, @Param("delta") BigDecimal delta);
}
