# ADR-0003: MLは価格予測器ではなくエントリーフィルタとして使う

- Status: Accepted
- Date: 2026-05-30
- Supersedes: None
- Related: `base_policy.md`, `AGENT.md`

## Context
未来価格の回帰予測はリークや過学習の温床となりやすく、実運用での再現性が低い。
本プロジェクトは「有利場面のみ参加」を目的にしているため、MLの責務を限定すべき。

## Decision
1. MLの主目的は「低期待値セットアップを除外するフィルタ」とする。
2. ラベルは TP/SL 先着の二値分類を採用する。
   - `1 = TP first`
   - `0 = SL first`
3. 禁止事項として以下を固定する。
   - `future_return` 回帰
   - 時系列 `shuffle`
   - リークを含む特徴量設計
4. 検証は時系列順 split と WalkForward を必須とする。

## Consequences
- Specにラベル生成契約とリーク検査ポイントを明記する。
- 予測スコアは単独で発注を許可せず、regime/risk gateを通過した後にのみ有効化する。
- モデル評価は精度指標より期待値安定性とDD影響を重視する。
