Set-Location -LiteralPath "C:\Users\solfm\OneDrive\Документы\Билеты\flight_price_bot"
& "C:\Users\solfm\AppData\Local\Programs\Python\Python312\python.exe" main.py *>&1 | Out-File -FilePath "bot.log" -Encoding utf8
