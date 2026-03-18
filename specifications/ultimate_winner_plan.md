# Implementation Plan: Ultimate Winner Celebration (LPSDJ-1)

This plan outlines the steps to implement a celebratory UI when a single winner remains in the Last Person Standing competition, and the deployment steps for AWS EKS.

## 1. Frontend Changes (`frontend/standings.html`)

### 1.1 Add Celebration Library
- Add `canvas-confetti` via CDN in the `<head>`:
  ```html
  <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
  ```

### 1.2 UI Components
- Add a hidden "Winner Overlay" component that displays when `activeCount === 1`.
- Include creative elements:
    - Large trophy icon.
    - Highlighted name of the winner.
    - "PARTY" effect with balloons and glitter (CSS animations + Confetti).

### 1.3 Vue Logic
- **State**: Add `hasCelebrated` flag to prevent repeat triggers.
- **Computed**: `winner` (returns the user object where `is_active === true`).
- **Watcher**: Watch `activeCount`.
    - If `newCount === 1` and `oldCount > 1`:
        - Set `hasCelebrated = true`.
        - Trigger `confetti()` burst.
        - Show winner overlay.

## 2. Infrastructure & Deployment (AWS EKS)

### 2.1 Containerization
- Build image: `docker build -t lms-app .`
- Tag and push to AWS ECR:
  ```bash
  aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
  docker tag lms-app:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/lms-app:latest
  docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/lms-app:latest
  ```

### 2.2 Kubernetes Manifests
- **Deployment**: Update `k8s/deployment.yaml` to use the ECR image URI.
- **Storage**:
    - Update `k8s/pvc.yaml` to use `storageClassName: gp2` (AWS EBS).
    - Remove `hostPath` from `deployment.yaml` and use the PVC.
- **Service**:
    - Update `k8s/service.yaml` to `type: LoadBalancer`.
    - Add AWS annotations for SSL (if using ACM) and health checks.

### 2.3 Secrets
- Create a secret in EKS for the API key:
  ```bash
  kubectl create secret generic app-secrets --from-literal=football-api-key=<YOUR_KEY>
  ```

## 3. Implementation Steps (TODO)
1. [x] Add `canvas-confetti` script to `standings.html`.
2. [x] Implement `winner` computed property and `activeCount` watcher.
3. [x] Create celebratory CSS for balloons and overlay.
4. [x] Test celebration logic by mocking a 1-player-active state.
5. [x] Update K8s manifests for AWS environment.
6. [x] Deploy to EKS.
