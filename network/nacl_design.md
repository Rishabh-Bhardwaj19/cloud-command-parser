# Public-subnet NACL design (CS3081 Task 5)

The public subnet is `10.20.4.0/24`. The remaining VLSM allocations are app `10.20.0.0/22`, data `10.20.5.0/25`, and management `10.20.5.128/27`.

The NACL is stateless, so a response packet is evaluated independently from the request. The public subnet therefore has an inbound rule for TCP destination ports 1024-65535 from the app subnet (application replies to client ephemeral ports) and an outbound rule for TCP destination ports 1024-65535 to any client (load-balancer replies).

The inbound deny for `198.51.100.0/24` is rule 100, before the public HTTP/HTTPS allow rules. This ordering is essential: first matching rule wins, so placing the deny after the web allows would let traffic from the blocked range reach those ports.

| Direction | Rule | Match | Action | Reason |
|---|---:|---|---|---|
| Inbound | 100 | Any protocol/port from `198.51.100.0/24` | Deny | Block known abusive range before any allow |
| Inbound | 110 | TCP destination 80 from anywhere | Allow | HTTP |
| Inbound | 120 | TCP destination 443 from anywhere | Allow | HTTPS |
| Inbound | 130 | TCP destination 22 from `10.20.5.128/27` | Allow | SSH only from management |
| Inbound | 140 | TCP destination 1024-65535 from `10.20.0.0/22` | Allow | App-subnet replies to client ephemeral ports |
| Outbound | 100 | TCP destination 8000 to `10.20.0.0/22` | Allow | Forward application traffic |
| Outbound | 110 | TCP destination 1024-65535 to anywhere | Allow | Return traffic to client ephemeral ports |

All unmatched traffic is denied. The rule file is validated with the supplied standard-library `tools/nacl_sim.py` simulator using both the six starter packets and additional requirement-focused cases in `network/packets_assignment_examples.jsonl`.
