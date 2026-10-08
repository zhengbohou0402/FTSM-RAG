package com.ftsm.conversation;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.ftsm.conversation.mapper")
public class ConversationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConversationApplication.class, args);
    }
}
