package com.example.fluidwebapp.controller;

import com.example.fluidwebapp.service.JiraWebhookService;
import com.example.fluidwebapp.service.GitRepoService;
import com.example.fluidwebapp.service.CodeSynthesisService;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;
import java.util.Map;

@RestController
@RequestMapping("/api/webhook")
public class JiraWebhookController {
    private final JiraWebhookService jiraService;
    private final GitRepoService gitService;
    private final CodeSynthesisService synthService;

    public JiraWebhookController(JiraWebhookService jiraService,
                                 GitRepoService gitService,
                                 CodeSynthesisService synthService) {
        this.jiraService = jiraService;
        this.gitService = gitService;
        this.synthService = synthService;
    }

    @PostMapping("/ticket-created")
    public Mono<Map<String, Object>> handleTicketCreated(@RequestBody Map<String, Object> payload) {
        return jiraService.processWebhookEvent(payload)
            .doOnNext(p -> System.out.println("Webhook event processed: " + p))
            .onErrorResume(e -> Mono.just(Map.of("error", e.getMessage())));
    }

    @PostMapping("/trigger-automation")
    public Mono<Map<String, String>> triggerAutomation(
            @RequestParam String ticketKey,
            @RequestParam String repoUrl,
            @RequestParam String branch,
            @RequestParam String description) {
        
        return gitService.cloneRepository(repoUrl, branch, "token_placeholder")
            .flatMap(repoPath -> synthService.generatePatch(description, repoPath)
                .flatMap(patch -> gitService.createQABranch(repoPath, ticketKey)
                    .flatMap(branchName -> gitService.commitAndPush(repoPath, 
                            "Automated fix for " + ticketKey, "token_placeholder")
                        .thenReturn(Map.of(
                            "status", "success",
                            "branch", branchName,
                            "message", "QA branch created and pushed"))
                    )
                )
            )
            .onErrorResume(e -> Mono.just(Map.of(
                "status", "error",
                "message", e.getMessage()
            )));
    }

    @PostMapping("/demo/generate-code")
    public Mono<Map<String, Object>> generateDemoCode(@RequestBody Map<String, String> request) {
        String description = request.get("description");
        if (description == null || description.trim().isEmpty()) {
            return Mono.just(Map.of("error", "Description is required"));
        }

        // Use a mock repo path for demo
        String mockRepoPath = "/tmp/demo-repo";

        return synthService.generatePatch(description, mockRepoPath)
            .map(generatedCode -> Map.<String, Object>of(
                "status", "success",
                "generatedCode", generatedCode,
                "description", description
            ))
            .onErrorResume(e -> Mono.just(Map.of(
                "status", "error",
                "message", e.getMessage(),
                "description", description
            )));
    }
}
