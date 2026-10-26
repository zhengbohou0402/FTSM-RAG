package com.ftsm.knowledge.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.ftsm.knowledge.entity.QueryLog;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

public interface QueryLogMapper extends BaseMapper<QueryLog> {

    /**
     * Trending questions aggregated in SQL instead of Java:
     * group by question over the time window, order by frequency, and join back
     * on MAX(id) so "hit" reflects the most recent occurrence of each question.
     */
    @Select("""
            SELECT q.question AS question, t.cnt AS cnt, (q.hit = 1) AS latest_hit
            FROM query_log q
            JOIN (
                SELECT question, MAX(id) AS max_id, COUNT(*) AS cnt
                FROM query_log
                WHERE created_at >= #{since} AND question IS NOT NULL AND question != ''
                GROUP BY question
                ORDER BY cnt DESC
                LIMIT 6
            ) t ON q.id = t.max_id
            ORDER BY t.cnt DESC
            """)
    List<Map<String, Object>> selectPopular(@Param("since") long since);
}
