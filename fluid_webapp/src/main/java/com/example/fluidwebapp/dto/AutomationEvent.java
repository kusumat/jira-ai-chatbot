package com.example.fluidwebapp.dto;

import java.time.LocalDateTime;

public class AutomationEvent {
    private String ticketKey;
    private String description;
    private String repositoryUrl;
    private String targetBranch;
    private String status; // PENDING, IN_PROGRESS, COMPLETED, FAILED
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
    private String qaUrl;
    private String errorMessage;

    public AutomationEvent() {}

    public AutomationEvent(String ticketKey, String description, String repositoryUrl, String targetBranch) {
        this.ticketKey = ticketKey;
        this.description = description;
        this.repositoryUrl = repositoryUrl;
        this.targetBranch = targetBranch;
        this.status = "PENDING";
        this.createdAt = LocalDateTime.now();
    }

    // Getters and Setters
    public String getTicketKey() { return ticketKey; }
    public void setTicketKey(String ticketKey) { this.ticketKey = ticketKey; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getRepositoryUrl() { return repositoryUrl; }
    public void setRepositoryUrl(String repositoryUrl) { this.repositoryUrl = repositoryUrl; }

    public String getTargetBranch() { return targetBranch; }
    public void setTargetBranch(String targetBranch) { this.targetBranch = targetBranch; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getCompletedAt() { return completedAt; }
    public void setCompletedAt(LocalDateTime completedAt) { this.completedAt = completedAt; }

    public String getQaUrl() { return qaUrl; }
    public void setQaUrl(String qaUrl) { this.qaUrl = qaUrl; }

    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
}
