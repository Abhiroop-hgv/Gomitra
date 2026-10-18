# Builds the pose container (slow: PyTorch + DeepLabCut + weights) and deploys it to Cloud Run (private). usage: deploy_pose.ps1 v1
if ($env:GOMITRA_GCLOUD_CONFIG) { $env:CLOUDSDK_CONFIG = $env:GOMITRA_GCLOUD_CONFIG }
if ($env:GOMITRA_GCLOUD_PYTHON) { $env:CLOUDSDK_PYTHON = $env:GOMITRA_GCLOUD_PYTHON }
$g = if ($env:GOMITRA_GCLOUD) { $env:GOMITRA_GCLOUD } else { "gcloud" }
$p = "cattle-id-511705"; $r = "asia-south1"; $img = "$r-docker.pkg.dev/$p/cattle"
$sa = "gomitra-router@$p.iam.gserviceaccount.com"
$tag = $args[0]
"== build pose $tag"
& $g builds submit "$PSScriptRoot\pose" --tag "$img/pose:$tag" --project=$p --region=$r --machine-type=e2-highcpu-8 --timeout=3000 --quiet
if ($args.Count -gt 1 -and $args[1] -eq "build-only") { "DONE (build only)"; exit }
"== deploy pose $tag"
& $g run deploy gomitra-pose --image "$img/pose:$tag" --region=$r --project=$p --port=8080 --memory=8Gi --cpu=4 --no-cpu-throttling `
  --concurrency=1 --min-instances=0 --max-instances=1 --timeout=300 --no-allow-unauthenticated --quiet
$url = (& $g run services describe gomitra-pose --region=$r --project=$p --format="value(status.url)").Trim()
"pose url: $url"
& $g run services add-iam-policy-binding gomitra-pose --region=$r --project=$p --member="serviceAccount:$sa" --role=roles/run.invoker --quiet | Out-Null
& $g run services update gomitra --region=$r --project=$p --update-env-vars="POSE_URL=$url" --quiet
"ALLDONE"
