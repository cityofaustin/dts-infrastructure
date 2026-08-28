"""AWS Lambda handler that posts SNS events to Slack via an incoming webhook."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _is_cloudwatch_alarm(message: Any) -> bool:
    return isinstance(message, dict) and "AlarmName" in message and "NewStateReason" in message


def _format_alarm_time(raw_time: str | None) -> str:
    if not raw_time:
        return "(unknown time)"
    try:
        # CloudWatch uses e.g. 2026-08-07T20:16:30.631+0000
        parsed = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        try:
            parsed = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return raw_time
    central = parsed.astimezone(ZoneInfo("America/Chicago"))
    hour12 = central.hour % 12 or 12
    ampm = "AM" if central.hour < 12 else "PM"
    tz_abbr = central.tzname() or "CT"
    return (
        f"{central.strftime('%B')} {central.day}, {central.year} "
        f"at {hour12}:{central.minute:02d}:{central.second:02d} {ampm} {tz_abbr}"
    )


def _alarm_console_url(alarm: dict[str, Any]) -> str | None:
    alarm_name = alarm.get("AlarmName")
    alarm_arn = alarm.get("AlarmArn") or ""
    if not alarm_name or not alarm_arn:
        return None

    # arn:aws:cloudwatch:REGION:ACCOUNT:alarm:NAME
    parts = alarm_arn.split(":")
    if len(parts) < 4:
        return None
    region = parts[3]
    encoded_name = urllib.parse.quote(alarm_name, safe="")
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/deeplink.js"
        f"?region={region}#alarmsV2:alarm/{encoded_name}"
    )


def _format_cloudwatch_alarm(sns: dict[str, Any], alarm: dict[str, Any]) -> str:
    subject = sns.get("Subject") or alarm.get("AlarmName") or "(unknown alarm)"
    state_change_time = _format_alarm_time(alarm.get("StateChangeTime"))
    reason = alarm.get("NewStateReason") or "(no reason provided)"
    lines = [
        f"*{subject}*",
        f"*Time:* {state_change_time}",
        f"*Reason:* {reason}",
    ]
    url = _alarm_console_url(alarm)
    if url:
        lines.append(f"<{url}|View alarm in CloudWatch>")
    return "\n".join(lines)


def _format_slack_text(sns: dict[str, Any], parsed_message: Any) -> str:
    if _is_cloudwatch_alarm(parsed_message):
        return _format_cloudwatch_alarm(sns, parsed_message)

    subject = sns.get("Subject") or "(no subject)"
    topic_arn = sns.get("TopicArn") or "(unknown topic)"
    message_id = sns.get("MessageId") or "(unknown id)"

    if isinstance(parsed_message, (dict, list)):
        message_body = json.dumps(parsed_message, indent=2)
    else:
        message_body = str(parsed_message)

    return (
        f"*SNS notification*\n"
        f"*Subject:* {subject}\n"
        f"*Topic:* `{topic_arn}`\n"
        f"*MessageId:* `{message_id}`\n"
        f"*Message:*\n```\n{message_body}\n```"
    )


def _post_to_slack(webhook_url: str, text: str) -> None:
    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            logger.info("Slack webhook response status=%s body=%s", response.status, body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Slack webhook HTTP error status=%s body=%s", exc.code, error_body)
        raise
    except urllib.error.URLError as exc:
        logger.error("Slack webhook request failed: %s", exc.reason)
        raise


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Log each SNS record and post it to the configured Slack webhook."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL environment variable is required")

    records = event.get("Records", [])
    logger.info("Received %s SNS record(s)", len(records))

    for record in records:
        sns = record.get("Sns", {})
        message = sns.get("Message", "")
        message_id = sns.get("MessageId")
        topic_arn = sns.get("TopicArn")
        subject = sns.get("Subject")

        try:
            parsed_message = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            parsed_message = message

        logger.info(
            "SNS event MessageId=%s TopicArn=%s Subject=%s Message=%s",
            message_id,
            topic_arn,
            subject,
            parsed_message,
        )

        _post_to_slack(webhook_url, _format_slack_text(sns, parsed_message))

    return {
        "statusCode": 200,
        "body": f"Successfully processed {len(records)} records",
    }
