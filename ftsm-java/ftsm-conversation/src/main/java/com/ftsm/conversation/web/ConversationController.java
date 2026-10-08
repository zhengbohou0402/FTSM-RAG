package com.ftsm.conversation.web;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ftsm.conversation.entity.Conversation;
import com.ftsm.conversation.entity.ConversationMessage;
import com.ftsm.conversation.mapper.ConversationMapper;
import com.ftsm.conversation.mapper.ConversationMessageMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Student-facing conversation API. Response shapes match the legacy monolith so the
 * frontend keeps working: {"items":[{id,title,updated_at}]} and
 * {id,title,updated_at,messages:[{role,content}]}. Timestamps stay epoch seconds.
 */
@RestController
public class ConversationController {

    static final int MAX_EXPOSED_CONVERSATIONS = 50;
    static final int MAX_MESSAGES_PER_CONVERSATION = 40;

    private final ConversationMapper conversations;
    private final ConversationMessageMapper messages;

    public ConversationController(ConversationMapper conversations, ConversationMessageMapper messages) {
        this.conversations = conversations;
        this.messages = messages;
    }

    @PostMapping("/api/conversations")
    public ResponseEntity<Map<String, Object>> create(
            @RequestHeader(value = "X-Student-Id", required = false) String studentId) {
        ResponseEntity<String> guard = requireStudent(studentId);
        if (guard != null) {
            return ResponseEntity.status(guard.getStatusCode()).build();
        }
        String id = UUID.randomUUID().toString();
        long now = Instant.now().getEpochSecond();
        Conversation conv = new Conversation();
        conv.setId(id);
        conv.setStudentId(studentId);
        conv.setTitle("New chat");
        conv.setCreatedAt(now);
        conv.setUpdatedAt(now);
        conversations.insert(conv);
        return ResponseEntity.ok(Map.of("id", id, "title", "New chat", "updated_at", now, "messages", List.of()));
    }

    @GetMapping("/api/conversations")
    public ResponseEntity<Map<String, Object>> list(
            @RequestHeader(value = "X-Student-Id", required = false) String studentId) {
        ResponseEntity<String> guard = requireStudent(studentId);
        if (guard != null) {
            return ResponseEntity.status(guard.getStatusCode()).build();
        }
        List<Map<String, Object>> items = conversations.selectList(new LambdaQueryWrapper<Conversation>()
                        .eq(Conversation::getStudentId, studentId)
                        .orderByDesc(Conversation::getUpdatedAt))
                .stream()
                .limit(MAX_EXPOSED_CONVERSATIONS)
                .map(c -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", c.getId());
                    row.put("title", c.getTitle());
                    row.put("updated_at", c.getUpdatedAt());
                    return row;
                })
                .toList();
        return ResponseEntity.ok(Map.of("items", items));
    }

    @GetMapping("/api/conversations/{conversationId}")
    public ResponseEntity<Map<String, Object>> get(
            @PathVariable String conversationId,
            @RequestHeader(value = "X-Student-Id", required = false) String studentId) {
        ResponseEntity<String> guard = requireStudent(studentId);
        if (guard != null) {
            return ResponseEntity.status(guard.getStatusCode()).build();
        }
        Conversation conv = owned(studentId, conversationId);
        if (conv == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "Conversation not found"));
        }
        List<Map<String, Object>> msgs = messages.selectList(new LambdaQueryWrapper<ConversationMessage>()
                        .eq(ConversationMessage::getConversationId, conversationId)
                        .orderByAsc(ConversationMessage::getId))
                .stream()
                .map(m -> Map.<String, Object>of("role", m.getRole(), "content", m.getContent()))
                .toList();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", conv.getId());
        body.put("title", conv.getTitle());
        body.put("updated_at", conv.getUpdatedAt());
        body.put("messages", msgs);
        return ResponseEntity.ok(body);
    }

    @DeleteMapping("/api/conversations/{conversationId}")
    public ResponseEntity<Map<String, Object>> delete(
            @PathVariable String conversationId,
            @RequestHeader(value = "X-Student-Id", required = false) String studentId) {
        ResponseEntity<String> guard = requireStudent(studentId);
        if (guard != null) {
            return ResponseEntity.status(guard.getStatusCode()).build();
        }
        Conversation conv = owned(studentId, conversationId);
        if (conv == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "Conversation not found"));
        }
        conversations.deleteById(conversationId);
        messages.delete(new LambdaQueryWrapper<ConversationMessage>()
                .eq(ConversationMessage::getConversationId, conversationId));
        return ResponseEntity.ok(Map.of("ok", true));
    }

    static Conversation owned(ConversationMapper conversations, String studentId, String conversationId) {
        return conversations.selectOne(new LambdaQueryWrapper<Conversation>()
                .eq(Conversation::getId, conversationId)
                .eq(Conversation::getStudentId, studentId));
    }

    private Conversation owned(String studentId, String conversationId) {
        return owned(conversations, studentId, conversationId);
    }

    private static ResponseEntity<String> requireStudent(String studentId) {
        return studentId == null || studentId.isBlank()
                ? ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
                : null;
    }
}
