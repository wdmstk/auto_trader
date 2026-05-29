# Specレビュー結果（Phase 0-3）

- Date: 2026-05-30
- Scope: Phase 0-3 Specs
- Reviewer: Codex

## 結論
Phase 0実装着手前レビューとして、実装ブレの原因になりやすい契約を固定した。
現時点で、Phase 0の実装に追加判断は不要。

## 固定した事項
1. 設定インターフェース（Phase 0）
- `config.<env>.yaml` の最小キー契約を明文化。
- `exchange.margin_type=isolated` 固定を仕様に反映。
- `risk.*` と `exchange.max_leverage` の検証前提を明示。

2. Regime出力・説明可能性（Phase 3）
- `reason_codes` の許可列挙を固定。
- 判定不能時の `FALLBACK_*` コードを定義。

3. 初期閾値/遷移（Phase 3）
- HIGH_VOL/TREND/RANGE の v1 初期閾値を固定。
- チャタリング抑制とクールダウンの初期値を固定。

## 残留リスク（実装で吸収）
- 閾値は銘柄と時間足で再調整が必要（WalkForward前提）。
- spread widening はデータソース依存のため、v1では取得可能な代理指標で実装する。

## 次アクション
1. Phase 0 実装開始（pyproject, 品質ゲート, configローダ, 構造化ログ）。
2. 実装時にキー不整合が出たら、Specを先に更新してからコード変更する。
