<#
크라운 응원봉 — 하나로 합친 작업 스크립트.

인자 없이 실행하면 대화형으로 들어간다 (crown.bat 을 더블클릭한 경우).
그 안에서 번호나 명령을 계속 칠 수 있고, 창이 닫히지 않는다.

인자를 주면 그 명령 하나만 하고 끝난다.

    .\crown.ps1 build               배포 빌드
    .\crown.ps1 build -Dev          개발자 빌드
    .\crown.ps1 burn                굽기 (모니터 안 엶 — 웹 모니터 쓸 때)
    .\crown.ps1 flash -Dev -Erase   플래시 통째로 지우고 굽기
    .\crown.ps1 release             지금 배포 빌드를 서버에 올린다
    .\crown.ps1 version 0.5.1       버전 올리기
    .\crown.ps1 status              어느 빌드가 준비돼 있는지

-Dev 를 붙이면 개발자 빌드를 대상으로 한다. 두 빌드는 build/ 와 build_dev/,
sdkconfig 와 sdkconfig.devbuild 로 완전히 갈라져 있어서 섞이지 않는다.
#>
param(
    [Parameter(Position = 0)][string]$Command,
    [Parameter(Position = 1)][string]$Arg,
    [switch]$Dev,
    [switch]$Erase,
    [switch]$Force,
    [string]$Port
)

Set-Location $PSScriptRoot

<#
  서버 폴더를 찾는다.

  저장소 구조(firmware/ 와 server/ 가 나란히)면 자동으로 잡힌다.
  펌웨어만 다른 곳에 떼어 두고 쓰는 경우 — 예를 들어 프로젝트 경로에 한글이
  있어 ESP-IDF 가 깨지는 바람에 C:\esp\cheerstick 같은 데서 빌드하는 경우 —
  환경변수 CROWN_SERVER_DIR 로 알려준다.
#>
$parent = Split-Path $PSScriptRoot -Parent
$SERVER_DIR =
    if ($env:CROWN_SERVER_DIR)                        { $env:CROWN_SERVER_DIR }
    elseif (Test-Path (Join-Path $parent 'server'))   { Join-Path $parent 'server' }
    else                                              { Join-Path $PSScriptRoot 'server' }
$script:IdfReady = $false

# ESP-IDF 환경은 한 번만 잡으면 된다. 대화형에서 매번 부르면 느리다.
<#
  ESP-IDF 환경을 잡는다. 한 번만 하면 된다 — 대화형에서 매번 부르면 느리다.

  IdfId 는 설치할 때 정해지는 값이라 사람마다 다르다. 그래서
    1. idf.py 가 이미 PATH 에 있으면 그대로 쓰고
    2. 아니면 Initialize-Idf.ps1 을 찾아 부른다 (여러 개면 첫 번째)
    3. 그것도 없으면 안내만 하고 넘어간다
  환경변수 CROWN_IDF_ID 로 직접 지정할 수도 있다.
#>
function Use-Idf {
    if ($script:IdfReady) { return }
    $script:IdfReady = $true

    if (Get-Command idf.py -ErrorAction SilentlyContinue) { return }

    $init = 'C:\Espressif\Initialize-Idf.ps1'
    if (-not (Test-Path $init)) {
        Write-Host "ESP-IDF 를 찾지 못했습니다. ESP-IDF 설치 후 다시 시도하세요." -ForegroundColor Red
        Write-Host "  https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/" -ForegroundColor DarkGray
        return
    }

    if ($env:CROWN_IDF_ID) {
        & $init -IdfId $env:CROWN_IDF_ID *>$null
        return
    }

    # 설치된 IDF 가 하나뿐이면 이름을 몰라도 된다
    $ids = Get-ChildItem 'C:\Espressiframeworks' -Directory -ErrorAction SilentlyContinue
    if ($ids.Count -eq 1) { & $init *>$null } else { & $init *>$null }
}

function Get-Version { (Get-Content 'version.txt' -Raw).Trim() }

# 해당 build 디렉터리가 실제로 어떤 빌드인지 (설정 파일이 아니라 결과물을 본다)
function Test-IsDevBuild([string]$dir) {
    $h = Join-Path $dir 'config\sdkconfig.h'
    if (-not (Test-Path $h)) { return $null }
    return [bool](Select-String -Path $h -Pattern '#define CONFIG_CROWN_DEV 1' -Quiet)
}

function Show-Help {
    Write-Host ""
    Write-Host "  명령" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    build [-Dev]              빌드"
    Write-Host "    burn  [-Dev] [COM3]      굽기 (시리얼 모니터 안 엶)"
    Write-Host "    flash [-Dev] [-Erase]    굽고 시리얼 모니터까지"
    Write-Host "    monitor [-Dev]           굽지 않고 시리얼 로그만 본다"
    Write-Host "    release [-Force]         배포 빌드를 서버에 올린다 (-Force: 되돌리기)"
    Write-Host "    launchpad [https://주소]  브라우저로 굽는 ESP Launchpad 파일 생성"
    Write-Host "    version [0.5.1]          버전 보기 / 올리기"
    Write-Host "    status                   지금 상태"
    Write-Host "    ports                    COM 포트 목록"
    Write-Host "    freeport                 포트 잡은 모니터 종료"
    Write-Host "    exit                     나가기"
    Write-Host ""
    Write-Host "    -Dev 를 붙이면 개발자 빌드 (로그 전송 + 5초마다 갱신 확인)" -ForegroundColor DarkGray
    Write-Host ""
}

function Show-Menu {
    $script:SkipBar = $true
    Write-Host ""
    Write-Host "  크라운 응원봉  v$(Get-Version)" -ForegroundColor Cyan
    Write-Host "  ------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "   1  build         빌드 (배포)"
    Write-Host "   2  build -dev    빌드 (개발자)"
    Write-Host "   3  burn          굽기만 — 모니터 안 엶 (배포)"
    Write-Host "   4  burn -dev     굽기만 (개발자)"
    Write-Host "   5  flash -dev    굽고 시리얼 모니터까지 (개발자)"
    Write-Host "   6  monitor -dev  시리얼 로그만 보기 (굽지 않음)"
    Write-Host ""
    Write-Host "   7  release       서버에 배포 — 봉들이 알아서 받아갑니다" -ForegroundColor Green
    Write-Host ""
    Write-Host "   8  status        지금 상태"
    Write-Host "   9  ports         COM 포트 목록"
    Write-Host "   f  freeport      포트 잡은 모니터 종료"
    Write-Host "   0  나가기"
    Write-Host "  ------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  번호를 누르거나 명령을 직접 치세요. help 로 전체 목록." -ForegroundColor DarkGray
    Write-Host ""
}

# ---------------------------------------------------------------- 명령 본체

function Invoke-Crown {
    param(
        [string]$Command,
        [string]$Arg,
        [switch]$Dev,
        [switch]$Erase,
        [switch]$Force,
        [string]$Port
    )

    $idfArgs = @()
    if ($Dev) {
        $idfArgs += @('-B', 'build_dev',
                      '-D', 'SDKCONFIG=sdkconfig.devbuild',
                      '-D', 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.dev')
    }
    if ($Port) { $idfArgs += @('-p', $Port) }
    $label = if ($Dev) { '개발자 빌드' } else { '배포 빌드' }

    switch ($Command.ToLower()) {

    'build' {
        Use-Idf
        Write-Host "$label v$(Get-Version)" -ForegroundColor Cyan
        idf.py @idfArgs build
    }

    'burn' {
        Use-Idf
        Write-Host "$label v$(Get-Version) 굽는 중" -ForegroundColor Cyan
        idf.py @idfArgs flash
        Write-Host ""
        Write-Host "완료. 시리얼 모니터는 열지 않았습니다." -ForegroundColor Green
        Write-Host "설정 페이지(확장 프로그램 옵션)에서 상태를 보세요."
    }

    'flash' {
        Use-Idf
        if ($Erase) {
            Write-Host "플래시를 통째로 지웁니다 (봉에 저장된 WiFi 설정도 사라집니다)" -ForegroundColor Yellow
            idf.py @idfArgs erase-flash
        }
        Write-Host "$label v$(Get-Version)" -ForegroundColor Cyan
        Write-Host "모니터를 빠져나올 때는 Ctrl+]  (Ctrl+C 아님)" -ForegroundColor DarkGray
        idf.py @idfArgs flash monitor
    }

    'monitor' {
        Use-Idf
        Write-Host "시리얼 모니터를 엽니다. 빠져나올 때는 Ctrl+]  (Ctrl+C 아님)" -ForegroundColor DarkGray
        Write-Host "모니터가 COM 포트를 잡고 있으면 설정 페이지가 봉에 연결하지 못합니다." -ForegroundColor DarkGray
        idf.py @idfArgs monitor
    }

    'release' {
        $ver = Get-Version
        $bin = 'build\cheerstick.bin'

        if (-not (Test-Path $bin)) {
            Write-Host "배포 빌드가 없습니다. 먼저 build 를 하세요." -ForegroundColor Red
            return
        }
        # 개발자 빌드를 실수로 올리면 팬들 봉에서 로그 전송이 켜진다.
        if (Test-IsDevBuild 'build') {
            Write-Host "build\ 안에 개발자 빌드가 들어 있습니다. 배포할 수 없습니다." -ForegroundColor Red
            Write-Host "  build  를 다시 실행해 배포 빌드를 지으세요."
            return
        }

        $live    = Join-Path $SERVER_DIR 'firmware'
        $archive = Join-Path $live 'archive'
        New-Item -ItemType Directory -Force $archive | Out-Null

        # 서버는 firmware/ 의 가장 최근 파일 하나를 내보낸다.
        # 옛 버전은 지우지 않고 archive/ 로 물린다 — 되돌려야 할 때가 온다.
        Get-ChildItem "$live\cheerstick-*.bin" -ErrorAction SilentlyContinue | ForEach-Object {
            Move-Item $_.FullName (Join-Path $archive $_.Name) -Force
            Write-Host "이전 버전 보관: archive\$($_.Name)" -ForegroundColor DarkGray
        }

        $out = Join-Path $live "cheerstick-$ver.bin"
        Copy-Item $bin $out -Force

        <#
          봉은 기본적으로 '더 새것' 만 받는다. 옛 버전을 되돌려 뿌려야 할 때는
          -Force 를 붙인다. 그러면 FORCE 파일이 생기고, 봉이 버전이 낮아지는
          것도 받아들인다.
        #>
        $flag = Join-Path $live 'FORCE'
        if ($Force) {
            Set-Content $flag 'downgrade allowed' -Encoding ascii
            Write-Host "되돌리기 모드: 봉이 이 버전으로 내려갑니다" -ForegroundColor Yellow
        } elseif (Test-Path $flag) {
            Remove-Item $flag -Force
        }
        $kb = [math]::Round((Get-Item $out).Length / 1KB)

        Write-Host ""
        Write-Host "배포: v$ver ($kb KB)" -ForegroundColor Green
        Write-Host "봉이 다음 확인 때 받아 갑니다. 지금 받게 하려면 시리얼에 UPDATE."
    }

    'launchpad' {
        <#
          ESP Launchpad 용 파일을 만든다.

          Launchpad 는 브라우저만으로 보드를 굽게 해주는 웹 도구다.
          ESP-IDF 도, 드라이버도 필요 없다 (이 보드는 USB-Serial-JTAG 이 내장).

          합쳐진(merged) 이미지 하나를 요구한다. 부트로더·파티션테이블·
          otadata·앱이 한 파일로 들어가고 0x0 에 통째로 구워진다.

          주의: 합쳐진 이미지는 NVS 자리(0x9000)를 0xFF 로 덮는다. 즉
          **WiFi 설정이 지워진다.** 처음 굽는 보드에는 맞고, 이미 설정된
          봉을 다시 구울 때는 설정을 다시 넣어야 한다.
        #>
        Use-Idf
        $ver = Get-Version

        if (Test-IsDevBuild 'build') {
            Write-Host "build\ 안에 개발자 빌드가 들어 있습니다. 먼저 build 를 하세요." -ForegroundColor Red
            return
        }
        if (-not (Test-Path 'build\cheerstick.bin')) {
            Write-Host "배포 빌드가 없습니다. 먼저 build 를 하세요." -ForegroundColor Red
            return
        }

        $name = "cheerstick-$ver-merged.bin"
        New-Item -ItemType Directory -Force 'build\launchpad' | Out-Null
        idf.py merge-bin -o "launchpad\$name" | Out-Null

        $src = "build\launchpad\$name"
        if (-not (Test-Path $src)) {
            Write-Host "합치기에 실패했습니다." -ForegroundColor Red
            return
        }

        $dest = Join-Path $SERVER_DIR 'launchpad'
        New-Item -ItemType Directory -Force $dest | Out-Null
        Get-ChildItem "$dest\cheerstick-*-merged.bin" -ErrorAction SilentlyContinue | Remove-Item -Force
        Copy-Item $src (Join-Path $dest $name) -Force

        # config.toml — Launchpad 가 이걸 읽고 무엇을 어디서 가져올지 정한다
        $base = if ($Arg) { $Arg.TrimEnd('/') } else { 'https://주소를-여기에' }
        $toml = @"
esp_toml_version = 1.0

firmware_images_url = "$base/launchpad/"

supported_apps = ["crown"]

[crown]
chipsets = ["ESP32-S3"]
image.esp32-s3 = "$name"
description = "크라운 응원봉 v$ver — 흔들면 치지직 채팅에 이모티콘이 올라갑니다"
console_baudrate = 115200
"@
        # PowerShell 5.1 의 -Encoding utf8 은 BOM 을 붙인다. TOML 파서가 걸릴 수
        # 있으므로 BOM 없이 쓴다.
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText((Join-Path $dest 'config.toml'), $toml, $utf8)

        <#
          Netlify / Cloudflare Pages 용 CORS 설정.

          Launchpad 는 espressif.github.io 에서 돌면서 이 파일들을 가져가므로
          다른 출처를 허용해야 한다. GitHub Pages 는 기본으로 허용하지만
          다른 곳은 아니라서, 어디에 올리든 되도록 같이 둔다. 모르는 호스트는
          이 파일을 그냥 무시한다.
        #>
        $headers = "/*`n  Access-Control-Allow-Origin: *`n"
        [System.IO.File]::WriteAllText((Join-Path $dest '_headers'), $headers, $utf8)

        $kb = [math]::Round((Get-Item $src).Length / 1KB)
        Write-Host ""
        Write-Host "만들었습니다: $name ($kb KB)" -ForegroundColor Green
        Write-Host "  -> $dest"
        Write-Host ""
        if ($Arg) {
            Write-Host "팬에게 줄 주소:" -ForegroundColor Cyan
            Write-Host "  https://espressif.github.io/esp-launchpad/?flashConfigURL=$base/launchpad/config.toml"
        } else {
            Write-Host "서버 주소를 주면 팬에게 줄 링크까지 만들어 드립니다:" -ForegroundColor Yellow
            Write-Host "  launchpad https://crown.내도메인"
        }
        Write-Host ""
        Write-Host "주소는 반드시 https 여야 합니다. Launchpad 가 https 라 평문은 브라우저가 막습니다." -ForegroundColor DarkGray
        Write-Host "굽는 순간 봉의 WiFi 설정이 지워집니다 (NVS 가 함께 덮이기 때문)." -ForegroundColor DarkGray
    }

    'version' {
        if (-not $Arg) {
            Write-Host "지금 버전: $(Get-Version)"
            Write-Host "바꾸려면:  version 0.5.1"
            return
        }
        if ($Arg -notmatch '^\d+\.\d+\.\d+$') {
            Write-Host "버전은 0.5.1 형태여야 합니다." -ForegroundColor Red
            return
        }
        $old = Get-Version
        Set-Content 'version.txt' $Arg -NoNewline -Encoding ascii
        Write-Host "펌웨어  $old  ->  $Arg" -ForegroundColor Green

        <#
          확장 버전도 같이 올린다.

          따로 두면 반드시 어긋난다 — 실제로 확장이 0.4.0 에 멈춰 있는 동안
          코드가 네 번 바뀌었다. 숫자가 같으면 "이 봉과 이 확장은 한 세트"
          라고 말할 수 있어서 팬에게 안내하기도 쉽다.

          manifest.json 과 inject.js 두 곳에 있다. inject.js 쪽은 콘솔 배너와
          crown.diag() 에 찍히는 값이다.
        #>
        $ext = Join-Path (Split-Path $PSScriptRoot -Parent) 'extension'
        if (-not (Test-Path $ext)) { $ext = $env:CROWN_EXTENSION_DIR }

        if ($ext -and (Test-Path $ext)) {
            foreach ($f in @(
                @{ path = 'manifest.json'; pat = '("version"\s*:\s*")[^"]+(")' },
                @{ path = 'inject.js';     pat = "(const VERSION = ')[^']+(')" }
            )) {
                $full = Join-Path $ext $f.path
                if (-not (Test-Path $full)) { continue }
                $txt = [System.IO.File]::ReadAllText($full)
                $new = [regex]::Replace($txt, $f.pat, "`${1}$Arg`${2}", 1)
                if ($new -ne $txt) {
                    [System.IO.File]::WriteAllText($full, $new,
                        (New-Object System.Text.UTF8Encoding $false))
                    Write-Host "확장    $($f.path) 갱신" -ForegroundColor Green
                }
            }
        } else {
            Write-Host "확장 폴더를 못 찾아 건너뜁니다 (CROWN_EXTENSION_DIR 로 지정 가능)" -ForegroundColor DarkGray
        }

        Write-Host ""
        Write-Host "다시 빌드해야 봉이 새 버전으로 인식합니다."
        Write-Host "확장은 chrome://extensions 에서 새로고침하면 됩니다."
    }

    'status' {
        Write-Host ""
        Write-Host "  버전 (version.txt) : $(Get-Version)" -ForegroundColor Cyan
        Write-Host ""
        foreach ($d in @('build', 'build_dev')) {
            $bin = Join-Path $d 'cheerstick.bin'
            if (-not (Test-Path $bin)) {
                Write-Host ("  {0,-10} 없음" -f $d) -ForegroundColor DarkGray
                continue
            }
            $isDev = Test-IsDevBuild $d
            $kind  = if ($isDev) { '개발자' } else { '배포  ' }
            $kb    = [math]::Round((Get-Item $bin).Length / 1KB)
            $when  = (Get-Item $bin).LastWriteTime.ToString('MM-dd HH:mm')
            $color = if ($isDev) { 'Yellow' } else { 'Green' }
            Write-Host ("  {0,-10} {1}  {2} KB  {3}" -f $d, $kind, $kb, $when) -ForegroundColor $color
        }
        Write-Host ""
        $live = Join-Path $SERVER_DIR 'firmware'
        $cur = Get-ChildItem "$live\cheerstick-*.bin" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($cur) {
            Write-Host "  서버에 올라간 것 : $($cur.Name)" -ForegroundColor Cyan
        } else {
            Write-Host "  서버에 올라간 것 : 없음" -ForegroundColor DarkGray
        }
        $old = @(Get-ChildItem "$live\archive\cheerstick-*.bin" -ErrorAction SilentlyContinue)
        if ($old.Count) { Write-Host "  보관 중인 이전 버전 : $($old.Count)개" -ForegroundColor DarkGray }
        Write-Host ""
    }

    'ports' {
        Get-CimInstance Win32_PnPEntity |
          Where-Object { $_.Name -match 'COM\d+' } |
          Select-Object @{n='포트';e={[regex]::Match($_.Name,'COM\d+').Value}}, Name |
          Format-Table -AutoSize | Out-Host
    }

    'freeport' {
        # 설정 페이지가 "연결 실패" 할 때. ESP-IDF 모니터만 골라 죽인다.
        $targets = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -match 'esp_idf_monitor|idf_monitor|idf\.py.*monitor' }
        if (-not $targets) {
            Write-Host "포트를 잡고 있는 모니터가 없습니다." -ForegroundColor Green
        } else {
            foreach ($t in $targets) {
                Write-Host ("종료: PID {0}" -f $t.ProcessId)
                Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Write-Host "정리 완료." -ForegroundColor Green
        }
    }

    { $_ -in 'help', '?', '' } { Show-Help }

    default {
        Write-Host "모르는 명령: $Command" -ForegroundColor Red
        Write-Host "help 를 치면 목록이 나옵니다." -ForegroundColor DarkGray
    }

    }
}

function Show-Bar {
    Write-Host ""
    Write-Host "  ------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "   1 build  2 build-dev  3 burn  4 burn-dev  5 flash-dev  6 monitor" -ForegroundColor DarkGray
    Write-Host "   7 release     8 status   9 ports   f freeport   0 나가기" -ForegroundColor DarkGray
}

# ------------------------------------------------------- 입력 한 줄 처리

# 번호는 자주 쓰는 명령의 지름길일 뿐이다. 명령을 직접 쳐도 된다.
$MENU = @{
    '1' = 'build';      '2' = 'build -dev'
    '3' = 'burn';       '4' = 'burn -dev'
    '5' = 'flash -dev'; '6' = 'monitor -dev'
    '7' = 'release'
    '8' = 'status';     '9' = 'ports';      'f' = 'freeport'
}

function Invoke-Line([string]$line) {
    $t = $line.Trim()
    if (-not $t) { return }
    if ($MENU.ContainsKey($t)) { $t = $MENU[$t] }

    $parts = $t -split '\s+'
    $cmd = $parts[0]
    $a = $null; $d = $false; $e = $false; $f = $false; $p = $null

    for ($i = 1; $i -lt $parts.Count; $i++) {
        $tok = $parts[$i]
        if     ($tok -match '^-{0,2}dev$')   { $d = $true }
        elseif ($tok -match '^-{0,2}erase$') { $e = $true }
        elseif ($tok -match '^-{0,2}force$') { $f = $true }
        elseif ($tok -match '^COM\d+$')      { $p = $tok }
        elseif ($tok -match '^-{0,2}port$')  { $i++; if ($i -lt $parts.Count) { $p = $parts[$i] } }
        else                                 { $a = $tok }
    }

    try {
        Invoke-Crown -Command $cmd -Arg $a -Dev:$d -Erase:$e -Force:$f -Port $p
    } catch {
        Write-Host "실패: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# ------------------------------------------------------------------ 진입

if ($Command) {
    # 인자를 준 경우 — 한 번만 하고 끝낸다
    Invoke-Crown -Command $Command -Arg $Arg -Dev:$Dev -Erase:$Erase -Force:$Force -Port $Port
    return
}

Show-Menu
while ($true) {
    if (-not $script:SkipBar) { Show-Bar }
    $script:SkipBar = $false
    Write-Host "crown> " -NoNewline -ForegroundColor Cyan
    $line = Read-Host
    if ($null -eq $line) { break }                       # Ctrl+Z
    $t = $line.Trim().ToLower()
    if ($t -in '0', 'exit', 'quit', 'q') { break }
    if ($t -in 'menu', 'm') { Show-Menu; continue }
    if ($t -in 'cls', 'clear') { Clear-Host; Show-Menu; continue }
    Invoke-Line $line
}
