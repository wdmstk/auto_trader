# Phase 0-3 実装チェックリスト

## Phase 0: 開発基盤
- [ ] `pyproject.toml` を単一設定源として整備
- [ ] lint/format/type/test をCIゲート化
- [ ] pre-commit 導入
- [ ] `config.<env>.yaml` 契約を実装
- [ ] 構造化ログ必須キーを実装

Done定義:
- [ ] ローカル/CIで同一品質ゲートが通る
- [ ] `prod` ガードが有効

## Phase 1: データ基盤
- [ ] Binance historical downloader 実装
- [ ] incremental updater 実装
- [ ] 欠損/重複/異常値検知実装
- [ ] UTC正規化とParquet保存実装
- [ ] 同期品質レポート出力実装

Done定義:
- [ ] 再実行しても主キー重複が起きない
- [ ] 中断後の再開が可能

## Phase 2: 特徴量エンジン
- [ ] 共通特徴量（RSI/ATR/BB等）実装
- [ ] RANGE/TREND専用特徴量実装
- [ ] feature_version 付与実装
- [ ] warmup除外ロジック実装
- [ ] リーク検査実装

Done定義:
- [ ] 主キー一意性とdtype契約を満たす
- [ ] 未来参照ゼロを検証できる

## Phase 3: Regime Classifier
- [ ] RANGE/TREND/HIGH_VOL 判定実装
- [ ] 遷移制御（継続バー数、クールダウン）実装
- [ ] HIGH_VOL 強制停止実装
- [ ] 判定根拠 `reason_codes` 実装
- [ ] overlay用出力実装

Done定義:
- [ ] HIGH_VOL 時に `is_trade_allowed=false` が保証される
- [ ] 判定不能時に安全側停止する
