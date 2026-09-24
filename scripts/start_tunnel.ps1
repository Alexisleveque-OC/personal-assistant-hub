# ==============================================================================
# Personal Assistant Hub - Lanceur de Tunnel Sécurisé Cloudflare (Mobile HTTPS)
# ==============================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $workspaceRoot "tools"
$cloudflaredPath = Join-Path $toolsDir "cloudflared.exe"
$envPath = Join-Path $workspaceRoot ".env"

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "   🚀 Personal Assistant Hub - Tunnel Sécurisé Mobile HTTPS" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""

# 1. Vérifier si le serveur backend Uvicorn tourne sur le port 8000
$portActive = $false
try {
    $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue
    $portActive = $conn.TcpTestSucceeded
} catch {
    $portActive = $false
}

if (-not $portActive) {
    Write-Host "⚠️  Attention : Le serveur local Uvicorn n'est pas détecté sur le port 8000." -ForegroundColor Yellow
    Write-Host "   Pensez à lancer le serveur dans un terminal séparé avec :" -ForegroundColor Yellow
    Write-Host "   .\.venv\Scripts\uvicorn app.main:app --reload --port 8000" -ForegroundColor White
    Write-Host ""
    $continue = Read-Host "Souhaitez-vous continuer quand même ? (O/n)"
    if ($continue -eq "n") {
        exit 0
    }
} else {
    Write-Host "✅ Serveur local actif sur http://127.0.0.1:8000" -ForegroundColor Green
}

# 2. Récupérer la clé API configurée dans le fichier .env (si présente)
$apiKey = ""
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match "^\s*API_KEY\s*=\s*(.+)$") {
            $apiKey = $matches[1].Trim(' "\''')
        }
    }
}

# 3. Vérifier la présence de cloudflared (dans PATH ou dans tools/)
if (-not (Test-Path $cloudflaredPath)) {
    $cmd = Get-Command "cloudflared" -ErrorAction SilentlyContinue
    if ($cmd) {
        $cloudflaredPath = $cmd.Source
    } else {
        Write-Host "⬇️  Téléchargement automatique de Cloudflare Tunnel (cloudflared)..." -ForegroundColor Cyan
        if (-not (Test-Path $toolsDir)) {
            New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
        }
        $cfUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        curl.exe -L -o $cloudflaredPath $cfUrl
        Write-Host "✅ Téléchargement terminé." -ForegroundColor Green
    }
}

# 4. Lancement du tunnel Cloudflare
Write-Host "🌐 Démarrage du tunnel HTTPS vers http://127.0.0.1:8000..." -ForegroundColor Cyan
$tempLog = Join-Path $workspaceRoot "tunnel.log"
if (Test-Path $tempLog) { Remove-Item $tempLog -Force }

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $cloudflaredPath
$processInfo.Arguments = "tunnel --url http://127.0.0.1:8000"
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true
$processInfo.UseShellExecute = $false
$processInfo.CreateNoWindow = $true

$process = [System.Diagnostics.Process]::Start($processInfo)

# Attente de la détection de l'URL publique
$publicUrl = ""
$startTime = [DateTime]::UtcNow

try {
    while (-not $process.HasExited) {
        $line = $process.StandardError.ReadLine()
        if ($line) {
            Add-Content -Path $tempLog -Value $line
            if ($line -match "(https://[a-zA-Z0-9-]+\.trycloudflare\.com)") {
                $publicUrl = $matches[1]
                break
            }
        }
        if (([DateTime]::UtcNow - $startTime).TotalSeconds -gt 30) {
            Write-Host "❌ Délai d'attente dépassé pour la création du tunnel." -ForegroundColor Red
            break
        }
    }

    if ($publicUrl) {
        $appUrl = "$publicUrl/app"
        Write-Host ""
        Write-Host "==================================================================" -ForegroundColor Green
        Write-Host "   🎉 VOTRE TUNNEL SÉCURISÉ EST EN LIGNE !" -ForegroundColor Green
        Write-Host "==================================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "📱 URL À OUVRIR SUR LE SMARTPHONE :" -ForegroundColor Yellow
        Write-Host "   $appUrl" -ForegroundColor Cyan -BackgroundColor Black
        Write-Host ""
        Write-Host "📷 OU SCANNEZ DIRECTEMENT CE QR CODE AVEC VOTRE SMARTPHONE :" -ForegroundColor Yellow
        try {
            curl.exe -s --max-time 4 "https://qrenco.de/$appUrl"
        } catch {
            # Affichage alternatif silencieux si le service qr est temporairement indisponible
        }
        Write-Host ""

        if ($apiKey) {
            Write-Host "🔑 Clé API détectée (.env) :" -ForegroundColor Yellow
            Write-Host "   $apiKey" -ForegroundColor Magenta
            Write-Host "   (À renseigner dans l'icône Paramètres ⚙️ de la PWA sur votre mobile)" -ForegroundColor Gray
        } else {
            Write-Host "ℹ️  Aucune clé API configurée dans .env (Mode permissif actif)." -ForegroundColor Gray
        }

        Write-Host ""
        Write-Host "📋 PROCHAINES ÉTAPES SUR VOTRE SMARTPHONE :" -ForegroundColor White
        Write-Host "   1. Ouvrez Chrome sur votre smartphone et allez sur : $appUrl" -ForegroundColor Gray
        Write-Host "   2. Touchez le menu de Chrome (3 points verticaux) > 'Ajouter à l'écran d'accueil'" -ForegroundColor Gray
        Write-Host "   3. L'application s'installe en plein écran avec sa propre icône." -ForegroundColor Gray
        Write-Host ""
        Write-Host "💡 Appuyez sur Ctrl+C pour arrêter le tunnel à tout moment." -ForegroundColor DarkGray
        Write-Host "==================================================================" -ForegroundColor Green
        Write-Host ""

        # Maintenir le tunnel ouvert et relayer les logs importants
        while (-not $process.HasExited) {
            $line = $process.StandardError.ReadLine()
            if ($line -and ($line -match "ERR" -or $line -match "WARN" -or $line -match "Registered tunnel")) {
                Write-Host $line -ForegroundColor DarkGray
            }
        }
    } else {
        Write-Host "❌ Impossible de récupérer l'URL publique de Cloudflare." -ForegroundColor Red
        if (Test-Path $tempLog) {
            Get-Content $tempLog -Tail 10 | Write-Host -ForegroundColor DarkRed
        }
    }
} finally {
    if (-not $process.HasExited) {
        Write-Host "🛑 Arrêt du tunnel..." -ForegroundColor Yellow
        $process.Kill()
    }
    if (Test-Path $tempLog) {
        Remove-Item $tempLog -Force -ErrorAction SilentlyContinue
    }
}
