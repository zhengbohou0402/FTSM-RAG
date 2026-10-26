package com.ftsm.knowledge.mq;

import com.ftsm.common.event.DocEvents;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Topology mirroring the template §4.1 contract. The index-request queue carries a
 * dead-letter policy: after 3 rejected deliveries a message lands in doc.index.dlq
 * and the document stays FAILED until a new request is published.
 */
@Configuration
public class RabbitTopology {

    @Bean
    public TopicExchange docExchange() {
        return new TopicExchange(DocEvents.EXCHANGE, true, false);
    }

    @Bean
    public Queue indexRequestQueue() {
        return QueueBuilder.durable(DocEvents.QUEUE_INDEX_REQUEST)
                .withArgument("x-dead-letter-exchange", "")
                .withArgument("x-dead-letter-routing-key", DocEvents.QUEUE_INDEX_DEAD_LETTER)
                .withArgument("x-message-ttl", 86_400_000)
                .build();
    }

    @Bean
    public Binding indexRequestBinding() {
        return BindingBuilder.bind(indexRequestQueue()).to(docExchange())
                .with(DocEvents.KEY_INDEX_REQUESTED);
    }

    @Bean
    public Queue indexResultQueue() {
        return QueueBuilder.durable(DocEvents.QUEUE_INDEX_RESULT).build();
    }

    @Bean
    public Binding indexResultBinding() {
        return BindingBuilder.bind(indexResultQueue()).to(docExchange())
                .with(DocEvents.KEY_INDEX_SUCCEEDED);
    }

    @Bean
    public Binding indexResultFailedBinding() {
        return BindingBuilder.bind(indexResultQueue()).to(docExchange())
                .with(DocEvents.KEY_INDEX_FAILED);
    }

    @Bean
    public Binding docDeletedBinding() {
        return BindingBuilder.bind(indexResultQueue()).to(docExchange())
                .with(DocEvents.KEY_DOC_DELETED);
    }

    @Bean
    public Queue retrievalLogQueue() {
        return QueueBuilder.durable(DocEvents.QUEUE_RETRIEVAL_LOG).build();
    }

    @Bean
    public Binding retrievalLogBinding() {
        return BindingBuilder.bind(retrievalLogQueue()).to(docExchange())
                .with(DocEvents.KEY_RETRIEVAL_LOGGED);
    }

    @Bean
    public Queue indexDeadLetterQueue() {
        return QueueBuilder.durable(DocEvents.QUEUE_INDEX_DEAD_LETTER).build();
    }
}
