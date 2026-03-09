#!/bin/bash
# Quick setup script for Fluid Webapp development

set -e

echo "📦 Setting up Fluid Webapp with Spring AI..."

# Check prerequisites
for cmd in java mvn node npm git; do
  if ! command -v $cmd &> /dev/null; then
    echo "❌ $cmd is not installed. Please install it first."
    exit 1
  fi
done

echo "✅ All prerequisites found"

# Setup environment
echo "🔧 Setting up environment variables..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Created .env file. Please add your API keys:"
  echo "   - JIRA_API_TOKEN"
  echo "   - GITHUB_PAT"
  echo "   - OPENAI_API_KEY"
  read -p "Press Enter after updating .env..."
fi

# Load environment
source .env

# Create required variables
export JIRA_API_TOKEN
export GITHUB_PAT
export OPENAI_API_KEY

# Build backend
echo "🏗️  Building Spring Boot backend..."
mvn clean install -q

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install -q
cd ..

echo "✅ Setup complete!"
echo ""
echo "🚀 To start the application, run: ./start.sh"
echo ""
echo "🌐 URLs once running:"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8080"
echo "   API Docs: http://localhost:8080/swagger-ui.html (after adding springdoc-openapi)"
