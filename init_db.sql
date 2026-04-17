-- FTSM-RAG 数据库初始化脚本
-- 执行方式：mysql -u root -p123456 < init_db.sql

CREATE DATABASE IF NOT EXISTS ftsm_rag
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE ftsm_rag;

-- 学生账号表
CREATE TABLE IF NOT EXISTS students (
    student_id   VARCHAR(80)  NOT NULL PRIMARY KEY COMMENT '学号/用户名',
    display_name VARCHAR(80)  NOT NULL               COMMENT '显示名称',
    password_hash VARCHAR(200) NOT NULL               COMMENT 'pbkdf2 密码哈希',
    created_at   INT UNSIGNED NOT NULL               COMMENT '注册时间戳(秒)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学生账号';

-- 登录会话表（替代内存 AUTH_SESSIONS，重启不丢登录状态）
CREATE TABLE IF NOT EXISTS auth_sessions (
    token      VARCHAR(64)  NOT NULL PRIMARY KEY COMMENT 'Cookie Token',
    student_id VARCHAR(80)  NOT NULL               COMMENT '关联学号',
    expires_at INT UNSIGNED NOT NULL               COMMENT '过期时间戳(秒)',
    INDEX idx_student (student_id),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录会话';

-- 对话列表表
CREATE TABLE IF NOT EXISTS conversations (
    id         VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'UUID',
    student_id VARCHAR(80)  NOT NULL               COMMENT '所属学号',
    title      VARCHAR(200) NOT NULL DEFAULT 'New chat' COMMENT '对话标题',
    updated_at INT UNSIGNED NOT NULL               COMMENT '最后更新时间戳(秒)',
    INDEX idx_student_updated (student_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话列表';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36)     NOT NULL COMMENT '所属对话 UUID',
    role            ENUM('user','assistant') NOT NULL COMMENT '消息角色',
    content         MEDIUMTEXT      NOT NULL COMMENT '消息内容',
    created_at      INT UNSIGNED    NOT NULL COMMENT '消息时间戳(秒)',
    INDEX idx_conv (conversation_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='聊天消息';
