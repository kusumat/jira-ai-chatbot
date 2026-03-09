package com.example.fluidwebapp.service;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import java.util.Map;

@Service
public class JiraWebhookService {
    private final WebClient webClient;

    public JiraWebhookService(WebClient.Builder builder) {
        this.webClient = builder.baseUrl("https://api.atlassian.com").build();
    }

    public Mono<Map<String, Object>> processWebhookEvent(Map<String, Object> payload) {
        // Validate ticket structure
        String ticketKey = (String) payload.get("key");
        String description = (String) payload.get("description");

        if (ticketKey == null || !isValidTicketFormat(description)) {
            return Mono.error(new IllegalArgumentException("Invalid ticket format"));
        }

        return Mono.just(payload);
    }

    private boolean isValidTicketFormat(String description) {
        return description != null && 
               (description.startsWith("Fix:") || description.startsWith("Feature:"));
    }

    public Mono<String> fetchTicketDetails(String ticketKey, String apiToken) {
        return webClient
            .get()
            .uri("/rest/api/3/issues/{key}", ticketKey)
            .header("Authorization", "Bearer " + apiToken)
            .retrieve()
            .bodyToMono(String.class);
    }
}
