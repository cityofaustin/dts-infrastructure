# SNS Slack Notifier Lambda

Python Lambda packaged as a container image. Subscribe it to an SNS topic; it posts each SNS record to a Slack channel via an incoming webhook (and logs to CloudWatch).

Set `SLACK_WEBHOOK_URL` to your Slack incoming webhook URL (the same URL used by the working `curl` command). Do not commit the webhook URL to git.

The webhook URL is in 1Password: **AWS Notification Slack Bot** in the **dev** vault. The field name is `SLACK_WEBHOOK_URL`.

## Dev loop (build → push → update Lambda)

Lambda runs `x86_64`, so on Apple Silicon build with `--platform linux/amd64`. Use `buildx` with `--push` so the image goes straight to ECR as a single-arch manifest Lambda accepts (`--provenance=false --sbom=false` avoids multi-arch attestation manifests).

Replace `ACCOUNT_ID` with your AWS account ID. Log in to ECR once per session if needed:

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

Then after each code change:

```bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/sns-slack-notifier:latest \
  --push \
  .

aws lambda update-function-code \
  --function-name sns-slack-notifier \
  --image-uri ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/sns-slack-notifier:latest \
  --region us-east-1
```

`update-function-code` is required even when reusing the `:latest` tag, so Lambda pulls the new digest.

## Testing locally

For the `SLACK_WEBHOOK_URL` environment variable, please see above for more information.

```bash
docker build -t sns-slack-notifier .
docker run --rm -p 9000:8080 \
  -e SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...' \
  sns-slack-notifier
```

In another terminal:

```bash
curl -s "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{
    "Records": [
      {
        "EventSource": "aws:sns",
        "Sns": {
          "Type": "Notification",
          "MessageId": "95df01b4-ee98-5cb9-9903-4c221d41eb5e",
          "TopicArn": "arn:aws:sns:us-east-1:ACCOUNT_ID:example-topic",
          "Subject": "Test notification",
          "Message": "{\"hello\": \"world\"}"
        }
      }
    ]
  }'
```

# Initial Install Notes

## Create the Lambda function 

Create a container-image Lambda that uses the image above and an execution role with basic CloudWatch Logs permissions. Pass your Slack webhook URL as an environment variable:

```bash
aws lambda create-function \
  --function-name sns-slack-notifier \
  --package-type Image \
  --code ImageUri=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/sns-slack-notifier:latest \
  --role arn:aws:iam::ACCOUNT_ID:role/YOUR_LAMBDA_EXECUTION_ROLE \
  --timeout 30 \
  --memory-size 128 \
  --environment "Variables={SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...}"
```

If the function already exists, update the env var with:

```bash
aws lambda update-function-configuration \
  --function-name sns-slack-notifier \
  --environment "Variables={SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...}"
```

Published messages will appear in Slack and in the function’s CloudWatch Logs.
