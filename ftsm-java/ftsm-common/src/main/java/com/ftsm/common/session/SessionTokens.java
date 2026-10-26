package com.ftsm.common.session;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

/**
 * Stateless signed session token shared by ftsm-user (issuer) and ftsm-gateway (verifier).
 *
 * <p>Format: base64url(payloadJson) + "." + base64url(HMAC-SHA256(payloadJson, secret))
 * with payload {"sid": studentId, "exp": epochSeconds}. The legacy monolith used an
 * opaque token plus an in-memory session dict; a signed token keeps the same cookie
 * contract while letting the gateway verify sessions without a database round trip.
 */
public final class SessionTokens {

    public static final String COOKIE_NAME = "ftsm_student_session";
    public static final long DEFAULT_TTL_SECONDS = 7 * 24 * 3600L;

    private SessionTokens() {
    }

    public static String issue(String studentId, long ttlSeconds, String secret) {
        long exp = System.currentTimeMillis() / 1000L + ttlSeconds;
        String payload = "{\"sid\":\"" + escape(studentId) + "\",\"exp\":" + exp + "}";
        String signedPart = base64Url(payload.getBytes(StandardCharsets.UTF_8));
        return signedPart + "." + base64Url(hmacSha256(signedPart, secret));
    }

    /** Returns the student id when the token is valid and unexpired, otherwise null. */
    public static String verify(String token, String secret) {
        if (token == null || token.isBlank()) {
            return null;
        }
        int dot = token.lastIndexOf('.');
        if (dot <= 0 || dot == token.length() - 1) {
            return null;
        }
        String signedPart = token.substring(0, dot);
        byte[] expected = hmacSha256(signedPart, secret);
        byte[] provided;
        try {
            provided = Base64.getUrlDecoder().decode(token.substring(dot + 1));
        } catch (IllegalArgumentException e) {
            return null;
        }
        if (!MessageDigest.isEqual(expected, provided)) {
            return null;
        }
        try {
            String payload = new String(Base64.getUrlDecoder().decode(signedPart), StandardCharsets.UTF_8);
            String sid = extractString(payload, "sid");
            long exp = extractLong(payload, "exp");
            if (sid == null || exp <= System.currentTimeMillis() / 1000L) {
                return null;
            }
            return sid;
        } catch (Exception e) {
            return null;
        }
    }

    private static byte[] hmacSha256(String data, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", e);
        }
    }

    private static String base64Url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String extractString(String json, String key) {
        String needle = "\"" + key + "\":\"";
        int start = json.indexOf(needle);
        if (start < 0) {
            return null;
        }
        int from = start + needle.length();
        int end = json.indexOf('"', from);
        return end < 0 ? null : json.substring(from, end);
    }

    private static long extractLong(String json, String key) {
        String needle = "\"" + key + "\":";
        int start = json.indexOf(needle);
        if (start < 0) {
            return -1;
        }
        int from = start + needle.length();
        int end = from;
        while (end < json.length() && (Character.isDigit(json.charAt(end)) || json.charAt(end) == '-')) {
            end++;
        }
        return Long.parseLong(json.substring(from, end));
    }
}
