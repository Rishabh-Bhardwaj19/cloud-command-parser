# VLSM Subnet Allocation

## Parent network

- Parent CIDR: 10.20.0.0/16
- Address range: 10.20.0.0 - 10.20.255.255
- Allocation method: Variable Length Subnet Masking (VLSM)
- Allocation order: Largest host requirement first.
- Allocation strategy: Sequential, non-overlapping CIDR blocks.

## Subnet allocation

| Network | Required hosts | Prefix | Subnet mask | Total addresses | Usable hosts | Network address | First usable | Last usable | Broadcast |
|---|---:|---|---|---:|---:|---|---|---|---|
| App | 1000 | /22 | 255.255.252.0 | 1024 | 1022 | 10.20.0.0 | 10.20.0.1 | 10.20.3.254 | 10.20.3.255 |
| Public | 250 | /24 | 255.255.255.0 | 256 | 254 | 10.20.4.0 | 10.20.4.1 | 10.20.4.254 | 10.20.4.255 |
| Data | 100 | /25 | 255.255.255.128 | 128 | 126 | 10.20.5.0 | 10.20.5.1 | 10.20.5.126 | 10.20.5.127 |
| Management | 20 | /27 | 255.255.255.224 | 32 | 30 | 10.20.5.128 | 10.20.5.129 | 10.20.5.158 | 10.20.5.159 |

## VLSM calculations

The required subnet size is the smallest power of two that provides the required number of usable hosts plus network and broadcast addresses.

- App: 1000 + 2 = 1002; next power of two is 1024 = 2^10. Prefix = 32 - 10 = /22.
- Public: 250 + 2 = 252; next power of two is 256 = 2^8. Prefix = 32 - 8 = /24.
- Data: 100 + 2 = 102; next power of two is 128 = 2^7. Prefix = 32 - 7 = /25.
- Management: 20 + 2 = 22; next power of two is 32 = 2^5. Prefix = 32 - 5 = /27.

## Allocation verification

- Allocated address count: 1024 + 256 + 128 + 32 = 1440.
- Every subnet starts on a valid CIDR boundary.
- The four subnets do not overlap.
- All four subnets are contained within 10.20.0.0/16.
- Remaining address space is reserved for future expansion.

## Design rationale

The application subnet receives the largest block because it requires 1000 hosts. The public subnet receives a /24 block, while the data and management subnets receive smaller blocks according to their host requirements.

VLSM reduces unused address space compared with assigning the same large prefix to every network.
