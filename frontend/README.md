# 蛋白质-药物计算平台 · Vue 3 前端

基于 **Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router**，从原 `web/`（Vanilla JS）逐步迁移。

## 技术选型说明

| 方案 | 结论 |
|------|------|
| **Vue Vben Admin 完整版** | 功能过重（RBAC、动态菜单、Monorepo），与生信平台不匹配 |
| **生信专用 Vue 模板** | 面向基因组/序列编辑器，不含 3D 蛋白结构任务流 |
| **Vue 3 + Element Plus + Vite（当前）** | 轻量、中文生态好、表格/表单成熟，适合任务列表 + 详情 + 自定义 3D 组件 |

## 开发

```bash
cd frontend
npm install
npm run dev    # http://127.0.0.1:5173 ，API 代理到 8765
```

需同时启动后端：`scripts/start_platform.sh`

## 生产构建

```bash
cd frontend
npm run build   # 输出到 frontend/dist/
# 重启 API 后，优先挂载 frontend/dist；经典页在 /legacy-app/
```

## 目录

```
src/
  api/          REST 客户端
  stores/       Pinia 状态
  views/        页面
  layouts/      布局
  components/   可复用组件（3D、序列等，迁移中）
```

## 迁移阶段

1. ✅ 脚手架 + 登录 + 布局 + 任务列表
2. ⏳ 单条提交 / VHH 批量表单
3. ⏳ Mol* 结构 viewer 组件
4. ⏳ Kabat 序列 + PyMOL 多选
5. ⏳ PLIP 结合界面面板
6. ⏳ MD 模块

过渡期可通过 **经典界面**（`/legacy` → iframe `/legacy-app/`）使用完整旧功能。
