$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class XingchengWindowCapture {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
}
'@
$targetProcess = Get-Process -Name wechatdevtools | Where-Object { $_.MainWindowTitle -like '星程*' -or $_.MainWindowTitle -like 'xingcheng*' } | Select-Object -First 1
if (-not $targetProcess) { throw '未找到星程开发者工具窗口' }
$bounds = New-Object XingchengWindowCapture+RECT
[void][XingchengWindowCapture]::GetWindowRect($targetProcess.MainWindowHandle, [ref]$bounds)
$bitmap = New-Object System.Drawing.Bitmap ($bounds.Right - $bounds.Left), ($bounds.Bottom - $bounds.Top)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$deviceContext = $graphics.GetHdc()
try { [void][XingchengWindowCapture]::PrintWindow($targetProcess.MainWindowHandle, $deviceContext, 2) }
finally { $graphics.ReleaseHdc($deviceContext) }
$outputPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts\devtools-window.png'
$bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output $outputPath
