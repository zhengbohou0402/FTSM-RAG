package com.ftsm.user.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AuthRequest(
        @NotBlank @Size(min = 3, max = 80) String studentId,
        @NotBlank @Size(min = 6, max = 200) String password,
        @Size(max = 80) String displayName) {
}
