# Ψεύτικος ζυγός για Windows - δεν χρειάζεται Python.
# Ακούει στη θύρα 80 και καταγράφει ό,τι του στέλνει το AutoProcess.
# Εκτέλεση:  powershell -ExecutionPolicy Bypass -File fake_scale.ps1

$ErrorActionPreference = "Stop"
$out = Join-Path $PSScriptRoot "katagrafi_zygou.txt"
$port = 1235
if ($args.Count -gt 0) { $port = [int]$args[0] }

function Write-Both([string]$text) {
    Write-Host $text
    Add-Content -Path $out -Value $text -Encoding UTF8
}

Set-Content -Path $out -Value "" -Encoding UTF8
Write-Both "Psefdikos zygos: akouei sti thyra $port  (i thyra tou zygou)"
Write-Both "Vale 127.0.0.1 sto ip.xml kai trekse to AutoProcess."
Write-Both "Katagrafi sto arxeio: $out"
Write-Both "Stamatima: Ctrl+C`r`n"

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $port)
try { $listener.Start() }
catch {
    Write-Both "SFALMA: den mporo na desmefso ti thyra $port"
    Write-Both $_.Exception.Message
    Write-Both "Dokimase alli thyra i kleise oti trexei se afti."
    Read-Host "Enter gia eksodo"; exit 1
}

$n = 0
while ($true) {
    $client = $listener.AcceptTcpClient()
    $n++
    $stream = $client.GetStream()
    $client.ReceiveTimeout = 5000

    # --- διάβασε κεφαλίδες μέχρι την κενή γραμμή ---
    $buf = New-Object byte[] 65536
    $all = New-Object System.Collections.Generic.List[byte]
    $headerEnd = -1
    while ($headerEnd -lt 0) {
        $read = $stream.Read($buf, 0, $buf.Length)
        if ($read -le 0) { break }
        for ($i = 0; $i -lt $read; $i++) { $all.Add($buf[$i]) }
        $txt = [System.Text.Encoding]::ASCII.GetString($all.ToArray())
        $headerEnd = $txt.IndexOf("`r`n`r`n")
    }
    $bytes = $all.ToArray()
    $asText = [System.Text.Encoding]::ASCII.GetString($bytes)
    if ($headerEnd -lt 0) { $headerEnd = $asText.Length - 4 }
    $headers = $asText.Substring(0, $headerEnd)

    # --- διάβασε το σώμα, με βάση το Content-Length ---
    $len = 0
    if ($headers -match "(?im)^Content-Length:\s*(\d+)") { $len = [int]$Matches[1] }
    $bodyStart = $headerEnd + 4
    $have = $bytes.Length - $bodyStart
    while ($have -lt $len) {
        $read = $stream.Read($buf, 0, [Math]::Min($buf.Length, $len - $have))
        if ($read -le 0) { break }
        for ($i = 0; $i -lt $read; $i++) { $all.Add($buf[$i]) }
        $have += $read
    }
    $bytes = $all.ToArray()
    $bodyBytes = @()
    if ($bytes.Length -gt $bodyStart) {
        $bodyBytes = $bytes[$bodyStart..($bytes.Length - 1)]
    }

    Write-Both ("`r`n" + ("=" * 78))
    Write-Both ("AITIMA #$n   " + (Get-Date -Format "HH:mm:ss"))
    Write-Both ("=" * 78)
    Write-Both "--- KEFALIDES ---"
    Write-Both $headers
    if ($bodyBytes.Length -gt 0) {
        Write-Both "`r`n--- SOMA ($($bodyBytes.Length) bytes) ---"
        $body = [System.Text.Encoding]::UTF8.GetString($bodyBytes)
        Write-Both $body
    } else {
        Write-Both "`r`n(xoris soma)"
    }

    # --- απάντηση «ok» ---
    $json = '{"result":"success","code":0,"msg":"ok","status":"success"}'
    $payload = [System.Text.Encoding]::UTF8.GetBytes($json)
    $head = "HTTP/1.1 200 OK`r`nContent-Type: application/json`r`nContent-Length: $($payload.Length)`r`nConnection: close`r`n`r`n"
    $headBytes = [System.Text.Encoding]::ASCII.GetBytes($head)
    $stream.Write($headBytes, 0, $headBytes.Length)
    $stream.Write($payload, 0, $payload.Length)
    $stream.Flush()
    $client.Close()
}
