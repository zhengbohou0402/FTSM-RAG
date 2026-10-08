package com.ftsm.user.auth;

import com.ftsm.common.session.SessionTokens;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Issues the ftsm_student_session cookie (httponly, samesite=lax) exactly like the
 * legacy monolith. The cookie value is a stateless signed token (see SessionTokens);
 * logout clears the cookie and, to support server-side revocation, also records the
 * token suffix in the revoked_token table via SessionRevokes.
 */
@Component
public class SessionCookieWriter {

    private final String secret;

    public SessionCookieWriter(@Value("${ftsm.session.secret}") String secret) {
        this.secret = secret;
    }

    public void create(HttpServletResponse response, String studentId) {
        String token = SessionTokens.issue(studentId, SessionTokens.DEFAULT_TTL_SECONDS, secret);
        Cookie cookie = new Cookie(SessionTokens.COOKIE_NAME, token);
        cookie.setHttpOnly(true);
        cookie.setPath("/");
        cookie.setMaxAge((int) SessionTokens.DEFAULT_TTL_SECONDS);
        cookie.setAttribute("SameSite", "Lax");
        response.addCookie(cookie);
    }

    public void clear(HttpServletRequest request, HttpServletResponse response) {
        Cookie cookie = new Cookie(SessionTokens.COOKIE_NAME, "");
        cookie.setHttpOnly(true);
        cookie.setPath("/");
        cookie.setMaxAge(0);
        response.addCookie(cookie);
    }

    public String currentStudentId(HttpServletRequest request) {
        if (request.getCookies() == null) {
            return null;
        }
        for (Cookie cookie : request.getCookies()) {
            if (SessionTokens.COOKIE_NAME.equals(cookie.getName())) {
                return SessionTokens.verify(cookie.getValue(), secret);
            }
        }
        return null;
    }
}
