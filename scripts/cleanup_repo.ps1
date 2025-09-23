Write-Host "Cleaning up repository: removing __pycache__ and untracking .env if present..."
Get-ChildItem -Path . -Recurse -Force -Directory -Filter '__pycache__' | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
git rm -f --quiet --ignore-unmatch .env 2>$null
Write-Host "Cleanup complete. Don't forget to commit any changes: git add -A; git commit -m 'cleanup'; git push" 