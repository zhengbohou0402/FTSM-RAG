package com.ftsm.knowledge.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

@TableName("doc")
public class Doc {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String docId;
    private String name;
    private String title;
    private String sourceType;
    private String sourceUrl;
    private Long size;
    private String fileHash;
    /** JSON array string of deterministic chunk ids owned by ftsm-rag. */
    private String chunkIds;
    private Integer chunkCount;
    private String status;
    private String error;
    private Long indexedAt;
    private Long createdAt;
    private Long updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getDocId() { return docId; }
    public void setDocId(String docId) { this.docId = docId; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getSourceType() { return sourceType; }
    public void setSourceType(String sourceType) { this.sourceType = sourceType; }
    public String getSourceUrl() { return sourceUrl; }
    public void setSourceUrl(String sourceUrl) { this.sourceUrl = sourceUrl; }
    public Long getSize() { return size; }
    public void setSize(Long size) { this.size = size; }
    public String getFileHash() { return fileHash; }
    public void setFileHash(String fileHash) { this.fileHash = fileHash; }
    public String getChunkIds() { return chunkIds; }
    public void setChunkIds(String chunkIds) { this.chunkIds = chunkIds; }
    public Integer getChunkCount() { return chunkCount; }
    public void setChunkCount(Integer chunkCount) { this.chunkCount = chunkCount; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getError() { return error; }
    public void setError(String error) { this.error = error; }
    public Long getIndexedAt() { return indexedAt; }
    public void setIndexedAt(Long indexedAt) { this.indexedAt = indexedAt; }
    public Long getCreatedAt() { return createdAt; }
    public void setCreatedAt(Long createdAt) { this.createdAt = createdAt; }
    public Long getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Long updatedAt) { this.updatedAt = updatedAt; }
}
