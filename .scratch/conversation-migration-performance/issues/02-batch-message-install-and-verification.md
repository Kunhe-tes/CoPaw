# 02: 消息批量写入与已提交记录批量核对

**What to build:** migrate 对消息元数据执行有界多行插入，对已提交批次按表分块读取后全量比较，使首次导入和恢复核对减少逐行往返，用户仍得到相同会话与发布结果。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 在现有 publication 事务内优先批量写入连续、同字段集合的 Message 记录，保留每行定位解析、关联及 source 归属校验。
- [x] 使用可信表/字段白名单和参数化 prepared 多行插入，受行数、字节及服务器 packet 共同限制，不依靠忽略错误或覆盖冲突。
- [x] 不任意重排 Session、Chat、Turn、Message 或更新记录；一条错误导致当前事务回滚，数据错误与共享数据库错误继续按既有规则分类。
- [x] 已提交记录按表及有界 ID 集合查询，再逐条比较不可变字段；缺失、重复身份及不一致明确失败，不做抽样。
- [x] 覆盖空、单条、满块、跨块、不同字段集合、Unicode/二进制/空值、大字段与单行 packet 超限。
- [ ] 通过现有迁移入口验证成功发布、重复执行幂等、坏 source 跳过及已发布 source 新数据保护；SQL 计数证明插入和核对由逐行变为按块。

## Answer

- 实现提交：`92397c8e9`；已合并集成分支 `5c7fe8879`，合并提交 `7924916f1`。
- 连续同字段集合的 Message 使用惰性 prepared 多行插入；字段键顺序差异不会拆批，保留 Session/Chat/Turn 与更新的原始顺序、每行 locator 解析和关联/source 归属校验。SQL 分块复用现有 100 行、256 KiB 和服务器 packet 预算。
- 已提交记录按表与 service key 使用现有有界 ID 查询（最多 256 个 ID，另受查询字节和 packet 限制），固定窄字段白名单后逐行核对原不可变字段。缺失、重复输入身份与不一致明确失败；不缓存数据库核对结果。
- TDD：实现前新测试 `11 failed, 2 passed`，失败证明确为逐条 INSERT/SELECT；键序等价测试另观察 `1 failed, 13 passed` 后修复。
- 官方 mysql.connector prepared cursor 协议测试确认：513 条消息为 6 次 execute，513 条已提交核对为 3 次 SELECT；覆盖空、单条、100/101/256/257/513、字段集合切换、Unicode/二进制/空值、packet 分块、单行超限和 publication 失败回滚。
- 回归命令：`PYTHONPATH=src /Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/conversation_storage tests/unit/database/test_prepared.py tests/integrated/conversation_storage/test_legacy_roundtrip.py -q --basetemp=/private/tmp/migration-perf-02-full2`；结果 `1634 passed, 5 skipped`。所有提交 hooks 通过（含 mypy、black、flake8、pylint）。
- 限制：5 项真实 MySQL roundtrip 因未配置隔离数据库而跳过；未访问远程数据库。真实 MySQL 中的迁移入口、坏 source 隔离、已发布 source 新写保护和提交故障验收由集成验收执行，不能以本地协议计数替代；未测真实 NAS 或墙钟收益。最后一项验收保留未勾选以明确此边界。
