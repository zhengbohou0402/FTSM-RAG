-- FTSM-RAG microservices schema (executed automatically by the MySQL container on first start)
-- Timestamps are epoch seconds (BIGINT) to keep parity with the legacy Python contracts.

CREATE DATABASE IF NOT EXISTS ftsm_user DEFAULT CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS ftsm_conversation DEFAULT CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS ftsm_knowledge DEFAULT CHARACTER SET utf8mb4;

USE ftsm_user;

CREATE TABLE IF NOT EXISTS student (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id    VARCHAR(80)  NOT NULL UNIQUE,
    display_name  VARCHAR(80)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    BIGINT       NOT NULL,
    updated_at    BIGINT       NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

USE ftsm_conversation;

CREATE TABLE IF NOT EXISTS conversation (
    id         VARCHAR(36)  PRIMARY KEY,
    student_id VARCHAR(80)  NOT NULL,
    title      VARCHAR(200) NOT NULL DEFAULT 'New chat',
    created_at BIGINT       NOT NULL,
    updated_at BIGINT       NOT NULL,
    KEY idx_student_updated (student_id, updated_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS conversation_message (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36)   NOT NULL,
    role            VARCHAR(16)   NOT NULL,
    content         MEDIUMTEXT    NOT NULL,
    created_at      BIGINT        NOT NULL,
    KEY idx_conv (conversation_id, id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

USE ftsm_knowledge;

-- status: INDEXING -> READY | FAILED (state machine; doc_id is the authority key)
CREATE TABLE IF NOT EXISTS doc (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    doc_id      VARCHAR(128)  NOT NULL UNIQUE,
    name        VARCHAR(500)  NOT NULL,
    title       VARCHAR(500)  NOT NULL,
    source_type VARCHAR(32)   NOT NULL DEFAULT 'file',
    source_url  VARCHAR(500)  NOT NULL DEFAULT '',
    size        BIGINT        NOT NULL DEFAULT 0,
    file_hash   VARCHAR(64)   NOT NULL DEFAULT '',
    chunk_ids   MEDIUMTEXT    NOT NULL DEFAULT '[]',
    chunk_count INT           NOT NULL DEFAULT 0,
    status      VARCHAR(16)   NOT NULL DEFAULT 'INDEXING',
    error       VARCHAR(1000) NOT NULL DEFAULT '',
    indexed_at  BIGINT        NULL,
    created_at  BIGINT        NOT NULL,
    updated_at  BIGINT        NOT NULL,
    KEY idx_status (status)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS query_log (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    question   VARCHAR(255)  NOT NULL,
    hit        TINYINT(1)    NOT NULL DEFAULT 0,
    hit_count  INT           NOT NULL DEFAULT 0,
    top_score  DOUBLE        NOT NULL DEFAULT 0,
    sources    VARCHAR(1000) NOT NULL DEFAULT '',
    latency_ms INT           NOT NULL DEFAULT 0,
    created_at BIGINT        NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
