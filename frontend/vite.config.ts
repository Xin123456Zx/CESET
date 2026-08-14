
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default defineConfig({
  plugins: [vue()],
  base: '',
  // 默认的 node_modules/.vite 缓存归属其他账号、无法写入（共享 scratch 多人协作），
  // 改成按用户名区分的缓存目录，各自可写
  cacheDir: `node_modules/.vite_${process.env.USER || 'default'}`,
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'), // 确保这里的路径正确
    },
  },
  server: {
    // 默认只绑 [::1]（IPv6 loopback），ssh 隧道按 IPv4 连会被拒。
    // 绑 0.0.0.0 后 127.0.0.1 和节点内网地址都能连，隧道可以直接一跳到本节点 5173
    host: '0.0.0.0',
    proxy: {
      "/api": {
        // 后端在别的节点时，启动 vite 前设 BACKEND_HOST=<节点名>
        target: `http://${process.env.BACKEND_HOST || "127.0.0.1"}:5001`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
