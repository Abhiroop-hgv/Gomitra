# Deploys the GoMitra backend: service account + roles, router image, model container (Cloud Run), router (Cloud Run).
# Run from the folder that contains router\ and serving\.  Re-running is safe.
$ErrorActionPreference = "Continue"
if ($env:GOMITRA_GCLOUD_CONFIG) { $env:CLOUDSDK_CONFIG = $env:GOMITRA_GCLOUD_CONFIG }
if ($env:GOMITRA_GCLOUD_PYTHON) { $env:CLOUDSDK_PYTHON = $env:GOMITRA_GCLOUD_PYTHON }
$g = if ($env:GOMITRA_GCLOUD) { $env:GOMITRA_GCLOUD } else { "gcloud" }
$p = "cattle-id-511705"; $r = "asia-south1"; $img = "$r-docker.pkg.dev/$p/cattle"
$sa = "gomitra-router@$p.iam.gserviceaccount.com"
$tag = if ($args.Count -gt 0) { $args[0] } else { "v1" }

"== service account"
& $g iam service-accounts create gomitra-router --display-name="GoMitra router" --project=$p
foreach ($role in "roles/datastore.user", "roles/aiplatform.user") {
  & $g projects add-iam-policy-binding $p --member="serviceAccount:$sa" --role=$role --condition=None --quiet | Out-Null
}

"== build router image $tag"
& $g builds submit "$PSScriptRoot\router" --tag "$img/router:$tag" --project=$p --region=$r --quiet

"== model container on Cloud Run (private)"
& $g run deploy cattle-serving --image "$img/serving:v3" --region=$r --project=$p --port=8080 --memory=4Gi --cpu=2 `
  --no-cpu-throttling --min-instances=1 --max-instances=2 --timeout=300 --no-allow-unauthenticated --quiet
$serving = (& $g run services describe cattle-serving --region=$r --project=$p --format="value(status.url)").Trim()
"serving url: $serving"
& $g run services add-iam-policy-binding cattle-serving --region=$r --project=$p --member="serviceAccount:$sa" --role=roles/run.invoker --quiet | Out-Null

"== router on Cloud Run (public)"
$keyFile = "$PSScriptRoot\.admin_key"
if (-not (Test-Path $keyFile)) { -join ((1..24) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) }) | Set-Content $keyFile }
$key = (Get-Content $keyFile).Trim()
& $g run deploy gomitra --image "$img/router:$tag" --region=$r --project=$p --service-account=$sa --allow-unauthenticated `
  --memory=1Gi --cpu=1 --min-instances=0 --max-instances=4 --timeout=300 `
  --set-env-vars="INFER_BACKEND=cloudrun,SERVING_URL=$serving,ADMIN_KEY=$key,PROJECT=$p,REGION=$r" --quiet
"router url: " + (& $g run services describe gomitra --region=$r --project=$p --format="value(status.url)")
"DONE"
