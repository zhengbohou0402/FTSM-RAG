package com.ftsm.conversation.web;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ftsm.conversation.entity.Conversation;
import com.ftsm.conversation.entity.ConversationMessage;
import com.ftsm.conversation.mapper.ConversationMapper;
import com.ftsm.conversation.mapper.ConversationMessageMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Internal API consumed by ftsm-rag after each chat turn (replaces the in-process
 * ConversationStore). Callers must come from the gateway network; student scoping is
 * enforced by the X-Student-Id header the gateway attaches after session verification.
 */
@RestController
@RequestMapping("/internal/conversations")
public class InternalConversationController {

    private final ConversationMapper conversations;
    private final ConversationMessageMapper messages;

    public InternalConversationController(ConversationMapper conversations, ConversationMessageMapper messages) {
        this.conversations = conversations;
        this.messages = messages;
    }

    public record TurnRequest(String studentId, String userContent, String assistantContent, String title) {
    }

    @PostMapping("/{conversationId}/turn")
    public ResponseEntity<Map<String, Object>> appendTurn(@PathVariable String conversationId,
                                                          @RequestBody TurnRequest payload) {
        if (payload.studentId() == null || payload.studentId().isBlank()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "studentId required"));
        }
        Conversation conv = ConversationController.owned(conversations, payload.studentId(), conversationId);
        long now = Instant.now().getEpochSecond();
        if (conv == null) {
            conv = new Conversation();
            conv.setId(conversationId);
            conv.setStudentId(payload.studentId());
            conv.setTitle(payload.title() == null || payload.title().isBlank() ? "New chat" : payload.title());
            conv.setCreatedAt(now);
            conv.setUpdatedAt(now);
            conversations.insert(conv);
        } else if (payload.title() != null && !payload.title().isBlank()
                && "New chat".equals(conv.getTitle())) {
            conv.setTitle(payload.title());
        }
        conv.setUpdatedAt(now);
        conversations.updateById(conv);

        insertMessage(conversationId, "user", payload.userContent(), now);
        insertMessage(conversationId, "assistant", payload.assistantContent(), now);
        trimToCap(conversationId);
        return ResponseEntity.ok(Map.of("ok", true));
    }

    @GetMapping("/{conversationId}/recent")
    public ResponseEntity<List<Map<String, String>>> recent(@PathVariable String conversationId,
                                                            @RequestParam(defaultValue = "5") int maxTurns,
                                                            @RequestParam String studentId) {
        Conversation conv = ConversationController.owned(conversations, studentId, conversationId);
        if (conv == null) {
            return ResponseEntity.ok(List.of());
        }
        int limit = Math.max(1, maxTurns) * 2;
        List<ConversationMessage> rows = messages.selectList(new LambdaQueryWrapper<ConversationMessage>()
                .eq(ConversationMessage::getConversationId, conversationId)
                .orderByDesc(ConversationMessage::getId)
                .last("LIMIT " + limit));
        List<Map<String, String>> result = new java.util.ArrayList<>(rows.size());
        for (int i = rows.size() - 1; i >= 0; i--) {
            ConversationMessage m = rows.get(i);
            result.add(Map.of("role", m.getRole(), "content", m.getContent()));
        }
        return ResponseEntity.ok(result);
    }

    private void insertMessage(String conversationId, String role, String content, long now) {
        ConversationMessage msg = new ConversationMessage();
        msg.setConversationId(conversationId);
        msg.setRole(role);
        msg.setContent(content == null ? "" : content);
        msg.setCreatedAt(now);
        messages.insert(msg);
    }

    /** Keeps at most the latest MAX_MESSAGES_PER_CONVERSATION rows (user+assistant pairs). */
    private void trimToCap(String conversationId) {
        List<Long> ids = messages.selectList(new LambdaQueryWrapper<ConversationMessage>()
                        .eq(ConversationMessage::getConversationId, conversationId)
                        .orderByDesc(ConversationMessage::getId))
                .stream()
                .skip(ConversationController.MAX_MESSAGES_PER_CONVERSATION)
                .map(ConversationMessage::getId)
                .toList();
        if (!ids.isEmpty()) {
            messages.deleteBatchIds(ids);
        }
    }
}
