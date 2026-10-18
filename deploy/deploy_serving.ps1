$repo = Split-Path $PSScriptRoot -Parent
# Builds the model container and (re)deploys it to Cloud Run, then points the router at it.
# usage: deploy_serving.ps1 v4
if ($env:GOMITRA_GCLOUD_CONFIG) { $env:CLOUDSDK_CONFIG = $env:GOMITRA_GCLOUD_CONFIG }
if ($env:GOMITRA_GCLOUD_PYTHON) { $env:CLOUDSDK_PYTHON = $env:GOMITRA_GCLOUD_PYTHON }
$g = if ($env:GOMITRA_GCLOUD) { $env:GOMITRA_GCLOUD } else { "gcloud" }
$p = "cattle-id-511705"; $r = "asia-south1"; $img = "$r-docker.pkg.dev/$p/cattle"
$sa = "gomitra-router@$p.iam.gserviceaccount.com"
$tag = $args[0]
"== build serving $tag"
& $g builds submit "$repo\serving" --tag "$img/serving:$tag" --project=$p --region=$r --quiet
"== deploy serving $tag"
& $g run deploy cattle-serving --image "$img/serving:$tag" --region=$r --project=$p --port=8080 --memory=4Gi --cpu=2 `
  --no-cpu-throttling --min-instances=1 --max-instances=2 --timeout=300 --no-allow-unauthenticated --quiet
$serving = (& $g run services describe cattle-serving --region=$r --project=$p --format="value(status.url)").Trim()
"serving url: $serving"
& $g run services add-iam-policy-binding cattle-serving --region=$r --project=$p --member="serviceAccount:$sa" --role=roles/run.invoker --quiet | Out-Null
& $g run services update gomitra --region=$r --project=$p --update-env-vars="SERVING_URL=$serving" --quiet
"DONE"
