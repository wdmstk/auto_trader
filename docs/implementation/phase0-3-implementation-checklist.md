# Phase 0-3 実装チェックリスト

## Phase 0: 開発基盤
- [x] `pyproject.toml` を単一設定源として整備
- [x] lint/format/type/test をCIゲート化
- [x] pre-commit 導入
- [x] `config.<env>.yaml` 契約を実装
- [x] 構造化ログ必須キーを実装

Done定義:
- [x] ローカル/CIで同一品質ゲートが通る
- [x] `prod` ガードが有効

## Phase 1: データ基盤
- [x] Binance historical downloader 実装
- [x] incremental updater 実装
- [x] 欠損/重複/異常値検知実装
- [x] UTC正規化とParquet保存実装
- [x] 同期品質レポート出力実装

Done定義:
- [x] 再実行しても主キー重複が起きない
- [x] 中断後の再開が可能

## Phase 2: 特徴量エンジン
- [x] 共通特徴量（RSI/ATR/BB等）実装
- [x] RANGE/TREND専用特徴量実装
- [x] feature_version 付与実装
- [x] warmup除外ロジック実装
- [x] リーク検査実装

Done定義:
- [x] 主キー一意性とdtype契約を満たす
- [x] 未来参照ゼロを検証できる

## Phase 3: Regime Classifier
- [x] RANGE/TREND/HIGH_VOL 判定実装
- [x] 遷移制御（継続バー数、クールダウン）実装
- [x] HIGH_VOL 強制停止実装
- [x] 判定根拠 `reason_codes` 実装
- [x] overlay用出力実装

Done定義:
- [x] HIGH_VOL 時に `is_trade_allowed=false` が保証される
- [x] 判定不能時に安全側停止する
