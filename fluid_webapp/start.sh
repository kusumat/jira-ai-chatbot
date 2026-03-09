#!/bin/bash

# Fluid Webapp Startup Script
# Starts both the Spring Boot backend and React frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Fluid Webapp..."

# Start Backend
echo "Starting Spring Boot backend..."
cd "$SCRIPT_DIR"
mvn clean spring-boot:run &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 5

# Start Frontend
echo "Starting React frontend..."
cd "$SCRIPT_DIR/frontend"
npm install
npm run dev &
FRONTEND_PID=$!

echo "✅ Fluid Webapp is running!"
echo "Backend: http://localhost:8080"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
