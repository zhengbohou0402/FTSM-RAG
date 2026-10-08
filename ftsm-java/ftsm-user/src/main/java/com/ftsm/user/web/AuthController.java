package com.ftsm.user.web;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.ftsm.user.auth.PasswordHasher;
import com.ftsm.user.auth.SessionCookieWriter;
import com.ftsm.user.entity.Student;
import com.ftsm.user.mapper.StudentMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Port of the legacy monolith auth endpoints (contract preserved):
 * POST /api/auth/register | /api/auth/login | /api/auth/logout, GET /api/auth/me.
 */
@RestController
public class AuthController {

    private static final Pattern STUDENT_ID_PATTERN = Pattern.compile("[a-z0-9@._-]{3,80}");

    private final StudentMapper studentMapper;
    private final SessionCookieWriter sessions;

    public AuthController(StudentMapper studentMapper, SessionCookieWriter sessions) {
        this.studentMapper = studentMapper;
        this.sessions = sessions;
    }

    @PostMapping("/api/auth/register")
    public ResponseEntity<Map<String, Object>> register(@Valid @RequestBody AuthRequest payload,
                                                        HttpServletResponse response) {
        String studentId = normalize(payload.studentId());
        String displayName = (payload.displayName() == null || payload.displayName().isBlank()
                ? studentId : payload.displayName().trim());

        Long existing = studentMapper.selectCount(new LambdaQueryWrapper<Student>()
                .eq(Student::getStudentId, studentId));
        if (existing > 0) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body(
                    Map.of("detail", "Student account already exists."));
        }

        long now = Instant.now().getEpochSecond();
        Student student = new Student();
        student.setStudentId(studentId);
        student.setDisplayName(displayName);
        student.setPasswordHash(PasswordHasher.hash(payload.password()));
        student.setCreatedAt(now);
        student.setUpdatedAt(now);
        studentMapper.insert(student);

        sessions.create(response, studentId);
        return ResponseEntity.ok(Map.of(
                "authenticated", true,
                "student", Map.of("student_id", studentId, "display_name", displayName)));
    }

    @PostMapping("/api/auth/login")
    public ResponseEntity<Map<String, Object>> login(@Valid @RequestBody AuthRequest payload,
                                                     HttpServletResponse response) {
        String studentId = normalize(payload.studentId());
        Student student = studentMapper.selectOne(new LambdaQueryWrapper<Student>()
                .eq(Student::getStudentId, studentId));
        if (student == null || !PasswordHasher.verify(payload.password(), student.getPasswordHash())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(
                    Map.of("detail", "Invalid student ID or password."));
        }
        sessions.create(response, studentId);
        return ResponseEntity.ok(Map.of(
                "authenticated", true,
                "student", Map.of("student_id", studentId, "display_name", student.getDisplayName())));
    }

    @PostMapping("/api/auth/logout")
    public ResponseEntity<Map<String, Object>> logout(HttpServletRequest request, HttpServletResponse response) {
        sessions.clear(request, response);
        return ResponseEntity.ok(Map.of("authenticated", false));
    }

    @GetMapping("/api/auth/me")
    public ResponseEntity<Map<String, Object>> me(HttpServletRequest request) {
        String studentId = sessions.currentStudentId(request);
        if (studentId == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "Login required"));
        }
        Student student = studentMapper.selectOne(new LambdaQueryWrapper<Student>()
                .eq(Student::getStudentId, studentId));
        if (student == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "Login required"));
        }
        return ResponseEntity.ok(Map.of(
                "authenticated", true,
                "student", Map.of("student_id", studentId, "display_name", student.getDisplayName())));
    }

    private String normalize(String studentId) {
        String normalized = studentId == null ? "" : studentId.trim().toLowerCase();
        if (!STUDENT_ID_PATTERN.matcher(normalized).matches()) {
            throw new IllegalArgumentException(
                    "Student ID can only contain letters, numbers, @, dot, underscore, or hyphen.");
        }
        return normalized;
    }
}
