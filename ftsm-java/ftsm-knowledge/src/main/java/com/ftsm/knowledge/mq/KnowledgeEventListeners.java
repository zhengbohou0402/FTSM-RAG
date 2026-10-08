package com.ftsm.knowledge.mq;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ftsm.common.event.DocEvents;
import com.ftsm.knowledge.entity.Doc;
import com.ftsm.knowledge.mapper.DocMapper;
import com.ftsm.knowledge.mapper.QueryLogMapper;
import com.ftsm.knowledge.entity.QueryLog;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Consumes indexing results and retrieval-log events. All state transitions are
 * atomic ("WHERE status = 'INDEXING'") so duplicated deliveries are harmless no-ops —
 * same idempotency approach as the tjxt payment-success consumer.
 */
@Component
public class KnowledgeEventListeners {

    private static final Logger log = LoggerFactory.getLogger(KnowledgeEventListeners.class);

    private final DocMapper docMapper;
    private final QueryLogMapper queryLogMapper;
    private final ObjectMapper objectMapper;

    public KnowledgeEventListeners(DocMapper docMapper, QueryLogMapper queryLogMapper, ObjectMapper objectMapper) {
        this.docMapper = docMapper;
        this.queryLogMapper = queryLogMapper;
        this.objectMapper = objectMapper;
    }

    @RabbitListener(queues = DocEvents.QUEUE_INDEX_RESULT)
    public void onIndexResult(JsonNode payload) {
        String kind = payload.path("kind").asText("");
        String docId = payload.path("docId").asText("");
        if (docId.isBlank()) {
            log.warn("[mq] index result without docId: {}", payload);
            return;
        }
        long now = Instant.now().getEpochSecond();
        switch (kind) {
            case "succeeded" -> migrate(docId, "READY", "", payload, now);
            case "failed" -> migrate(docId, "FAILED",
                    truncate(payload.path("error").asText("Indexing failed")), payload, now);
            case "deleted" -> docMapper.delete(new LambdaQueryWrapper<Doc>().eq(Doc::getDocId, docId));
            default -> log.warn("[mq] unknown index result kind={} docId={}", kind, docId);
        }
    }

    private void migrate(String docId, String targetStatus, String error, JsonNode payload, long now) {
        List<String> chunkIds = new ArrayList<>();
        payload.path("chunkIds").forEach(node -> chunkIds.add(node.asText()));
        LambdaUpdateWrapper<Doc> update = new LambdaUpdateWrapper<Doc>()
                .eq(Doc::getDocId, docId)
                .eq(Doc::getStatus, "INDEXING")
                .set(Doc::getStatus, targetStatus)
                .set(Doc::getError, error)
                .set(Doc::getChunkIds, toJson(chunkIds))
                .set(Doc::getChunkCount, chunkIds.size())
                .set(Doc::getIndexedAt, "READY".equals(targetStatus) ? now : null)
                .set(Doc::getUpdatedAt, now);
        int updated = docMapper.update(null, update);
        if (updated == 0) {
            // Duplicate delivery or already migrated — safe to acknowledge.
            log.info("[mq] idempotent skip: docId={} already migrated (target={})", docId, targetStatus);
        }
    }

    @RabbitListener(queues = DocEvents.QUEUE_RETRIEVAL_LOG)
    public void onRetrievalLogged(JsonNode payload) {
        QueryLog row = new QueryLog();
        row.setQuestion(truncate(payload.path("question").asText("")));
        row.setHit(payload.path("hit").asBoolean(false));
        row.setHitCount(payload.path("hitCount").asInt(0));
        row.setTopScore(payload.path("topScore").asDouble(0D));
        row.setSources(truncate(payload.path("sources").asText("")));
        row.setLatencyMs(payload.path("latencyMs").asInt(0));
        row.setCreatedAt(Instant.now().getEpochSecond());
        queryLogMapper.insert(row);
    }

    private String toJson(List<String> chunkIds) {
        try {
            return objectMapper.writeValueAsString(chunkIds);
        } catch (Exception e) {
            return "[]";
        }
    }

    private String truncate(String value) {
        String safe = value == null ? "" : value.replace("\r", " ").replace("\n", " ");
        return safe.length() > 900 ? safe.substring(0, 900) : safe;
    }
}
