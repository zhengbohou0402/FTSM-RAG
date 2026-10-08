package com.ftsm.knowledge;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.ftsm.knowledge.mapper")
public class KnowledgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(KnowledgeApplication.class, args);
    }
}
