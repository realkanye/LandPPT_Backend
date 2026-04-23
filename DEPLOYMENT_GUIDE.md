# LandPPT API 部署指南

## 📋 目录

1. [本地开发部署](#本地开发部署)
2. [Docker 部署](#docker-部署)
3. [Jenkins CI/CD 流水线](#jenkins-cicd-流水线)
4. [Kubernetes 部署](#kubernetes-部署)

---

## 本地开发部署

### 前置要求

- Python 3.11+
- uv (推荐) 或 pip
- OpenAI / Anthropic / Google API Key

### 快速启动

```bash
# 1. 克隆项目
cd LandPPT

# 2. 安装依赖
uv sync

# 3. 配置环境变量
cp .env.api .env
# 编辑 .env，填入你的 OPENAI_API_KEY

# 4. 启动API服务器
uv run python run_api.py

# 5. 访问API文档
# http://localhost:8000/docs
```

### 运行API测试

```bash
# 运行所有测试
python test_api.py

# 运行特定测试
python test_api.py health
python test_api.py outline
python test_api.py full
```

---

## Docker 部署

### 构建API镜像

```bash
# 使用API专用Dockerfile构建
docker build -f Dockerfile.api -t landppt-api:latest .

# 或使用原Dockerfile（兼容API模式）
docker build -t landppt-api:latest .
```

### 运行容器

```bash
docker run -d \
  --name landppt-api \
  -p 8000:8000 \
  -e OPENAI_API_KEY=your_api_key_here \
  -e DISABLE_AUTH=true \
  -e API_ONLY_MODE=true \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/temp:/app/temp \
  landppt-api:latest
```

### Docker Compose 部署

```yaml
# docker-compose.api.yml
version: '3.8'

services:
  landppt-api:
    build:
      context: .
      dockerfile: Dockerfile.api
    image: landppt-api:latest
    container_name: landppt-api
    ports:
      - "8000:8000"
    environment:
      - DISABLE_AUTH=true
      - API_ONLY_MODE=true
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEFAULT_AI_PROVIDER=openai
    volumes:
      - landppt_data:/app/data
      - landppt_temp:/app/temp
      - landppt_uploads:/app/uploads
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  landppt_data:
  landppt_temp:
  landppt_uploads:
```

```bash
# 启动
docker-compose -f docker-compose.api.yml up -d

# 查看日志
docker-compose -f docker-compose.api.yml logs -f
```

---

## Jenkins CI/CD 流水线

### 1. 准备工作

1. 安装Jenkins推荐插件：
   - Git Plugin
   - Docker Plugin
   - Docker Pipeline Plugin
   - Kubernetes Plugin
   - Credentials Plugin

2. 在Jenkins中添加凭证：
   - `docker-hub-credentials`: Docker Hub 用户名和密码
   - `k8s-kubeconfig`: Kubernetes kubeconfig 文件

### 2. Jenkinsfile

在项目根目录创建 `Jenkinsfile`：

```groovy
pipeline {
    agent any

    environment {
        // Docker 镜像配置
        DOCKER_REGISTRY = 'your-registry.example.com'
        DOCKER_IMAGE = "${DOCKER_REGISTRY}/landppt/landppt-api"
        DOCKER_TAG = "${BUILD_NUMBER}"

        // Kubernetes 配置
        K8S_NAMESPACE = 'landppt'
        K8S_DEPLOYMENT = 'landppt-api'

        // 构建参数
        PYTHON_VERSION = '3.11'
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "Checked out source code from branch: ${env.BRANCH_NAME}"
            }
        }

        stage('Dependency Check') {
            steps {
                echo 'Checking uv.lock and pyproject.toml...'
                sh 'ls -la pyproject.toml uv.lock'
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    echo "Building Docker image: ${DOCKER_IMAGE}:${DOCKER_TAG}"
                    sh """
                        docker build -f Dockerfile.api \
                            -t ${DOCKER_IMAGE}:${DOCKER_TAG} \
                            -t ${DOCKER_IMAGE}:latest .
                    """
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    withCredentials([usernamePassword(
                        credentialsId: 'docker-hub-credentials',
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )]) {
                        sh 'docker login ${DOCKER_REGISTRY} -u ${DOCKER_USER} -p ${DOCKER_PASS}'
                        sh 'docker push ${DOCKER_IMAGE}:${DOCKER_TAG}'
                        sh 'docker push ${DOCKER_IMAGE}:latest'
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when {
                branch 'main'
            }
            steps {
                script {
                    echo "Deploying to Kubernetes namespace: ${K8S_NAMESPACE}"

                    // 使用 kubeconfig 凭证
                    withCredentials([file(
                        credentialsId: 'k8s-kubeconfig',
                        variable: 'KUBECONFIG'
                    )]) {
                        // 1. 创建命名空间（如果不存在）
                        sh '''
                            kubectl --kubeconfig=${KUBECONFIG} create namespace ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl --kubeconfig=${KUBECONFIG} apply -f -
                        '''

                        // 2. 更新或创建 ConfigMap（排除敏感数据）
                        sh '''
                            kubectl --kubeconfig=${KUBECONFIG} create configmap landppt-api-config \
                                --namespace=${K8S_NAMESPACE} \
                                --from-literal=DISABLE_AUTH=true \
                                --from-literal=API_ONLY_MODE=true \
                                --from-literal=DEFAULT_AI_PROVIDER=openai \
                                --dry-run=client -o yaml | kubectl --kubeconfig=${KUBECONFIG} apply -f -
                        '''

                        // 3. 部署应用
                        sh '''
                            cat k8s/deployment.yaml | envsubst | kubectl --kubeconfig=${KUBECONFIG} apply -f -
                            kubectl --kubeconfig=${KUBECONFIG} apply -f k8s/service.yaml --namespace=${K8S_NAMESPACE}
                            kubectl --kubeconfig=${KUBECONFIG} apply -f k8s/ingress.yaml --namespace=${K8S_NAMESPACE}
                        '''

                        // 4. 等待部署完成
                        sh '''
                            kubectl --kubeconfig=${KUBECONFIG} rollout status deployment/${K8S_DEPLOYMENT} \
                                --namespace=${K8S_NAMESPACE} \
                                --timeout=5m
                        '''
                    }
                }
            }
        }

        stage('Health Check') {
            when {
                branch 'main'
            }
            steps {
                script {
                    echo 'Performing health check on deployed service...'
                    // 这里可以添加实际的健康检查逻辑
                    // 例如调用内部API端点验证
                }
            }
        }
    }

    post {
        success {
            echo '✅ Pipeline completed successfully!'
            echo "Docker Image: ${DOCKER_IMAGE}:${DOCKER_TAG}"
            echo "Deployed to K8s namespace: ${K8S_NAMESPACE}"
        }
        failure {
            echo '❌ Pipeline failed!'
            // 可以添加告警通知，如邮件、Slack、钉钉等
        }
        cleanup {
            echo 'Cleaning up...'
            sh 'docker system prune -f || true'
        }
    }
}
```

### 3. Jenkins 流水线配置步骤

1. **新建流水线任务**
   - 登录 Jenkins → 新建任务 → 流水线
   - 任务名称: `LandPPT-API-Build`

2. **配置源码管理**
   - 选择 Git
   - 填入代码仓库 URL
   - 选择凭证（如需要）
   - 分支指定: `*/main`

3. **配置流水线**
   - 选择 "Pipeline script from SCM"
   - SCM: Git
   - Script Path: `Jenkinsfile`

4. **添加构建触发器**（可选）
   - 轮询 SCM: `H/5 * * * *`（每5分钟检查一次）
   - 或配置 Webhook 触发

---

## Kubernetes 部署

### 目录结构

创建 `k8s/` 目录，包含以下文件：

```
k8s/
├── namespace.yaml
├── configmap.yaml
├── secret.yaml
├── deployment.yaml
├── service.yaml
├── ingress.yaml
└── hpa.yaml
```

### 1. namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: landppt
  labels:
    name: landppt
    environment: production
```

### 2. configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: landppt-api-config
  namespace: landppt
data:
  DISABLE_AUTH: "true"
  API_ONLY_MODE: "true"
  ANONYMOUS_USER_ID: "1"
  DEFAULT_AI_PROVIDER: "openai"
  LOG_LEVEL: "info"
  WORKERS: "2"
```

### 3. secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: landppt-api-secrets
  namespace: landppt
type: Opaque
stringData:
  # 使用 base64 编码前的值，应用时请替换为实际值
  OPENAI_API_KEY: "your-openai-api-key-here"
  # ANTHROPIC_API_KEY: "your-anthropic-key"
  # TAVILY_API_KEY: "your-tavily-key"
```

**应用方式：**
```bash
# 或者通过命令行创建（更安全）
kubectl create secret generic landppt-api-secrets \
  --namespace=landppt \
  --from-literal=OPENAI_API_KEY=your-actual-key
```

### 4. deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: landppt-api
  namespace: landppt
  labels:
    app: landppt-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: landppt-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: landppt-api
    spec:
      containers:
      - name: landppt-api
        image: your-registry.example.com/landppt/landppt-api:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
          name: api

        # 环境变量 - 从 ConfigMap 和 Secret 读取
        envFrom:
        - configMapRef:
            name: landppt-api-config
        - secretRef:
            name: landppt-api-secrets

        # 资源限制 - 根据实际情况调整
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"

        # 健康检查
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10

        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 5

        # 共享内存 - Playwright/Chromium 需要
        volumeMounts:
        - name: dshm
          mountPath: /dev/shm
        - name: temp-storage
          mountPath: /app/temp
        - name: data-storage
          mountPath: /app/data

      # 共享内存卷 - 用于 Chromium
      volumes:
      - name: dshm
        emptyDir:
          medium: Memory
          sizeLimit: 2Gi
      - name: temp-storage
        emptyDir: {}
      - name: data-storage
        persistentVolumeClaim:
          claimName: landppt-data-pvc

      # 拉取镜像的凭证（如果是私有仓库）
      # imagePullSecrets:
      # - name: regcred
```

### 5. service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: landppt-api-service
  namespace: landppt
  labels:
    app: landppt-api
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
    name: http-api
  selector:
    app: landppt-api
```

### 6. ingress.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: landppt-api-ingress
  namespace: landppt
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    # cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  # tls:
  # - hosts:
  #   - api.landppt.example.com
  #   secretName: landppt-api-tls
  rules:
  - host: api.landppt.example.com  # 替换为你的域名
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: landppt-api-service
            port:
              name: http-api
```

### 7. hpa.yaml (自动扩缩容)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: landppt-api-hpa
  namespace: landppt
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: landppt-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 20
        periodSeconds: 120
```

### 8. pvc.yaml (持久化存储)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: landppt-data-pvc
  namespace: landppt
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # storageClassName: standard  # 根据你的集群配置
```

### 部署命令

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 2. 创建Secret（替换为实际的API Key）
kubectl create secret generic landppt-api-secrets \
  --namespace=landppt \
  --from-literal=OPENAI_API_KEY=sk-your-actual-key-here

# 3. 创建存储卷声明
kubectl apply -f k8s/pvc.yaml

# 4. 应用配置
kubectl apply -f k8s/configmap.yaml

# 5. 部署应用
kubectl apply -f k8s/deployment.yaml

# 6. 部署服务
kubectl apply -f k8s/service.yaml

# 7. 部署Ingress（可选）
kubectl apply -f k8s/ingress.yaml

# 8. 部署HPA（可选）
kubectl apply -f k8s/hpa.yaml

# 检查部署状态
kubectl get pods -n landppt
kubectl get services -n landppt
kubectl get deployments -n landppt

# 查看日志
kubectl logs -f deployment/landppt-api -n landppt

# 查看HPA状态
kubectl get hpa -n landppt
```

### 验证部署

```bash
# 端口转发测试
kubectl port-forward service/landppt-api-service 8000:80 -n landppt

# 测试API
curl http://localhost:8000/health
```

---

## 生产环境注意事项

### 1. 安全

- ✅ 不要在公网直接暴露无认证的API
- ✅ 使用网络策略限制Pod间访问
- ✅ 敏感信息全部使用K8s Secret管理
- ✅ 考虑添加API密钥认证中间件
- ✅ 启用HTTPS（TLS）

### 2. 性能

- ✅ 根据负载调整CPU/Memory资源限制
- ✅ 配置合理的HPA自动扩缩容
- ✅ 考虑使用Redis缓存热点数据
- ✅ Playwright需要足够的共享内存

### 3. 监控

- ✅ 配置Prometheus监控指标
- ✅ 设置告警规则（响应时间、错误率等）
- ✅ 日志收集（ELK/Loki）

### 4. 高可用

- ✅ 至少2个副本
- ✅ 配置Pod反亲和性
- ✅ 使用分布式数据库替代SQLite

---

## 故障排查

### 常见问题

1. **Pod启动失败 - CrashLoopBackOff**
   ```bash
   kubectl describe pod <pod-name> -n landppt
   kubectl logs <pod-name> -n landppt
   ```

2. **Chromium/Playwright无法启动**
   - 检查 `/dev/shm` 共享内存大小
   - 确保所有依赖库已安装

3. **API响应缓慢**
   - 检查AI Provider的API限流
   - 调整Pod资源配额
   - 检查网络延迟

4. **PDF/PPTX导出失败**
   - 检查临时目录权限
   - 确保Playwright浏览器正确安装

---

## 联系方式

如有部署问题，请查看：
1. 容器日志: `kubectl logs -f <pod-name>`
2. API文档: `http://your-domain/docs`
3. 健康检查端点: `/health`
