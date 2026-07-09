# 将 Node.js 添加到用户 PATH

$nodePath = "C:\Program Files\nodejs"
$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User')

if ($currentPath -notlike "*$nodePath*") {
    [Environment]::SetEnvironmentVariable('Path', "$currentPath;$nodePath", 'User')
    Write-Host "✓ 已将 Node.js 添加到 PATH: $nodePath" -ForegroundColor Green
    Write-Host ""
    Write-Host "请关闭当前命令行窗口，重新打开后生效。" -ForegroundColor Yellow
} else {
    Write-Host "✓ Node.js 已在 PATH 中" -ForegroundColor Green
}
