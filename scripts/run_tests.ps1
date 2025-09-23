Write-Host "Running tests with pytest..."
py -3 -m pip install --upgrade pip setuptools wheel
py -3 -m pip install -r requirements.txt
py -3 -m pytest -q
Write-Host "Tests finished."