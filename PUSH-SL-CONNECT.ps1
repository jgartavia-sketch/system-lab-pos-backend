$ErrorActionPreference = "Stop"
$entrega = Get-Content .\ENTREGA-SL-CONNECT.json -Raw | ConvertFrom-Json
$archivos = @($entrega.archivos)
$origen = git remote get-url origin
if ($LASTEXITCODE -ne 0) { throw "Abri la terminal del repositorio correspondiente." }
$esperado = [regex]::Escape("jgartavia-sketch/$($entrega.repositorio)")
if ($origen -notmatch "$esperado(\.git)?$") { throw "Este ZIP corresponde a $($entrega.repositorio)." }
if ((git branch --show-current) -ne "main") { throw "Selecciona main antes de publicar." }
if ($entrega.tipo -eq "frontend") {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de dependencias." }
    npm run build
} else {
    $python = @($archivos | Where-Object { $_.EndsWith(".py") })
    python -m compileall -q -- $python
}
if ($LASTEXITCODE -ne 0) { throw "La verificacion fallo; no se hizo commit ni push." }
git add -- $archivos
if ($LASTEXITCODE -ne 0) { throw "No se pudieron preparar los archivos." }
$cambios = git diff --cached --name-only -- $archivos
if ($LASTEXITCODE -ne 0) { throw "No se pudo revisar el cambio." }
if ($cambios) {
    git commit -m $entrega.mensaje -- $archivos
    if ($LASTEXITCODE -ne 0) { throw "El commit fallo; no se hizo push." }
}
git push origin main
if ($LASTEXITCODE -ne 0) { throw "El push fallo. Conserva tu commit y revisa el mensaje de Git." }
