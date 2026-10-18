# Points the router at Vertex AI or at the Cloud Run model container.
#   .\switch_backend.ps1 vertex 4319921811904004096     (after the deploy-model command has finished)
#   .\switch_backend.ps1 cloudrun                       (back to Cloud Run, e.g. after undeploying Vertex)
if ($env:GOMITRA_GCLOUD_CONFIG) { $env:CLOUDSDK_CONFIG = $env:GOMITRA_GCLOUD_CONFIG }
if ($env:GOMITRA_GCLOUD_PYTHON) { $env:CLOUDSDK_PYTHON = $env:GOMITRA_GCLOUD_PYTHON }
$g = if ($env:GOMITRA_GCLOUD) { $env:GOMITRA_GCLOUD } else { "gcloud" }
$p = "cattle-id-511705"; $r = "asia-south1"
if ($args[0] -eq "vertex") {
  & $g run services update gomitra --region=$r --project=$p --update-env-vars="INFER_BACKEND=vertex,ENDPOINT_ID=$($args[1])" --quiet
} else {
  & $g run services update gomitra --region=$r --project=$p --update-env-vars="INFER_BACKEND=cloudrun" --quiet
}
(Invoke-RestMethod "https://gomitra-337344659283.asia-south1.run.app/api/status") | ConvertTo-Json
