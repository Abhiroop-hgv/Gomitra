# Rebuilds the router + web app image and rolls the Cloud Run service forward. usage: deploy_router.ps1 v2
if ($env:GOMITRA_GCLOUD_CONFIG) { $env:CLOUDSDK_CONFIG = $env:GOMITRA_GCLOUD_CONFIG }
if ($env:GOMITRA_GCLOUD_PYTHON) { $env:CLOUDSDK_PYTHON = $env:GOMITRA_GCLOUD_PYTHON }
$g = if ($env:GOMITRA_GCLOUD) { $env:GOMITRA_GCLOUD } else { "gcloud" }
$p = "cattle-id-511705"; $r = "asia-south1"; $img = "$r-docker.pkg.dev/$p/cattle"
$tag = $args[0]
"== build router $tag"
& $g builds submit "$PSScriptRoot\router" --tag "$img/router:$tag" --project=$p --region=$r --quiet
"== deploy router $tag"
& $g run deploy gomitra --image "$img/router:$tag" --region=$r --project=$p --quiet
"DONE"
