package com.ftsm.knowledge.web;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ftsm.knowledge.entity.Doc;
import com.ftsm.knowledge.mapper.DocMapper;
import com.ftsm.knowledge.mapper.QueryLogMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Public knowledge API. Shapes keep the legacy keys the frontend already consumes
 * ({"documents":[{name,size,modified,...}]}); the values now come from the doc table,
 * which is the single authority for indexing state.
 */
@RestController
public class KnowledgeController {

    private final DocMapper docMapper;
    private final com.ftsm.knowledge.mapper.QueryLogMapper queryLogMapper;

    public KnowledgeController(DocMapper docMapper, QueryLogMapper queryLogMapper) {
        this.docMapper = docMapper;
        this.queryLogMapper = queryLogMapper;
    }

    /**
     * Document list. Legacy behaviour (no params) returns every row so existing
     * consumers (desktop client.ts) keep working; when page/size are supplied the
     * query is LIMIT/OFFSET-bounded and total is included for the pager.
     */
    @GetMapping("/api/documents")
    public Map<String, Object> listDocuments(
            @org.springframework.web.bind.annotation.RequestParam(required = false) Integer page,
            @org.springframework.web.bind.annotation.RequestParam(required = false) Integer size) {
        boolean paginated = page != null || size != null;
        int p = page == null ? 1 : Math.max(1, page);
        int s = size == null ? 100 : Math.min(Math.max(1, size), 200);

        LambdaQueryWrapper<Doc> wrapper = new LambdaQueryWrapper<Doc>()
                .orderByDesc(Doc::getUpdatedAt);
        if (paginated) {
            wrapper.last("LIMIT " + s + " OFFSET " + (long) (p - 1) * s);
        }
        List<Map<String, Object>> documents = docMapper.selectList(wrapper)
                .stream()
                .map(doc -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("name", doc.getName());
                    // 与 Python 侧契约对齐：uploads/ 前缀 = 用户上传，其余 = 官方语料
                    row.put("source", doc.getName() != null && doc.getName().startsWith("uploads/") ? "upload" : "official");
                    row.put("size", doc.getSize());
                    row.put("modified", doc.getUpdatedAt());
                    row.put("doc_id", doc.getDocId());
                    row.put("title", doc.getTitle());
                    row.put("source_type", doc.getSourceType());
                    row.put("source_url", doc.getSourceUrl());
                    row.put("status", doc.getStatus());
                    row.put("error", doc.getError());
                    row.put("chunk_count", doc.getChunkCount());
                    row.put("indexed", "READY".equals(doc.getStatus()));
                    row.put("stale", false);
                    row.put("covered_by", null);
                    return row;
                })
                .toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("documents", documents);
        if (paginated) {
            result.put("page", p);
            result.put("size", s);
            result.put("total", docMapper.selectCount(null));
        }
        return result;
    }

    @GetMapping("/api/knowledge/stats")
    public Map<String, Object> stats() {
        List<Doc> all = docMapper.selectList(null);
        long ready = all.stream().filter(d -> "READY".equals(d.getStatus())).count();
        long totalChunks = all.stream().mapToLong(d -> d.getChunkCount() == null ? 0 : d.getChunkCount()).sum();
        String lastIndexed = all.stream()
                .map(Doc::getIndexedAt)
                .filter(java.util.Objects::nonNull)
                .max(Long::compare)
                .map(sec -> java.time.Instant.ofEpochSecond(sec).toString())
                .orElse(null);
        String lastError = all.stream()
                .filter(d -> "FAILED".equals(d.getStatus()))
                .max(java.util.Comparator.comparing(Doc::getUpdatedAt))
                .map(Doc::getError)
                .orElse(null);

        Map<String, Long> sourceTypeCounts = new LinkedHashMap<>();
        all.forEach(doc -> sourceTypeCounts.merge(
                doc.getSourceType() == null ? "file" : doc.getSourceType(), 1L, Long::sum));

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("document_count", all.size());
        stats.put("ready_count", ready);
        stats.put("indexing_count", all.size() - ready - all.stream().filter(d -> "FAILED".equals(d.getStatus())).count());
        stats.put("manifest_records", all.size());
        stats.put("total_chunks", totalChunks);
        stats.put("last_indexed", lastIndexed);
        // Semantic cache lives inside ftsm-rag; the dashboard fetches /api/cache/stats there.
        stats.put("cache_entries", 0);
        stats.put("index_version", 0);
        stats.put("index_updated_at", lastIndexed);
        stats.put("index_last_error", lastError);
        stats.put("source_type_counts", sourceTypeCounts);
        return stats;
    }

    @GetMapping("/api/training/status")
    public Map<String, Object> trainingStatus() {
        long indexing = docMapper.selectCount(new LambdaQueryWrapper<Doc>().eq(Doc::getStatus, "INDEXING"));
        Doc latest = docMapper.selectOne(new LambdaQueryWrapper<Doc>()
                .orderByDesc(Doc::getUpdatedAt)
                .last("LIMIT 1"));
        Object lastResult = latest != null && "READY".equals(latest.getStatus()) ? "success" : null;
        Object lastError = latest != null && "FAILED".equals(latest.getStatus()) ? latest.getError() : null;
        // Map.of rejects null values — an empty doc table yields nulls, so use a LinkedHashMap.
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("running", indexing > 0);
        status.put("pending", false);
        status.put("last_result", lastResult);
        status.put("last_error", lastError);
        return status;
    }

    /**
     * Trending questions: most-asked queries over the last 7 days, aggregated in SQL
     * (see QueryLogMapper.selectPopular) from the query_log rows produced by the
     * retrieval.logged consumer. Feeds the "Trending questions" section on the guide
     * page (click a chip to ask).
     */
    @GetMapping("/api/knowledge/popular")
    public Map<String, Object> popular() {
        long since = java.time.Instant.now().getEpochSecond() - 7L * 24 * 3600;
        long total = queryLogMapper.selectCount(
                new LambdaQueryWrapper<com.ftsm.knowledge.entity.QueryLog>()
                        .ge(com.ftsm.knowledge.entity.QueryLog::getCreatedAt, since));

        List<Map<String, Object>> items = queryLogMapper.selectPopular(since).stream()
                .map(row -> {
                    Map<String, Object> r = new LinkedHashMap<>();
                    r.put("question", row.get("question"));
                    r.put("count", row.get("cnt"));
                    Object hit = row.get("latest_hit");
                    r.put("hit", hit != null && ((Number) hit).longValue() != 0);
                    return r;
                })
                .toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("window_days", 7);
        result.put("total_queries", total);
        result.put("items", items);
        return result;
    }

    @GetMapping("/api/retrieval/quality")
    public Map<String, Object> quality() {
        long total = queryLogMapper.selectCount(null);
        long hits = queryLogMapper.selectCount(new LambdaQueryWrapper<com.ftsm.knowledge.entity.QueryLog>()
                .eq(com.ftsm.knowledge.entity.QueryLog::getHit, true));
        List<com.ftsm.knowledge.entity.QueryLog> recent = queryLogMapper.selectList(
                new LambdaQueryWrapper<com.ftsm.knowledge.entity.QueryLog>()
                        .orderByDesc(com.ftsm.knowledge.entity.QueryLog::getId)
                        .last("LIMIT 50"));
        double avgLatency = recent.stream().mapToInt(r -> r.getLatencyMs() == null ? 0 : r.getLatencyMs())
                .average().orElse(0);
        double avgScore = recent.stream().mapToDouble(r -> r.getTopScore() == null ? 0 : r.getTopScore())
                .average().orElse(0);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", total);
        result.put("hit", hits);
        result.put("miss", total - hits);
        result.put("hit_rate", total == 0 ? 0D : Math.round(hits * 10000D / total) / 100D);
        result.put("avg_latency_ms", Math.round(avgLatency));
        result.put("avg_top_score", Math.round(avgScore * 10000D) / 10000D);
        result.put("recent", recent);
        return result;
    }
}
