---
id: INC-030
title: RabbitMQ Memory Alarm Halting Publishers
severity: SEV-2
service: notification-service
environment: prod
category: degradation
date: 2026-02-22
duration: "35m"
tags:
  - incident
  - rabbitmq
  - memory
  - messaging
  - backpressure
---

## Summary

RabbitMQ triggered a memory alarm when usage exceeded the 80% watermark (3.2GB of 4GB), blocking all publisher connections. The notification-service queue backed up 2.4 million messages in the application layer, causing email and SMS notifications to be delayed by 35 minutes.

## Symptoms

- RabbitMQ management UI: `Memory alarm` status on all nodes
- Publisher connections showing `blocked` state
- Application logs: `com.rabbitmq.client.AlreadyClosedException: connection is already closed due to resource alarm`
- notification-service in-memory queue growing at 40k msgs/sec
- PagerDuty: `RabbitMQ-MemoryAlarm-Critical`
- Customer complaints about missing OTP and verification emails

## Diagnosis

1. Checked RabbitMQ status: `rabbitmqctl status` showed memory at 3.4GB, alarm triggered
2. Identified queue `notifications.email.send` had 8M unacknowledged messages
3. Consumer pods for email-sender were in CrashLoopBackOff due to SMTP gateway timeout
4. Messages accumulated because consumers died but publishers kept sending
5. No dead-letter policy configured — messages sat in queue consuming memory

## Resolution

1. Restarted SMTP gateway service that was in a hung state
2. Purged 6M messages older than 30 minutes (stale OTPs): `rabbitmqctl purge_queue notifications.email.send`
3. Restarted email-sender consumers — began draining remaining messages
4. Memory dropped below watermark, publisher block lifted automatically
5. In-memory application queue drained within 10 minutes

## Post-Incident Review

Configured dead-letter exchanges with message TTL of 10 minutes for time-sensitive queues. Added consumer health monitoring with auto-restart. Increased RabbitMQ memory to 8GB. Set queue length limits with overflow policy to reject-publish.

## Links
- Related: [[RB-013-redis-memory-management]]
