package com.ftsm.user.auth;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * PBKDF2 password hashing, byte-compatible with the legacy monolith
 * (hashlib.pbkdf2_hmac("sha256", password, salt, 200000).hex()):
 * format "pbkdf2_sha256$200000$salt$hexdigest" — existing accounts can be imported as-is.
 */
public final class PasswordHasher {

    public static final int ITERATIONS = 200_000;
    private static final String SCHEME = "pbkdf2_sha256";
    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordHasher() {
    }

    public static String hash(String password) {
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        String saltHex = toHex(salt);
        return SCHEME + "$" + ITERATIONS + "$" + saltHex + "$" + toHex(derive(password, saltHex, ITERATIONS));
    }

    public static boolean verify(String password, String storedHash) {
        if (password == null || storedHash == null) {
            return false;
        }
        String[] parts = storedHash.split("\\$", 4);
        if (parts.length != 4 || !SCHEME.equals(parts[0])) {
            return false;
        }
        try {
            int iterations = Integer.parseInt(parts[1]);
            byte[] expected = fromHex(parts[3]);
            byte[] actual = derive(password, parts[2], iterations);
            return MessageDigest.isEqual(expected, actual);
        } catch (Exception e) {
            return false;
        }
    }

    private static byte[] derive(String password, String saltHex, int iterations) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), saltHex.getBytes(StandardCharsets.UTF_8), iterations, 256);
            return SecretKeyFactory.getInstance("PBKDF2WithHMACSHA256").generateSecret(spec).getEncoded();
        } catch (Exception e) {
            throw new IllegalStateException("PBKDF2 unavailable", e);
        }
    }

    private static byte[] fromHex(String hex) {
        int len = hex.length();
        byte[] out = new byte[len / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(Character.forDigit((b >> 4) & 0xF, 16)).append(Character.forDigit(b & 0xF, 16));
        }
        return sb.toString();
    }
}
