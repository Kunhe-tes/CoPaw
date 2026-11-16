# 09: 减少完整 binding 与 manifest 镜像重复处理

**What to build:** 同一迁移作业在多个 source 连续执行时，减少无变化绑定及镜像的重复处理，保持 SQL 权威、证据审计和中断续跑能力。

**Blocked by:** None (can start immediately).

**Status:** claimed

- [ ] 先记录完整 binding 序列化、manifest 写入的次数、字节和耗时，依据实际调用建立优化前后对照，不先放宽持久性。
- [ ] 仅在绑定数据确定未变化的生命周期复用结果；重审修订、cutoff/target 改变或重新加载时失效，仍验证不可变作业身份。
- [ ] 消除可证明冗余的镜像处理；任何检查点调整均保留必要文件/目录 fsync、原子写入及 SQL 已确认映射持久化契约。
- [ ] 不将外部 JSON 变成发布权威，不更改文件格式、稳定 ID 或票据，不跨命令信任内存证明。
- [ ] 对已提交 SQL、镜像落后、镜像替换、source 失败、取消与写盘错误注入故障，原 manifest 能安全恢复或明确拒绝异常。
- [ ] 经现有迁移入口证明序列化/写入减少及结果不变；若测量不支持安全消除，保留原行为并记录证据，不削弱可靠性换取计数下降。

## Measurement and decision

Measured on 2026-11-16 with local temporary directories, Python 3.12, one SQL owner, complete parent binding through real TenantManifest / MigrationJournal._bindings / atomic MigrationManifest._persist entry points. This fixture isolates serialization and mirroring; it performs no business import or database/network IO and does not represent end-to-end migration wall time. Each source retains a checkpoint; no checkpoint was removed.

| Sources | Binding serializations | Binding UTF-8 bytes | Binding seconds | Completed manifest writes | Manifest bytes | Write seconds (includes fsync) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 30 | 78,810 | 0.000741 | 30 | 80,370 | 0.013081 |
| 100 | 100 | 822,700 | 0.006168 | 100 | 827,900 | 0.108090 |
| 1,000 | 1,000 | 81,127,000 | 0.529779 | 1,000 | 81,179,000 | 8.767882 |

The source binding contains mutable nested evidence. Collection identity and review revision alone cannot prove unchanged evidence; a cache would need either an enforceable immutable lifecycle or a bounded exact snapshot with shared-memory accounting. Neither exists on every current caller. At 30 sources encoding is below 1 ms; at 1,000 it is about 5.7% of these two isolated measured costs. No safe checkpoint elimination was established: SQL commit can precede mirror persistence, publication and failure recovery rely on their existing boundaries, and file/directory fsync remain necessary. The ticket's explicit conservative fallback applies: retain serialization and all mirror checkpoints, expose their actual costs, and make no performance reduction claim. No unbounded cache or duplicate binding is introduced.

Progress now reports binding serialization count/UTF-8 bytes/seconds plus manifest write attempts, completed writes/bytes and total attempted write seconds. Failed writes retain elapsed cost but do not count as completed durable checkpoints. Metrics include no binding values, SQL, bodies or paths. File format, atomic replacement, temporary-file cleanup and both fsync operations are unchanged.

The focused mutation regressions retain exact SQL binding rejection after nested target, cutoff, workspace, service or tenant evidence changes, review revision changes and data reload. Existing SQL-committed/mirror-lag and mirror-replacement recovery regressions, source failure invalidation and cancellation/global-stop tests remain in the focused suite. A replacement failure test proves old checkpoint bytes and temporary cleanup survive write failure.
