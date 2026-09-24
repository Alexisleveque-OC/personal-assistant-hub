Add-Type -AssemblyName System.Drawing

$srcPath = "C:\Users\alexi\.gemini\antigravity-ide\brain\2bd36cda-f34a-45e9-8693-7aed48b626db\.user_uploaded\media_1790241389464.png"
$destDir = "c:\Users\alexi\.gemini\antigravity-ide\scratch\personal-assistant-hub\app\static\icons"

if (-not (Test-Path $srcPath)) {
    Write-Error "Source file does not exist: $srcPath"
    exit 1
}

$src = [System.Drawing.Bitmap]::new($srcPath)

# Content bounds: minX=210, minY=190, maxX=850, maxY=892
# Width=640, Height=702. Center = (530, 541)
# Desired 5% margin around the max dimension (Height 702):
# Box size = 702 / 0.90 = 780
$boxSize = 780
$srcX = [int][Math]::Round(530 - ($boxSize / 2)) # 140
$srcY = [int][Math]::Round(541 - ($boxSize / 2)) # 151

Write-Host "Cropping source rectangle: X=$srcX, Y=$srcY, Width=$boxSize, Height=$boxSize"
$srcRect = [System.Drawing.Rectangle]::new($srcX, $srcY, $boxSize, $boxSize)
$bgColor = [System.Drawing.Color]::FromArgb(255, 247, 246, 242) # theme cream #f7f6f2

# Helper function to save high quality bitmap
function Save-HQImage($srcBmp, $destW, $destH, $outPath, $useBgColor, $artW, $artH, $artX, $artY) {
    $bmp = [System.Drawing.Bitmap]::new($destW, $destH, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    if ($useBgColor) {
        $g.Clear($bgColor)
    } else {
        $g.Clear([System.Drawing.Color]::Transparent)
    }
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    
    $destRect = [System.Drawing.Rectangle]::new($artX, $artY, $artW, $artH)
    $g.DrawImage($srcBmp, $destRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
    Write-Host "Saved: $outPath"
}

# 1. Standard transparent icons (app header, desktop favicons)
Save-HQImage $src 512 512 (Join-Path $destDir "icon-512.png") $false 512 512 0 0
Save-HQImage $src 512 512 (Join-Path $destDir "icon.png") $false 512 512 0 0
Save-HQImage $src 192 192 (Join-Path $destDir "icon-192.png") $false 192 192 0 0

# 2. Maskable Android icons for Home Screen (with #f7f6f2 background and ~82% safe zone so it fills the adaptive icon)
Save-HQImage $src 512 512 (Join-Path $destDir "icon-maskable-512.png") $true 430 430 41 41
Save-HQImage $src 192 192 (Join-Path $destDir "icon-maskable-192.png") $true 162 162 15 15

# 3. Apple Touch Icon for iOS / Mobile Chrome Add-to-Home
Save-HQImage $src 180 180 (Join-Path $destDir "apple-touch-icon.png") $true 162 162 9 9

$src.Dispose()
Write-Host "All home screen & PWA icons generated successfully!"
