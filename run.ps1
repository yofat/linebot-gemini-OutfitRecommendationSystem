<#
run.ps1 - Utility PowerShell script to run common tasks for the project
Usage:
  ./run.ps1 help
  ./run.ps1 dev         # run app.py in dev mode
  ./run.ps1 gunicorn    # run via gunicorn (production-like)
  ./run.ps1 test        # create venv, install deps, run pytest
  ./run.ps1 docker-build
  ./run.ps1 docker-run
#>
param(
    [string]$mode = 'help'
)

function Show-Help {
    Write-Host "Usage: ./run.ps1 <mode>"
    Write-Host "Modes: help, dev, gunicorn, test, docker-build, docker-run"
}

switch ($mode.ToLower()) {
    'help' {
        Show-Help
        break
    }
    'dev' {
        if (-not (Test-Path -Path .venv)) {
            python -m venv .venv
            Write-Host "Created virtualenv .venv"
        }
        .\.venv\Scripts\Activate.ps1
        pip install -r requirements.txt
        Write-Host "Starting dev server..."
        python .\app.py
        break
    }
    'gunicorn' {
        pip install -r requirements.txt
        Write-Host "Starting Gunicorn..."
        gunicorn app:app -c gunicorn.conf.py
        break
    }
    'test' {
        if (-not (Test-Path -Path .venv)) {
            python -m venv .venv
            Write-Host "Created virtualenv .venv"
        }
        .\.venv\Scripts\Activate.ps1
        pip install -r requirements.txt
        pytest -q
        break
    }
    'docker-build' {
        docker build -t line-gemini-app:latest .
        break
    }
    'docker-run' {
        if (Test-Path -Path "docker-compose.yml") {
            Write-Host "Running docker-compose up (reads .env if present)..."
            docker-compose up --build
        }
        else {
            Write-Host "Run with: docker run -e LINE_CHANNEL_ACCESS_TOKEN=... -e LINE_CHANNEL_SECRET=... -e GENAI_API_KEY=... -p 5000:5000 line-gemini-app:latest"
        }
        break
    }
    Default {
        Write-Host "Unknown mode: $mode"
        Show-Help
        break
    }
}
