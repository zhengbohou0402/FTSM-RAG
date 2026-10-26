package com.ftsm.gateway.filter;

import com.ftsm.common.session.SessionTokens;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.util.MultiValueMap;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * Session + admin-key enforcement at the edge.
 *
 * <p>Student paths require the ftsm_student_session cookie (HMAC-signed by ftsm-user);
 * a verified request gets a fresh X-Student-Id header and any client-supplied
 * X-Student-Id is stripped first, so downstream services can trust that header.
 * Admin paths require X-Admin-Api-Key to equal the configured ADMIN_API_KEY, matching
 * the legacy require_admin_api_key contract (500 when the server has no key set).
 *
 * <p>{@code /api/training/start} used to sit in the admin list; it is now treated as a
 * student action (re-index of files the student already uploaded) and only needs a session.
 */
@Component
public class SessionAuthFilter implements GlobalFilter, Ordered {

    private static final List<String> STUDENT_PREFIXES = List.of(
            "/api/conversations");

    private static final List<String> STUDENT_EXACT = List.of(
            "/api/chat", "/api/upload", "/api/training/start",
            // P0-3：语音接口烧的是 Cloud TTS / Gemini 配额，必须登录会话
            "/api/voice/tts", "/api/voice/stt");

    // Manual re-index of the student's own uploaded materials is a student action
    // (it only rebuilds the vector index from files already in the shared data dir),
    // so it needs a session instead of the admin key. Crawler/admin refresh
    // (/api/knowledge/update) stays admin-only.
    private static final List<String> ADMIN_PATHS = List.of(
            "/api/knowledge/update",
            // P0-3：全局模型配置会写 .env（DASHSCOPE_API_KEY 等），写操作必须管理员密钥
            "/api/settings");

    private final String secret;
    private final String adminApiKey;

    public SessionAuthFilter(@Value("${ftsm.session.secret}") String secret,
                             @Value("${ftsm.admin.api-key:}") String adminApiKey) {
        this.secret = secret;
        this.adminApiKey = adminApiKey == null ? "" : adminApiKey.trim();
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();
        if (request.getMethod() == HttpMethod.OPTIONS) {
            return chain.filter(exchange);
        }
        String rawPath = request.getPath().pathWithinApplication().value();
        String path = (rawPath != null) ? rawPath.replaceAll("/+", "/") : "";

        // Block direct external access to internal microservice endpoints
        if (path.equals("/internal") || path.startsWith("/internal/")) {
            return reject(exchange, HttpStatus.FORBIDDEN, "Access to internal endpoints is forbidden");
        }

        // P0-3：管理员校验只针对写操作；GET 视为只读（桌面端设置页需要读回掩码配置）
        if (request.getMethod() != HttpMethod.GET
                && ADMIN_PATHS.stream().anyMatch(p -> path.equals(p) || path.startsWith(p + "/"))) {
            if (adminApiKey.isEmpty()) {
                return reject(exchange, HttpStatus.INTERNAL_SERVER_ERROR,
                        "ADMIN_API_KEY is not configured on the server.");
            }
            String provided = request.getHeaders().getFirst("X-Admin-Api-Key");
            if (provided == null || !adminApiKey.equals(provided.trim())) {
                return reject(exchange, HttpStatus.UNAUTHORIZED, "Unauthorized");
            }
        }

        boolean studentRequired = STUDENT_PREFIXES.stream().anyMatch(prefix -> path.equals(prefix) || path.startsWith(prefix + "/"))
                || STUDENT_EXACT.stream().anyMatch(exact -> path.equals(exact) || path.startsWith(exact + "/"))
                || (path.startsWith("/api/documents/") && request.getMethod() == HttpMethod.DELETE);

        String studentId = null;
        if (studentRequired) {
            studentId = extractStudent(request);
            if (studentId == null) {
                return reject(exchange, HttpStatus.UNAUTHORIZED, "Login required");
            }
        }

        ServerHttpRequest mutated = request.mutate()
                .headers(headers -> headers.remove("X-Student-Id"))
                .build();
        ServerHttpRequest finalRequest = studentId == null ? mutated
                : mutated.mutate().header("X-Student-Id", studentId).build();
        return chain.filter(exchange.mutate().request(finalRequest).build());
    }

    private String extractStudent(ServerHttpRequest request) {
        MultiValueMap<String, org.springframework.http.HttpCookie> cookies = request.getCookies();
        if (cookies == null) {
            return null;
        }
        List<org.springframework.http.HttpCookie> values = cookies.get(SessionTokens.COOKIE_NAME);
        if (values == null || values.isEmpty()) {
            return null;
        }
        return SessionTokens.verify(values.get(0).getValue(), secret);
    }

    private Mono<Void> reject(ServerWebExchange exchange, HttpStatus status, String detail) {
        exchange.getResponse().setStatusCode(status);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        byte[] body = ("{\"detail\":\"" + detail + "\"}").getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = exchange.getResponse().bufferFactory().wrap(body);
        return exchange.getResponse().writeWith(Mono.just(buffer));
    }

    @Override
    public int getOrder() {
        return -10;
    }
}
