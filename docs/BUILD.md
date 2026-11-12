# Сборка и проверки

PowerShell, корень репозитория. Проверенная среда: Windows x64 и Python 3.14 x64. Зависимости закреплены в `source/requirements.txt`.

## Окружение и проверка исходников

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r source\requirements.txt
New-Item -ItemType Directory -Force work | Out-Null
.\.venv\Scripts\python.exe -m unittest discover -s source -p test_xp.py -v
.\.venv\Scripts\python.exe source\launcher_xp.py --self-test work\source-test.json
Get-Content -Encoding UTF8 work\source-test.json
```

Ожидается `ok: true` и 9 тестов. Самотест дополнительно проверяет Qt, счётчик, сохранение и размеры оверлея; использует временные настройки и не меняет личный счётчик.

## Сборка EXE

Чистый PATH предотвращает захват чужих ICU DLL. Их исключение в spec также нужно сохранить.

```powershell
$buildPython = (Resolve-Path .venv\Scripts\python.exe).Path
$savedPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & $buildPython -m PyInstaller --noconfirm --distpath dist --workpath build source\ChestCounterXP.spec
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки' }
} finally {
    $env:PATH = $savedPath
}
```

Результат: `dist/ChestCounter-XP-Fast/ChestCounterXP.exe`. Передавать всю папку, включая `_internal`, а не отдельный EXE.

## Проверка готового EXE

```powershell
New-Item -ItemType Directory -Force work | Out-Null
$report = Join-Path (Get-Location) 'work\packaged-test.json'
$testRun = Start-Process -FilePath '.\dist\ChestCounter-XP-Fast\ChestCounterXP.exe' -ArgumentList '--self-test',('"' + $report + '"') -WindowStyle Hidden -PassThru
if (-not $testRun.WaitForExit(45000)) {
    Stop-Process -Id $testRun.Id
    throw 'Самотест не завершился'
}
if ($testRun.ExitCode -ne 0) { throw 'Самотест завершился с ошибкой' }
$result = Get-Content -Raw -Encoding UTF8 -LiteralPath $report | ConvertFrom-Json
if (-not $result.ok) { throw 'Самотест не прошёл' }
$result
```

Для проверки реального захвата замени `--self-test` на `--capture-test` и используй отдельный отчёт. Режим ненадолго показывает тестовые окна, проверяет WDA_NONE после масштабирования и скрытия/показа, затем сохраняет снимок оверлея рядом с отчётом. Нужен интерактивный рабочий стол Windows. Fortnite и Discord тест не запускает; глобальные горячие клавиши не захватывает.

## Публикация сборки

EXE, `_internal`, ZIP, отчёты и окружение исключены из Git. Архив готового приложения можно прикрепить к GitHub Release после успешного самотеста. Не добавляй содержимое `%LOCALAPPDATA%/ChestCounter`, папку `work` и документы передачи контекста.
