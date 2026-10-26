package com.ftsm.knowledge.mq;

import com.ftsm.common.event.DocEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

/**
 * Event publisher with publisher confirms: a nacked/unrouted message is logged loudly
 * so an operator can republish instead of silently losing the indexing request.
 */
@Component
public class DocEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(DocEventPublisher.class);

    private final RabbitTemplate rabbitTemplate;

    public DocEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
        this.rabbitTemplate.setConfirmCallback(this::onConfirm);
    }

    public void publish(String routingKey, Object payload) {
        CorrelationData correlation = new CorrelationData(routingKey + ":" + System.nanoTime());
        rabbitTemplate.convertAndSend(DocEvents.EXCHANGE, routingKey, payload, correlation);
    }

    private void onConfirm(CorrelationData correlation, boolean ack, String cause) {
        if (!ack) {
            log.error("[mq] publisher nack for {} cause={}", correlation == null ? "?" : correlation.getId(), cause);
        }
    }
}
