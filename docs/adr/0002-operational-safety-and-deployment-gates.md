# ADR-0002: 運用安全基準と段階デプロイ

- Status: Accepted
- Date: 2026-05-30
- Supersedes: None
- Related: `base_policy.md`, `PROJECT_RULES.md`

## Context
暗号資産取引は API 障害、約定不整合、急変相場が常時発生しうる。
高レバレッジや未検証本番投入は短期で破綻を招く。

## Decision
運用安全基準を以下に固定する。
1. 証拠金モードは `isolated` のみ許可し、`cross` は禁止。
2. レバレッジは低レバ（1-3x）を標準とし、設定上限を強制する。
3. DD優先制御（シンボル別/ポートフォリオ別）の上限違反時は新規建て停止。
4. 段階デプロイは `DryRun -> Testnet -> Production` を必須化し、スキップ禁止。
5. 緊急操作（停止・全キャンセル・全クローズ）は常時利用可能にする。

## Consequences
- Spec は各モードの入出力と遷移条件を明文化する必要がある。
- 本番移行条件には「安定WalkForward・安定Testnet・許容DD」を必須項目として含める。
- GUI/監視は運用安全機能として扱い、装飾機能より優先実装する。
