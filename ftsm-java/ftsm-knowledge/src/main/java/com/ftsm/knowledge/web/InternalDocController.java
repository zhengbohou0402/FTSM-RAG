package com.ftsm.knowledge.web;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.ftsm.common.event.DocEvents;
import com.ftsm.knowledge.entity.Doc;
import com.ftsm.knowledge.mapper.DocMapper;
import com.ftsm.knowledge.mq.DocEventPublisher;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Internal API for ftsm-rag. Creating (or re-requesting) a document always inserts
 * rows in INDEXING state and publishes doc.index.requested — the file itself lives in
 * ftsm-rag's data directory, the state lives here (single authority).
 */
@RestController
@RequestMapping("/internal/docs")
public class InternalDocController {

    private final DocMapper docMapper;
    private final DocEventPublisher publisher;

    public InternalDocController(DocMapper docMapper, DocEventPublisher publisher) {
        this.docMapper = docMapper;
        this.publisher = publisher;
    }

    public record DocRegistration(String docId, String name, String title, String sourceType,
                                  String sourceUrl, Long size, String fileHash) {
    }

    public record DocRegistrationRequest(List<DocRegistration> docs) {
    }

    /** One locally-indexed document reported by ftsm-rag: docId + chunkCount + optional metadata for cold-start upsert. */
    public record DocReady(String docId, Integer chunkCount, String name, String title,
                           String sourceType, Long size, String fileHash) {
    }

    public record DocReadyRequest(List<DocReady> docs) {
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> register(@RequestBody DocRegistrationRequest request) {
        List<String> requested = new ArrayList<>();
        long now = Instant.now().getEpochSecond();
        if (request.docs() != null) {
            for (DocRegistration reg : request.docs()) {
                if (reg.docId() == null || reg.docId().isBlank()) {
                    continue;
                }
                Doc existing = docMapper.selectOne(new LambdaQueryWrapper<Doc>()
                        .eq(Doc::getDocId, reg.docId()));
                long size = reg.size() == null ? 0L : reg.size();
                if (existing == null) {
                    Doc doc = new Doc();
                    doc.setDocId(reg.docId());
                    doc.setName(orDefault(reg.name(), reg.docId()));
                    doc.setTitle(orDefault(reg.title(), reg.name()));
                    doc.setSourceType(orDefault(reg.sourceType(), "file"));
                    doc.setSourceUrl(orDefault(reg.sourceUrl(), ""));
                    doc.setSize(size);
                    doc.setFileHash(orDefault(reg.fileHash(), ""));
                    doc.setChunkIds("[]");
                    doc.setChunkCount(0);
                    doc.setStatus("INDEXING");
                    doc.setError("");
                    doc.setCreatedAt(now);
                    doc.setUpdatedAt(now);
                    docMapper.insert(doc);
                } else {
                    // Re-indexing an existing document: reset through the state machine entry point.
                    docMapper.update(null, new LambdaUpdateWrapper<Doc>()
                            .eq(Doc::getId, existing.getId())
                            .set(Doc::getStatus, "INDEXING")
                            .set(Doc::getError, "")
                            .set(Doc::getChunkIds, "[]")
                            .set(Doc::getChunkCount, 0)
                            .set(Doc::getSize, size)
                            .set(Doc::getFileHash, orDefault(reg.fileHash(), existing.getFileHash()))
                            .set(Doc::getUpdatedAt, now));
                }
                publisher.publish(DocEvents.KEY_INDEX_REQUESTED, Map.of(
                        "docId", reg.docId(),
                        "filePath", orDefault(reg.name(), reg.docId()),
                        "ts", now));
                requested.add(reg.docId());
            }
        }
        return ResponseEntity.ok(Map.of("requested", requested));
    }

    @GetMapping("/ready-ids")
    public ResponseEntity<Map<String, Object>> readyIds() {
        List<String> ready = docMapper.selectList(new LambdaQueryWrapper<Doc>()
                        .eq(Doc::getStatus, "READY")
                        .select(Doc::getDocId))
                .stream()
                .map(Doc::getDocId)
                .toList();
        return ResponseEntity.ok(Map.of("readyIds", ready));
    }

    /**
     * Marks locally-indexed documents READY.
     *
     * <p>Why this exists: the MQ event {@code doc.index.succeeded} is the only other way a row
     * leaves INDEXING. When RabbitMQ is unreachable ftsm-rag falls back to its in-process
     * training thread, which cannot publish that event — so the rows would stick at INDEXING
     * forever and {@code /api/knowledge/stats} would report a growing indexing_count that never
     * resolves. ftsm-rag closes that loop by POSTing the authoritative manifest state here
     * (see services/knowledge_client.py).
     *
     * <p>The transition is guarded by {@code WHERE status = 'INDEXING'}, so a concurrent MQ
     * delivery, a retry, or a document that is already READY are all harmless no-ops — exactly
     * the idempotency approach used by KnowledgeEventListeners.migrate.
     */
    @PostMapping("/ready")
    public ResponseEntity<Map<String, Object>> markReady(@RequestBody DocReadyRequest request) {
        List<String> updated = new ArrayList<>();
        List<String> skipped = new ArrayList<>();
        long now = Instant.now().getEpochSecond();
        if (request.docs() != null) {
            for (DocReady item : request.docs()) {
                if (item.docId() == null || item.docId().isBlank()) {
                    continue;
                }
                int chunkCount = item.chunkCount() == null ? 0 : Math.max(0, item.chunkCount());
                Doc existing = docMapper.selectOne(new LambdaQueryWrapper<Doc>()
                        .eq(Doc::getDocId, item.docId()));
                if (existing == null) {
                    // Cold-start / initial sync: document exists in manifest but not yet in MySQL
                    Doc doc = new Doc();
                    doc.setDocId(item.docId());
                    String name = orDefault(item.name(), item.docId());
                    doc.setName(name);
                    doc.setTitle(orDefault(item.title(), name));
                    doc.setSourceType(orDefault(item.sourceType(), "official"));
                    doc.setSourceUrl("");
                    doc.setSize(item.size() == null ? 0L : item.size());
                    doc.setFileHash(orDefault(item.fileHash(), ""));
                    doc.setChunkIds("[]");
                    doc.setChunkCount(chunkCount);
                    doc.setStatus("READY");
                    doc.setError("");
                    doc.setIndexedAt(now);
                    doc.setCreatedAt(now);
                    doc.setUpdatedAt(now);
                    docMapper.insert(doc);
                    updated.add(item.docId());
                } else {
                    int rows = docMapper.update(null, new LambdaUpdateWrapper<Doc>()
                            .eq(Doc::getId, existing.getId())
                            // P2-8：允许 FAILED 恢复 —— 本地重训（sync_training_result）直接报 READY，
                            // 不经过 INDEXING；只认 INDEXING 会让失败的文档永远卡在 FAILED。
                            .in(Doc::getStatus, List.of("INDEXING", "FAILED"))
                            .set(Doc::getStatus, "READY")
                            .set(Doc::getError, "")
                            .set(Doc::getChunkCount, chunkCount)
                            .set(Doc::getIndexedAt, now)
                            .set(Doc::getUpdatedAt, now));
                    if (rows > 0) {
                        updated.add(item.docId());
                    } else {
                        // Already READY (duplicate delivery)
                        skipped.add(item.docId());
                    }
                }
            }
        }
        return ResponseEntity.ok(Map.of("updated", updated, "skipped", skipped));
    }

    private static String orDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
}
