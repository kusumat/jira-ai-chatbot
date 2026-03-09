package com.example.fluidwebapp.service;

import org.springframework.stereotype.Component;

/**
 * Utility class for building optimized prompts for code generation.
 */
@Component
public class PromptEngineer {
    
    public String buildFixPrompt(String issue) {
        return String.format(
            "You are a senior Java developer. Fix the following issue:\\n"
            + "%s\\n\\n"
            + "Provide the complete corrected code with proper error handling.",
            issue
        );
    }

    public String buildFeaturePrompt(String requirement) {
        return String.format(
            "You are a software architect. Implement the following feature:\\n"
            + "%s\\n\\n"
            + "Provide production-ready code following Spring Boot best practices.",
            requirement
        );
    }

    public String buildRefactorPrompt(String currentCode, String goal) {
        return String.format(
            "Refactor the following code to meet this goal:\\n"
            + "GOAL: %s\\n\\n"
            + "CURRENT CODE:\\n%s\\n\\n"
            + "Provide improved, cleaner code.",
            goal,
            currentCode
        );
    }

    public String buildTestPrompt(String sourceCode) {
        return String.format(
            "Generate comprehensive unit tests for the following code:\\n"
            + "%s\\n\\n"
            + "Use JUnit 5 and Mockito. Cover happy path and edge cases.",
            sourceCode
        );
    }

    public String buildDocumentationPrompt(String sourceCode) {
        return String.format(
            "Generate JavaDoc and detailed comments for the following code:\\n"
            + "%s\\n\\n"
            + "Explain purpose, parameters, return values, and exceptions.",
            sourceCode
        );
    }
}
