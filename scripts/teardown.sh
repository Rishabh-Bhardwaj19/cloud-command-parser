#!/usr/bin/env bash
set -Eeuo pipefail

CLUSTER_NAME="cloud-command-parser"

echo "This deletes the entire k3d cluster '${CLUSTER_NAME}',"
echo "including its Kubernetes namespaces, PVCs, and SeaweedFS objects."
echo "Repository files and GitHub Release assets are not deleted."

if k3d cluster list | awk 'NR > 1 {print $1}' | grep -Fxq "$CLUSTER_NAME"; then
    k3d cluster delete "$CLUSTER_NAME"
    echo "Cluster deleted."
else
    echo "Cluster does not exist; nothing to delete."
fi
