# Spring AI Integration Guide for Fluid Webapp

## Overview
This document explains how Spring AI is integrated into Fluid Webapp and how to use it for code generation.

## Architecture

### Code Generation Flow
```
Jira Ticket → JiraWebhookController
              ↓
         JiraWebhookService (validates format)
              ↓
         CodeSynthesisService (generates code using Spring AI)
         ├─ Extracts repository context
         ├─ Builds optimized prompt via PromptEngineer
         ├─ Calls Spring AI ChatClient (GPT-4)
         ├─ Processes LLM response
         └─ Validates syntax
              ↓
         GitRepoService (commits & pushes)
              ↓
         GitHub QA Branch (waiting for review)
```

## Key Classes

### 1. CodeSynthesisService
**File**: `src/main/java/com/example/fluidwebapp/service/CodeSynthesisService.java`

**Responsibilities**:
- Generate code patches from ticket descriptions
- Extract repository context for better understanding
- Validate generated code syntax
- Refine code based on feedback

**Key Methods**:
```java
// Generate initial code patch
Mono<String> generatePatch(String ticketDescription, String repositoryPath)

// Validate syntax via Maven or script
Mono<Boolean> validateSyntax(String repositoryPath)

// Refine code with feedback
Mono<String> refineCodeWithFeedback(String generatedCode, String feedbackNotes)
```

### 2. PromptEngineer
**File**: `src/main/java/com/example/fluidwebapp/service/PromptEngineer.java`

**Responsibilities**:
- Build structured, optimized prompts for different scenarios
- Ensure consistent quality of prompts across the system

**Supported Scenarios**:
- `buildFixPrompt()` - For bug fixes
- `buildFeaturePrompt()` - For new features
- `buildRefactorPrompt()` - For code refactoring
- `buildTestPrompt()` - For test generation
- `buildDocumentationPrompt()` - For JavaDoc/comments

### 3. ChatClient (Auto-configured)
**Configured In**: `src/main/resources/application.properties`

Spring AI auto-configures ChatClient when `spring-ai-openai-spring-boot-starter` is on the classpath.

**Configuration**:
```properties
spring.ai.openai.api-key=${OPENAI_API_KEY}
spring.ai.openai.chat.options.model=gpt-4
spring.ai.openai.chat.options.temperature=0.7
spring.ai.openai.chat.options.max-tokens=2048
```

## Usage Examples

### Example 1: Basic Code Generation
```java
@Service
public class MyCodeGenService {
    private final ChatClient chatClient;
    
    public MyCodeGenService(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }
    
    public String generateJavaMethod(String description) {
        String response = chatClient
            .prompt(description)
            .call()
            .content();
        return response;
    }
}
```

### Example 2: Using PromptEngineer
```java
@Service
public class FixGenerationService {
    private final PromptEngineer engineer;
    private final ChatClient chatClient;
    
    public String fixBug(String bugDescription) {
        String prompt = engineer.buildFixPrompt(bugDescription);
        return chatClient
            .prompt(prompt)
            .call()
            .content();
    }
}
```

### Example 3: Reactive Workflow
```java
public Mono<String> generateCodeReactively(String description) {
    return Mono.fromCallable(() -> {
        String prompt = "Generate a Spring Boot REST controller for: " + description;
        return chatClient
            .prompt(prompt)
            .call()
            .content();
    }).subscribeOn(Schedulers.parallel());
}
```

## Advanced Features

### Context Extraction
The system automatically extracts repository context to help the LLM understand:
- Project structure (Maven, Gradle, etc.)
- Existing code patterns
- Framework versions
- Code style conventions

### Iterative Refinement
Code can be refined based on feedback:
```java
String initialCode = generatePatch(description, repoPath).block();
String refined = refineCodeWithFeedback(initialCode, "Add error handling").block();
```

### Syntax Validation
Generated code is validated before committing:
```java
validateSyntax(repoPath)
    .doOnNext(valid -> System.out.println("Code is " + (valid ? "valid" : "invalid")))
    .subscribe();
```

## Best Practices

### 1. Prompt Engineering
- Be specific and detailed in descriptions
- Include existing code patterns as examples
- Specify the framework and version
- Include constraints and requirements

Example Ticket Format:
```
Fix: Add validation to PaymentService
Repository: github.com/myorg/payment-service
Framework: Spring Boot 3.1
Context: Existing validation in UserService uses custom @Validated annotation
Requirement: Follow same pattern, add null-safety checks
```

### 2. Error Handling
```java
codeSynthesis.generatePatch(description, path)
    .onErrorResume(e -> {
        logger.error("Code generation failed", e);
        // Fallback or retry logic
        return Mono.error(new RuntimeException("Code generation failed", e));
    })
    .subscribe();
```

### 3. Rate Limiting
Since OpenAI API calls cost money:
```properties
# Consider implementing rate limiting
spring.ai.openai.chat.options.max-tokens=2048  # Limit response size
# Monitor API usage in OpenAI dashboard
```

## Configuration

### Environment Variables
```bash
export OPENAI_API_KEY="sk-..."  # Your OpenAI API key
export JIRA_API_TOKEN="..."      # Your Jira token
export GITHUB_PAT="ghp_..."       # Your GitHub PAT
```

### Model Selection
Current: GPT-4 (recommended for code generation)
Alternative: GPT-3.5-turbo (faster, cheaper, less accurate)

To switch:
```properties
spring.ai.openai.chat.options.model=gpt-3.5-turbo
```

### Temperature Settings
- **0.7 (current)**: Balanced between creativity and consistency
- **0.0**: Deterministic (always same output for same prompt)
- **1.0**: Maximum creativity/randomness

## Troubleshooting

### Issue: "OpenAI API key not found"
**Solution**: 
```bash
export OPENAI_API_KEY="your-key-here"
# Or add to application.properties
spring.ai.openai.api-key=your-key-here
```

### Issue: API Rate Limits
**Solution**: Implement backoff strategy
```java
.retryWhen(Retry.backoff(3, Duration.ofSeconds(2)))
```

### Issue: Generated Code Quality
**Solution**: 
1. Improve ticket description with more context
2. Adjust temperature (lower for consistency)
3. Use PromptEngineer for specific scenarios
4. Add code examples to prompt

## Testing

### Unit Testing ChatClient
```java
@SpringBootTest
class CodeSynthesisServiceTest {
    @MockBean
    private ChatClient chatClient;
    
    @Autowired
    private CodeSynthesisService service;
    
    @Test
    void testGeneratePatch() {
        when(chatClient.prompt(anyString()).call().content())
            .thenReturn("generated code");
        
        Mono<String> result = service.generatePatch("test", "/path");
        StepVerifier.create(result)
            .expectNext("generated code")
            .verifyComplete();
    }
}
```

## Future Enhancements

1. **Multi-model Support**: Support Claude, Mistral, etc.
2. **Fine-tuning**: Fine-tune models on company code patterns
3. **Vector Embeddings**: Use embeddings for semantic search
4. **Audit Trail**: Track all generated code and reviews
5. **Approval Workflows**: Manual approval before merge
6. **Cost Optimization**: Monitor and optimize API spending

## References

- [Spring AI Documentation](https://spring.io/projects/spring-ai)
- [OpenAI API Reference](https://platform.openai.com/docs)
- [Prompt Engineering Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)
