# Environment Setup Guide

This document provides instructions for setting up a development environment for the trading platform.

## Prerequisites

Before starting, ensure you have the following installed on your system:

- Python 3.9+ with pip
- Git
- Node.js 16+ and npm (for UI development)
- Docker and Docker Compose (for running services locally)
- Visual Studio Code (recommended) or your preferred IDE

## Getting the Source Code

Clone the repository:

```bash
git clone https://github.com/tradingplatform/trading-platform.git
cd trading-platform
```

## Backend Setup

### 1. Create a Python Virtual Environment

```bash
# For Windows
python -m venv venv
venv\Scripts\activate

# For macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

### 3. Set Up Configuration

Create a local configuration file by copying the example:

```bash
cp config/config.example.yaml config/config.local.yaml
```

Edit `config/config.local.yaml` to configure your local development environment.

### 4. Initialize the Database

```bash
python scripts/init_db.py
```

### 5. Run Backend Services

```bash
python main.py
```

The API server will start running at http://localhost:8000.

## Frontend Setup

### 1. Install UI Dependencies

```bash
cd ui
npm install
```

### 2. Set Up Environment Variables

Create a local environment file:

```bash
cp .env.example .env.local
```

Edit `.env.local` to point to your local API server.

### 3. Run Development Server

```bash
npm run dev
```

The UI will be available at http://localhost:3000.

## Docker Setup (Alternative)

You can also run the entire platform using Docker Compose:

```bash
docker-compose up -d
```

This will start all services defined in the `docker-compose.yml` file, including the API server, database, and UI.

## Testing

### Running Unit Tests

```bash
pytest
```

### Running Integration Tests

```bash
pytest tests/integration
```

### Running UI Tests

```bash
cd ui
npm test
```

## Development Tools

### Code Formatting

We use Black for Python code formatting and Prettier for JavaScript/TypeScript:

```bash
# Format Python code
black .

# Format JavaScript/TypeScript code
cd ui
npm run format
```

### Linting

We use flake8 for Python linting and ESLint for JavaScript/TypeScript:

```bash
# Lint Python code
flake8

# Lint JavaScript/TypeScript code
cd ui
npm run lint
```

## Debugging

### Backend Debugging

You can use the built-in Python debugger or your IDE's debugger. In VS Code, use the provided launch configurations in `.vscode/launch.json`.

### Frontend Debugging

For frontend debugging, use your browser's developer tools. Chrome DevTools is recommended for debugging React applications.

## Troubleshooting

### Common Issues

1. **Database connection errors**: Ensure your database service is running and the connection details in `config.local.yaml` are correct.

2. **Dependency conflicts**: If you encounter dependency conflicts, try creating a fresh virtual environment.

3. **Port conflicts**: If a port is already in use, change the port number in the configuration files.

For more help, contact the development team or open an issue on GitHub.