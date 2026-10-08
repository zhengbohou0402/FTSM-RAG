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

    @GetMapping("/api/documents")
    public Map<String, Object> listDocuments() {
        List<Map<String, Object>> documents = docMapper.selectList(new LambdaQueryWrapper<Doc>()
                        .orderByDesc(Doc::getUpdatedAt))
                .stream()
                .map(doc -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("name", doc.getName());
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
        return Map.of("documents", documents);
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
                .map(String::valueOf)
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
        return Map.of(
                "running", indexing > 0,
                "pending", false,
                "last_result", lastResult,
                "last_error", lastError);
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
