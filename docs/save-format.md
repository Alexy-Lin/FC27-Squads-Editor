# FC26 / FC27 存档写入规则

FC26 `Squads` 文件是 `FBCHUNKS` 容器包裹的 `DB\x00\x08` 数据库。核心解析器沿用 FIFA 系列的位压缩表结构，但 FC26 的容器和数据库目录不同。FC27 存档使用同样的容器与表结构，差异集中在公开 ID 映射和生日换算上。

关键约束：

- 动态查找 `DB\x00\x08`，完整保留 DB 前的 FBCHUNKS 头。
- `DataSize` 位于文件偏移 14，保存时必须等于 `文件总长度 - 1126`。
- `DB` 头为 24 字节，表目录每项 8 字节；实际样本包含 83 张表。
- FC26 表头的 `field_count_raw` 写入字段数量本身，不加 `0x100`。
- 修改记录时只覆盖字段位，保留记录 padding、空槽、压缩字符串区和表尾元数据。
- CRC 使用 CRC-32/MPEG-2：多项式 `0x04C11DB7`、初值 `0xFFFFFFFF`、无最终异或。
- `SaveType_Squads\0` 后的 8 个旧哈希字节在数据库变更后归零。

编辑器的保存服务先写入临时文件，再重新解析并校验容器、表记录数量及每个修改字段，最后生成新的 `SquadsYYYYMMDDHHMMSS` 文件。原始存档不会被覆盖。

## FC27 差异（本编辑器已按此实现）

- 球员：存档 `playerid` = 公开/EA id + 1（C 罗 20802 / 20801），高置信度覆盖写在 `data/player_id_map.csv`。
- 球队：FC27 官方档 `lyxL.teamid` = `assetid` + 2；FC26 档仍是 `assetid = teamid`。国家队识别不依赖固定 ID 表，而是用 `CxJp` 球队→国籍链接 + 队名（含 `... Women` / `... 女足` 后缀）+ 名单多数国籍判断。
- 自由球员池内部 id = `111594`（公开 111592）。
- 生日：`birthdate` 为距 `1582-10-14` 的天数；`2026-age` 年 7 月 1 日对应 `(2026-age)` 岁。低于 `125812`（1927-04-01）的生日会让游戏隐藏该球员。Web 球员编辑以 `YYYY-MM-DD` 显示和输入，保存时换算回天数。
- 年龄功能保留每名球员真实月日，只调整年份；3DM 名单里的统一值 `154774`（2006-07-17）不是真实生日。
- `contractvaliduntil` 存的是「2000 + 年份」偏移（30 = 2030），不是四位年份；从 `legend_database.db` 导入时必须换算，否则 1 字节字段会被截断。
- `nQVU` 是 editedplayernames 表（firstname/surname/commonname/playerjerseyname/playerid）；`bneD` 是 dcplayernames（nameid/name）。传奇等姓名不在原姓名表里的记录要补 `nQVU`。
- `CZUM.gender`：0 男 / 1 女；男足与女足国家队共用 nationality id，候选池必须按目标名单的多数性别过滤。
- 巅峰数据：`data/fifa19_peak.csv`（公开 id，FIFA19 口径）优先；`data/fc27_peak_fallback.csv`（3DM 存档导出，FC27 存档 id）用于 FIFA19 缺失的球员。

## 安全编辑范围

球员基础资料和能力值写入 `CZUM`；球衣号码、俱乐部/国家队关系使用现有 `RrqT` 记录原位修改。国家队选拔会复用目标国家队已有的 26 条 `RrqT` 关系记录，只替换球员 ID 和号码，不新增或删除记录。球队 `lyxL` 基础数据在 Web 编辑器中保持只读，以减少默认阵容和赛事数据被破坏的风险。

新增球员（补齐缺失/添加传奇）会向 `CZUM` 追加记录，并向 `RrqT` 追加自由球员关系；姓名缺失时同步补姓名行（`bneD`/`nQVU`，传奇的 Kempes/Rivellino 走 `nQVU`）。所有新增都先经过容量检查，写入失败不会改动原存档。
