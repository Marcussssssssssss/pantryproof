[CmdletBinding()]
param(
    [string]$DeviceSerial,
    [switch]$AllowPhysicalDevice
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$androidRoot = $PSScriptRoot
$gradleWrapper = Join-Path $androidRoot 'gradlew.bat'
$appRoot = Join-Path $androidRoot 'app'
$previousAndroidSerial = $env:ANDROID_SERIAL
$taskResults = [System.Collections.Generic.List[object]]::new()
$verificationFailed = $false
$animationSettings = @(
    'window_animation_scale',
    'transition_animation_scale',
    'animator_duration_scale'
)
$originalAnimationSettings = @{}
$modifiedAnimationSettings = [System.Collections.Generic.List[string]]::new()

function Invoke-AdbCommand {
    param(
        [Parameter(Mandatory)][string]$AdbPath,
        [Parameter(Mandatory)][string[]]$AdbArguments,
        [Parameter(Mandatory)][string]$Description
    )

    $output = @(& $AdbPath @AdbArguments 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $detail = ($output | ForEach-Object { "$_" }) -join [Environment]::NewLine
        throw "ADB command failed while $Description (exit $exitCode): adb $($AdbArguments -join ' ')`n$detail"
    }
    @($output | ForEach-Object { "$_" })
}

function Get-GlobalSetting {
    param(
        [Parameter(Mandatory)][string]$AdbPath,
        [Parameter(Mandatory)][string]$Serial,
        [Parameter(Mandatory)][string]$Name
    )

    $output = Invoke-AdbCommand `
        -AdbPath $AdbPath `
        -AdbArguments @('-s', $Serial, 'shell', 'settings', 'get', 'global', $Name) `
        -Description "reading global setting '$Name'"
    ([string]($output | Select-Object -Last 1)).Trim()
}

function Resolve-AndroidTool {
    param([Parameter(Mandatory)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    foreach ($sdkRoot in @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME)) {
        if ([string]::IsNullOrWhiteSpace($sdkRoot)) { continue }
        $candidate = if ($Name -eq 'adb') {
            Join-Path $sdkRoot 'platform-tools\adb.exe'
        } else {
            Join-Path $sdkRoot 'emulator\emulator.exe'
        }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    throw "Android tool '$Name' was not found on PATH or under ANDROID_SDK_ROOT/ANDROID_HOME."
}

function Get-OnlineDevices {
    param([Parameter(Mandatory)][string]$AdbPath)

    @(Invoke-AdbCommand -AdbPath $AdbPath -AdbArguments @('devices') -Description 'listing online devices') |
        Select-String '^\S+\s+device$' |
        ForEach-Object { ($_.Line -split '\s+')[0] }
}

function Invoke-GradleVerificationTask {
    param(
        [Parameter(Mandatory)][string]$Task,
        [Parameter(Mandatory)][string]$Label
    )

    Write-Host "`n=== $Label ($Task) ==="
    $startedUtc = [DateTime]::UtcNow
    & $gradleWrapper $Task '--console=plain' '--quiet'
    $exitCode = $LASTEXITCODE
    $taskResults.Add([pscustomobject]@{
        Label = $Label
        Task = $Task
        ExitCode = $exitCode
        StartedUtc = $startedUtc
        FinishedUtc = [DateTime]::UtcNow
    })
    if ($exitCode -ne 0) {
        $script:verificationFailed = $true
    }
}

function Read-TestSummary {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][string]$Label,
        [DateTime]$NotOlderThanUtc = [DateTime]::MinValue
    )

    $files = @(
        Get-ChildItem -LiteralPath $Directory -Filter 'TEST-*.xml' -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTimeUtc -ge $NotOlderThanUtc }
    )
    $summary = [ordered]@{ Tests = 0; Failures = 0; Errors = 0; Skipped = 0; Files = $files.Count }
    foreach ($file in $files) {
        [xml]$xml = Get-Content -LiteralPath $file.FullName
        $summary.Tests += [int]$xml.testsuite.tests
        $summary.Failures += [int]$xml.testsuite.failures
        $summary.Errors += [int]$xml.testsuite.errors
        $summary.Skipped += [int]$xml.testsuite.skipped
    }
    Write-Host ("{0}: tests={1} passed={2} failed={3} errors={4} skipped={5} xmlFiles={6}" -f
        $Label,
        $summary.Tests,
        ($summary.Tests - $summary.Failures - $summary.Errors - $summary.Skipped),
        $summary.Failures,
        $summary.Errors,
        $summary.Skipped,
        $summary.Files)
    [pscustomobject]$summary
}

if (-not (Test-Path -LiteralPath $gradleWrapper)) {
    throw "Gradle wrapper not found: $gradleWrapper"
}

$adb = Resolve-AndroidTool -Name 'adb'
$emulator = Resolve-AndroidTool -Name 'emulator'
$availableAvds = @(& $emulator -list-avds)
$onlineDevices = @(Get-OnlineDevices -AdbPath $adb)

if ($DeviceSerial) {
    if ($DeviceSerial -notin $onlineDevices) {
        throw "Requested device '$DeviceSerial' is not online. Online devices: $($onlineDevices -join ', ')"
    }
    $selectedDevice = $DeviceSerial
} elseif ($onlineDevices.Count -eq 1) {
    $selectedDevice = $onlineDevices[0]
} elseif ($onlineDevices.Count -eq 0) {
    throw "No Android device is online. Available AVDs: $($availableAvds -join ', ')"
} else {
    throw "Multiple Android devices are online. Pass -DeviceSerial. Devices: $($onlineDevices -join ', ')"
}

$isEmulator = $selectedDevice.StartsWith('emulator-', [System.StringComparison]::OrdinalIgnoreCase)
if (-not $isEmulator -and -not $AllowPhysicalDevice) {
    throw @"
Physical device '$selectedDevice' was selected. Emulator execution is the safe default.
Re-run with -AllowPhysicalDevice only after accepting that Android Test Orchestrator uses
clearPackageData=true and can clear the installed PantryProof test application's local data.
"@
}
if (-not $isEmulator) {
    Write-Warning @"
Physical-device opt-in accepted for '$selectedDevice'. Android Test Orchestrator runs with
clearPackageData=true and can clear the installed PantryProof test application's local data.
"@
}

$bootOutput = Invoke-AdbCommand `
    -AdbPath $adb `
    -AdbArguments @('-s', $selectedDevice, 'shell', 'getprop', 'sys.boot_completed') `
    -Description 'checking device boot completion'
$bootComplete = ([string]($bootOutput | Select-Object -Last 1)).Trim()
if ($bootComplete -ne '1') {
    throw "Device '$selectedDevice' is online but has not completed booting."
}

$sdk = ([string](Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'shell', 'getprop', 'ro.build.version.sdk') -Description 'reading the device API level' | Select-Object -Last 1)).Trim()
$release = ([string](Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'shell', 'getprop', 'ro.build.version.release') -Description 'reading the Android release' | Select-Object -Last 1)).Trim()
$model = ([string](Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'shell', 'getprop', 'ro.product.model') -Description 'reading the device model' | Select-Object -Last 1)).Trim()
$avdName = if ($isEmulator) {
    ([string](Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'emu', 'avd', 'name') -Description 'reading the AVD name' | Select-Object -First 1)).Trim()
} else {
    'physical-device'
}

Write-Host "Android SDK tools: adb=$adb emulator=$emulator"
Write-Host "Available AVDs: $($availableAvds -join ', ')"
Write-Host "Selected device: serial=$selectedDevice avd=$avdName model=$model Android=$release API=$sdk"

try {
    $env:ANDROID_SERIAL = $selectedDevice

    # A device can report boot-complete while its keyguard still prevents Espresso window focus.
    Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP') -Description 'waking the test device' | Out-Null
    Invoke-AdbCommand -AdbPath $adb -AdbArguments @('-s', $selectedDevice, 'shell', 'wm', 'dismiss-keyguard') -Description 'dismissing the PIN-free test keyguard' | Out-Null
    foreach ($setting in $animationSettings) {
        $value = Get-GlobalSetting -AdbPath $adb -Serial $selectedDevice -Name $setting
        $originalAnimationSettings[$setting] = $value
        # Track before the write so a command that changes the setting but reports
        # failure still triggers an independent restoration attempt.
        $modifiedAnimationSettings.Add($setting)
        Invoke-AdbCommand `
            -AdbPath $adb `
            -AdbArguments @('-s', $selectedDevice, 'shell', 'settings', 'put', 'global', $setting, '0') `
            -Description "disabling animation setting '$setting'" | Out-Null
        $disabledValue = Get-GlobalSetting -AdbPath $adb -Serial $selectedDevice -Name $setting
        $disabledNumber = 1.0
        if (-not [double]::TryParse(
            $disabledValue,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$disabledNumber
        ) -or $disabledNumber -ne 0.0) {
            throw "Animation setting '$setting' did not read back as disabled; value='$disabledValue'."
        }
    }

    Push-Location -LiteralPath $androidRoot
    try {
        Invoke-GradleVerificationTask ':app:assembleDebug' 'Debug build'
        Invoke-GradleVerificationTask ':app:testDebugUnitTest' 'Unit tests'
        Invoke-GradleVerificationTask ':app:lintDebug' 'Android lint'
        Invoke-GradleVerificationTask ':app:connectedDebugAndroidTest' 'Instrumentation tests'
    } finally {
        Pop-Location
    }

    Write-Host "`n=== Parsed verification results ==="
    $unitDirectory = Join-Path $appRoot 'build\test-results\testDebugUnitTest'
    $instrumentationDirectory = Join-Path $appRoot 'build\outputs\androidTest-results\connected\debug'
    $unit = Read-TestSummary -Directory $unitDirectory -Label 'Unit tests'
    $instrumentationTask = $taskResults |
        Where-Object Task -eq ':app:connectedDebugAndroidTest' |
        Select-Object -First 1
    $instrumentation = Read-TestSummary `
        -Directory $instrumentationDirectory `
        -Label 'Instrumentation tests' `
        -NotOlderThanUtc $instrumentationTask.StartedUtc.AddSeconds(-2)

    if ($unit.Tests -eq 0 -or $unit.Failures -gt 0 -or $unit.Errors -gt 0) {
        Write-Error 'Unit-test XML did not report a nonzero passing suite.' -ErrorAction Continue
        $verificationFailed = $true
    }
    if ($instrumentation.Tests -eq 0) {
        Write-Error 'Instrumentation XML reported zero executed tests; NO-SOURCE is not success.' -ErrorAction Continue
        $verificationFailed = $true
    }
    if ($instrumentation.Failures -gt 0 -or $instrumentation.Errors -gt 0) {
        Write-Error 'Instrumentation XML contains failures or errors.' -ErrorAction Continue
        $verificationFailed = $true
    }

    Write-Host "`n=== Task exit codes ==="
    $taskResults | Format-Table -AutoSize
    Write-Host 'Artifacts:'
    Write-Host "  APK: $appRoot\build\outputs\apk\debug\app-debug.apk"
    Write-Host "  Unit XML: $unitDirectory"
    Write-Host "  Unit HTML: $appRoot\build\reports\tests\testDebugUnitTest"
    Write-Host "  Lint XML/HTML: $appRoot\build\reports\lint-results-debug.xml / lint-results-debug.html"
    Write-Host "  Instrumentation XML: $instrumentationDirectory"
    Write-Host "  Instrumentation HTML: $appRoot\build\reports\androidTests\connected\debug"
} finally {
    $animationRestorationFailures = 0
    foreach ($setting in $modifiedAnimationSettings) {
        try {
            $value = $originalAnimationSettings[$setting]
            if ([string]::IsNullOrWhiteSpace($value) -or $value -eq 'null') {
                Invoke-AdbCommand `
                    -AdbPath $adb `
                    -AdbArguments @('-s', $selectedDevice, 'shell', 'settings', 'delete', 'global', $setting) `
                    -Description "restoring absent animation setting '$setting'" | Out-Null
            } else {
                Invoke-AdbCommand `
                    -AdbPath $adb `
                    -AdbArguments @('-s', $selectedDevice, 'shell', 'settings', 'put', 'global', $setting, $value) `
                    -Description "restoring animation setting '$setting'" | Out-Null
            }
            $restoredValue = Get-GlobalSetting -AdbPath $adb -Serial $selectedDevice -Name $setting
            $expectedValue = if ([string]::IsNullOrWhiteSpace($value)) { 'null' } else { $value }
            if ($restoredValue -ne $expectedValue) {
                throw "Animation setting '$setting' restored as '$restoredValue', expected '$expectedValue'."
            }
        } catch {
            $animationRestorationFailures++
            $verificationFailed = $true
            Write-Error "Failed to restore animation setting '$setting': $($_.Exception.Message)" -ErrorAction Continue
        }
    }
    if ($modifiedAnimationSettings.Count -gt 0 -and $animationRestorationFailures -eq 0) {
        Write-Host "Restored and verified $($modifiedAnimationSettings.Count) modified device animation-scale setting(s)."
    } elseif ($animationRestorationFailures -gt 0) {
        Write-Warning "Animation restoration was incomplete: $animationRestorationFailures of $($modifiedAnimationSettings.Count) setting(s) failed verification."
    }
    if ($null -eq $previousAndroidSerial) {
        Remove-Item Env:ANDROID_SERIAL -ErrorAction SilentlyContinue
    } else {
        $env:ANDROID_SERIAL = $previousAndroidSerial
    }
}

if ($verificationFailed) {
    Write-Error 'Android verification failed. Review the task output and XML reports.' -ErrorAction Continue
    exit 1
}

Write-Host 'Android verification passed with nonzero unit and instrumentation tests.'
exit 0
