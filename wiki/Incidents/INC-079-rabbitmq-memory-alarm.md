---
id: INC-079
title: RabbitMQ Memory Alarm Halting All Publishers
severity: SEV-2
service: notification-service
environment: prod
category: capacity
date: 2026-03-14
duration: "35m"
tags:
  - incident
  - rabbitmq
  - messaging
  - memory
  - publisher-block
  - queue
---

## Summary

RabbitMQ triggered a memory alarm after the `email-notifications` queue accumulated 2.4 million unprocessed messages. The alarm blocked ALL publishers cluster-wide (not just the offending queue), causing notification delivery and event processing to halt for 35 minutes.

## Symptoms

- Publishers received `AMQP channel blocked` / connection flow-control
- RabbitMQ management UI: memory alarm triggered, `mem_used: 3.8GB / mem_limit: 4.0GB`
- `email-notifications` queue depth: 2,419,832 messages
- All other queues (payments, audit, webhooks) also blocked from publishing
- Consumer for `email-notifications` had been down for 18 hours (unnoticed)

## Diagnosis

1. Checked RabbitMQ alarms:
   ```bash
   rabbitmqctl list_alarms
   # memory: [{resource_limit,memory,rabbit@rmq-01}]
   ```
2. Identified the bloated queue:
   ```bash
   rabbitmqctl list_queues name messages --sort=messages | tail -5
   # email-notifications    2419832
   ```
3. Consumer pod for email-notifications had been in `CrashLoopBackOff` since previous day (SMTP credential rotation broke the consumer)
4. No alert existed for consumer downtime on this queue
5. Messages accumulated until memory limit was reached

## Resolution

1. Fixed SMTP credentials in consumer config:
   ```bash
   kubectl create secret generic smtp-creds -n notifications --from-literal=password=<NEW_PASS> --dry-run=client -o yaml | kubectl apply -f -
   ```
2. Restarted consumer deployment:
   ```bash
   kubectl rollout restart deployment email-consumer -n notifications
   ```
3. Consumers began draining the queue (~50K/min)
4. Memory alarm cleared within 8 minutes as queue drained
5. All publishers unblocked automatically

## Post-Incident Review

- Memory alarm blocks ALL publishers globally — a single runaway queue can halt the entire messaging system
- Added per-queue max-length policy: `x-max-length: 500000` with `overflow: reject-publish`
- Added alert: consumer down for any queue > 15 minutes
- Added alert: queue depth > 1 million messages
- Separated critical queues onto dedicated RabbitMQ vhosts

## Links

- Related: [[RB-013-redis-memory-management]]
