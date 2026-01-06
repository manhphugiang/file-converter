# Multi-stage build for React frontend
FROM node:18-alpine as builder

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Build the application with default API URL
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy built application from builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Create a script to replace API URL at runtime
RUN echo '#!/bin/sh' > /docker-entrypoint.d/30-replace-api-url.sh && \
    echo 'API_URL=${REACT_APP_API_URL:-http://localhost}' >> /docker-entrypoint.d/30-replace-api-url.sh && \
    echo 'echo "Replacing API URL with: $API_URL"' >> /docker-entrypoint.d/30-replace-api-url.sh && \
    echo 'find /usr/share/nginx/html -name "*.js" -exec sed -i "s|http://localhost:8000|$API_URL|g" {} \;' >> /docker-entrypoint.d/30-replace-api-url.sh && \
    echo 'echo "API URL replacement completed"' >> /docker-entrypoint.d/30-replace-api-url.sh && \
    chmod +x /docker-entrypoint.d/30-replace-api-url.sh

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]