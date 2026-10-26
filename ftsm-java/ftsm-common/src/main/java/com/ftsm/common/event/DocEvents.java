package com.ftsm.common.event;

/**
 * MQ event contract between ftsm-knowledge (owner of document state) and ftsm-rag
 * (indexing worker). Mirrors the tjxt pattern: PAY_EXCHANGE + trade.pay.success.queue
 * with atomic state migration on the consumer side for idempotency.
 */
public final class DocEvents {

    private DocEvents() {
    }

    public static final String EXCHANGE = "ftsm.doc.exchange";

    public static final String KEY_INDEX_REQUESTED = "doc.index.requested";
    public static final String KEY_INDEX_SUCCEEDED = "doc.index.succeeded";
    public static final String KEY_INDEX_FAILED = "doc.index.failed";
    public static final String KEY_INDEX_DEAD = "doc.index.dead";
    public static final String KEY_DOC_DELETED = "doc.deleted";
    public static final String KEY_RETRIEVAL_LOGGED = "retrieval.logged";

    public static final String QUEUE_INDEX_REQUEST = "doc.index.request.queue";
    public static final String QUEUE_INDEX_RESULT = "doc.index.result.queue";
    public static final String QUEUE_RETRIEVAL_LOG = "retrieval.log.queue";
    public static final String QUEUE_INDEX_DEAD_LETTER = "doc.index.dlq";
}
