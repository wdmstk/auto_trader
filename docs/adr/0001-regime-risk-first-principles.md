# ADR-0001: Regime/Risk/Execution 優先原則

- Status: Accepted
- Date: 2026-05-30
- Supersedes: None
- Related: `base_policy.md`, `PROJECT_RULES.md`

## Context
`base_policy.md` では、予測精度よりも「長期生存・DD制御・危険相場回避・実運用耐性」を優先している。
実装側でこの優先順位が崩れると、短期PF偏重や高ボラ追従など禁止事項に逸脱する。

## Decision
以下を全実装の不変原則として固定する。
1. `regime first`: エントリー判断の前に市場構造判定を必須化する。
2. `risk first`: 期待収益より先にDDとエクスポージャ制約を評価する。
3. `execution safety first`: 注文成功を仮定しない。冪等・再試行・重複防止を必須化する。
4. `observability first`: 主要判断（特徴量・regime・ML score・発注理由）を全て追跡可能にする。
5. `prediction last`: 予測モデルは補助であり、システムの主役は構造認識とリスク管理。

## Consequences
- Specは「regime未確定なら戦略実行不可」を前提に記述する。
- HIGH_VOLは戦略選択ではなく停止判定として扱う。
- 設計レビューで PF より DD と障害復旧性を優先評価する。
