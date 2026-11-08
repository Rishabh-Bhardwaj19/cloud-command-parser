import ipaddress
import json
from pathlib import Path

parent = ipaddress.ip_network("10.20.0.0/16")

subnets = [
    {"name": "App", "cidr": "10.20.0.0/22", "required_hosts": 1000},
    {"name": "Public", "cidr": "10.20.4.0/24", "required_hosts": 250},
    {"name": "Data", "cidr": "10.20.5.0/25", "required_hosts": 100},
    {"name": "Management", "cidr": "10.20.5.128/27", "required_hosts": 20},
]

networks = []
results = []

for item in subnets:
    network = ipaddress.ip_network(item["cidr"], strict=True)

    assert network.version == parent.version
    assert network.subnet_of(parent), f"{network} outside parent network"

    usable = network.num_addresses - 2
    assert usable >= item["required_hosts"], (
        f"{item['name']} has insufficient hosts"
    )

    networks.append(network)

    results.append({
        "name": item["name"],
        "cidr": str(network),
        "network_address": str(network.network_address),
        "first_usable": str(network.network_address + 1),
        "last_usable": str(network.broadcast_address - 1),
        "broadcast_address": str(network.broadcast_address),
        "required_hosts": item["required_hosts"],
        "available_usable_hosts": usable,
        "host_capacity_pass": usable >= item["required_hosts"],
        "within_parent": network.subnet_of(parent)
    })

for index, first in enumerate(networks):
    for second in networks[index + 1:]:
        assert not first.overlaps(second), (
            f"Overlapping subnets: {first} and {second}"
        )

for previous, current in zip(networks, networks[1:]):
    assert int(current.network_address) == int(previous.broadcast_address) + 1, (
        f"Allocation is not sequential: {previous} then {current}"
    )

report = {
    "parent_network": str(parent),
    "allocation_method": "VLSM, largest host requirement first",
    "subnet_count": len(results),
    "non_overlapping": True,
    "all_within_parent": True,
    "sequential_allocation": True,
    "all_host_requirements_met": True,
    "allocated_addresses": sum(n.num_addresses for n in networks),
    "subnets": results
}

Path("results").mkdir(exist_ok=True)
Path("results/subnet_validation.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print(json.dumps(report, indent=2))
print("\nPASS: All VLSM checks succeeded.")
