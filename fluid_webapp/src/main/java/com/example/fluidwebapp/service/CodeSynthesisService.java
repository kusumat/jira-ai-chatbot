package com.example.fluidwebapp.service;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

@Service
public class CodeSynthesisService {
    private final ChatClient chatClient;

    public CodeSynthesisService(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }

    public Mono<String> generatePatch(String ticketDescription, String repositoryPath) {
        return Mono.fromCallable(() -> {
            // Build a context-aware prompt for the LLM
            String repositoryContext = extractRepositoryContext(repositoryPath);
            String prompt = buildCodeGenerationPrompt(ticketDescription, repositoryContext);
            
            try {
                // Call Spring AI to generate code
                String generatedCode = chatClient
                    .prompt(prompt)
                    .call()
                    .content();
                
                return generatedCode;
            } catch (Exception e) {
                // Fallback to mock code generation if AI is not available
                System.out.println("AI generation failed, using mock fallback: " + e.getMessage());
                return generateMockPatch(ticketDescription, repositoryPath);
            }
        });
    }

    private String buildCodeGenerationPrompt(String ticketDescription, String repoContext) {
        return String.format(
            "You are an expert Java developer. Based on the following Jira ticket description and repository context, "
            + "generate a complete, production-ready code patch.\n\n"
            + "TICKET DESCRIPTION:\n%s\n\n"
            + "REPOSITORY CONTEXT:\n%s\n\n"
            + "REQUIREMENTS:\n"
            + "1. Generate valid Java code that solves the described problem\n"
            + "2. Follow existing code style and patterns in the repository\n"
            + "3. Include appropriate error handling\n"
            + "4. Add meaningful comments where needed\n"
            + "5. Ensure the code is testable\n\n"
            + "OUTPUT FORMAT:\n"
            + "Provide the complete file content that should replace the existing file. Start with package and imports, then the full implementation.\n",
            ticketDescription,
            repoContext
        );
    }

    private String extractRepositoryContext(String repositoryPath) {
        try {
            // Try to read main source files for context
            Path srcPath = Paths.get(repositoryPath, "src/main/java");
            if (Files.exists(srcPath)) {
                return "Java Maven project. Source files located at: src/main/java";
            }
            Path srcPath2 = Paths.get(repositoryPath, "src");
            if (Files.exists(srcPath2)) {
                return "Source code project. Main sources at: src/";
            }
            return "Source repository. Structure not fully identified.";
        } catch (Exception e) {
            return "Unable to extract full context: " + e.getMessage();
        }
    }

    private String generateMockPatch(String ticketDescription, String repositoryPath) {
        // Mock code generation for when AI is not available
        return String.format(
            "// Mock code patch generated for ticket: %s\n" +
            "// Repository: %s\n" +
            "// Note: This is a placeholder. Please implement the actual solution.\n\n" +
            "package com.example;\n\n" +
            "public class MockSolution {\n" +
            "    // TODO: Implement based on ticket description\n" +
            "    // Ticket: %s\n" +
            "    \n" +
            "    public void solveIssue() {\n" +
            "        // Placeholder implementation\n" +
            "        System.out.println(\"Issue addressed: \" + \"%s\");\n" +
            "    }\n" +
            "}\n",
            ticketDescription.substring(0, Math.min(50, ticketDescription.length())),
            repositoryPath,
            ticketDescription,
            ticketDescription
        );
    }

    public Mono<Boolean> validateSyntax(String repositoryPath) {
        return Mono.fromCallable(() -> {
            // Run mvn compile or similar validation
            ProcessBuilder pb = new ProcessBuilder("mvn", "compile");
            pb.directory(new java.io.File(repositoryPath));
            pb.inheritIO();
            Process process = pb.start();
            int exitCode = process.waitFor();
            return exitCode == 0;
        }).doOnError(e -> System.err.println("Syntax validation failed: " + e.getMessage()));
    }

    public Mono<String> refineCodeWithFeedback(String generatedCode, String feedbackNotes) {
        return Mono.fromCallable(() -> {
            String refinementPrompt = String.format(
                "You are refining previously generated code based on feedback.\n\n"
                + "ORIGINAL CODE:\n%s\n\n"
                + "FEEDBACK/ISSUES:\n%s\n\n"
                + "Please provide an improved version of the code that addresses all feedback points.\n",
                generatedCode,
                feedbackNotes
            );
            
            try {
                return chatClient
                    .prompt(refinementPrompt)
                    .call()
                    .content();
            } catch (Exception e) {
                // Fallback to mock refinement
                System.out.println("AI refinement failed, using mock fallback: " + e.getMessage());
                return generatedCode + "\n// TODO: Refine based on feedback: " + feedbackNotes;
            }
        });
    }
}
