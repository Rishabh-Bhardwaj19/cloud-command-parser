#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CLUSTER_NAME="cloud-command-parser"
RELEASE_TAG="${RELEASE_TAG:-v1.0.0}"
REPOSITORY="Rishabh-Bhardwaj19/cloud-command-parser"
CACHE_DIR="$ROOT_DIR/.cache/bootstrap"

echo "=== Cloud Command Parser: reproducible bootstrap ==="

for tool in docker kubectl k3d helm curl tar sha256sum python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "ERROR: Required tool not found: $tool" >&2
        exit 1
    }
done

docker info >/dev/null 2>&1 || {
    echo "ERROR: Docker is not running. Start Docker Desktop and retry." >&2
    exit 1
}

echo
echo "=== Creating or reusing k3d cluster ==="
if ! k3d cluster list | awk 'NR > 1 {print $1}' | grep -Fxq "$CLUSTER_NAME"; then
    k3d cluster create --config cluster/k3d.yaml
else
    echo "Reusing existing cluster: $CLUSTER_NAME"
fi

kubectl config use-context "k3d-${CLUSTER_NAME}"

echo
echo "=== Installing SeaweedFS ==="
helm repo add seaweedfs https://seaweedfs.github.io/seaweedfs/helm \
    --force-update
helm repo update

kubectl create namespace data \
    --dry-run=client -o yaml | kubectl apply -f -

# Create credentials only on a fresh installation. Never overwrite an
# existing SeaweedFS admin Secret.
if ! kubectl get secret seaweedfs-s3-admin -n data >/dev/null 2>&1; then
    ACCESS_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(10))')"
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"

    kubectl create secret generic seaweedfs-s3-admin \
        -n data \
        --from-literal=admin_access_key_id="$ACCESS_KEY" \
        --from-literal=admin_secret_access_key="$SECRET_KEY" \
        >/dev/null

    unset ACCESS_KEY SECRET_KEY
    echo "Generated SeaweedFS credentials and stored them in Kubernetes."
else
    echo "Reusing existing SeaweedFS credentials."
fi

helm upgrade --install seaweedfs seaweedfs/seaweedfs \
    --version 4.52.0 \
    --namespace data \
    --create-namespace \
    --values k8s/data/values.yaml \
    --wait \
    --timeout 10m

kubectl wait \
    --for=condition=Ready \
    pod \
    -l app.kubernetes.io/instance=seaweedfs \
    -n data \
    --timeout=600s

echo
echo "=== Preparing isolated bootstrap tools ==="
if [ ! -x .venv-bootstrap/bin/python ]; then
    python3 -m venv .venv-bootstrap
fi

.venv-bootstrap/bin/python -m pip install \
    --disable-pip-version-check \
    -r requirements-bootstrap.txt

echo
echo "=== Downloading model assets from GitHub Release ==="
mkdir -p "$CACHE_DIR" "$CACHE_DIR/v1" "$CACHE_DIR/v2"

BASE_URL="https://github.com/${REPOSITORY}/releases/download/${RELEASE_TAG}"

curl -fL --retry 3 \
    "$BASE_URL/pythia-70m-v1.tar.gz" \
    -o "$CACHE_DIR/pythia-70m-v1.tar.gz"

curl -fL --retry 3 \
    "$BASE_URL/pythia-70m-v2.tar.gz" \
    -o "$CACHE_DIR/pythia-70m-v2.tar.gz"

curl -fL --retry 3 \
    "$BASE_URL/model.sha256" \
    -o "$CACHE_DIR/model.sha256"

(
    cd "$CACHE_DIR"
    sha256sum -c model.sha256
)

tar -xzf "$CACHE_DIR/pythia-70m-v1.tar.gz" -C "$CACHE_DIR/v1"
tar -xzf "$CACHE_DIR/pythia-70m-v2.tar.gz" -C "$CACHE_DIR/v2"

cp "$CACHE_DIR/model.sha256" "$CACHE_DIR/v1/model.sha256"
(
    cd "$CACHE_DIR"
    sha256sum pythia-70m-v2.tar.gz > v2/model.sha256
)

echo
echo "=== Starting or reusing local S3 port-forward ==="
PORT_FORWARD_STARTED=0
PF_PID=""

if ! python3 -c \
    'import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(s.connect_ex(("127.0.0.1",8333)))' \
    >/dev/null 2>&1; then

    kubectl -n data port-forward svc/seaweedfs-s3 8333:8333 \
        >"$CACHE_DIR/port-forward.log" 2>&1 &
    PF_PID=$!
    PORT_FORWARD_STARTED=1

    cleanup_port_forward() {
        if [ "$PORT_FORWARD_STARTED" = "1" ] && [ -n "$PF_PID" ]; then
            kill "$PF_PID" >/dev/null 2>&1 || true
        fi
    }
    trap cleanup_port_forward EXIT

    for attempt in $(seq 1 30); do
        if python3 -c \
            'import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(s.connect_ex(("127.0.0.1",8333)))' \
            >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

python3 -c \
    'import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(s.connect_ex(("127.0.0.1",8333)))' \
    || {
        echo "ERROR: SeaweedFS S3 port-forward is unavailable." >&2
        exit 1
    }

echo
echo "=== Loading S3 credentials without printing them ==="
export AWS_ACCESS_KEY_ID="$(
    kubectl get secret seaweedfs-s3-admin -n data \
        -o jsonpath='{.data.admin_access_key_id}' | base64 -d
)"
export AWS_SECRET_ACCESS_KEY="$(
    kubectl get secret seaweedfs-s3-admin -n data \
        -o jsonpath='{.data.admin_secret_access_key}' | base64 -d
)"
export AWS_DEFAULT_REGION="us-east-1"

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "ERROR: SeaweedFS Secret is missing credential values." >&2
    exit 1
fi

echo
echo "=== Initializing buckets and uploading project assets ==="
.venv-bootstrap/bin/python scripts/s3_init.py \
    --model-v1 "$CACHE_DIR/v1" \
    --model-v2 "$CACHE_DIR/v2" \
    --dataset-root "$ROOT_DIR/data" \
    --prompt "$ROOT_DIR/prompts/teacher_prompt.txt"

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION

if [ "$PORT_FORWARD_STARTED" = "1" ]; then
    kill "$PF_PID" >/dev/null 2>&1 || true
    PORT_FORWARD_STARTED=0
fi
trap - EXIT

echo
echo "=== Preparing application namespace and Secret ==="
kubectl create namespace app \
    --dry-run=client -o yaml | kubectl apply -f -

APP_ACCESS="$(
    kubectl get secret seaweedfs-s3-admin -n data \
        -o jsonpath='{.data.admin_access_key_id}' | base64 -d
)"
APP_SECRET="$(
    kubectl get secret seaweedfs-s3-admin -n data \
        -o jsonpath='{.data.admin_secret_access_key}' | base64 -d
)"

kubectl create secret generic service-s3-credentials \
    -n app \
    --from-literal=access_key="$APP_ACCESS" \
    --from-literal=secret_key="$APP_SECRET" \
    --dry-run=client -o yaml | kubectl apply -f -

unset APP_ACCESS APP_SECRET

echo
echo "=== Building and importing inference image ==="
docker build -t cloud-command-parser:1.0.0 \
    -f service/Dockerfile .

k3d image import cloud-command-parser:1.0.0 \
    --cluster "$CLUSTER_NAME"

echo
echo "=== Applying application manifests ==="
kubectl apply -f k8s/app/

echo
echo "=== Waiting for inference deployment ==="
kubectl rollout status deployment/command-parser \
    -n app --timeout=10m

echo
echo "=== Bootstrap completed ==="
kubectl get deployment,pods,services,ingress,hpa -n app

echo
echo "Ingress test URL:"
echo "http://127.0.0.1:8080/parse"
echo "Send Host header: parser.local"
