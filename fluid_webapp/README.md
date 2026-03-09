# Fluid Webapp - Jira-to-Code Automation System

## Overview
Fluid Webapp is a reactive Spring Boot + React application that automates the code generation and deployment workflow triggered by Jira tickets.

## Features
- ✅ **Jira Webhook Integration**: Listens to ticket creation events
- ✅ **Git Repository Automation**: Clones repos, creates QA branches, commits, and pushes
- ✅ **Code Synthesis Placeholder**: Ready for Spring AI integration
- ✅ **Reactive Architecture**: Built on Spring WebFlux for high throughput
- ✅ **React UI**: Monitor automation progress in real-time

## Project Structure
```
fluid_webapp/
├── pom.xml                          # Maven configuration
├── src/main/java/com/example/...
│   ├── FluidWebappApplication.java
│   ├── config/AppConfig.java
│   ├── controller/JiraWebhookController.java
│   ├── service/
│   │   ├── JiraWebhookService.java
│   │   ├── GitRepoService.java
│   │   └── CodeSynthesisService.java
│   ├── dto/AutomationEvent.java
│   └── resources/application.properties
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── start.sh                         # Startup script
└── README.md
```

## Prerequisites
- Java 17+
- Maven 3.8+
- Node.js 18+
- Git
- OpenAI API Key (for Spring AI code generation)

## Installation & Running

### Option 1: Using the startup script
```bash
chmod +x start.sh
./start.sh
```

### Option 2: Manual startup

**Backend:**
```bash
mvn clean spring-boot:run
```

**Frontend (in another terminal):**
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables
Configure these before running:
```bash
export JIRA_API_TOKEN="your_jira_token"
export GITHUB_PAT="your_github_pat"
export OPENAI_API_KEY="your_openai_key"  # Required for Spring AI
```

Or copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

## API Endpoints

### Webhook Endpoint
```
POST /api/webhook/ticket-created
```
Receives Jira webhook payloads for new ticket events.

### Automation Trigger
```
POST /api/webhook/trigger-automation?ticketKey=PROJ-123&repoUrl=https://github.com/user/repo.git&branch=main&description=Fix:%20description
```
Manually trigger the automation pipeline.

## Next Steps
1. **Spring AI Code Generation** ✅ - Now integrated! See Spring AI Integration section below.
2. Add **Jira webhook configuration** for automatic ticket detection
3. Implement **audit logging and traceability**
4. Add **error handling and retry mechanisms**
5. Deploy to **cloud platform** (AWS/GCP/Azure)

## Spring AI Integration

This project leverages **Spring AI** with OpenAI's GPT-4 for intelligent code generation based on Jira ticket descriptions.

### Key Components

**CodeSynthesisService.java**
- Generates code patches using Spring AI ChatClient
- Extracts repository context for better code understanding
- Validates syntax with Maven compilation
- Supports code refinement based on feedback

**PromptEngineer.java**
- Builder utilities for optimized prompts
- Supports multiple scenarios: Fix, Feature, Refactor, Test generation, Documentation

### How It Works

1. Jira ticket arrives with description like "Fix: Add null safety checks to UserService"
2. System calls `CodeSynthesisService.generatePatch()`
3. Spring AI ChatClient sends context-aware prompt to GPT-4
4. LLM generates production-ready code
5. Code is validated and committed to QA branch

### Configuration

In `application.properties`:
```properties
spring.ai.openai.api-key=${OPENAI_API_KEY}
spring.ai.openai.chat.options.model=gpt-4
spring.ai.openai.chat.options.temperature=0.7
spring.ai.openai.chat.options.max-tokens=2048
```

### Example Usage

```java
// Inject the service
@Autowired
private CodeSynthesisService codeSynthesis;

// Generate code for a ticket
Mono<String> generatedCode = codeSynthesis.generatePatch(
    "Fix: Add validation to prevent null pointer exceptions in payment processing",
    "/path/to/repository"
);

// Validate the generated code
Mono<Boolean> isValid = codeSynthesis.validateSyntax("/path/to/repository");

// Refine based on feedback
Mono<String> refined = codeSynthesis.refineCodeWithFeedback(
    generatedCode.block(),
    "Add logging for debugging"
);
```

## Architecture
```
Jira Webhook → JiraWebhookService → GitRepoService → CodeSynthesisService → GitHub (QA Branch)
↓
React UI ← AutomationEvent Status
```

## Security Notes
- Store all tokens in environment variables, never commit them
- Use GitHub PAT with minimal scopes (repo only)
- Implement rate limiting on webhook endpoints
- Validate ticket format before processing
- Keep generated code changes auditable

## License
MIT
