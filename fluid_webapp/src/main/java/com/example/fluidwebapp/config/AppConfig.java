package com.example.fluidwebapp.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Component
public class AppConfig {
    @Value("${jira.api.url:https://api.atlassian.com}")
    private String jiraApiUrl;

    @Value("${jira.api.token:}")
    private String jiraApiToken;

    @Value("${github.pat.token:}")
    private String githubPat;

    @Value("${spring.ai.openai.api-key:}")
    private String openaiApiKey;

    public String getJiraApiUrl() {
        return jiraApiUrl;
    }

    public String getJiraApiToken() {
        return jiraApiToken;
    }

    public String getGithubPat() {
        return githubPat;
    }

    public String getOpenaiApiKey() {
        return openaiApiKey;
    }
}

@Configuration
class ChatClientConfig {
    /**
     * ChatClient bean is auto-configured by Spring AI starter.
     * Available for injection via ChatClient.Builder in services.
     */
}
