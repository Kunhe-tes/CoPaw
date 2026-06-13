## 1. Scope 编码与规范化

- [x] 1.1 调整 `src/swe/config/context.py` 中的 scope 编码、解码与格式识别逻辑，使 canonical `scope_id` 变为 `<tenant_b64>.<source_b64>`
- [x] 1.2 为 legacy `scope.v1.*` 输入补充兼容解析与 canonicalize helper，保证下游统一看到新格式
- [x] 1.3 更新与 scope 格式直接相关的单元测试，覆盖新格式输出和旧格式兼容输入

## 2. 本地目录与 Provider 迁移

- [x] 2.1 调整 tenant 路径 helper、workspace 初始化和 provider 存储解析逻辑，使新写入统一落到无前缀目录
- [x] 2.2 实现 `~/.swe` 与 `~/.swe.secret` 下 legacy `scope.v1.*` 目录向 canonical 目录的懒迁移逻辑
- [x] 2.3 为目录迁移补充测试，覆盖仅旧目录存在、仅新目录存在以及新旧目录并存三类场景

## 3. Scope-aware 调用点切换

- [x] 3.1 更新 middleware、router、workspace、runner、provider manager 与相关 runtime registry，统一在边界处 canonicalize scope
- [x] 3.2 更新 approvals、suggestions、MCP progress 等 transient store 的 scope key 生成与查找逻辑
- [x] 3.3 更新 CLI、internal API、callback 与 cron 相关测试，确认旧格式输入可兼容、新格式输出为标准结果

## 4. 文档与回归验证

- [x] 4.1 更新 `analysis/tenant-source-user-directory-analysis.md`、playbook 与相关设计文档中的目录示例，去掉 `scope.v1.` 前缀
- [x] 4.2 运行受影响测试集合，重点验证 tenant/source 路径解析、provider 隔离和 scope-aware store 行为
- [x] 4.3 执行一次本地目录整理与手工回归，确认已有 `scope.v1.*` 目录能够被迁移到无前缀结构
