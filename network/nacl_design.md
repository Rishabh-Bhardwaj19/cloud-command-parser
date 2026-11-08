# NACL Design and Stateless Reply Traffic

## General behavior

The NACL is stateless. It does not automatically allow response traffic
because a request packet was allowed. Every inbound and outbound packet
is evaluated independently.

The simulator checks rules in ascending rule-number order. The first
matching rule decides the packet action. If no rule matches, the packet
is denied. Rule 32766 explicitly denies all remaining traffic.

## Inbound rules

| Rule | Protocol | Destination port | Source CIDR | Action | Purpose |
|---:|---|---|---|---|---|
| 100 | TCP | 22 | 0.0.0.0/0 | Deny | Block SSH |
| 110 | TCP | 5432 | 10.20.5.0/25 | Deny | Block direct database access |
| 120 | TCP | 1024-65535 | 10.20.0.0/22 | Allow | Permit ephemeral-port replies from app subnet |
| 130 | TCP | 443 | 192.0.2.0/24 | Allow | Permit HTTPS from approved public range |
| 140 | TCP | 443 | 0.0.0.0/0 | Deny | Deny HTTPS from other sources |
| 32766 | All | All | 0.0.0.0/0 | Deny | Explicit fallback deny |

## Outbound rules

| Rule | Protocol | Destination port | Destination CIDR | Action | Purpose |
|---:|---|---|---|---|---|
| 100 | TCP | 8000 | 10.20.0.0/22 | Allow | Permit application service traffic |
| 110 | TCP | 1024-65535 | 192.0.2.0/24 | Allow | Permit ephemeral-port replies to approved public clients |
| 32766 | All | All | 0.0.0.0/0 | Deny | Explicit fallback deny |

## Stateless reply examples

1. An outbound TCP connection to an application service on port 8000
   can receive a response from the app subnet on an ephemeral client
   port. The inbound rule 120 explicitly permits that return packet.

2. An inbound HTTPS request from an approved public client reaches
   destination port 443. Its outbound response is sent to the client's
   ephemeral port. Outbound rule 110 explicitly permits that return packet.

These response permissions are required because the NACL is stateless.

## Rule ordering

Specific restrictions and permissions are evaluated before the
fallback deny rule.

- Rule 100 blocks SSH before any later rule is considered.
- Rule 110 blocks TCP database access from the data subnet.
- Rule 130 permits HTTPS from the approved public CIDR.
- Rule 140 denies HTTPS from all other source addresses.
- Rule 32766 denies all traffic that did not match an earlier rule.

The lower the rule number, the earlier the rule is evaluated.
