# dts-infrastructure

Infrastructure and deployment code for TPW Data & Technology Services' internal AWS tooling. Each tool lives in its own directory with its own README.

## Tools

### SNS Slack Notifier

[`sns-slack-notifier`](sns-slack-notifier/) is a Python Lambda packaged as a container image. Subscribe it to an SNS topic; it posts each SNS record (including CloudWatch alarms) to a Slack channel via an incoming webhook, and logs to CloudWatch.

See the [SNS Slack Notifier README](sns-slack-notifier/README.md) for build, deploy, and local testing instructions.
