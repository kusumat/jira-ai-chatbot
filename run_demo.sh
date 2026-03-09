#!/bin/bash
#
# Complete End-to-End Automation Demo Script
# This script:
# 1. Creates a test buggy app
# 2. Pushes it to GitHub
# 3. Creates a JIRA ticket
# 4. Triggers the automation workflow
# 5. Monitors the QA branch creation
#

set -e

# Configuration
GITHUB_PAT="${GITHUB_PAT:-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}"
GITHUB_USERNAME="kusumat"
JIRA_HOST="${JIRA_HOST:-https://kusumathatavarthi.atlassian.net}"
JIRA_API_TOKEN="${JIRA_API_TOKEN:-ATATT3xFfGF06rQFOfL6uTNQP7tEDMyJ-46OxJaS4WyIa3zFe8a6WGeLnIaCGgfsK_zP08zMzsuZYQDx7DDetghKx2OLMS2zVWs4ZEWNSJjt1IiM94eC1mxEHxQEg4gPU8nUTyV2j1glpxUhndFOUVTZKRZ_x8hdgJJ6iJIBWtCHgP33d7OMW0g=23D2D730}"
REPO_NAME="buggy-demo-app"
TICKET_KEY="AUTO-001"

BACKEND_URL="http://localhost:8000"

echo "=========================================="
echo "🚀 End-to-End Automation Demo"
echo "=========================================="
echo ""

# Step 1: Prepare the demo app (already done in /tmp/demo-buggy-app)
DEMO_APP_PATH="/tmp/demo-buggy-app"
if [ ! -d "$DEMO_APP_PATH" ]; then
    mkdir -p "$DEMO_APP_PATH"
    cd "$DEMO_APP_PATH"
    git init
    git config user.email "demo@example.com"
    git config user.name "Demo Bot"
    
    # Create buggy code
    cat > UserAgeCalculator.java << 'EOF'
public class UserAgeCalculator {
    public static int calculateAge(int birthYear, int currentYear) {
        return (currentYear - birthYear) / (currentYear - birthYear);
    }
    public static void main(String[] args) {
        System.out.println("Age: " + calculateAge(1990, 2026));
        System.out.println("Newborn age: " + calculateAge(2026, 2026)); // Crashes here
    }
}
EOF
    
    git add UserAgeCalculator.java
    git commit -m "Add buggy UserAgeCalculator"
fi

echo "✅ Demo app prepared at: $DEMO_APP_PATH"
echo ""

# Step 2: Push to GitHub (Optional - skip if repo already exists)
echo "📤 Preparing GitHub repository..."
REPO_URL="https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"

# Check if repo exists locally with remote
cd "$DEMO_APP_PATH"
if ! git remote get-url origin 2>/dev/null | grep -q "github.com"; then
    echo "Setting up GitHub remote..."
    git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
    git branch -M main
    echo "Remote configured: $REPO_URL"
else
    echo "Remote already configured"
fi

echo ""

# Step 3: Start FastAPI backend (if not running)
echo "🔧 Starting FastAPI backend..."
if ! curl -s "$BACKEND_URL/health" > /dev/null 2>&1; then
    echo "Backend not running. Start it with:"
    echo "  cd /Users/kusumathatavarthi/jira_ai_chatbot_artifacts"
    echo "  python -m uvicorn backend.api:app --reload --port 8000"
    echo ""
    read -p "Press Enter once backend is running..."
else
    echo "✅ Backend is running"
fi

echo ""

# Step 4: Create JIRA ticket (Optional)
echo "🎫 Creating JIRA ticket (optional)..."
read -p "Create JIRA ticket? (y/n, default: n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Would need valid JIRA credentials to create ticket"
    echo "Skipping for now - using manual ticket key: $TICKET_KEY"
fi

echo ""

# Step 5: Trigger automation workflow
echo "⚙️  Triggering automated bug fix workflow..."
echo ""
echo "Sending request to: $BACKEND_URL/auto-fix"
echo ""

RESPONSE=$(curl -s -X POST "$BACKEND_URL/auto-fix" \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_key": "'$TICKET_KEY'",
    "issue_description": "Fix division by zero in UserAgeCalculator.calculateAge(). When currentYear equals birthYear, the code should return 0, not crash.",
    "repo_url": "'$REPO_URL'",
    "github_pat": "'$GITHUB_PAT'",
    "github_username": "'$GITHUB_USERNAME'",
    "target_branch": "main"
  }')

echo "Response:"
echo "$RESPONSE" | python -m json.tool 2>/dev/null || echo "$RESPONSE"

echo ""
echo "=========================================="
echo "✅ Demo completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Review the generated fix in GitHub:"
echo "   https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo ""
echo "2. Check the QA branch:"
echo "   git branch -a | grep qa/"
echo ""
echo "3. Create a Pull Request from the QA branch to main"
echo ""
