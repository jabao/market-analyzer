#!/bin/bash

# Start both backend and frontend for Market Analyzer

echo "Starting Market Analyzer..."

# Get the script directory (project root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env with your API keys (Plaid, OpenAI, Anthropic)"
    echo "   Then run this script again."
    exit 1
fi

# Check if Plaid is configured
if grep -q "your_plaid_client_id_here" .env; then
    echo "⚠️  Plaid not configured in .env file"
    echo "   Brokerage imports will be disabled."
    echo "   Edit .env to enable Plaid integration."
    echo ""
fi

# Check if frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install --prefix frontend
fi

# Start backend in background
# Use --reload with proper Python path handling
echo "Starting FastAPI backend on port 8000..."
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" uv run uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "Starting React frontend on port 5173..."
npm run dev --prefix frontend &
FRONTEND_PID=$!

# Wait for both processes
echo ""
echo "Market Analyzer is running!"
echo "Frontend: http://localhost:5173"
echo "Backend API: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

# Trap Ctrl+C and kill both processes
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT

wait
