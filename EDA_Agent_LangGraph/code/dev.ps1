# 启动 LangGraph 本地开发服务器（Studio + API 文档）
#
#   .\dev.ps1
#
# 首次运行若被策略拦截：Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$env:PYTHONUTF8 = '1'          # 必须：否则 langgraph_api 用 GBK 读 openapi.json 会崩
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "API      : http://127.0.0.1:2024" -ForegroundColor Cyan
Write-Host "API 文档 : http://127.0.0.1:2024/docs" -ForegroundColor Cyan
Write-Host "Studio   : https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止`n" -ForegroundColor DarkGray

& "$PSScriptRoot\venv\Scripts\langgraph.exe" dev --no-browser
