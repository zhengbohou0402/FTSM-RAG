package com.ftsm.knowledge.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

@TableName("query_log")
public class QueryLog {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String question;
    private Boolean hit;
    private Integer hitCount;
    private Double topScore;
    private String sources;
    private Integer latencyMs;
    private Long createdAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getQuestion() { return question; }
    public void setQuestion(String question) { this.question = question; }
    public Boolean getHit() { return hit; }
    public void setHit(Boolean hit) { this.hit = hit; }
    public Integer getHitCount() { return hitCount; }
    public void setHitCount(Integer hitCount) { this.hitCount = hitCount; }
    public Double getTopScore() { return topScore; }
    public void setTopScore(Double topScore) { this.topScore = topScore; }
    public String getSources() { return sources; }
    public void setSources(String sources) { this.sources = sources; }
    public Integer getLatencyMs() { return latencyMs; }
    public void setLatencyMs(Integer latencyMs) { this.latencyMs = latencyMs; }
    public Long getCreatedAt() { return createdAt; }
    public void setCreatedAt(Long createdAt) { this.createdAt = createdAt; }
}
