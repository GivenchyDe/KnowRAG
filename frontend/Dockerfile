# KnowRAG 前端镜像（多阶段构建）
# 阶段一：Node 构建 Vue3 静态产物
FROM node:22-alpine AS build

WORKDIR /app

# 先复制依赖清单，利用镜像层缓存跳过重复 npm install。
COPY package*.json ./
RUN npm ci

COPY . .

# 构建命令包含 vue-tsc 类型检查，类型错误会直接让镜像构建失败。
RUN npm run build

# 阶段二：Nginx 托管静态资源，并用最小镜像减小体积
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
